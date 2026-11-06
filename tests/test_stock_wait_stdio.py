import json
import queue
import tempfile
import threading
import time
import unittest

from helpers import CFG
from adobe_stock_analytics.app import App
from adobe_stock_analytics import mcp_server


class Input:
    def __init__(self):
        self.lines = queue.Queue()

    def __iter__(self):
        while True:
            line = self.lines.get()
            if line is None:
                return
            yield json.dumps(line)


class Output:
    def __init__(self):
        self.lines = queue.Queue()

    def write(self, data):
        self.lines.put(json.loads(data))

    def flush(self):
        pass


class WaitStdioTests(unittest.TestCase):
    def setUp(self):
        self.app = App(data_dir=tempfile.mkdtemp(), cfg=CFG)
        self.job = self.app.queue.enqueue("search", {"keyword": "synthetic"})
        self.input, self.output = Input(), Output()
        self.server = threading.Thread(target=mcp_server.serve, args=(self.app, self.input, self.output))
        self.server.start()

    def tearDown(self):
        self.input.lines.put(None)
        self.server.join(2)
        self.assertFalse(self.server.is_alive())

    def send(self, mid, method, params=None):
        msg = {"jsonrpc": "2.0", "method": method, "params": params or {}}
        if mid is not None:
            msg["id"] = mid
        self.input.lines.put(msg)

    def wait_request(self, mid, seconds=3):
        self.send(mid, "tools/call", {"name": "stock_wait", "arguments": {"job_ids": [self.job], "timeout_seconds": seconds}})

    def test_wait_does_not_block_ping_and_cancel_does_not_mutate_job(self):
        self.wait_request(1)
        self.send(2, "ping")
        self.assertEqual(self.output.lines.get(timeout=1)["id"], 2)
        self.send(None, "notifications/cancelled", {"requestId": 1})
        self.send(3, "ping")
        self.assertEqual(self.output.lines.get(timeout=1)["id"], 3)
        with self.assertRaises(queue.Empty):
            self.output.lines.get(timeout=0.2)
        self.assertEqual(self.app.queue.job(self.job)["state"], "queued")
        self.assertIsNone(self.app.queue.stop_state())

    def test_fractional_numeric_id_is_supported_and_cancelled(self):
        self.wait_request(1.5, 1)
        self.send(None, "notifications/cancelled", {"requestId": 1.5})
        self.send(2, "ping")
        self.assertEqual(self.output.lines.get(timeout=1)["id"], 2)
        with self.assertRaises(queue.Empty):
            self.output.lines.get(timeout=1.2)

    def test_boolean_cancel_id_does_not_cancel_numeric_request(self):
        self.wait_request(1, 1)
        self.send(None, "notifications/cancelled", {"requestId": True})
        self.assertEqual(self.output.lines.get(timeout=2)["id"], 1)

    def test_malformed_cancel_does_not_terminate_server(self):
        self.wait_request(11, 1)
        self.input.lines.put({"jsonrpc": "2.0", "method": "notifications/cancelled", "params": ["bad"]})
        self.send(12, "ping")
        self.assertEqual(self.output.lines.get(timeout=1)["id"], 12)
        self.assertEqual(self.output.lines.get(timeout=2)["id"], 11)

    def test_duplicate_inflight_id_is_rejected(self):
        self.wait_request(10)
        self.send(10, "ping")
        response = self.output.lines.get(timeout=1)
        self.assertIsNone(response["id"])
        self.assertIn("duplicate", response["error"]["message"])
        self.send(None, "notifications/cancelled", {"requestId": 10})

    def test_wait_returns_for_terminal_and_stop(self):
        self.app.store.db.execute("UPDATE job SET state='done' WHERE job_id=?", (self.job,))
        self.wait_request(4)
        response = self.output.lines.get(timeout=1)
        self.assertEqual(response["id"], 4)
        self.assertEqual(json.loads(response["result"]["content"][0]["text"])["state"], "completed")
        self.app.store.db.execute("UPDATE job SET state='queued' WHERE job_id=?", (self.job,))
        self.app.queue.stop("captcha")
        self.wait_request(5)
        response = self.output.lines.get(timeout=1)
        self.assertEqual(json.loads(response["result"]["content"][0]["text"])["state"], "stopped")

    def test_wait_returns_after_job_completes_without_dispatching(self):
        self.wait_request(8)
        self.send(9, "ping")
        self.assertEqual(self.output.lines.get(timeout=1)["id"], 9)
        self.app.store.db.execute("UPDATE job SET state='done' WHERE job_id=?", (self.job,))
        response = self.output.lines.get(timeout=2)
        self.assertEqual(response["id"], 8)
        self.assertEqual(json.loads(response["result"]["content"][0]["text"])["state"], "completed")
        self.assertEqual(self.app.queue.pages_today(), 0)

    def test_pending_waits_are_bounded(self):
        for mid in range(20, 29):
            self.wait_request(mid, 120)
        response = self.output.lines.get(timeout=2)
        self.assertEqual(response["id"], 28)
        self.assertIn("capacity", response["error"]["message"])
        for mid in range(20, 28):
            self.send(None, "notifications/cancelled", {"requestId": mid})
        self.send(29, "ping")
        self.assertEqual(self.output.lines.get(timeout=1)["id"], 29)
        self.assertEqual(self.app.queue.job(self.job)["state"], "queued")

    def test_timeout_and_eof_end_waits(self):
        self.wait_request(6, 1)
        self.assertEqual(self.output.lines.get(timeout=2)["id"], 6)
        self.wait_request(7, 120)
        self.input.lines.put(None)
        self.server.join(2)
        self.assertFalse(self.server.is_alive())
        self.assertEqual(self.app.queue.job(self.job)["state"], "queued")
