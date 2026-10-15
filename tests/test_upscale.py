import importlib.util
import os
import stat
import sys
import tempfile
import unittest
from pathlib import Path

from helpers import CFG  # noqa: F401  (adds src to sys.path)
from adobe_stock_analytics import upscale as U

HAS_PIL = importlib.util.find_spec("PIL") is not None
# stands in for realesrgan-ncnn-vulkan: writes the input at 4x with Pillow
FAKE = """#!{py}
import sys
from PIL import Image
a = sys.argv
i, o = a[a.index("-i") + 1], a[a.index("-o") + 1]
im = Image.open(i)
im.resize((im.width * 4, im.height * 4)).save(o)
"""


class UpscaleTests(unittest.TestCase):
    def setUp(self):
        self.d = Path(tempfile.mkdtemp())
        self.src = self.d / "raw"
        self.src.mkdir()
        self.out = self.d / "final"

    def fake_bin(self):
        p = self.d / "bin" / "realesrgan-ncnn-vulkan"
        p.parent.mkdir()
        p.write_text(FAKE.format(py=sys.executable))
        p.chmod(p.stat().st_mode | stat.S_IEXEC)
        return str(p)

    def test_no_binary_gives_options_not_a_resize(self):
        (self.src / "a.png").write_bytes(b"x")
        with unittest.mock.patch.dict(os.environ, {"PATH": str(self.d)}):
            r = U.run(self.src, self.out)
        self.assertFalse(r["ok"])
        self.assertEqual(len(r["options"]), 3)
        self.assertFalse(self.out.exists())

    def test_dry_run_lists_and_skips_existing(self):
        b = self.fake_bin()
        for n in ("a.png", "b.jpg", "notes.txt"):
            (self.src / n).write_bytes(b"x")
        self.out.mkdir()
        (self.out / "b.jpg").write_bytes(b"old")
        r = U.run(self.src, self.out, binary=b)
        self.assertEqual((r["written"], r["to_upscale"], r["already_done"]), (False, ["a.png"], ["b.jpg"]))
        self.assertEqual((self.out / "b.jpg").read_bytes(), b"old")

    @unittest.skipUnless(HAS_PIL, "Pillow not installed")
    def test_upscales_to_long_edge_and_refuses_to_stretch(self):
        from PIL import Image
        Image.new("RGB", (1200, 900), (90, 120, 150)).save(self.src / "big.png")
        Image.new("RGB", (400, 300), (90, 120, 150)).save(self.src / "small.png")
        r = U.run(self.src, self.out, binary=self.fake_bin(), confirm_write=True)
        self.assertEqual([d["size"] for d in r["done"]], [[3840, 2880]])
        self.assertEqual([f["file"] for f in r["failed"]], ["small.png"])
        self.assertFalse((self.out / "small.jpg").exists())
        with Image.open(self.out / "big.jpg") as im:
            self.assertEqual((im.format, im.size), ("JPEG", (3840, 2880)))
        self.assertTrue((self.out / "upscale_manifest.json").is_file())
        full = U.run(self.src, self.d / "full", binary=self.d / "bin" / "realesrgan-ncnn-vulkan", long_edge=0, confirm_write=True)
        self.assertEqual(sorted(d["size"] for d in full["done"]), [[1600, 1200], [4800, 3600]])


import unittest.mock  # noqa: E402

if __name__ == "__main__":
    unittest.main()
