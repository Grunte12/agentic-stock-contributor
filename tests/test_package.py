import json
import struct
import tempfile
import unittest
from pathlib import Path

from helpers import CFG  # noqa: F401  (adds src to sys.path)
from adobe_stock_analytics import package as P
from adobe_stock_analytics.upload_stage import sha256_file


def fake_jpeg(path, w, h, pad=0):
    sof = b"\xff\xc0" + struct.pack(">HBHHB", 11, 8, h, w, 1) + b"\x01\x11\x00"
    Path(path).write_bytes(b"\xff\xd8" + b"\xff\xe0\x00\x04ab" + sof + b"x" * pad + b"\xff\xd9")


REG = {"scenarios": {
    "cookie-tray-flatlay": {"title": "Cookie tray flatlay", "category": 7, "keywords": ["cookie", "tray", "flatlay", "baking", "christmas"],
                            "prompt": "Photorealistic flatlay of a cookie tray. No text, no logos, no watermark."},
    "wrapped-gifts-tree": {"title": "Wrapped gifts by a tree", "category": 5, "keywords": ["gift", "tree", "wrapped", "holiday", "cozy"],
                           "prompt": "Photorealistic wrapped gifts beside a decorated tree in a living room."}}}


class PackageTests(unittest.TestCase):
    def setUp(self):
        self.d = Path(tempfile.mkdtemp())
        self.pkg = self.d / "PKG"
        self.pkg.mkdir()
        fake_jpeg(self.pkg / "01_cookie-tray-flatlay.jpg", 2400, 1800)
        fake_jpeg(self.pkg / "02_wrapped-gifts-tree.jpg", 3000, 2000, pad=10)
        self.reg = self.d / "reg.json"
        self.reg.write_text(json.dumps(REG))

    def names(self, folder=None):
        return {f["name"]: f["sha256"] for f in P.check_images(folder or self.pkg)["files"]}

    def test_jpeg_size(self):
        self.assertEqual(P.jpeg_size(self.pkg / "01_cookie-tray-flatlay.jpg"), (2400, 1800))
        (self.d / "x.jpg").write_bytes(b"notajpeg")
        self.assertIsNone(P.jpeg_size(self.d / "x.jpg"))

    def test_check_images_flags_small_and_duplicates(self):
        self.assertTrue(P.check_images(self.pkg)["ok"])
        fake_jpeg(self.pkg / "03_small.jpg", 1000, 1000)
        fake_jpeg(self.pkg / "04_dup.jpg", 2400, 1800)
        r = P.check_images(self.pkg)
        self.assertFalse(r["ok"])
        self.assertTrue(any("03_small.jpg" in p and "MP" in p for p in r["problems"]))
        self.assertTrue(any("04_dup.jpg" in p and "duplicate" in p for p in r["problems"]))

    def test_lint_registry(self):
        self.assertTrue(P.lint_registry(self.reg)["ok"])
        bad = json.loads(json.dumps(REG))
        bad["scenarios"]["cookie-tray"] = dict(bad["scenarios"]["cookie-tray-flatlay"])
        bad["scenarios"]["wrapped-gifts-tree"]["prompt"] = "A tree in the style of a famous painter, in a living room."
        p = self.d / "bad.json"
        p.write_text(json.dumps(bad))
        r = P.lint_registry(p)
        self.assertFalse(r["ok"])
        self.assertTrue(any("contained in" in x for x in r["problems"]))
        self.assertTrue(any("in the style of" in x for x in r["problems"]))

    def test_negation_does_not_hide_style_phrase(self):
        bad = json.loads(json.dumps(REG))
        bad["scenarios"]["wrapped-gifts-tree"]["prompt"] = "A tree, no people, in the style of Van Gogh, in a living room."
        p = self.d / "bad2.json"
        p.write_text(json.dumps(bad))
        self.assertTrue(any("in the style of" in x for x in P.lint_registry(p)["problems"]))

    def test_scenario_match_needs_word_boundaries(self):
        reg = {"scenarios": {"tea": {}, "teapot-shelf": {}}}
        m, probs = P.match_scenarios(reg, ["03_steam.jpg", "04_teapot-shelf.jpg", "05_tea.jpg"])
        self.assertEqual(m, {"04_teapot-shelf.jpg": "teapot-shelf", "05_tea.jpg": "tea"})
        self.assertEqual(len(probs), 1)

    def test_more_than_one_wave_is_not_ready(self):
        csv_path = self.pkg / "adobe_stock_upload.csv"
        P.build_csv(self.reg, self.pkg, csv_path)
        names = self.names()
        qc = self.d / "qc.json"
        qc.write_text(json.dumps({"reviewer": "r", "mode": "user", "pass": sorted(names), "fail": []}))
        r = P.prepare_plan(self.pkg, csv_path, qc, self.d / "p.json", [], max_files=1)
        self.assertFalse(r["ready_for_upload"])
        self.assertTrue(any("wave" in f for f in r["failures"]))

    def test_full_prepare_flow(self):
        csv_path = self.pkg / "adobe_stock_upload.csv"
        res = P.build_csv(self.reg, self.pkg, csv_path)
        self.assertTrue(res["ok"], res)
        names = self.names()
        qc = self.d / "qc.json"
        qc.write_text(json.dumps({"reviewer": "test-reviewer", "mode": "single-pass", "pass": sorted(names), "fail": [], "sha256": names}))
        plan = self.d / "plan.json"
        r = P.prepare_plan(self.pkg, csv_path, qc, plan, ["DO_NOT_UPLOAD"])
        self.assertTrue(r["ok"], r)
        data = json.loads(plan.read_text())
        self.assertTrue(data["ready_for_upload"])
        self.assertEqual(len(data["package_digest"]), 64)
        self.assertEqual(data["csv"][0]["sha256"], sha256_file(csv_path))

    def test_plan_is_accepted_by_stage_loader(self):
        from adobe_stock_analytics import upload_stage as U
        csv_path = self.pkg / "adobe_stock_upload.csv"
        P.build_csv(self.reg, self.pkg, csv_path)
        names = self.names()
        qc = self.d / "qc.json"
        qc.write_text(json.dumps({"reviewer": "r", "mode": "user", "pass": sorted(names), "fail": []}))
        plan = self.d / "plan.json"
        P.prepare_plan(self.pkg, csv_path, qc, plan, [])
        on = {**CFG, "upload_stage": {**CFG["upload_stage"], "enabled": True}}
        out = U.load_plan(plan, on)
        self.assertEqual(len(out["files"]), 2)

    def test_qc_gate_blocks(self):
        names = self.names()
        qc = self.d / "qc.json"
        qc.write_text(json.dumps({"reviewer": "", "mode": "bogus", "pass": [sorted(names)[0]], "fail": [sorted(names)[1]]}))
        r = P.check_qc(qc, names)
        self.assertFalse(r["ok"])
        self.assertGreaterEqual(len(r["problems"]), 4)

    def test_qc_detects_changed_bytes(self):
        names = self.names()
        qc = self.d / "qc.json"
        qc.write_text(json.dumps({"reviewer": "r", "mode": "user", "pass": sorted(names), "fail": [], "sha256": {sorted(names)[0]: "0" * 64}}))
        self.assertTrue(any("changed after review" in p for p in P.check_qc(qc, names)["problems"]))

    def test_protected_folder_blocks_plan(self):
        prot = self.d / "DO_NOT_UPLOAD"
        prot.mkdir()
        fake_jpeg(prot / "01_cookie-tray-flatlay.jpg", 2400, 1800)
        P.build_csv(self.reg, prot, prot / "a.csv")
        names = self.names(prot)
        qc = self.d / "qc.json"
        qc.write_text(json.dumps({"reviewer": "r", "mode": "user", "pass": sorted(names), "fail": []}))
        r = P.prepare_plan(prot, prot / "a.csv", qc, self.d / "p.json", ["DO_NOT_UPLOAD"])
        self.assertFalse(r["ready_for_upload"])
        self.assertTrue(any("protected" in f for f in r["failures"]))

    def test_generation_decisions_need_the_user(self):
        d = self.d / "gd.json"
        d.write_text(json.dumps({"decisions": {}}))
        r = P.check_decisions(d)
        self.assertFalse(r["ok"])
        self.assertEqual(len(r["open"]), len(P.GENERATION_QUESTIONS))
        full = {k: {"value": "x", "decided_by": "agent"} for k in P.GENERATION_QUESTIONS}
        d.write_text(json.dumps({"decisions": full}))
        r = P.check_decisions(d)
        self.assertFalse(r["ok"])
        self.assertGreaterEqual(len(r["problems"]), len(P.GENERATION_QUESTIONS))
        full = {k: {"value": "x", "decided_by": "user", "asked_on": "2026-10-15"} for k in P.GENERATION_QUESTIONS}
        full["go_ahead"]["value"] = full["terms"]["value"] = "yes"
        full["scenario_count"]["value"] = full["variants"]["value"] = full["canary"]["value"] = 2
        full["spend"]["value"] = 0
        d.write_text(json.dumps({"decisions": full}))
        self.assertTrue(P.check_decisions(d)["ok"], P.check_decisions(d))
        for bad in (False, 0, [], {}, " ", "Unknown", None):
            full["provider"]["value"] = bad
            d.write_text(json.dumps({"decisions": full}))
            self.assertFalse(P.check_decisions(d)["ok"], bad)
        full["provider"]["value"] = "x"
        full["go_ahead"]["value"] = "no"
        d.write_text(json.dumps({"decisions": full}))
        self.assertFalse(P.check_decisions(d)["ok"])
        full["go_ahead"]["value"] = "yes"
        full["size"]["asked_on"] = ""
        d.write_text(json.dumps({"decisions": full}))
        self.assertFalse(P.check_decisions(d)["ok"])
        def one(key, value, asked="2026-10-15"):
            f = {k: {"value": "x", "decided_by": "user", "asked_on": "2026-10-15"} for k in P.GENERATION_QUESTIONS}
            f["go_ahead"]["value"] = f["terms"]["value"] = "yes"
            f["scenario_count"]["value"] = f["variants"]["value"] = f["canary"]["value"] = 2
            f[key] = {"value": value, "decided_by": " USER ", "asked_on": asked}
            d.write_text(json.dumps({"decisions": f}))
            return P.check_decisions(d)["ok"]
        self.assertTrue(one("canary", "2"))
        self.assertTrue(one("go_ahead", True))
        self.assertTrue(one("spend", 0))
        for key, bad in (("canary", "0"), ("canary", " 0 "), ("canary", "-1"), ("canary", 0.5), ("canary", float("inf")),
                         ("spend", -5), ("spend", float("nan")), ("provider", "I do not know"), ("provider", "not sure"),
                         ("terms", "no"), ("go_ahead", "no")):
            self.assertFalse(one(key, bad), (key, bad))
        self.assertFalse(one("provider", "x", "2026-13-45"))
        self.assertFalse(one("provider", "x", "2099-01-01"))
        for raw in ('{"decisions": []}', "[]", "{bad"):
            d.write_text(raw)
            with self.assertRaises(ValueError):
                P.check_decisions(d)


if __name__ == "__main__":
    unittest.main()
