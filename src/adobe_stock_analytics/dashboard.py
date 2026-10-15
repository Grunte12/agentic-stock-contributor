"""HTML dashboard rendered from stored metrics only. Charts are inline SVG, so the page needs no network and no scripts.
Every figure keeps the metric id it came from (tooltip or table cell)."""
import html
from datetime import date
from math import log10

from . import report as R

esc = html.escape

PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
{refresh}<title>Stock Analytics Dashboard</title>
<style>
:root{{--bg:#fff;--card:#f6f7f9;--fg:#1a1a1a;--mute:#666;--line:#ddd;--go:#1b7f3b;--maybe:#b07800;--skip:#b3261e;--none:#8a8f98;--supply:#2f6fdb;--attn:#e08a00}}
@media (prefers-color-scheme:dark){{:root{{--bg:#16181c;--card:#1f2227;--fg:#e8e8e8;--mute:#9a9a9a;--line:#33363b;--go:#5fd38a;--maybe:#e0b24a;--skip:#ff8a80;--none:#8a8f98;--supply:#6aa0ff;--attn:#f0a830}}}}
*{{box-sizing:border-box}}body{{margin:0;padding:16px;background:var(--bg);color:var(--fg);font:15px/1.5 system-ui,sans-serif;max-width:1100px;margin-inline:auto}}
h1{{font-size:1.3rem;margin:.2rem 0}}h2{{font-size:1.05rem;margin:2rem 0 .2rem}}p.note{{color:var(--mute);margin:.2rem 0 .8rem}}
.kpis{{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;margin-top:12px}}
.kpi{{background:var(--card);border-radius:10px;padding:10px 14px}}.kpi b{{display:block;font-size:1.4rem}}.kpi span{{color:var(--mute);font-size:.8rem}}
.chart{{overflow-x:auto;background:var(--card);border-radius:10px;padding:10px}}svg{{display:block;max-width:100%;height:auto}}
svg text{{fill:var(--fg);font:12px system-ui,sans-serif}}svg .mute{{fill:var(--mute)}}svg .grid{{stroke:var(--line);stroke-width:1;fill:none}}
.b-supply{{fill:var(--supply)}}.b-attn{{fill:var(--attn)}}.b-one{{fill:var(--supply)}}
.GO{{fill:var(--go);color:var(--go)}}.MAYBE{{fill:var(--maybe);color:var(--maybe)}}.SKIP{{fill:var(--skip);color:var(--skip)}}.UNMEASURED{{fill:var(--none);color:var(--none)}}
.spark{{fill:none;stroke:var(--supply);stroke-width:2}}
.legend span{{display:inline-block;margin-right:14px;font-size:.85rem}}.legend i{{display:inline-block;width:10px;height:10px;border-radius:2px;margin-right:4px}}
.wrap{{overflow-x:auto}}table{{border-collapse:collapse;width:100%}}th,td{{text-align:left;padding:6px 10px;border-bottom:1px solid var(--line);white-space:nowrap}}
th{{color:var(--mute);font-weight:600}}code{{color:var(--mute);font-size:.75em}}
</style></head><body>
<h1>Stock Analytics Dashboard</h1>
<p class="note">Read-only view of stored observations, built {stamp}. {fresh} Scores are relative indices, not sales. Weights are uncalibrated until compared with your own sales.</p>
{body}
</body></html>"""


def _latest(metrics):
    """The store keeps older versions of a metric; keep the newest per subject and name."""
    by = {}
    for m in metrics:
        k = (m["subject"], m["name"])
        if k not in by or m["computed_at"] >= by[k]["computed_at"]:
            by[k] = m
    return list(by.values())


def refresh(store, cfg, today):
    """Recompute every metric the stored observations support, so the dashboard shows current numbers."""
    kws = [{"keyword": r["keyword"], "media_type": r["media_type"]}
           for r in store.db.execute("SELECT DISTINCT keyword, media_type FROM search_count ORDER BY keyword, media_type")]
    terms = [r["term"] for r in store.db.execute("SELECT DISTINCT term FROM trend_point ORDER BY term")]
    lower = {t.lower(): t for t in terms}
    opps = [{"keyword": k["keyword"], "media_type": k["media_type"], "term": lower[k["keyword"].lower()]}
            for k in kws if k["keyword"].lower() in lower]
    r = R.report(store, cfg, kws, terms, lead_as_of=today, portfolio=True, opportunities=opps)
    return {"keywords": len(kws), "terms": len(terms), "opportunities": len(opps), "metrics": len(r["metrics"])}


def _id(m):
    return f"metric {m['metric_id']}" if m else ""


def _trunc(s, n=34):
    return s if len(s) <= n else s[: n - 1] + "…"


def _cell(m):
    return esc(R.fmt(m)) + f" <code>{m['metric_id']}</code>" if m else "n/a"


def _table(title, note, head, rows):
    if not rows:
        return ""
    th = "".join(f"<th>{esc(h)}</th>" for h in head)
    tr = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in rows)
    return f'<h2>{esc(title)}</h2><p class="note">{esc(note)}</p><div class="wrap"><table><tr>{th}</tr>{tr}</table></div>'


def _section(title, note, svg, legend=""):
    if not svg:
        return ""
    return f'<h2>{esc(title)}</h2><p class="note">{esc(note)}</p>{legend}<div class="chart">{svg}</div>'


def opportunity_chart(rows, cfg):
    """rows: [(subject, metric)] already sorted. Bar = weighted supply part + weighted attention part."""
    if not rows:
        return ""
    w, lw, bw, rh = cfg["opportunity"]["weights"], 300, 380, 30
    out = []
    for i, (s, m) in enumerate(rows):
        kw, term, _media = s.split("::")
        label = kw if kw == term else f"{kw} ← {term}"
        y, v = i * rh, m["value"]
        out.append(f'<text x="{lw - 8}" y="{y + 19}" text-anchor="end">{esc(_trunc(label))}</text>')
        if v:
            sw, aw = w["supply"] * v["supply"] * bw, w["attention"] * v["attention"] * bw
            out.append(f'<g><title>{esc(label)}: {esc(R.fmt(m))} ({_id(m)})</title>'
                       f'<rect class="b-supply" x="{lw}" y="{y + 6}" width="{sw:.1f}" height="18"/>'
                       f'<rect class="b-attn" x="{lw + sw:.1f}" y="{y + 6}" width="{aw:.1f}" height="18"/>'
                       f'<text x="{lw + sw + aw + 6:.1f}" y="{y + 19}">{v["score"]:.2f}</text></g>')
        else:
            out.append(f'<text class="mute" x="{lw}" y="{y + 19}">n/a: scan or attention series missing</text>')
    return f'<svg viewBox="0 0 {lw + bw + 60} {len(rows) * rh}" width="{lw + bw + 60}" role="img" aria-label="Opportunity ranking">{"".join(out)}</svg>'


def niche_map(kws, cfg):
    """Supply size (log) against AI share. Lower left is the open space; colour is the supply rating."""
    pts = []
    for s, d in kws:
        res, ai, rt = d.get("results"), d.get("ai_share"), d.get("supply_rating")
        if res and ai and res["value"] and ai["value"] is not None:
            pts.append((s.rsplit("|", 1)[0], res, ai, rt["value"] if rt else "UNMEASURED"))
    if not pts:
        return ""
    W, H, L, B, T, Rr = 700, 400, 52, 40, 34, 20
    lo, hi = 1.0, 5.6
    x = lambda r: L + (log10(max(r, 10)) - lo) / (hi - lo) * (W - L - Rr)
    y = lambda a: H - B - a * (H - B - T)
    out = [f'<line class="grid" x1="{L}" y1="{H - B}" x2="{W - Rr}" y2="{H - B}"/><line class="grid" x1="{L}" y1="{T}" x2="{L}" y2="{H - B}"/>']
    for a in (0, .25, .5, .75, 1):
        out.append(f'<line class="grid" x1="{L}" y1="{y(a):.1f}" x2="{W - Rr}" y2="{y(a):.1f}" stroke-dasharray="2 4"/>'
                   f'<text class="mute" x="{L - 6}" y="{y(a) + 4:.1f}" text-anchor="end">{a * 100:.0f}%</text>')
    for r in (100, 1000, 10000, 100000):
        out.append(f'<text class="mute" x="{x(r):.1f}" y="{H - B + 16}" text-anchor="middle">{r:,}</text>')
    for i, b in enumerate(cfg["bands"][:-1]):
        out.append(f'<line class="grid" x1="{x(b["max"]):.1f}" y1="{T - 12 + 12 * (i % 2)}" x2="{x(b["max"]):.1f}" y2="{H - B}" stroke-dasharray="6 4"/>'
                   f'<text class="mute" x="{x(b["max"]) + 3:.1f}" y="{T - 2 + 12 * (i % 2)}">{esc(b["name"])} &lt;{b["max"]:,}</text>')
    out.append(f'<text class="mute" x="{(W + L) / 2}" y="{H - 6}" text-anchor="middle">Search results on Adobe Stock (log scale)</text>'
               f'<text class="mute" x="12" y="{T - 18}">AI share of results</text>')
    placed = []  # label boxes already used; push a label down until it clears them
    for label, res, ai, rt in sorted(pts, key=lambda p: p[1]["value"]):
        cx, cy = x(res["value"]), y(ai["value"])
        ly = cy + 4
        while any(abs(cx - px) < 150 and abs(ly - py) < 13 for px, py in placed):
            ly += 13
        placed.append((cx, ly))
        leader = f'<line class="grid" x1="{cx:.1f}" y1="{cy:.1f}" x2="{cx + 8:.1f}" y2="{ly - 4:.1f}"/>' if ly > cy + 5 else ""
        out.append(f'<g><title>{esc(label)}: {res["value"]:,} results, AI share {ai["value"] * 100:.1f}%, {esc(str(rt))} ({_id(res)}, {_id(ai)})</title>'
                   f'{leader}<circle class="{esc(str(rt))}" cx="{cx:.1f}" cy="{cy:.1f}" r="7"/>'
                   f'<text x="{cx + 10:.1f}" y="{ly:.1f}">{esc(_trunc(label, 24))}</text></g>')
    return f'<svg viewBox="0 0 {W} {H}" width="{W}" role="img" aria-label="Niche map">{"".join(out)}</svg>'


def sparkline(values, w=140, h=30):
    lo, hi = min(values), max(values)
    span = (hi - lo) or 1
    xy = [(i / (len(values) - 1) * (w - 6) + 3, h - 4 - (v - lo) / span * (h - 8)) for i, v in enumerate(values)]
    pts = " ".join(f"{px:.1f},{py:.1f}" for px, py in xy)
    return (f'<svg viewBox="0 0 {w} {h}" width="{w}" height="{h}" role="img"><polyline class="spark" points="{pts}"/>'
            f'<circle class="b-one" cx="{xy[-1][0]:.1f}" cy="{xy[-1][1]:.1f}" r="3"/></svg>')


def _series(store, term):
    rows = store.db.execute(
        "SELECT value FROM trend_point WHERE lower(term)=lower(?) AND value IS NOT NULL AND file_sha256="
        "(SELECT file_sha256 FROM trend_point WHERE lower(term)=lower(?) ORDER BY rowid DESC LIMIT 1) ORDER BY date",
        (term, term)).fetchall()
    return [r["value"] for r in rows][-26:]


def group_chart(rows):
    """rows: [(label, downloads metric, assets metric)]"""
    rows = [r for r in rows if r[1]["value"] is not None]
    if not rows:
        return ""
    rows.sort(key=lambda r: -r[1]["value"])
    top, lw, bw, rh = max(r[1]["value"] for r in rows) or 1, 220, 380, 28
    out = []
    for i, (label, dl, assets) in enumerate(rows):
        y, n = i * rh, dl["value"]
        extra = f", {assets['value']:,} assets" if assets and assets["value"] is not None else ""
        out.append(f'<g><title>{esc(label)}: {n:,} downloads{esc(extra)} ({_id(dl)})</title>'
                   f'<text x="{lw - 8}" y="{y + 18}" text-anchor="end">{esc(_trunc(label, 28))}</text>'
                   f'<rect class="b-one" x="{lw}" y="{y + 5}" width="{max(n / top * bw, 1):.1f}" height="17"/>'
                   f'<text x="{lw + n / top * bw + 6:.1f}" y="{y + 18}">{n:,}{esc(extra)}</text></g>')
    return f'<svg viewBox="0 0 {lw + bw + 140} {len(rows) * rh}" width="{lw + bw + 140}" role="img" aria-label="Downloads by group">{"".join(out)}</svg>'


def season_chart(leads, today):
    """Next 12 months. Shaded span = the posting window before the event (config.lead); dot = the event day."""
    if not leads:
        return ""
    t0, lw, bw, rh = date.fromisoformat(today), 160, 520, 28
    pos = lambda d: min(max((date.fromisoformat(d) - t0).days / 365, 0), 1) * bw
    out = [f'<line class="grid" x1="{lw}" y1="0" x2="{lw}" y2="{len(leads) * rh}"/>']
    for i, (name, m) in enumerate(leads):
        v, y = m["value"], i * rh
        cls = {"open": "GO", "upcoming": "MAYBE", "late": "SKIP"}[v["state"]]
        a, b, e = pos(v["start"]), pos(v["end"]), pos(v["event"])
        out.append(f'<g><title>{esc(name)}: {esc(R.fmt(m))} ({_id(m)})</title>'
                   f'<text x="{lw - 8}" y="{y + 18}" text-anchor="end">{esc(name)}</text>'
                   f'<line class="grid" x1="{lw}" y1="{y + 14}" x2="{lw + bw}" y2="{y + 14}"/>'
                   f'<rect class="{cls}" x="{lw + a:.1f}" y="{y + 6}" width="{max(b - a, 3):.1f}" height="16" opacity=".8"/>'
                   f'<circle class="{cls}" cx="{lw + e:.1f}" cy="{y + 14}" r="4"/>'
                   f'<text class="mute" x="{lw + e + 8:.1f}" y="{y + 18}">{esc(v["event"])}</text></g>')
    return f'<svg viewBox="0 0 {lw + bw + 90} {len(leads) * rh}" width="{lw + bw + 90}" role="img" aria-label="Seasonal windows">{"".join(out)}</svg>'


def render(store, cfg, stamp, live=False):
    by = {}
    for m in _latest(store.metrics_for()):
        by.setdefault(m["subject"], {})[m["name"]] = m
    opp = sorted(((s[4:], d["opportunity_score"]) for s, d in by.items() if s.startswith("opp:")),
                 key=lambda x: (x[1]["value"] is None, -(x[1]["value"] or {}).get("score", 0), x[0]))
    kw = sorted((s, d) for s, d in by.items() if "|" in s and not s.startswith("opp:"))
    trend = sorted((s, d) for s, d in by.items() if "trend_mean" in d)
    lead = sorted(((s, d["lead_window"]) for s, d in by.items() if "lead_window" in d and d["lead_window"]["value"]), key=lambda x: x[1]["value"]["event"])
    frames = [d for s, d in by.items() if s.startswith("portfolio:") and d.get("pf_downloads_total", {}).get("value") is not None]
    own = max(frames, key=lambda d: d["pf_downloads_total"]["value"], default=None)  # the widest time frame
    groups = [(s[9:], d["mg_downloads"], d.get("mg_assets")) for s, d in by.items() if s.startswith("mapgroup:") and "mg_downloads" in d]
    groups = groups or [(s[6:], d["pf_downloads"], d.get("pf_assets")) for s, d in by.items() if s.startswith("group:") and "pf_downloads" in d]
    latest = store.db.execute("SELECT MAX(read_at) AS t FROM observation").fetchone()["t"]

    body = ""
    if own:
        cards = [("Downloads", "pf_downloads_total"), ("Earnings (USD)", "pf_earnings_usd"), ("Assets", "pf_assets_total")]
        body += '<div class="kpis">' + "".join(f'<div class="kpi"><b title="{_id(own[n])}">{esc(R.fmt(own[n]))}</b><span>{lab}</span></div>'
                                              for lab, n in cards if n in own) + "</div>"
    legend = ('<p class="legend"><span><i style="background:var(--supply)"></i>Supply part</span>'
              '<span><i style="background:var(--attn)"></i>Attention part</span></p>')
    body += _section("Which keyword first", "Longer bar is better. Blue is the supply rating, amber is attention momentum. Hover a bar for the metric id.",
                     opportunity_chart(opp, cfg), legend)
    body += _section("Niche map", "Each dot is a keyword. Lower left means few results and few AI images. Colour is the supply rating: green GO, amber MAYBE, red SKIP, grey unmeasured.",
                     niche_map(kw, cfg))
    spark = "".join(
        f'<tr><td>{esc(s)}</td><td>{sparkline(v)}</td><td>{_cell(d.get("trend_momentum"))}</td><td>{_cell(d.get("trend_mean"))}</td></tr>'
        for s, d in trend for v in [_series(store, s)] if len(v) > 1)
    if spark:
        body += ('<h2>Attention over time</h2><p class="note">Weekly series per term, newest on the right. Momentum above 1 means the newest weeks are higher than the weeks before.</p>'
                 f'<div class="wrap"><table><tr><th>Term</th><th>Trend</th><th>Momentum</th><th>Mean</th></tr>{spark}</table></div>')
    body += _section("Your portfolio by sub-niche", "Downloads per group from your own dashboard. This is the only place real sales show up.", group_chart(groups))
    body += _section("When to publish", "Shaded span is the posting window (13 to 8 weeks before the event); the dot is the event day.",
                     season_chart(lead, stamp[:10]))
    body += _table("Supply details", "Adobe public search pages: counts, AI share, who holds the top by downloads.",
                   ["Keyword", "Media"] + [h for _, h in R.KW_COLS],
                   [[esc(s.rsplit("|", 1)[0]), esc(s.rsplit("|", 1)[1])] +
                    [f'<span class="{esc(str(d[n]["value"]))}">{_cell(d[n])}</span>' if n == "supply_rating" and n in d
                     else _cell(d.get(n)) for n, _ in R.KW_COLS] for s, d in kw])
    return PAGE.format(stamp=esc(stamp), fresh=esc(f"Newest page read: {latest}." if latest else "No pages read yet."),
                       refresh='<meta http-equiv="refresh" content="60">\n' if live else "",
                       body=body or "<p>No metrics stored yet. Ask the agent to run a scan and a report, then reload.</p>")
