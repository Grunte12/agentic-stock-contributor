"""Versioned parsers. A page that does not match a known shape becomes 'unknown', never a guess."""
import re

from . import urls

PARSER_VERSION = "p1"
_COUNT = re.compile(
    r"(\d[\d,.\s  ]*)\s*(?:ผลลัพธ์|results?|résultats?|Ergebnisse|resultados?|risultati|結果|검색결과)",
    re.I,
)
# Adobe's "no exact match, related results below" heading: the exact phrase has 0 results; the rows are related assets.
_NO_MATCH = re.compile(r"ไม่พบผลลัพธ์ที่ตรงกัน|เราไม่พบผลลัพธ์(?:\s+\S+)?\s+สำหรับ|we couldn't find (?:any )?(?:matches|results)|no (?:exact )?(?:matches|results) for", re.I)
BLOCKED_STATES = {"captcha", "restricted", "signin"}
BLOCKED_HTTP = {403, 429}


def _blocked(payload):
    if isinstance(payload, dict):
        if payload.get("page_state") in BLOCKED_STATES:
            return payload["page_state"]
        if payload.get("http_status") in BLOCKED_HTTP:
            return f"http_{payload['http_status']}"
    return None


def parse_count(text):
    """'91,325 ผลลัพธ์สำหรับ ...' -> 91325. Returns None when no count is present."""
    if not isinstance(text, str):
        return None
    m = _COUNT.search(text)
    if not m:
        return None
    digits = re.sub(r"[^\d]", "", m.group(1))
    return int(digits) if digits else None


def _result(status, reason=None, **kw):
    return {"status": status, "reason": reason, "parser_version": PARSER_VERSION, **kw}


def _norm_rows(rows):
    out = []
    for r in rows or []:
        if not isinstance(r, dict) or not isinstance(r.get("asset_id"), int):
            return None
        out.append({
            "rank": r.get("rank"),
            "asset_id": r["asset_id"],
            "title": r.get("title"),
            "creator_id": r.get("creator_id") if isinstance(r.get("creator_id"), int) else None,
            "is_gentech": bool(r["is_gentech"]) if isinstance(r.get("is_gentech"), bool) else None,
            "category": r.get("category"),
            "w": r.get("w"),
            "h": r.get("h"),
        })
    return out


def parse_search(payload, expected=None):
    """payload: dict from extension/extract.js. expected: urls.expected_filters(...) or None."""
    if not isinstance(payload, dict):
        return _result("unknown", "payload_not_object")
    if _blocked(payload):
        return _result("blocked", _blocked(payload))
    rows = _norm_rows(payload.get("rows"))
    if rows is None:
        return _result("unknown", "row_shape")
    results = parse_count(payload.get("results_text"))
    if results is None and _NO_MATCH.search(payload.get("results_text") or ""):
        results = 0
    if results is None:
        return _result("unknown", "no_count_text", rows=rows)
    on_page = urls.read_back(payload.get("page_url") or "")
    if expected is not None:
        want = {k: expected[k] for k in ("keyword", "media", "gentech", "order")}
        if (on_page["keyword"] or "").lower() != want["keyword"].lower() or on_page["media"] != want["media"] \
                or on_page["gentech"] != want["gentech"] or on_page["order"] != want["order"]:
            return _result("unknown", "filters_not_applied", filters_on_page=on_page, rows=rows)
    return _result("ok", results=results, results_text=payload.get("results_text"),
                   filters_on_page=on_page, rows=rows)


def parse_contributor(payload):
    if not isinstance(payload, dict):
        return _result("unknown", "payload_not_object")
    if _blocked(payload):
        return _result("blocked", _blocked(payload))
    rows = _norm_rows(payload.get("rows"))
    if not rows:
        return _result("unknown", "no_rows")
    return _result("ok", rows=rows)


def parse_asset(payload):
    if not isinstance(payload, dict):
        return _result("unknown", "payload_not_object")
    if _blocked(payload):
        return _result("blocked", _blocked(payload))
    aid, title = payload.get("asset_id"), payload.get("title")
    if not isinstance(aid, int) or not title:
        return _result("unknown", "no_asset_id_or_title")
    kws = [k for k in (payload.get("keywords") or []) if isinstance(k, str)]
    total = None
    m = re.search(r"\((\d+)\)\s*$", payload.get("keywords_total_text") or "")
    if m:
        total = int(m.group(1))
    return _result("ok", asset_id=aid, title=title, keywords=kws, keywords_shown=len(kws), keywords_total=total)


def parse_portfolio(payload):
    """Own dashboard page. '-' on a card is kept as None (shown as a dash), never silently 0."""
    if not isinstance(payload, dict):
        return _result("unknown", "payload_not_object")
    if _blocked(payload):
        return _result("blocked", _blocked(payload))
    cards = payload.get("cards")
    dl = _int(payload.get("overview_downloads_text"))
    if not isinstance(cards, list) or not cards or dl is None:
        return _result("unknown", "no_portfolio_shape")
    rows = []
    for c in cards:
        t = (c.get("downloads_text") or "").strip()
        if not isinstance(c.get("asset_id"), int) or not (t == "-" or t.replace(",", "").isdigit()):
            return _result("unknown", "no_portfolio_shape")
        rows.append({"asset_id": c["asset_id"], "downloads": None if t == "-" else int(t.replace(",", ""))})
    named = []
    for n in payload.get("named") if isinstance(payload.get("named"), list) else []:
        if isinstance(n, dict) and isinstance(n.get("asset_id"), int) and isinstance(n.get("original_name"), str):
            named.append({"asset_id": n["asset_id"], "original_name": n["original_name"], "status": n.get("status"),
                          "created_ms": n.get("created_ms") if isinstance(n.get("created_ms"), int) else None})
    m = re.search(r"\((\d+)\)", payload.get("all_count_text") or "")
    e = re.sub(r"[^\d.]", "", payload.get("overview_earnings_text") or "")
    return _result("ok", rows=rows, overview_downloads=dl, overview_earnings=float(e) if e else None,
                   all_count=int(m.group(1)) if m else None, time_frame=payload.get("time_frame"),
                   sort_text=payload.get("sort_text"), named=named,
                   named_total=payload.get("named_total") if isinstance(payload.get("named_total"), int) else None,
                   pages_read=[n for n in payload.get("pages_read") or [] if isinstance(n, int)],
                   page_numbers=[n for n in payload.get("page_numbers") or [] if isinstance(n, int)],
                   pager_error=payload.get("pager_error") if isinstance(payload.get("pager_error"), str) else None)


def parse_probe(payload):
    """Structure dump of an own-dashboard page. Stored raw for a later purpose-built parser; extracts nothing itself."""
    if not isinstance(payload, dict):
        return _result("unknown", "payload_not_object")
    if _blocked(payload):
        return _result("blocked", _blocked(payload))
    text = payload.get("text")
    if not isinstance(text, str) or len(text.strip()) < 50:
        return _result("unknown", "no_probe_shape")
    return _result("ok", chars=len(text), tab_labels=payload.get("tab_labels") or [])


def parse_upload_stage(payload, expected_names):
    """Result of staging files on the Uploads page: the portal's "File types: All (N)" count must rise by exactly the number of files staged."""
    if not isinstance(payload, dict):
        return _result("unknown", "payload_not_object")
    if _blocked(payload):
        return _result("blocked", _blocked(payload))
    err = payload.get("error")
    if err == "new_not_empty":
        return _result("blocked", "new_not_empty")
    if err == "submission_limit":
        return _result("blocked", "submission_limit")
    if err == "submission_blocked":
        return _result("blocked", "submission_blocked")
    if err == "sha_mismatch":
        return _result("unknown", "stage_sha_mismatch", bad_file=str(payload.get("bad_file"))[:200])
    if err == "no_upload_input":
        return _result("unknown", "no_upload_input")
    if err:
        return _result("unknown", "stage_error:" + str(err)[:60])
    side = lambda k: payload.get(k) if isinstance(payload.get(k), dict) else {}
    count = lambda d: d.get("all_count") if isinstance(d.get("all_count"), int) and not isinstance(d.get("all_count"), bool) else None
    before, after = count(side("before")), count(side("after"))
    if before is None or after is None:
        return _result("unknown", "no_stage_shape")
    seen = [n for n in (payload.get("names_seen") or []) if n in expected_names]
    added = after - before
    base = {"expected": len(expected_names), "added": added, "before": before, "after": after,
            "names_seen": len(seen), "names_not_seen": sorted(set(expected_names) - set(seen))}
    if added != len(expected_names):
        return _result("unknown", "stage_incomplete", **base)
    return _result("ok", **base)


def parse_upload_metadata(payload, expected_count, flags=None):
    """Result of applying the CSV and the flags: every expected file must be in the New list, carry keywords, and be counted by Submit."""
    if not isinstance(payload, dict):
        return _result("unknown", "payload_not_object")
    if _blocked(payload):
        return _result("blocked", _blocked(payload))
    steps = [str(s)[:40] for s in (payload.get("steps") or [])][:20]
    err = payload.get("error")
    if err:
        return _result("unknown", "metadata_error:" + str(err)[:60], steps=steps, **({"detail": str(payload["detail"])[:300]} if payload.get("detail") else {}))
    side = payload.get("after") if isinstance(payload.get("after"), dict) else {}
    num = lambda k: side.get(k) if isinstance(side.get(k), int) and not isinstance(side.get(k), bool) else None
    all_count, submit = num("all_count"), num("submit_count")
    kw = side.get("keyword_counts") if isinstance(side.get("keyword_counts"), list) else []
    if all_count is None or submit is None or not kw:
        return _result("unknown", "no_metadata_shape", steps=steps)
    base = {"expected": expected_count, "all_count": all_count, "submit_count": submit, "tiles_with_keywords": sum(1 for k in kw if isinstance(k, int) and k >= 5),
            "ai_checked": side.get("ai_checked"), "include_checked": side.get("include_checked"), "steps": steps}
    if all_count != expected_count or submit != expected_count or base["tiles_with_keywords"] != expected_count:
        return _result("unknown", "metadata_incomplete", **base)
    if side.get("ai_checked") is not True or side.get("include_checked") is not True:
        return _result("unknown", "flags_not_set", **base)
    if (flags or {}).get("people_property_fictional") is True:
        base["fictional_checked"] = side.get("fictional_checked")
        if side.get("fictional_checked") is not True:
            return _result("unknown", "flags_not_set", **base)
    return _result("ok", **base)


# Adobe's own moderation cause codes as the Not accepted list reports them (history endpoint).
# 9 "Tech problems" is shown to the contributor as "Quality Issues"; 8 is "Similar content in our collection".
OUTCOME_CLASS = {9: "quality", 8: "similar"}


def parse_outcomes(payload):
    """Own Not accepted list: one row per asset with Adobe's refusal cause. Never keeps moderator data."""
    if not isinstance(payload, dict):
        return _result("unknown", "payload_not_object")
    if _blocked(payload):
        return _result("blocked", _blocked(payload))
    items = payload.get("items")
    if payload.get("ctx_found") is not True or not isinstance(items, list):
        return _result("unknown", "no_outcomes_shape")
    history = payload.get("history") if isinstance(payload.get("history"), dict) else {}
    rows, missing = [], 0
    for it in items:
        aid = it.get("asset_id") if isinstance(it, dict) else None
        if not isinstance(aid, int) or isinstance(aid, bool) or aid <= 0:
            return _result("unknown", "no_outcomes_shape")
        h = history.get(str(aid)) if isinstance(history.get(str(aid)), dict) else {}
        cause = h.get("cause") if isinstance(h.get("cause"), int) else None
        missing += cause is None
        rows.append({"asset_id": aid, "original_name": it.get("original_name"), "status": it.get("status"),
                     "created_ms": it.get("created_ms") if isinstance(it.get("created_ms"), int) else None,
                     "width": it.get("width") if isinstance(it.get("width"), int) else None,
                     "height": it.get("height") if isinstance(it.get("height"), int) else None,
                     "cause": cause, "cause_label": h.get("cause_label") if isinstance(h.get("cause_label"), str) else None,
                     "outcome_class": OUTCOME_CLASS.get(cause, "unknown" if cause is None else "other")})
    return _result("ok", rows=rows, history_missing=missing)


def _int(t):
    t = (t or "").replace(",", "").strip()
    return int(t) if t.isdigit() else None
