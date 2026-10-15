"""Run the toolkit without installing it or setting PYTHONPATH: `python3 stock.py doctor` (Windows: `py -3 stock.py doctor`)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))
from adobe_stock_analytics.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
