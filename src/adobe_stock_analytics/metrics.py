"""Deterministic metrics. Same stored observations + same config => same metric ids and values."""
import hashlib
import statistics
from collections import Counter
from datetime import date, timedelta

from .config import canon, metrics_version

NAMES = ["results", "supply_band", "ai_share", "ai_split_gap", "top_ai_share", "dl_top_ai_share",
         "dl_distinct_creators", "dl_top1_creator_share", "dl_recent_share", "keyword_freq", "supply_rating"]


def subject_key(keyword, media_type):
    return f"{' '.join(keyword.lower().split())}|{media_type}"


def mk(cfg, name, subject, value, inputs, reason="no_input"):
    inputs = sorted(inputs)
    mid = hashlib.sha256(canon([name, subject, inputs, metrics_version(cfg)]).encode()).hexdigest()[:16]
    return {"metric_id": mid, "name": name, "subject": subject, "value": value,
            "status": "ok" if value is not None else reason, "inputs": inputs,
            "metrics_version": metrics_version(cfg)}


def band(results, cfg):
    if results is None:
        return None
    for b in cfg["bands"]:
        if b["max"] is None or results < b["max"]:
            return b["name"]
    return None


def _share(num, den):
    return None if not den else round(num / den, 4)


def _creator_stats(rows, n):
    rows = rows[:n]
    ids = [r["creator_id"] for r in rows if r["creator_id"] is not None]
    if not ids:
        return None, None
    top = Counter(ids).most_common(1)[0][1]
    return len(set(ids)), _share(top, len(ids))


def _recent_share(rows, n, min_id):
    ids = [r["asset_id"] for r in rows[:n] if r["asset_id"] is not None]
    return _share(sum(1 for i in ids if i >= min_id), len(ids))


def _ai_share_of_rows(rows, n):
    flags = [r["is_gentech"] for r in rows[:n] if r["is_gentech"] is not None]
    return _share(sum(flags), len(flags))


def compute_keyword(store, cfg, keyword, media_type="photo", as_of=None):
    """Compute and store all metrics for one keyword. Missing observations give null metrics."""
    keyword = " ".join(keyword.split())
    subj = subject_key(keyword, media_type)
    n = cfg["top_n"]
    obs = {k: store.latest_search(keyword, media_type, *k, as_of=as_of)
           for k in [("all", "relevance"), ("only_ai", "relevance"), ("no_ai", "relevance"), ("all", "downloads")]}
    o = lambda k: obs[k]["obs_id"] if obs[k] else None
    ins = lambda *ks: [f"obs:{o(k)}" for k in ks if obs[k]]
    out = []

    def add(name, value, inputs, reason="no_input"):
        m = mk(cfg, name, subj, value, inputs, reason)
        store.put_metric(m)
        out.append(m)
        return m

    res = obs[("all", "relevance")]["results"] if obs[("all", "relevance")] else None
    add("results", res, ins(("all", "relevance")))
    add("supply_band", band(res, cfg), ins(("all", "relevance")))
    ai = obs[("only_ai", "relevance")]["results"] if obs[("only_ai", "relevance")] else None
    no = obs[("no_ai", "relevance")]["results"] if obs[("no_ai", "relevance")] else None
    ai_share = _share(ai, res) if ai is not None and res else None
    add("ai_share", ai_share, ins(("all", "relevance"), ("only_ai", "relevance")))
    add("ai_split_gap", (res - ai - no) if None not in (res, ai, no) else None,
        ins(("all", "relevance"), ("only_ai", "relevance"), ("no_ai", "relevance")))
    rel_rows = store.rows(o(("all", "relevance"))) if obs[("all", "relevance")] else []
    add("top_ai_share", _ai_share_of_rows(rel_rows, n), ins(("all", "relevance")))
    dl_rows = store.rows(o(("all", "downloads"))) if obs[("all", "downloads")] else []
    add("dl_top_ai_share", _ai_share_of_rows(dl_rows, n), ins(("all", "downloads")))
    distinct, top1 = _creator_stats(dl_rows, n)
    add("dl_distinct_creators", distinct, ins(("all", "downloads")))
    dl_top1 = add("dl_top1_creator_share", top1, ins(("all", "downloads")))
    add("dl_recent_share", _recent_share(dl_rows, n, cfg["recency"]["min_asset_id"]), ins(("all", "downloads")))

    details = store.asset_details([r["asset_id"] for r in dl_rows[:n]])
    freq = Counter(k for d in details for k in set(d["keywords"]))
    top_kw = sorted(freq.items(), key=lambda kv: (-kv[1], kv[0]))[:30]
    add("keyword_freq", [list(x) for x in top_kw] if top_kw else None,
        [f"obs:{d['obs_id']}" for d in details])

    rating, reason = rate(cfg, res, ai_share, top1)
    add("supply_rating", rating, ins(("all", "relevance"), ("only_ai", "relevance"), ("all", "downloads")), reason)
    return out


def rate(cfg, results, ai_share, dl_top1):
    if results is None or ai_share is None or dl_top1 is None:
        return "UNMEASURED", None
    b = band(results, cfg)
    r = cfg["rating"]
    if b in r["go"]["bands"] and dl_top1 <= r["go"]["max_dl_top1_creator_share"]:
        return "GO", None
    if b in r["skip"]["bands"] and ai_share >= r["skip"]["min_ai_share"]:
        return "SKIP", None
    return "MAYBE", None


def compute_contributor(store, cfg, creator_id):
    subj = f"creator:{int(creator_id)}"
    o = store.latest_contributor(creator_id)
    rows = store.rows(o["obs_id"]) if o else []
    ins = [f"obs:{o['obs_id']}"] if o else []
    out = []
    for name, val in (("creator_rows", len(rows) if rows else None),
                      ("creator_ai_share", _ai_share_of_rows(rows, len(rows)) if rows else None)):
        m = mk(cfg, name, subj, val, ins)
        store.put_metric(m)
        out.append(m)
    return out


def compute_trend(store, cfg, term):
    r = store.db.execute(
        "SELECT file_sha256, date, value FROM trend_point WHERE lower(term)=lower(?) AND file_sha256="
        "(SELECT file_sha256 FROM trend_point WHERE lower(term)=lower(?) ORDER BY rowid DESC LIMIT 1) ORDER BY date",
        (term, term)).fetchall()
    vals = [x["value"] for x in r if x["value"] is not None]
    ins = [f"file:{r[0]['file_sha256']}"] if r else []
    subj = " ".join(term.lower().split())
    out = []
    for name, val in (("trend_mean", round(statistics.fmean(vals), 2) if vals else None),
                      ("trend_points", len(vals) if vals else None),
                      ("trend_momentum", momentum(vals, cfg["momentum"]))):
        m = mk(cfg, name, subj, val, ins)
        store.put_metric(m)
        out.append(m)
    return out


def momentum(vals, mc):
    """Mean of the newest points divided by the mean of the points before them. Null when there is too little history."""
    r, b = mc["recent_points"], mc["baseline_points"]
    if len(vals) < r + b:
        return None
    base = statistics.fmean(vals[-(r + b):-r])
    return round(statistics.fmean(vals[-r:]) / base, 2) if base > 0 else None


def compute_opportunity(store, cfg, keyword, media_type, term):
    """Supply rating and attention momentum combined with config weights. Every component is shown and cited."""
    kw = {m["name"]: m for m in compute_keyword(store, cfg, keyword, media_type)}
    tr = {m["name"]: m for m in compute_trend(store, cfg, term)}
    oc = cfg["opportunity"]
    rating, mom = kw["supply_rating"], tr["trend_momentum"]
    supply = oc["supply_scores"].get(rating["value"])
    lo, hi = oc["attention_floor"], oc["attention_ceiling"]
    attn = None if mom["value"] is None else round(min(1.0, max(0.0, (mom["value"] - lo) / (hi - lo))), 2)
    w = oc["weights"]
    value, reason = None, "no_input"
    if supply is not None and attn is not None:
        value = {"score": round(w["supply"] * supply + w["attention"] * attn, 2), "supply": supply, "attention": attn,
                 "rating": rating["value"], "momentum": mom["value"]}
    m = mk(cfg, "opportunity_score", f"opp:{' '.join(keyword.lower().split())}::{' '.join(term.lower().split())}::{media_type}", value,
           [f"metric:{rating['metric_id']}", f"metric:{mom['metric_id']}"], reason)
    store.put_metric(m)
    return list(kw.values()) + list(tr.values()) + [m]


def _next_event(ev, today):
    """Next date of an event: the first listed date on or after today, or the same month/day this or next year."""
    if "dates" in ev:
        return next((d for d in map(date.fromisoformat, sorted(ev["dates"])) if d >= today), None)
    for y in (today.year, today.year + 1):
        d = date(y, ev["month"], ev["day"])
        if d >= today:
            return d
    raise ValueError("unreachable")


def compute_lead(store, cfg, as_of):
    """Lead window = event date minus start_weeks to minus end_weeks (config.lead; community hypothesis)."""
    today = date.fromisoformat(as_of)
    out = []
    for ev in cfg["events"]:
        d = _next_event(ev, today)
        if d is None:  # moving holiday with no listed future date: never guess one
            m = mk(cfg, "lead_window", ev["name"], None, [f"date:{as_of}"], "no_future_date_in_config")
        else:
            start, end = d - timedelta(weeks=cfg["lead"]["start_weeks"]), d - timedelta(weeks=cfg["lead"]["end_weeks"])
            state = "upcoming" if today < start else "open" if today <= end else "late"
            m = mk(cfg, "lead_window", ev["name"], {"event": d.isoformat(), "start": start.isoformat(),
                                                     "end": end.isoformat(), "state": state}, [f"date:{as_of}"])
        store.put_metric(m)
        out.append(m)
    return out


def forms(value):
    """All printed spellings of the numbers inside a metric value (used by the verifier)."""
    s = set()

    def walk(v):
        if isinstance(v, bool) or v is None:
            return
        if isinstance(v, int):
            s.update({str(v), f"{v:,}"})
        elif isinstance(v, float):
            s.update({repr(v), f"{v:.2f}", f"{v:.4f}", f"{v * 100:.1f}%", f"{v * 100:.1f}", f"{v * 100:.0f}%"})
        elif isinstance(v, str):
            for tok in __import__("re").findall(r"\d[\d,]*(?:\.\d+)?", v):
                s.add(tok)
        elif isinstance(v, (list, tuple)):
            for x in v:
                walk(x)
        elif isinstance(v, dict):
            for x in v.values():
                walk(x)

    walk(value)
    return s
