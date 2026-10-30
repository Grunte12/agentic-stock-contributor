"""Append-only SQLite store. Raw payloads are kept gzipped next to the database."""
import gzip
import hashlib
import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path

from .config import canon

SCHEMA = """
CREATE TABLE IF NOT EXISTS observation(
  obs_id TEXT PRIMARY KEY, kind TEXT, url TEXT, params TEXT, read_at TEXT,
  parser_version TEXT, status TEXT, status_reason TEXT, raw_path TEXT, payload_sha256 TEXT);
CREATE TABLE IF NOT EXISTS search_count(
  obs_id TEXT PRIMARY KEY, keyword TEXT, media_type TEXT, ai_filter TEXT, order_by TEXT,
  results INTEGER, results_text TEXT, filters_on_page TEXT);
CREATE TABLE IF NOT EXISTS asset_row(
  obs_id TEXT, rank INTEGER, asset_id INTEGER, title TEXT, creator_id INTEGER,
  is_gentech INTEGER, category TEXT, w INTEGER, h INTEGER);
CREATE INDEX IF NOT EXISTS ix_asset_row_obs ON asset_row(obs_id);
CREATE TABLE IF NOT EXISTS asset_detail(
  obs_id TEXT PRIMARY KEY, asset_id INTEGER, title TEXT, keywords TEXT, keywords_shown INTEGER, keywords_total INTEGER);
CREATE TABLE IF NOT EXISTS trend_point(
  file_sha256 TEXT, term TEXT, geo TEXT, date TEXT, value REAL, flag TEXT);
CREATE TABLE IF NOT EXISTS portfolio_row(
  file_sha256 TEXT, asset_id TEXT, filename TEXT, grp TEXT, downloads INTEGER, earnings REAL, period TEXT);
CREATE TABLE IF NOT EXISTS pf_overview(
  obs_id TEXT PRIMARY KEY, downloads INTEGER, earnings REAL, all_count INTEGER, time_frame TEXT, sort_text TEXT);
CREATE TABLE IF NOT EXISTS pf_asset(obs_id TEXT, asset_id INTEGER, downloads INTEGER);
CREATE TABLE IF NOT EXISTS pf_name(obs_id TEXT, asset_id INTEGER, original_name TEXT, status TEXT, created_ms INTEGER);
CREATE INDEX IF NOT EXISTS ix_pf_name_obs ON pf_name(obs_id);
CREATE TABLE IF NOT EXISTS group_map(asset_id INTEGER PRIMARY KEY, grp TEXT, file_sha256 TEXT);
CREATE TABLE IF NOT EXISTS group_keyword(grp TEXT PRIMARY KEY, keyword TEXT, media_type TEXT, file_sha256 TEXT);
CREATE TABLE IF NOT EXISTS asset_date(asset_id INTEGER PRIMARY KEY, uploaded_on TEXT, file_sha256 TEXT);
CREATE TABLE IF NOT EXISTS trend_related(file_sha256 TEXT, seed TEXT, section TEXT, rank INTEGER, query TEXT, value_text TEXT);
CREATE TABLE IF NOT EXISTS metric(
  metric_id TEXT PRIMARY KEY, name TEXT, subject TEXT, value TEXT, status TEXT,
  inputs TEXT, metrics_version TEXT, computed_at TEXT);
CREATE TABLE IF NOT EXISTS job(
  job_id TEXT PRIMARY KEY, kind TEXT, params TEXT, url TEXT, state TEXT,
  created_at TEXT, dispatched_at TEXT, obs_id TEXT);
CREATE TABLE IF NOT EXISTS upload_outcome(
  obs_id TEXT, asset_id INTEGER, original_name TEXT, status TEXT, created_ms INTEGER, width INTEGER, height INTEGER,
  cause INTEGER, cause_label TEXT, outcome_class TEXT);
CREATE INDEX IF NOT EXISTS ix_upload_outcome_obs ON upload_outcome(obs_id);
CREATE TABLE IF NOT EXISTS state(key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS workflow_event(
  event_id TEXT PRIMARY KEY, recorded_at TEXT, phase TEXT, run TEXT, session_id TEXT, before_id TEXT, data TEXT);
"""


class _Rows:
    """Fully fetched result, so no cursor is touched outside the lock."""
    def __init__(self, rows, rowcount, lastrowid):
        self._rows, self._i = rows, 0
        self.rowcount, self.lastrowid = rowcount, lastrowid

    def fetchone(self):
        if self._i >= len(self._rows):
            return None
        self._i += 1
        return self._rows[self._i - 1]

    def fetchall(self):
        out, self._i = self._rows[self._i:], len(self._rows)
        return out

    def __iter__(self):
        return iter(self.fetchall())


class _LockedDB:
    """One sqlite connection shared by the bridge thread and the MCP thread.
    Python's sqlite3 does not serialize use across threads, so every call holds one lock."""
    def __init__(self, conn):
        self._c, self._lock = conn, threading.RLock()
        conn.row_factory = sqlite3.Row

    def execute(self, sql, params=()):
        with self._lock:
            cur = self._c.execute(sql, params)
            return _Rows(cur.fetchall(), cur.rowcount, cur.lastrowid)

    def executemany(self, sql, seq):
        with self._lock:
            cur = self._c.executemany(sql, seq)
            return _Rows([], cur.rowcount, cur.lastrowid)

    def executescript(self, script):
        with self._lock:
            self._c.executescript(script)


def utcnow():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class Store:
    def __init__(self, data_dir, now=utcnow):
        self.dir = Path(data_dir)
        (self.dir / "raw").mkdir(parents=True, exist_ok=True)
        self.db = _LockedDB(sqlite3.connect(self.dir / "intel.sqlite", check_same_thread=False, isolation_level=None))
        self.db.executescript(SCHEMA)
        self.now = now

    # --- state -------------------------------------------------------
    def get_state(self, key, default=None):
        r = self.db.execute("SELECT value FROM state WHERE key=?", (key,)).fetchone()
        return json.loads(r["value"]) if r else default

    def set_state(self, key, value):
        self.db.execute("INSERT OR REPLACE INTO state VALUES(?,?)", (key, json.dumps(value)))

    # --- observations --------------------------------------------------
    def add_observation(self, kind, url, params, payload, parsed):
        read_at = self.now()
        raw = canon(payload).encode()
        sha = hashlib.sha256(raw).hexdigest()
        obs_id = hashlib.sha256(f"{url}|{read_at}|{sha}".encode()).hexdigest()[:24]
        raw_path = self.dir / "raw" / f"{obs_id}.json.gz"
        raw_path.write_bytes(gzip.compress(raw, mtime=0))
        status = parsed["status"]
        self.db.execute(
            "INSERT OR IGNORE INTO observation VALUES(?,?,?,?,?,?,?,?,?,?)",
            (obs_id, kind, url, canon(params), read_at, parsed["parser_version"], status,
             parsed.get("reason"), str(raw_path.relative_to(self.dir)), sha))
        if status == "ok":
            if kind == "search":
                self.db.execute(
                    "INSERT OR IGNORE INTO search_count VALUES(?,?,?,?,?,?,?,?)",
                    (obs_id, params["keyword"], params["media_type"], params["ai_filter"], params["order"],
                     parsed["results"], parsed["results_text"], canon(parsed["filters_on_page"])))
            if kind in ("search", "contributor"):
                self.db.executemany(
                    "INSERT INTO asset_row VALUES(?,?,?,?,?,?,?,?,?)",
                    [(obs_id, r["rank"], r["asset_id"], r["title"], r["creator_id"],
                      None if r["is_gentech"] is None else int(r["is_gentech"]), r["category"], r["w"], r["h"])
                     for r in parsed["rows"]])
            if kind == "portfolio":
                self.db.execute("INSERT OR IGNORE INTO pf_overview VALUES(?,?,?,?,?,?)",
                                (obs_id, parsed["overview_downloads"], parsed["overview_earnings"], parsed["all_count"],
                                 parsed["time_frame"], parsed["sort_text"]))
                self.db.executemany("INSERT INTO pf_asset VALUES(?,?,?)",
                                    [(obs_id, r["asset_id"], r["downloads"]) for r in parsed["rows"]])
                self.db.executemany("INSERT INTO pf_name VALUES(?,?,?,?,?)",
                                    [(obs_id, n["asset_id"], n["original_name"], n["status"], n["created_ms"]) for n in parsed.get("named", [])])
            if kind == "outcomes":
                self.db.executemany(
                    "INSERT INTO upload_outcome VALUES(?,?,?,?,?,?,?,?,?,?)",
                    [(obs_id, r["asset_id"], r["original_name"], r["status"], r["created_ms"], r["width"], r["height"],
                      r["cause"], r["cause_label"], r["outcome_class"]) for r in parsed["rows"]])
            if kind == "asset":
                self.db.execute(
                    "INSERT OR IGNORE INTO asset_detail VALUES(?,?,?,?,?,?)",
                    (obs_id, parsed["asset_id"], parsed["title"], canon(parsed["keywords"]),
                     parsed["keywords_shown"], parsed["keywords_total"]))
        return obs_id

    def observation(self, obs_id):
        r = self.db.execute("SELECT * FROM observation WHERE obs_id=?", (obs_id,)).fetchone()
        return dict(r) if r else None

    def latest_outcomes(self):
        o = self.db.execute("SELECT obs_id, read_at FROM observation WHERE kind='outcomes' AND status='ok' "
                            "ORDER BY read_at DESC, obs_id DESC LIMIT 1").fetchone()
        if not o:
            return None
        rows = [dict(r) for r in self.db.execute("SELECT * FROM upload_outcome WHERE obs_id=? ORDER BY asset_id", (o["obs_id"],))]
        return {"obs_id": o["obs_id"], "read_at": o["read_at"], "rows": rows}

    def latest_search(self, keyword, media_type, ai_filter, order, as_of=None):
        q = ("SELECT s.*, o.read_at FROM search_count s JOIN observation o USING(obs_id) "
             "WHERE lower(s.keyword)=lower(?) AND s.media_type=? AND s.ai_filter=? AND s.order_by=? AND o.status='ok'")
        a = [keyword, media_type, ai_filter, order]
        if as_of:
            q += " AND o.read_at<=?"
            a.append(as_of)
        r = self.db.execute(q + " ORDER BY o.read_at DESC, s.obs_id DESC LIMIT 1", a).fetchone()
        return dict(r) if r else None

    def rows(self, obs_id):
        return [dict(r) for r in self.db.execute(
            "SELECT * FROM asset_row WHERE obs_id=? ORDER BY rank", (obs_id,))]

    def asset_details(self, asset_ids):
        out = []
        for aid in asset_ids:
            r = self.db.execute(
                "SELECT d.*, o.read_at FROM asset_detail d JOIN observation o USING(obs_id) "
                "WHERE d.asset_id=? ORDER BY o.read_at DESC LIMIT 1", (aid,)).fetchone()
            if r:
                d = dict(r)
                d["keywords"] = json.loads(d["keywords"])
                out.append(d)
        return out

    def latest_contributor(self, creator_id):
        r = self.db.execute(
            "SELECT obs_id, read_at FROM observation WHERE kind='contributor' AND status='ok' AND url LIKE ? "
            "ORDER BY read_at DESC LIMIT 1", (f"%/contributor/{int(creator_id)}/%",)).fetchone()
        return dict(r) if r else None

    # --- metrics ---------------------------------------------------------
    def put_metric(self, m):
        self.db.execute(
            "INSERT OR IGNORE INTO metric VALUES(?,?,?,?,?,?,?,?)",
            (m["metric_id"], m["name"], m["subject"], canon(m["value"]), m["status"],
             canon(m["inputs"]), m["metrics_version"], self.now()))

    def metric(self, metric_id):
        r = self.db.execute("SELECT * FROM metric WHERE metric_id=?", (metric_id,)).fetchone()
        return _metric_row(r) if r else None

    def metrics_for(self, subject=None):
        q, a = "SELECT * FROM metric", []
        if subject:
            q += " WHERE subject=?"
            a.append(subject)
        return [_metric_row(r) for r in self.db.execute(q + " ORDER BY subject, name, metric_id", a)]


def _metric_row(r):
    d = dict(r)
    d["value"] = json.loads(d["value"])
    d["inputs"] = json.loads(d["inputs"])
    return d
