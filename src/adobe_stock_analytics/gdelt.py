"""Weekly news-volume intensity from the public GDELT DOC 2.0 API. No key, no login.
Measures how much news mentions a query, not stock-image demand. GDELT answers HTTP 429 when called too fast:
the call is paced and a 429 is reported, never retried in a loop."""
import gzip
import hashlib
import json
import subprocess
import time
import urllib.parse
from collections import defaultdict
from datetime import date, datetime, timedelta

API = "https://api.gdeltproject.org/api/v2/doc/doc?query={query}&mode=timelinevol&format=json&timespan={weeks}weeks"
USER_AGENT = "adobe-stock-analytics/0.1 (personal research tool)"
MIN_GAP_SECONDS = 6.0


class RateLimited(RuntimeError):
    pass


def http_get(url):
    r = subprocess.run(["curl", "-sS", "-m", "25", "-A", USER_AGENT, "-w", "\n%{http_code}", url], capture_output=True)
    if r.returncode:
        raise RuntimeError(f"GDELT request failed (curl exit {r.returncode}): {r.stderr.decode()[:200]}")
    body, _, code = r.stdout.rpartition(b"\n")
    if code.strip() == b"429":
        raise RateLimited("GDELT answered 429; wait before the next request")
    if code.strip() != b"200":
        raise RuntimeError(f"GDELT answered HTTP {code.decode().strip()}")
    return body


def weekly_means(points):
    """Mean of daily values per Monday-start week. Weeks with fewer than 7 days are dropped, not scaled."""
    days = defaultdict(dict)
    for p in points:
        d = datetime.strptime(p["date"][:8], "%Y%m%d").date()
        days[d - timedelta(days=d.weekday())][d] = float(p["value"])
    return {w.isoformat(): sum(v.values()) / 7 for w, v in sorted(days.items()) if len(v) == 7}


def _points(raw):
    doc = json.loads(raw)
    try:
        data = doc["timeline"][0]["data"]
        for p in data:
            p["date"], p["value"]
    except (KeyError, IndexError, TypeError):
        raise ValueError("unknown GDELT response shape; nothing stored")
    return data


def fetch(store, query, term=None, weeks=20, today=None, get=http_get, clock=time.time, sleep=time.sleep):
    last = store.get_state("gdelt_last_call")
    if last:
        wait = MIN_GAP_SECONDS - (clock() - float(last))
        if wait > 0:
            sleep(wait)
    store.set_state("gdelt_last_call", str(clock()))
    url = API.format(query=urllib.parse.quote(query, safe=""), weeks=weeks + 1)
    raw = get(url)
    sha = hashlib.sha256(raw).hexdigest()
    if store.db.execute("SELECT 1 FROM trend_point WHERE file_sha256=? LIMIT 1", (sha,)).fetchone():
        return {"file_sha256": sha, "points": 0, "already_imported": True}
    weekly = weekly_means(_points(raw))
    (store.dir / "raw").mkdir(exist_ok=True)
    with gzip.open(store.dir / "raw" / f"gdelt_{sha}.json.gz", "wb") as f:
        f.write(raw)
    name = term or f"gdelt: {query}"
    for week, v in weekly.items():
        store.db.execute("INSERT INTO trend_point VALUES(?,?,?,?,?,?)", (sha, name, "gdelt:volume_intensity", week, v, None))
    return {"file_sha256": sha, "points": len(weekly), "already_imported": False, "term": name, "url": url}
