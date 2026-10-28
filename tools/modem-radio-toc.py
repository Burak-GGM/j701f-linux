#!/usr/bin/env python3
"""Read and validate a Samsung Shannon RADIO TOC without extracting firmware.

This host-side tool only reads the 512-byte header. It never opens EFS, copies
firmware payloads, or talks to the modem. The format is the six-field, 32-byte
TOC described by Comsecuris' public sam.bt template. The fifth field is kept
as unknown because its meaning is not established for this device.
"""

import argparse
import json
from pathlib import Path
import stat
import struct
import sys


HEADER_SIZE = 512
ENTRY = struct.Struct("<12sIIIII")
MAX_ENTRIES = HEADER_SIZE // ENTRY.size


class TOCError(ValueError):
    pass


def parse_header(header: bytes, image_size: int) -> list[dict]:
    if len(header) != HEADER_SIZE:
        raise TOCError(f"need exactly {HEADER_SIZE} header bytes")
    if image_size < HEADER_SIZE:
        raise TOCError("image size is smaller than the TOC")

    entries = []
    seen = set()
    for index in range(MAX_ENTRIES):
        raw = ENTRY.unpack_from(header, index * ENTRY.size)
        raw_name = raw[0]
        if raw_name == b"\0" * 12:
            break
        name_bytes = raw_name.split(b"\0", 1)[0]
        if not name_bytes or any(c not in b"ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_" for c in name_bytes):
            raise TOCError(f"entry {index}: invalid name")
        if any(raw_name[len(name_bytes) + 1:]) and len(name_bytes) < 12:
            raise TOCError(f"entry {index}: nonzero bytes after name terminator")
        name = name_bytes.decode("ascii")
        if name in seen:
            raise TOCError(f"duplicate entry {name}")
        seen.add(name)
        entries.append({
            "name": name,
            "file_offset": raw[1],
            "load_address": raw[2],
            "size": raw[3],
            "unknown": raw[4],
            "id": raw[5],
        })

    if not entries or entries[0]["name"] != "TOC":
        raise TOCError("first entry is not TOC")
    if entries[0]["file_offset"] != 0 or entries[0]["size"] != HEADER_SIZE:
        raise TOCError("TOC entry does not describe the 512-byte header")
    for required in ("BOOT", "MAIN", "NV"):
        if required not in seen:
            raise TOCError(f"missing {required} entry")
    nv = next(item for item in entries if item["name"] == "NV")
    if nv["file_offset"] != 0:
        raise TOCError("NV unexpectedly points into the RADIO image")

    ranges = []
    for item in entries:
        if item["name"] in {"TOC", "NV"}:
            continue
        start, size = item["file_offset"], item["size"]
        if item["name"] == "OFFSET":
            # This section can describe offsets inside MAIN and overlap it.
            if size and (start < HEADER_SIZE or start > image_size or size > image_size - start):
                raise TOCError("OFFSET: payload outside image")
            continue
        if size == 0 or start < HEADER_SIZE or start > image_size or size > image_size - start:
            raise TOCError(f"{item['name']}: payload outside image")
        ranges.append((start, start + size, item["name"]))
    ranges.sort()
    for previous, current in zip(ranges, ranges[1:]):
        if previous[1] > current[0]:
            raise TOCError(f"overlapping payloads: {previous[2]} and {current[2]}")
    return entries


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", type=Path, help="regular RADIO image or a 512-byte header copy")
    parser.add_argument("--image-size", type=int, help="full partition size in bytes when input is header-only")
    parser.add_argument("--json", action="store_true", help="print metadata as JSON")
    args = parser.parse_args()
    try:
        info = args.image.stat()
        if not stat.S_ISREG(info.st_mode):
            raise TOCError("input must be a regular host file")
        if args.image_size is None and info.st_size == HEADER_SIZE:
            raise TOCError("header-only input needs --image-size for payload bounds")
        image_size = args.image_size if args.image_size is not None else info.st_size
        if info.st_size != HEADER_SIZE and image_size != info.st_size:
            raise TOCError("--image-size may differ from file length only for a 512-byte header copy")
        with args.image.open("rb") as stream:
            entries = parse_header(stream.read(HEADER_SIZE), image_size)
    except (OSError, TOCError) as error:
        print(f"RADIO TOC: {error}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps({"image_size": image_size, "entries": entries}, indent=2))
    else:
        print(f"RADIO TOC valid against {image_size} bytes")
        for item in entries:
            print(f"{item['name']:<10} file=0x{item['file_offset']:08x} "
                  f"load=0x{item['load_address']:08x} size=0x{item['size']:08x} "
                  f"id={item['id']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
