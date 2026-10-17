import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from adobe_stock_analytics import parsers, store as S, urls  # noqa: E402
from adobe_stock_analytics import config as _config  # noqa: E402
from adobe_stock_analytics.config import load_config  # noqa: E402

# Tests check the shipped defaults; the user's own config/local.json must not leak in.
_config.LOCAL_CONFIG = ROOT / "tests" / "no-local-config.json"

FIX = ROOT / "tests" / "fixtures" / "intel"
CFG = load_config()


def fixture(name):
    return json.loads((FIX / name).read_text(encoding="utf-8"))


def new_store(clock="2026-10-10T00:00:00Z"):
    d = tempfile.mkdtemp()
    return S.Store(d, now=lambda: clock)


def ingest_search(store, fixture_name, keyword, ai_filter, order, media="photo"):
    p = fixture(fixture_name)
    exp = urls.expected_filters(keyword, media, ai_filter, order)
    parsed = parsers.parse_search(p, exp)
    params = {"keyword": keyword, "media_type": media, "ai_filter": ai_filter, "order": order}
    return store.add_observation("search", urls.build_search(keyword, media, ai_filter, order), params, p, parsed), parsed


def seeded_store():
    st = new_store()
    ingest_search(st, "search_matcha_p0_1.json", "matcha latte", "all", "relevance")
    ingest_search(st, "search_matcha_p0_2.json", "matcha latte", "all", "downloads")
    ingest_search(st, "search_matcha_p0_3.json", "matcha latte", "only_ai", "relevance")
    return st
