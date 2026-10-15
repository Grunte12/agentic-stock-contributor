"""Own-portfolio numbers from a user-exported CSV (the existing portal capture tooling owns the portal read).

Columns (case-insensitive): downloads (required); asset_id or filename (one required); group, earnings, period optional.
The `group` column is the sub-niche label the user or the pipeline assigns.
"""
import csv
import hashlib
import io
from pathlib import Path

from . import metrics as M


def import_portfolio(store, path):
    raw = Path(path).read_bytes()
    sha = hashlib.sha256(raw).hexdigest()
    if store.db.execute("SELECT 1 FROM portfolio_row WHERE file_sha256=? LIMIT 1", (sha,)).fetchone():
        return {"file_sha256": sha, "rows": 0, "already_imported": True}
    rd = csv.DictReader(io.StringIO(raw.decode("utf-8-sig")))
    cols = {(c or "").strip().lower(): c for c in (rd.fieldnames or [])}
    if "downloads" not in cols or not ({"asset_id", "filename"} & set(cols)):
        raise ValueError("CSV needs a downloads column and an asset_id or filename column")
    n = 0
    for r in rd:
        g = lambda k: (r.get(cols[k]) or "").strip() if k in cols else ""
        try:
            dl = int(g("downloads").replace(",", ""))
        except ValueError:
            continue  # a non-numeric cell is skipped, never read as 0
        try:
            earn = float(g("earnings").replace(",", "")) if g("earnings") else None
        except ValueError:
            earn = None
        store.db.execute("INSERT INTO portfolio_row VALUES(?,?,?,?,?,?,?)",
                         (sha, g("asset_id") or None, g("filename") or None, g("group") or "(ungrouped)", dl, earn, g("period") or None))
        n += 1
    return {"file_sha256": sha, "rows": n, "already_imported": False}


def compute_portfolio(store, cfg):
    r = store.db.execute("SELECT file_sha256 FROM portfolio_row ORDER BY rowid DESC LIMIT 1").fetchone()
    if not r:
        return []
    sha = r["file_sha256"]
    out = []
    for g in store.db.execute("SELECT grp, count(*) c, sum(downloads) d FROM portfolio_row WHERE file_sha256=? GROUP BY grp ORDER BY grp", (sha,)):
        subj = f"group:{g['grp']}"
        for name, val in (("pf_assets", g["c"]), ("pf_downloads", g["d"]), ("pf_downloads_per_asset", round(g["d"] / g["c"], 2))):
            m = M.mk(cfg, name, subj, val, [f"file:{sha}"])
            store.put_metric(m)
            out.append(m)
    return out


def import_groups(store, path):
    """asset_id,group mapping (sub-niche labels) for the live dashboard rows."""
    raw = Path(path).read_bytes()
    sha = hashlib.sha256(raw).hexdigest()
    rd = csv.DictReader(io.StringIO(raw.decode("utf-8-sig")))
    cols = {(c or "").strip().lower(): c for c in (rd.fieldnames or [])}
    if not {"asset_id", "group"} <= set(cols):
        raise ValueError("CSV needs asset_id and group columns")
    n = 0
    for r in rd:
        a = (r[cols["asset_id"]] or "").strip()
        g = (r[cols["group"]] or "").strip()
        if a.isdigit() and g:
            store.db.execute("INSERT OR REPLACE INTO group_map VALUES(?,?,?)", (int(a), g, sha))
            n += 1
    return {"file_sha256": sha, "mapped": n}


def compute_live(store, cfg):
    """Metrics from the latest own-dashboard observation. A dash is zero only when the cards add up to the total."""
    o = store.db.execute("SELECT o.obs_id FROM observation o WHERE o.kind='portfolio' AND o.status='ok' "
                         "ORDER BY o.read_at DESC LIMIT 1").fetchone()
    if not o:
        return []
    oid = o["obs_id"]
    ov = dict(store.db.execute("SELECT * FROM pf_overview WHERE obs_id=?", (oid,)).fetchone())
    cards = [dict(r) for r in store.db.execute("SELECT asset_id, downloads FROM pf_asset WHERE obs_id=?", (oid,))]
    tf = ov["time_frame"] or "unknown"
    subj, ins = f"portfolio:{tf}", [f"obs:{oid}"]
    seen = sum(c["downloads"] for c in cards if c["downloads"] is not None)
    covered = seen == ov["downloads"]
    out = []

    def add(name, subject, value, inputs, reason="no_input"):
        m = M.mk(cfg, name, subject, value, inputs, reason)
        store.put_metric(m)
        out.append(m)

    add("pf_downloads_total", subj, ov["downloads"], ins)
    add("pf_earnings_usd", subj, ov["earnings"], ins)
    add("pf_assets_total", subj, ov["all_count"], ins)
    add("pf_cards_cover_total", subj, "yes" if covered else "no", ins)
    add("pf_assets_with_downloads", subj, sum(1 for c in cards if c["downloads"]), ins)
    groups = store.db.execute("SELECT grp, group_concat(asset_id) ids, count(*) c FROM group_map GROUP BY grp ORDER BY grp").fetchall()
    for g in groups:
        ids = {int(x) for x in g["ids"].split(",")}
        dl = sum(c["downloads"] or 0 for c in cards if c["asset_id"] in ids) if covered else None
        gi = ins + [f"file:{r['file_sha256']}" for r in store.db.execute(
            "SELECT DISTINCT file_sha256 FROM group_map WHERE grp=?", (g["grp"],))]
        add("mg_assets", f"mapgroup:{g['grp']} @ {tf}", g["c"], gi)
        add("mg_downloads", f"mapgroup:{g['grp']} @ {tf}", dl, gi, "cards_do_not_cover_total")
        add("mg_downloads_per_asset", f"mapgroup:{g['grp']} @ {tf}", round(dl / g["c"], 2) if dl is not None else None, gi,
            "cards_do_not_cover_total")
    return out


def compute_own_keywords(store, cfg):
    """Which keywords do the user's sold assets share? Needs asset pages read with `stock_asset` (only the keywords shown)."""
    o = store.db.execute("SELECT obs_id FROM observation WHERE kind='portfolio' AND status='ok' ORDER BY read_at DESC LIMIT 1").fetchone()
    if not o:
        return []
    oid = o["obs_id"]
    ov = dict(store.db.execute("SELECT * FROM pf_overview WHERE obs_id=?", (oid,)).fetchone())
    cards = [dict(r) for r in store.db.execute("SELECT asset_id, downloads FROM pf_asset WHERE obs_id=?", (oid,))]
    covered = sum(c["downloads"] for c in cards if c["downloads"] is not None) == ov["downloads"]
    sold = sorted(c["asset_id"] for c in cards if c["downloads"])
    unsold = sorted(c["asset_id"] for c in cards if c["downloads"] is None) if covered else None
    sd = store.asset_details(sold)
    ud = store.asset_details(unsold) if unsold else []
    subj, ins = f"own:{ov['time_frame'] or 'unknown'}", [f"obs:{oid}"] + [f"obs:{d['obs_id']}" for d in sd + ud]
    cov = M.mk(cfg, "own_kw_coverage", subj, {"sold_total": len(sold), "sold_read": len(sd),
                                              "unsold_total": None if unsold is None else len(unsold),
                                              "unsold_read": None if unsold is None else len(ud)}, ins)
    ok = cfg["own_keywords"]
    n_sold = {}
    for d in sd:
        for k in set(d["keywords"]):
            n_sold[k] = n_sold.get(k, 0) + 1
    n_unsold = {}
    for d in ud:
        for k in set(d["keywords"]):
            n_unsold[k] = n_unsold.get(k, 0) + 1
    rows = sorted(((k, n, n_unsold.get(k, 0) if unsold is not None else None)
                   for k, n in n_sold.items() if n >= ok["min_sold_assets"]), key=lambda r: (-r[1], r[2] or 0, r[0]))[:ok["top_k"]]
    kws = M.mk(cfg, "own_kw_sold", subj, [list(r) for r in rows] or None, ins, "no_sold_asset_pages_read")
    for m in (cov, kws):
        store.put_metric(m)
    return [cov, kws]
