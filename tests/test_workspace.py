import tempfile
import unittest
from datetime import date, datetime, timezone
from pathlib import Path

import helpers  # noqa: F401  (puts src on the path)
from adobe_stock_analytics import workspace as W
from adobe_stock_analytics.config import ROOT

NOW = datetime(2026, 10, 17, 12, 0, tzinfo=timezone.utc)
DAY = date(2026, 10, 17)


class WorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.ws = self.tmp / "workspace"
        W.init(self.ws)
        self.ev = self.ws / "runs" / "R1" / "REPORT.md"
        self.ev.parent.mkdir(parents=True)
        self.ev.write_text("report\n")

    def lint(self):
        return W.lint(self.ws, agents=self.tmp / "none.md", now=NOW)

    def test_init_creates_missing_and_never_overwrites(self):
        (self.ws / "STATE.md").write_text("mine\n")
        (self.ws / "LOG.md").unlink()
        r = W.init(self.ws)
        self.assertEqual(r["created"], ["LOG.md"])
        self.assertEqual((self.ws / "STATE.md").read_text(), "mine\n")

    def test_fresh_templates_pass_lint(self):
        r = self.lint()
        self.assertTrue(r["ok"], r)

    def test_lesson_needs_existing_evidence(self):
        with self.assertRaises(ValueError):
            W.add("x", ws=self.ws)
        with self.assertRaises(ValueError):
            W.add("x", evidence=[str(self.ws / "missing.md")], ws=self.ws)

    def test_add_vote_retire_round_trip(self):
        a = W.add("Plain resize beats Real-ESRGAN on wood grain", evidence=[str(self.ev)], tags=["upscale"], ws=self.ws, today=DAY)
        self.assertEqual(a["id"], "L-001")
        b = W.add("Second lesson", evidence=[str(self.ev)], ws=self.ws, today=DAY)
        self.assertEqual(b["id"], "L-002")
        other = self.ws / "runs" / "R2.md"
        other.write_text("r2\n")
        v = W.vote("L-001", "harmful", str(other), ws=self.ws)
        self.assertIn("| +0 -1 |", v["line"])
        self.assertIn(str(other), v["line"])
        r = self.lint()
        self.assertTrue(r["ok"], r)
        self.assertTrue(any("L-001" in w and "harmful" in w for w in r["warnings"]))
        t = W.retire("L-001", "wrong after outcome", ws=self.ws, today=DAY)
        self.assertIn("retired 2026-10-17", t["line"])
        text = (self.ws / "PLAYBOOK.md").read_text()
        self.assertGreater(text.index("[L-001]"), text.index("## Retired"))
        self.assertTrue(self.lint()["ok"])
        with self.assertRaises(ValueError):
            W.retire("L-001", "again", ws=self.ws)
        self.assertEqual(W.add("Third", evidence=[str(self.ev)], ws=self.ws)["id"], "L-003")
        W.retire("L-003", "superseded", ws=self.ws)
        self.assertEqual(W.add("Fourth", evidence=[str(self.ev)], ws=self.ws)["id"], "L-004")
        self.assertTrue(self.lint()["ok"])

    def test_choice_needs_source_and_rejects_duplicates_and_pipes(self):
        with self.assertRaises(ValueError):
            W.add("Keep upload switches on", kind="choice", ws=self.ws)
        c = W.add("Keep upload switches on", kind="choice", source="chat 2026-10-16", ws=self.ws, today=DAY)
        self.assertEqual(c["id"], "C-001")
        with self.assertRaises(ValueError):
            W.add("keep upload switches ON", kind="choice", source="chat", ws=self.ws)
        with self.assertRaises(ValueError):
            W.add("a | b", kind="choice", source="chat", ws=self.ws)

    def test_lint_catches_hand_edits(self):
        pb = self.ws / "PLAYBOOK.md"
        pb.write_text(pb.read_text().replace("## Lessons\n", "## Lessons\n- [L-001] hand written lesson\n"))
        log = self.ws / "LOG.md"
        log.write_text(log.read_text() + "## [2026-10-17] qc | R1 | claude\n- x\n## [2026-10-16] qc | R1 | codex\n- y\n## bad header\n")
        st = self.ws / "STATE.md"
        st.write_text(st.read_text().replace("## Stops and blockers", "- not a decision\n\n## Stops and blockers"))
        r = self.lint()
        self.assertFalse(r["ok"])
        joined = " ".join(r["problems"])
        for needle in ("tool's format", "out of date order", "header must be", "decision line"):
            self.assertIn(needle, joined)

    def test_stale_claim_warns(self):
        st = self.ws / "STATE.md"
        st.write_text(st.read_text().replace("Working now: none", "Working now: codex since 2026-10-16 08:00 UTC on R1 qc"))
        r = self.lint()
        self.assertTrue(r["ok"], r)
        self.assertTrue(any("older than" in w for w in r["warnings"]))

    def test_agents_md_stays_a_short_map(self):
        n = len((ROOT / "AGENTS.md").read_text(encoding="utf-8").splitlines())
        self.assertLessEqual(n, W.AGENTS_MAX_LINES)


if __name__ == "__main__":
    unittest.main()
