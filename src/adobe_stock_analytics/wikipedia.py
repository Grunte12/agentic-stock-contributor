"""Weekly Wikipedia pageviews as an attention series. Public API, no login. Measures interest in a topic, not stock-image demand."""
import gzip
import hashlib
import json
import subprocess
import urllib.parse
from collections import defaultdict
from datetime import date, datetime, timedelta

API = ("https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/"
       "{lang}.wikipedia/all-access/user/{article}/daily/{start}/{end}")
USER_AGENT = "adobe-stock-analytics/0.1 (personal research tool)"


def http_get(url):
    """curl uses the system trust store; the python.org build of Python has none until its certificates are installed."""
    r = subprocess.run(["curl", "-sS", "--fail", "-m", "20", "-A", USER_AGENT, url], capture_output=True)
    if r.returncode:
        raise RuntimeError(f"pageviews request failed (curl exit {r.returncode}): {r.stderr.decode()[:200]}")
    return r.stdout


def weekly_sums(items):
    """Sum daily views into Monday-start weeks. Weeks with fewer than 7 days are dropped, not scaled."""
    days = defaultdict(dict)
    for it in items:
        d = datetime.strptime(it["timestamp"][:8], "%Y%m%d").date()
        days[d - timedelta(days=d.weekday())][d] = it["views"]
    return {w.isoformat(): sum(v.values()) for w, v in sorted(days.items()) if len(v) == 7}


def fetch(store, article, term=None, lang="en", weeks=20, today=None, get=http_get):
    today = today or date.today()
    end = today - timedelta(days=1)
    start = end - timedelta(weeks=weeks + 1)
    title = urllib.parse.quote(article.replace(" ", "_"), safe="")
    url = API.format(lang=lang, article=title, start=start.strftime("%Y%m%d"), end=end.strftime("%Y%m%d"))
    raw = get(url)
    sha = hashlib.sha256(raw).hexdigest()
    if store.db.execute("SELECT 1 FROM trend_point WHERE file_sha256=? LIMIT 1", (sha,)).fetchone():
        return {"file_sha256": sha, "points": 0, "already_imported": True}
    weekly = weekly_sums(json.loads(raw)["items"])
    (store.dir / "raw").mkdir(exist_ok=True)
    with gzip.open(store.dir / "raw" / f"wikipedia_{sha}.json.gz", "wb") as f:
        f.write(raw)
    name = term or article
    for week, views in weekly.items():
        store.db.execute("INSERT INTO trend_point VALUES(?,?,?,?,?,?)", (sha, name, f"wikipedia:{lang}", week, float(views), None))
    return {"file_sha256": sha, "points": len(weekly), "already_imported": False, "term": name, "url": url}
