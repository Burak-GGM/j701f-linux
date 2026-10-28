"""Bounds checks for the host-only Shannon RADIO table reader."""

import importlib.util
from pathlib import Path
import struct
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "tools/modem-radio-toc.py"
spec = importlib.util.spec_from_file_location("modem_radio_toc", SCRIPT)
toc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(toc)


def entry(name, start, load, size, ident):
    return struct.pack("<12sIIIII", name.encode(), start, load, size, 0, ident)


def fixture():
    rows = [
        entry("TOC", 0, 0, 512, 1),
        entry("BOOT", 512, 0x40000000, 5900, 0),
        entry("MAIN", 6432, 0x40010000, 0x0250677C, 2),
        entry("NV", 0, 0x44900000, 1048576, 3),
        entry("OFFSET", 0x7AA00, 0, 0x85600, 4),
    ]
    return b"".join(rows).ljust(512, b"\0")


class TOCTests(unittest.TestCase):
    def test_measured_style_header(self):
        rows = toc.parse_header(fixture(), 38830512)
        self.assertEqual([row["name"] for row in rows], ["TOC", "BOOT", "MAIN", "NV", "OFFSET"])
        self.assertEqual(rows[2]["load_address"], 0x40010000)

    def test_rejects_payload_past_partition(self):
        with self.assertRaisesRegex(toc.TOCError, "outside image"):
            toc.parse_header(fixture(), 1024 * 1024)

    def test_rejects_overlap(self):
        data = bytearray(fixture())
        data[2 * toc.ENTRY.size + 12:2 * toc.ENTRY.size + 16] = struct.pack("<I", 600)
        with self.assertRaisesRegex(toc.TOCError, "overlapping"):
            toc.parse_header(bytes(data), 38830512)

    def test_rejects_bad_magic_and_missing_nv(self):
        data = bytearray(fixture())
        data[:3] = b"BAD"
        with self.assertRaisesRegex(toc.TOCError, "first entry"):
            toc.parse_header(bytes(data), 38830512)
        data = bytearray(fixture())
        data[3 * toc.ENTRY.size:4 * toc.ENTRY.size] = b"\0" * toc.ENTRY.size
        with self.assertRaisesRegex(toc.TOCError, "missing NV"):
            toc.parse_header(bytes(data), 38830512)

    def test_rejects_nv_in_radio_and_offset_out_of_bounds(self):
        data = bytearray(fixture())
        data[3 * toc.ENTRY.size + 12:3 * toc.ENTRY.size + 16] = struct.pack("<I", 512)
        with self.assertRaisesRegex(toc.TOCError, "NV unexpectedly"):
            toc.parse_header(bytes(data), 38830512)
        data = bytearray(fixture())
        data[4 * toc.ENTRY.size + 12:4 * toc.ENTRY.size + 16] = struct.pack("<I", 38830512)
        with self.assertRaisesRegex(toc.TOCError, "OFFSET: payload outside"):
            toc.parse_header(bytes(data), 38830512)


if __name__ == "__main__":
    unittest.main()
