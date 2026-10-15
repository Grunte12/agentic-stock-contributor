"""Structured params -> allowlisted Adobe Stock URL. No MCP tool accepts a raw URL."""
import re
from urllib.parse import parse_qs, quote_plus, urlparse

MEDIA = {"photo": "photo", "illustration": "illustration", "vector": "zip_vector", "video": "video"}
AI = {"all": None, "only_ai": "only", "no_ai": "exclude"}
ORDER = {"relevance": None, "downloads": "nb_downloads", "creation": "creation", "undiscovered": "undiscovered"}
HOST = "stock.adobe.com"


class UrlError(ValueError):
    pass


def _keyword(k):
    if not isinstance(k, str) or not k.strip():
        raise UrlError("keyword must be a non-empty string")
    if len(k) > 100 or re.search(r"[\x00-\x1f]", k):
        raise UrlError("keyword too long or has control characters")
    return " ".join(k.split())


def build_search(keyword, media_type="photo", ai_filter="all", order="relevance"):
    if media_type not in MEDIA:
        raise UrlError(f"media_type must be one of {sorted(MEDIA)}")
    if ai_filter not in AI:
        raise UrlError(f"ai_filter must be one of {sorted(AI)}")
    if order not in ORDER:
        raise UrlError(f"order must be one of {sorted(ORDER)}")
    parts = [("k", _keyword(keyword)), (f"filters[content_type:{MEDIA[media_type]}]", "1")]
    if AI[ai_filter]:
        parts.append(("filters[gentech]", AI[ai_filter]))
    if ORDER[order]:
        parts.append(("order", ORDER[order]))
    q = "&".join(f"{quote_plus(a, safe=':')}={quote_plus(b)}" for a, b in parts)
    return f"https://{HOST}/search?{q}"


def build_asset(asset_id):
    if not isinstance(asset_id, int) or isinstance(asset_id, bool) or asset_id <= 0:
        raise UrlError("asset_id must be a positive integer")
    return f"https://{HOST}/images/x/{asset_id}"


def build_contributor(creator_id):
    if not isinstance(creator_id, int) or isinstance(creator_id, bool) or creator_id <= 0:
        raise UrlError("creator_id must be a positive integer")
    return f"https://{HOST}/contributor/{creator_id}/x?load_type=author"


CONTRIB_HOST = "contributor.stock.adobe.com"


def build_portfolio():
    return f"https://{CONTRIB_HOST}/en/portfolio"


# Own-dashboard pages the read-only probe may open. Nothing else on the contributor portal.
CONTRIB_PAGES = {"portfolio": "/en/portfolio", "uploads": "/en/uploads", "rejected": "/en/uploads/rejected"}


def build_probe(page):
    if page not in CONTRIB_PAGES:
        raise UrlError(f"unknown dashboard page {page!r}")
    return f"https://{CONTRIB_HOST}{CONTRIB_PAGES[page]}"


def build_outcomes():
    return f"https://{CONTRIB_HOST}{CONTRIB_PAGES['rejected']}"


_ALLOWED = (
    re.compile(r"^/(?:[a-z]{2}(?:_[A-Z]{2})?/)?search$"),
    re.compile(r"^/(?:[a-z]{2}(?:_[A-Z]{2})?/)?images/[^/]+/\d+$"),
    re.compile(r"^/(?:[a-z]{2}(?:_[A-Z]{2})?/)?contributor/\d+/[^/]+$"),
)


def is_allowed(url):
    u = urlparse(url)
    if u.scheme == "https" and u.hostname == CONTRIB_HOST:
        return u.path in CONTRIB_PAGES.values() and not u.query  # read-only own-dashboard pages, nothing else on the portal
    return u.scheme == "https" and u.hostname == HOST and any(p.match(u.path) for p in _ALLOWED)


def read_back(page_url):
    """Filters actually present on the loaded page, for comparison with the request."""
    q = parse_qs(urlparse(page_url).query)
    return {
        "keyword": (q.get("k") or [None])[0],
        "media": sorted(k[len("filters[content_type:"):-1] for k in q if k.startswith("filters[content_type:")),
        "gentech": (q.get("filters[gentech]") or [None])[0],
        "order": (q.get("order") or [None])[0],
    }


def expected_filters(keyword, media_type, ai_filter, order):
    return {
        "keyword": " ".join(keyword.split()),
        "media": [MEDIA[media_type]],
        "gentech": AI[ai_filter],
        "order": ORDER[order],
    }
