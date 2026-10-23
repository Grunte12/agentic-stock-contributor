import re
import unittest
from pathlib import Path

from helpers import CFG  # noqa: F401  (adds src to sys.path)
import adobe_stock_analytics


class VersionTests(unittest.TestCase):
    def test_package_version_matches_pyproject(self):
        py = (Path(__file__).resolve().parents[1] / "pyproject.toml").read_text()
        self.assertEqual(re.search(r'^version = "([^"]+)"', py, re.M).group(1), adobe_stock_analytics.__version__)

    def test_release_docs_match_package_version(self):
        root = Path(__file__).resolve().parents[1]
        version = adobe_stock_analytics.__version__
        install = (root / "INSTALL.md").read_text(encoding="utf-8")
        changelog = (root / "CHANGELOG.md").read_text(encoding="utf-8")
        setup = (root / "docs" / "SETUP.md").read_text(encoding="utf-8")
        self.assertIn(f"--branch v{version}", install)
        self.assertIn(f"## Toolkit {version}", changelog)
        self.assertIn("stock.py init", install)
        self.assertIn("stock.py lint-workspace", install)
        self.assertIn("stock.py init", setup)


if __name__ == "__main__":
    unittest.main()
