import re
import unittest
from pathlib import Path

from helpers import CFG  # noqa: F401  (adds src to sys.path)
import adobe_stock_analytics


class VersionTests(unittest.TestCase):
    def test_package_version_matches_pyproject(self):
        py = (Path(__file__).resolve().parents[1] / "pyproject.toml").read_text()
        self.assertEqual(re.search(r'^version = "([^"]+)"', py, re.M).group(1), adobe_stock_analytics.__version__)


if __name__ == "__main__":
    unittest.main()
