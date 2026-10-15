#!/usr/bin/env python3
"""Dev driver: runs queued jobs through OpenCLI in the user's Chrome instead of the extension.

Uses the same Queue (pacing, daily cap, stop rules) and the same extension/extract.js, so it checks everything
except the extension glue. Read-only: open + eval only. Usage:
  python3 scripts/live_via_opencli.py scans.json   # [{"kind":"search","params":{...}}, ...]
"""
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from adobe_stock_analytics.app import App  # noqa: E402

SRC = "\n".join((ROOT / "extension" / "extract.js").read_text().splitlines()[:-1])
SESSION = "mi-live"


def oc(*args, timeout=90):
    r = subprocess.run(["opencli", "browser", SESSION, *args], capture_output=True, text=True, timeout=timeout)
    return r.stdout.splitlines()[0] if r.stdout.strip() else ""


def read(job):
    oc("open", job["url"])
    last = None
    for _ in range(8):
        time.sleep(3)
        line = oc("eval", f"(()=>{{{SRC}\nreturn JSON.stringify(intelExtract({json.dumps(job['kind'])}))}})()")
        try:
            last = json.loads(line)
        except ValueError:
            continue
        ready = last.get("page_state") or (last.get("keywords") if job["kind"] == "asset" else last.get("cards") if job["kind"] == "portfolio" else last.get("rows"))
        if ready:
            break
    return last


def main(path):
    app = App()
    ids = [app.queue.enqueue(j["kind"], j["params"]) for j in json.loads(Path(path).read_text())]
    print("queued", len(ids), flush=True)
    while True:
        states = [app.queue.job(i)["state"] for i in ids]
        if all(s in ("done", "failed") for s in states) or app.queue.stop_state():
            break
        job, why = app.queue.next_job()
        if not job:
            time.sleep(2)
            continue
        res = app.queue.complete(job["job_id"], read(job))
        print(job["kind"], job["url"][-70:], res, flush=True)
    oc("close")
    print("final", app.queue.status(), flush=True)


if __name__ == "__main__":
    main(sys.argv[1])
