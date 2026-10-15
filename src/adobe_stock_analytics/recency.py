"""Suggest recency.min_asset_id from the user's own upload dates (asset ids rise with time in this account).

Linear interpolation between the two own assets that bracket the target date. It never extrapolates and never edits
the config: the user copies the value in, which changes the metric ids on purpose.
"""
import csv
import hashlib
import io
from datetime import date, timedelta
from pathlib import Path

from . import metrics as M


def import_upload_dates(store, path):
    """CSV asset_id,uploaded_on (YYYY-MM-DD): upload dates from the user's own records (not Adobe acceptance dates)."""
    raw = Path(path).read_bytes()
    sha = hashlib.sha256(raw).hexdigest()
    rd = csv.DictReader(io.StringIO(raw.decode("utf-8-sig")))
    cols = {(c or "").strip().lower(): c for c in (rd.fieldnames or [])}
    if not {"asset_id", "uploaded_on"} <= set(cols):
        raise ValueError("CSV needs asset_id and uploaded_on columns")
    n = 0
    for r in rd:
        a, d = (r[cols["asset_id"]] or "").strip(), (r[cols["uploaded_on"]] or "").strip()
        try:
            date.fromisoformat(d)
        except ValueError:
            continue  # a bad date is skipped, never guessed
        if a.isdigit():
            store.db.execute("INSERT OR REPLACE INTO asset_date VALUES(?,?,?)", (int(a), d, sha))
            n += 1
    return {"file_sha256": sha, "dated": n}


def compute_recency_cut(store, cfg, as_of):
    rc = cfg["recency"]
    rows = [(date.fromisoformat(r["uploaded_on"]), r["asset_id"], r["file_sha256"]) for r in
            store.db.execute("SELECT asset_id, uploaded_on, file_sha256 FROM asset_date ORDER BY uploaded_on, asset_id")]
    if not rows:
        return []
    target = date.fromisoformat(as_of) - timedelta(days=rc["window_days"])
    ins = [f"date:{as_of}"] + [f"file:{s}" for s in sorted({r[2] for r in rows})]
    value, reason = None, "no_input"
    if len(rows) < rc["min_anchors"]:
        reason = "too_few_anchors"
    elif any(b[1] < a[1] for a, b in zip(rows, rows[1:])):
        reason = "ids_not_monotonic"
    elif not rows[0][0] <= target <= rows[-1][0]:
        reason = "outside_anchor_range"
    else:
        lo = max((r for r in rows if r[0] <= target), key=lambda r: (r[0], r[1]))
        hi = min((r for r in rows if r[0] >= target), key=lambda r: (r[0], r[1]))
        span = (hi[0] - lo[0]).days
        cut = lo[1] if span == 0 else lo[1] + round((hi[1] - lo[1]) * (target - lo[0]).days / span)
        value = {"suggested_min_asset_id": cut, "target_date": target.isoformat(), "anchors": len(rows),
                 "current_min_asset_id": rc["min_asset_id"]}
    m = M.mk(cfg, "recency_cut_suggestion", "calrecency:cut", value, ins, reason)
    store.put_metric(m)
    return [m]
