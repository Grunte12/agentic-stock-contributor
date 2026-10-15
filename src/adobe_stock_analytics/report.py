"""Tables are rendered by code from stored metrics. The agent pastes them unchanged."""
import hashlib
import re

from . import calibration as C, metrics as M, portfolio as P, recency as RC, related as RL

BLOCK_RE = re.compile(
    r"<!-- intel:table ids=(?P<ids>[0-9a-f,]*) sha256=(?P<sha>[0-9a-f]{64}) -->\n(?P<body>.*?)\n<!-- /intel:table -->",
    re.S)

KW_COLS = [("results", "Results"), ("supply_band", "Band"), ("ai_share", "AI share"),
           ("dl_top_ai_share", "AI share in top by downloads"),
           ("dl_distinct_creators", "Creators in top by downloads"),
           ("dl_top1_creator_share", "Top creator share"),
           ("dl_recent_share", "New assets in top by downloads"), ("supply_rating", "Rating")]


def fmt(m):
    v = m["value"]
    if v is None:
        return f"n/a ({m['status']})"
    n = m["name"]
    if n in ("ai_share", "top_ai_share", "dl_top_ai_share", "dl_top1_creator_share", "dl_recent_share", "creator_ai_share"):
        return f"{v * 100:.1f}%"
    if isinstance(v, int) and not isinstance(v, bool):
        return f"{v:,}"
    if isinstance(v, float):
        return f"{v:.2f}"
    if n.startswith("mg_") and v is None:
        return f"n/a ({m['status']})"
    if n == "keyword_freq":
        return ", ".join(f"{k} ({c})" for k, c in v[:10])
    if n == "opportunity_score":
        return (f"{v['score']:.2f} (supply {v['supply']:.2f} from {v['rating']}, "
                f"attention {v['attention']:.2f} from momentum {v['momentum']:.2f})")
    if n in ("related_top", "related_rising"):
        return "; ".join(f"{q} ({x})" for q, x in v[:10])
    if n == "recency_cut_suggestion":
        return (f"suggested min asset id {v['suggested_min_asset_id']:,} for {v['target_date']} from {v['anchors']} anchors "
                f"(config now {v['current_min_asset_id']:,}; not applied)")
    if n == "own_kw_coverage":
        return ", ".join(f"{k.replace('_', ' ')} {'n/a' if v[k] is None else v[k]}"  # fixed key order: stored JSON is key-sorted
                         for k in ("sold_total", "sold_read", "unsold_total", "unsold_read"))
    if n == "own_kw_sold":
        return "; ".join(f"{k} (sold {a}, unsold {'n/a' if b is None else b})" for k, a, b in v[:10])
    if n == "cal_group":
        return (f"{v['keyword']}: {v['results']:,} results, {v['band']}, {v['rating']}; {v['assets']:,} assets, "
                f"{v['downloads']:,} downloads, {v['dl_per_asset']:.2f} per asset")
    if n in ("cal_band", "cal_rating"):
        return f"{v['groups']} groups, {v['assets']:,} assets, {v['downloads']:,} downloads, {v['dl_per_asset']:.2f} per asset"
    if isinstance(v, dict):
        return f"{v['event']} (post {v['start']} to {v['end']}, {v['state']})"
    return str(v)


def render_body(metrics):
    by = {}
    for m in metrics:
        by.setdefault(m["subject"], {})[m["name"]] = m
    kw = {s: d for s, d in by.items() if "|" in s and not s.startswith(("opp:", "cal:", "own:", "calrecency:", "related:"))}
    opp = {s: d for s, d in by.items() if s.startswith("opp:")}
    lead = {s: d for s, d in by.items() if "lead_window" in d}
    trend = {s: d for s, d in by.items() if "trend_mean" in d}
    cre = {s: d for s, d in by.items() if s.startswith("creator:")}
    pf = {s: d for s, d in by.items() if s.startswith("group:")}
    own = {s: d for s, d in by.items() if s.startswith("portfolio:")}
    mg = {s: d for s, d in by.items() if s.startswith("mapgroup:")}
    out = []
    if kw:
        out += ["| Keyword | Media | " + " | ".join(h for _, h in KW_COLS) + " | Metric ids |",
                "|" + "---|" * (len(KW_COLS) + 3)]
        for s in sorted(kw):
            k, media = s.rsplit("|", 1)
            d = kw[s]
            cells = [fmt(d[n]) if n in d else "n/a (not_computed)" for n, _ in KW_COLS]
            ids = " ".join(f"`{d[n]['metric_id']}`" for n, _ in KW_COLS if n in d)
            out.append(f"| {k} | {media} | " + " | ".join(cells) + f" | {ids} |")
    if lead:
        out += ["", "| Event | Lead window | Metric id |", "|---|---|---|"]
        for s in sorted(lead, key=lambda s: (lead[s]["lead_window"]["value"] is None, (lead[s]["lead_window"]["value"] or {}).get("event", ""), s)):
            m = lead[s]["lead_window"]
            out.append(f"| {s} | {fmt(m)} | `{m['metric_id']}` |")
    if trend:
        out += ["", "| Term | Trends mean | Points | Momentum | Metric ids |", "|---|---|---|---|---|"]
        for s in sorted(trend):
            a, b, c = trend[s]["trend_mean"], trend[s].get("trend_points"), trend[s].get("trend_momentum")
            ids = " ".join(f"`{x['metric_id']}`" for x in (a, b, c) if x)
            out.append(f"| {s} | {fmt(a)} | {fmt(b) if b else 'n/a'} | {fmt(c) if c else 'n/a'} | {ids} |")
    if opp:
        out += ["", "| Keyword::attention term::media | Opportunity | Metric id |", "|---|---|---|"]
        for s in sorted(opp):
            m = opp[s]["opportunity_score"]
            out.append(f"| {s[4:]} | {fmt(m)} | `{m['metric_id']}` |")
    cal = [(s, d) for s, d in sorted(by.items()) if s.startswith(("cal:", "calband:", "calrating:", "calrecency:"))]
    if cal:
        out += ["", "| Calibration subject (association in this portfolio, not a forecast) | Result | Metric id |", "|---|---|---|"]
        for s, d in cal:
            m = next(iter(d.values()))
            out.append(f"| {s} | {fmt(m)} | `{m['metric_id']}` |")
    rel = [(s, d) for s, d in sorted(by.items()) if s.startswith("related:")]
    if rel:
        out += ["", "| Google Trends related queries (search demand, not stock-image demand) | List | Result (first 10) | Metric id |", "|---|---|---|---|"]
        for s, d in rel:
            for m in d.values():
                out.append(f"| {s[8:]} | {m['name'][8:]} | {fmt(m)} | `{m['metric_id']}` |")
    ownk = [(s, d) for s, d in sorted(by.items()) if s.startswith("own:")]
    if ownk:
        out += ["", "| Own keywords (association only) | Metric | Result | Metric id |", "|---|---|---|---|"]
        for s, d in ownk:
            for m in d.values():
                out.append(f"| {s} | {m['name']} | {fmt(m)} | `{m['metric_id']}` |")
    if cre:
        out += ["", "| Creator | Rows | AI share | Metric ids |", "|---|---|---|---|"]
        for s in sorted(cre):
            a, b = cre[s]["creator_rows"], cre[s]["creator_ai_share"]
            out.append(f"| {s} | {fmt(a)} | {fmt(b)} | `{a['metric_id']}` `{b['metric_id']}` |")
    if pf:
        out += ["", "| Group | Assets | Downloads | Downloads per asset | Metric ids |", "|---|---|---|---|---|"]
        for s in sorted(pf):
            a, b, c = pf[s]["pf_assets"], pf[s]["pf_downloads"], pf[s]["pf_downloads_per_asset"]
            out.append(f"| {s[6:]} | {fmt(a)} | {fmt(b)} | {fmt(c)} | `{a['metric_id']}` `{b['metric_id']}` `{c['metric_id']}` |")
    if own:
        names = ["pf_downloads_total", "pf_earnings_usd", "pf_assets_total", "pf_assets_with_downloads", "pf_cards_cover_total"]
        out += ["", "| Dashboard time frame | Downloads | Earnings (USD) | Assets | Assets with downloads | Cards cover total | Metric ids |",
                "|---|---|---|---|---|---|---|"]
        for s in sorted(own):
            d = own[s]
            out.append(f"| {s[10:]} | " + " | ".join(fmt(d[n]) for n in names) + " | " + " ".join(f"`{d[n]['metric_id']}`" for n in names) + " |")
    if mg:
        out += ["", "| Sub-niche group | Assets mapped | Downloads | Downloads per asset | Metric ids |", "|---|---|---|---|---|"]
        for s in sorted(mg):
            d = mg[s]
            ns = ["mg_assets", "mg_downloads", "mg_downloads_per_asset"]
            out.append(f"| {s[9:]} | " + " | ".join(fmt(d[n]) for n in ns) + " | " + " ".join(f"`{d[n]['metric_id']}`" for n in ns) + " |")
    return "\n".join(out).strip("\n")


def block(metrics):
    metrics = sorted(metrics, key=lambda m: m["metric_id"])
    body = render_body(metrics)
    sha = hashlib.sha256(body.encode()).hexdigest()
    ids = ",".join(m["metric_id"] for m in metrics)
    return f"<!-- intel:table ids={ids} sha256={sha} -->\n{body}\n<!-- /intel:table -->", sha


def report(store, cfg, keywords=(), trends=(), creators=(), as_of=None, lead_as_of=None, portfolio=False, opportunities=(), calibration=False, own_keywords=False, related=()):
    ms = []
    for k in keywords:
        ms += M.compute_keyword(store, cfg, k["keyword"], k.get("media_type", "photo"), as_of=as_of)
    for t in trends:
        ms += M.compute_trend(store, cfg, t)
    for o in opportunities:
        ms += M.compute_opportunity(store, cfg, o["keyword"], o.get("media_type", "photo"), o["term"])
    for c in creators:
        ms += M.compute_contributor(store, cfg, c)
    if portfolio:
        ms += _portfolio(store, cfg) + P.compute_live(store, cfg)
    for seed in related:
        ms += RL.compute_related(store, cfg, seed)
    if own_keywords:
        ms += P.compute_own_keywords(store, cfg)
    if calibration:
        ms += C.compute_calibration(store, cfg) + RC.compute_recency_cut(store, cfg, (as_of or store.now())[:10])
    if lead_as_of:
        ms += M.compute_lead(store, cfg, lead_as_of)
    text, sha = block(ms)
    return {"markdown": text, "render_sha256": sha, "metrics": ms}


def _portfolio(store, cfg):
    return P.compute_portfolio(store, cfg)
