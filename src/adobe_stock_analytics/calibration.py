"""Do low-supply niches sell better for this user? Joins own downloads per group with the supply rating of the group's keyword.

An association inside the user's own portfolio, not a forecast. Supply is measured now; the sales accumulated earlier.
Nothing here changes a band or a weight: the user edits the config after reading the tables.
"""
import csv
import hashlib
import io
from pathlib import Path

from . import metrics as M, portfolio as P


def import_group_keywords(store, path):
    """CSV group,keyword[,media_type]: the search phrase that stands for each of the user's groups."""
    raw = Path(path).read_bytes()
    sha = hashlib.sha256(raw).hexdigest()
    rd = csv.DictReader(io.StringIO(raw.decode("utf-8-sig")))
    cols = {(c or "").strip().lower(): c for c in (rd.fieldnames or [])}
    if not {"group", "keyword"} <= set(cols):
        raise ValueError("CSV needs group and keyword columns")
    n = 0
    for r in rd:
        g, k = (r[cols["group"]] or "").strip(), " ".join((r[cols["keyword"]] or "").split())
        media = (r.get(cols["media_type"]) or "").strip() if "media_type" in cols else ""
        if g and k:
            store.db.execute("INSERT OR REPLACE INTO group_keyword VALUES(?,?,?,?)", (g, k, media or "photo", sha))
            n += 1
    return {"file_sha256": sha, "mapped": n}


def compute_calibration(store, cfg):
    mapped = store.db.execute("SELECT grp, keyword, media_type, file_sha256 FROM group_keyword ORDER BY grp").fetchall()
    if not mapped:
        return []
    live = {}  # (group, name) -> metric from the latest own-dashboard observation
    for m in P.compute_live(store, cfg):
        if m["subject"].startswith("mapgroup:"):
            live[(m["subject"][9:].rsplit(" @ ", 1)[0], m["name"])] = m
    out, rows = [], []
    for g in mapped:
        kw = {m["name"]: m for m in M.compute_keyword(store, cfg, g["keyword"], g["media_type"])}
        a, d = live.get((g["grp"], "mg_assets")), live.get((g["grp"], "mg_downloads"))
        parts = [kw["results"], kw["supply_band"], kw["supply_rating"], a, d]
        ok = all(x is not None and x["value"] is not None for x in parts)
        value = None
        if ok:
            value = {"keyword": g["keyword"], "results": kw["results"]["value"], "band": kw["supply_band"]["value"],
                     "rating": kw["supply_rating"]["value"], "assets": a["value"], "downloads": d["value"],
                     "dl_per_asset": round(d["value"] / a["value"], 2) if a["value"] else None}
        m = M.mk(cfg, "cal_group", f"cal:{g['grp']}", value,
                 [f"metric:{x['metric_id']}" for x in parts if x] + [f"file:{g['file_sha256']}"])
        store.put_metric(m)
        out.append(m)
        if value:
            rows.append((m, value))
    floor = cfg["calibration"]["min_assets_per_bucket"]
    for name, key, prefix in (("cal_band", "band", "calband"), ("cal_rating", "rating", "calrating")):
        for label in sorted({v[key] for _, v in rows}):
            members = [(m, v) for m, v in rows if v[key] == label]
            assets, dls = sum(v["assets"] for _, v in members), sum(v["downloads"] for _, v in members)
            value = ({"groups": len(members), "assets": assets, "downloads": dls, "dl_per_asset": round(dls / assets, 2)}
                     if assets >= floor else None)
            m = M.mk(cfg, name, f"{prefix}:{label}", value, [f"metric:{x['metric_id']}" for x, _ in members], "too_few_assets")
            store.put_metric(m)
            out.append(m)
    return out
