# Observed recovery image format

All values below came from the supplied `tools/orangefox/recovery.img`, whose SHA-256 is:

```text
5bbcb385a5b007a037713b169e69255534fbfb3527fa9ced63c61fe08b1eb68e
```

The parser intentionally pins this baseline. Supporting a different image requires inspecting it and reviewing the parser, not changing a hash to bypass a check.

## Header and layout

The image starts at byte zero with `ANDROID!`. It uses a legacy Android boot header with **`dt_size` at byte 40**. That field contains 358400, not a modern Android header version. The complete first 2048 bytes are retained, including name, command-line buffers, reserved fields, ID padding and header-page padding.

| Field | Observed value |
| --- | --- |
| File length | 32,194,576 bytes |
| Page size | 2048 bytes |
| Kernel size / file offset | 18,270,584 / 2048 bytes |
| Kernel load address | `0x10008000` |
| Ramdisk size / file offset | 13,559,951 / 18,274,304 bytes |
| Ramdisk load address | `0x11000000` |
| Second-stage size | 0 bytes |
| Second-stage address | `0x10f00000` |
| Tags address | `0x10000100` |
| DT table size / file offset | 358,400 / 31,836,160 bytes |
| Raw word at byte 44 | `0x2004063c`, preserved without reinterpretation |
| Board name | Empty |
| Header command line | `buildvariant=eng` |
| Extra command line | Empty |
| Trailing bytes | ASCII `SEANDROIDENFORCE`, 16 bytes |

Kernel, ramdisk, second payload (empty here), and DT table each start on a page boundary. Payload padding is zero. There is no inferred partition number or inferred load base. Absolute addresses are already present in the header; a command-line `mkbootimg --base` is unnecessary and not uniquely encoded.

The kernel has ARM64 Image magic and identifies itself as `3.18.140-SIMPLE-KERNEL_V1.0`, built July 30, 2021. `extracted/dtb` starts with Samsung `DTBH` and retains the whole multi-tree payload. It is not a single raw FDT, so passing the whole table directly to `dtc` as one DTB would be wrong. No DTB is split, edited, or selected in this stage.

The original ramdisk is **LZMA-alone**, not gzip. Its 13-byte header has property byte `0x5d`, an 8 MiB dictionary, and unknown uncompressed length. The builder derives lc/lp/pb and dictionary size from this header and verifies that the new compression header matches. It also emits `ramdisk.cpio.gz`; embedded config confirms both `CONFIG_RD_LZMA=y` and `CONFIG_RD_GZIP=y`.

The boot ID is SHA-1 over kernel bytes + little-endian kernel size, ramdisk bytes + size, second bytes + size (including zero), and DT table bytes + size, in that order. This formula reproduces the original ID exactly. It follows the legacy-DT branch in the [mkbootimg source](https://github.com/osm0sis/mkbootimg/blob/master/mkbootimg.c). This is a content checksum, not a cryptographic bootloader signature. The Samsung trailer is preserved; it is not treated as a signing or secure-boot bypass mechanism.

## Changes made during repacking

Only the ramdisk bytes, header ramdisk-size word at bytes 16–19, and 20-byte SHA-1 at bytes 576–595 change. All other header bytes are compared directly. The full kernel and DT table are compared byte-for-byte with the original.

**Load addresses remain identical. File offsets after the ramdisk necessarily move** when its compressed length changes. The DT table's new position follows the same page-alignment rule; retaining its old file offset while declaring a smaller ramdisk would produce an inconsistent legacy image. Both layouts are recorded in `build/build-report.json`. Kernel and ramdisk starting file offsets remain unchanged.

Before a modified image is built, the tool reconstructs the original using the original compressed ramdisk. It must match all 32,194,576 bytes. Unknown trailers, nonzero component padding, modern header layouts, bad checksums, and truncated payloads cause an error. The builder refuses growth beyond the original image length.

The resulting Odin container uses uncompressed USTAR, uid/gid 0, fixed metadata, and exactly one regular `recovery.img` member. Flash validation also compares the complete archive to its canonical encoding, rejecting additional files, symlinks, alternate paths, hidden trailing payloads or extra metadata. `recovery.tar` needs no tar.md5 extension for the supplied Odin4's AP input.
