import importlib.util
import tempfile
import unittest
from pathlib import Path

from helpers import CFG  # noqa: F401  (adds src to sys.path)
from adobe_stock_analytics import similar as SM

HAS_PIL = importlib.util.find_spec("PIL") is not None


@unittest.skipUnless(HAS_PIL, "Pillow not installed")
class SimilarTests(unittest.TestCase):
    def setUp(self):
        from PIL import Image
        self.d = Path(tempfile.mkdtemp())
        new, old = self.d / "new", self.d / "old"
        new.mkdir()
        old.mkdir()

        def img(path, split, shade=0):
            im = Image.new("RGB", (64, 48), (20 + shade, 20, 20))
            im.paste((230, 230, 230), (0, 0, split, 48))
            im.save(path)
        img(new / "a.jpg", 32)
        img(new / "b.jpg", 32, shade=10)   # same layout, slightly different colour: a look-alike
        img(new / "c.png", 8)
        img(old / "x.jpg", 8)              # earlier upload that c repeats
        img(old / "y.jpg", 8)              # earlier-vs-earlier pairs are not reported
        self.new, self.old = new, old

    def test_pairs_within_new_and_against_earlier(self):
        r = SM.screen(self.new, [self.old], threshold=4)
        kinds = sorted((Path(p["a"]).name, Path(p["b"]).name, p["kind"]) for p in r["pairs"])
        self.assertIn(("a.jpg", "b.jpg", "within_new"), kinds)
        self.assertTrue(any(k[2] == "new_vs_earlier" and "c.png" in k[:2] for k in kinds))
        self.assertFalse(any({"x.jpg", "y.jpg"} == set(k[:2]) for k in kinds))
        self.assertEqual((r["new_files"], r["earlier_files"]), (3, 2))
        self.assertEqual(r["groups_over_max"], [])

    def test_group_over_max_and_bad_folder(self):
        r = SM.screen(self.new, [self.old], threshold=4, max_group=2)
        self.assertEqual(len(r["groups_over_max"]), 1)
        with self.assertRaises(ValueError):
            SM.screen(self.d / "missing")


if __name__ == "__main__":
    unittest.main()
