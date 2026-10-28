"""RFS parser and RAM-only NV behavior against synthetic data."""

import importlib.util
from pathlib import Path
import struct
import sys
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "tools/modem/rfs.py"
spec = importlib.util.spec_from_file_location("j701f_rfs", SCRIPT)
rfs = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = rfs
spec.loader.exec_module(rfs)


def request(index, sequence, offset, size, data=b""):
    body = struct.pack("<II", offset, size) + data
    return struct.pack("<IBB", 6 + len(body), index, sequence) + body


class RFSTests(unittest.TestCase):
    def test_read_and_write_stay_in_ram(self):
        source = bytes(rfs.NV_SIZE)
        memory = rfs.NVMemory(source)
        write = rfs.parse_request(request(2, 7, 4094, 4, b"abcd"))
        self.assertEqual(write.sequence, 7)
        self.assertIsNone(memory.apply(write))
        self.assertEqual(memory.apply(rfs.parse_request(request(1, 8, 4094, 4))), b"abcd")
        self.assertEqual(source[4094:4098], b"\0" * 4)

    def test_rejects_truncation_and_out_of_range(self):
        for data in (
            b"\0" * 3,
            request(1, 1, rfs.NV_SIZE - 1, 2),
            request(2, 1, 0, 4, b"abc"),
            request(1, 1, 0, 1, b"x"),
            request(3, 1, 0, 1),
        ):
            with self.subTest(data=data[:8]), self.assertRaises(rfs.RFSError):
                rfs.parse_request(data)

    def test_requires_exact_private_snapshot(self):
        with self.assertRaisesRegex(rfs.RFSError, "exactly 1 MiB"):
            rfs.NVMemory(b"short")

    def test_direct_requests_are_checked_too(self):
        memory = rfs.NVMemory(bytes(rfs.NV_SIZE))
        for bad in (
            rfs.NVRequest(1, -1, 0, 1),
            rfs.NVRequest(1, 0, 0, 1, b"x"),
            rfs.NVRequest(2, 0, 0, 2, b"x"),
            rfs.NVRequest(1, 0, -1, 1),
        ):
            with self.subTest(index=bad.index, offset=bad.offset):
                with self.assertRaises(rfs.RFSError):
                    memory.apply(bad)


if __name__ == "__main__":
    unittest.main()
