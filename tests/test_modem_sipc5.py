"""Protocol-boundary tests based on the vendor SIPC5 header layout."""

import importlib.util
from pathlib import Path
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "tools/modem/sipc5.py"
spec = importlib.util.spec_from_file_location("j701f_sipc5", SCRIPT)
sipc5 = importlib.util.module_from_spec(spec)
import sys
sys.modules[spec.name] = sipc5
spec.loader.exec_module(sipc5)


class SIPC5Tests(unittest.TestCase):
    def test_fmt_and_padded_rfs(self):
        fmt = sipc5.Frame(235, b"abc")
        wire = sipc5.encode_frame(fmt)
        self.assertEqual(wire[:4], bytes.fromhex("f8 eb 07 00"))
        self.assertEqual(sipc5.decode_one(wire), (fmt, 7))
        self.assertEqual(fmt.kind, "fmt")

        rfs = sipc5.Frame(245, b"abc", padded=True)
        wire = sipc5.encode_frame(rfs)
        self.assertEqual(len(wire), 8)
        self.assertEqual(wire[0], 0xFC)
        self.assertEqual(sipc5.decode_one(wire), (rfs, 8))
        self.assertEqual(rfs.kind, "rfs")

    def test_multiframe_and_extended_length(self):
        boot = sipc5.Frame(215, b"part", control=0x80)
        self.assertEqual(sipc5.decode_one(sipc5.encode_frame(boot))[0], boot)
        self.assertEqual(boot.kind, "boot")
        large = sipc5.Frame(235, b"x" * 70000)
        wire = sipc5.encode_frame(large)
        self.assertEqual(wire[0], 0xFA)
        self.assertEqual(sipc5.decode_one(wire), (large, len(wire)))

    def test_partial_stream_and_invalid_lengths(self):
        one = sipc5.encode_frame(sipc5.Frame(235, b"hello"))
        two = sipc5.encode_frame(sipc5.Frame(245, b"world", padded=True))
        decoder = sipc5.FrameDecoder()
        self.assertEqual(decoder.feed(one[:3]), [])
        self.assertEqual([f.kind for f in decoder.feed(one[3:] + two[:5])], ["fmt"])
        self.assertEqual([f.kind for f in decoder.feed(two[5:])], ["rfs"])
        with self.assertRaisesRegex(sipc5.FrameError, "length"):
            sipc5.decode_one(bytes.fromhex("f8 eb 03 00"))
        with self.assertRaisesRegex(sipc5.FrameError, "start bits"):
            sipc5.decode_one(bytes.fromhex("00 eb 04 00"))


if __name__ == "__main__":
    unittest.main()
