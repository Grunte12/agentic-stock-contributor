"""Import a Google Trends CSV exported by the user."""
import csv
import hashlib
import io
import re
from pathlib import Path


def import_trends(store, path):
    raw = Path(path).read_bytes()
    sha = hashlib.sha256(raw).hexdigest()
    if store.db.execute("SELECT 1 FROM trend_point WHERE file_sha256=? LIMIT 1", (sha,)).fetchone():
        return {"file_sha256": sha, "points": 0, "already_imported": True}
    rows = list(csv.reader(io.StringIO(raw.decode("utf-8-sig"))))
    head = next((i for i, r in enumerate(rows) if r and r[0].strip() in ("Week", "Day", "Month", "Time") and len(r) > 1), None)
    if head is None:
        raise ValueError("no Trends header row (Week/Day/Month/Time) found")
    terms = []
    for h in rows[head][1:]:
        m = re.match(r"^(.*?):\s*\((.*)\)\s*$", h.strip())
        terms.append((m.group(1).strip(), m.group(2).strip()) if m else (h.strip(), ""))
    n = 0
    for r in rows[head + 1:]:
        if len(r) < 2 or not r[0].strip():
            continue
        for (term, geo), cell in zip(terms, r[1:]):
            cell = cell.strip()
            flag = None
            if cell == "<1":
                val, flag = None, "lt1"
            else:
                try:
                    val = float(cell)
                except ValueError:
                    val, flag = None, "unparsed"
            store.db.execute("INSERT INTO trend_point VALUES(?,?,?,?,?,?)", (sha, term, geo, r[0].strip(), val, flag))
            n += 1
    return {"file_sha256": sha, "points": n, "already_imported": False, "terms": [t for t, _ in terms]}
