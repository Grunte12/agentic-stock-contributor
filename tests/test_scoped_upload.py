import unittest
from helpers import CFG, new_store

from adobe_stock_analytics import parsers
from adobe_stock_analytics.queue import Queue
from helpers import CFG, new_store


def row(aid, name):
    return {"asset_id": aid, "original_name": name}


def side(items):
    return {"all_count": len(items), "items": items}


class ScopedTests(unittest.TestCase):
    def test_stage_requires_exact_additions_and_preserves_existing(self):
        old = row(1, "other.jpg")
        new = row(2, "a.jpg")
        payload = {"before": side([old]), "after": side([old, new])}
        self.assertEqual(parsers.parse_upload_stage(payload, ["a.jpg"], True)["target_ids"], {"a.jpg": 2})
        for before, after in [(side([new]), side([new, row(3, "a.jpg")])),
                              (side([old]), side([new, row(3, "other.jpg")])),
                              (side([old]), {"all_count": 2, "items": [new]}),
                              ({"all_count": 0}, {"all_count": 1})]:
            self.assertNotEqual(parsers.parse_upload_stage({"before": before, "after": after}, ["a.jpg"], True)["status"], "ok")

    def test_metadata_exact_ids_and_flags(self):
        target = {**row(2, "a.jpg"), "keyword_count": 5, "ai_checked": True, "include_checked": True, "fictional_checked": True, "title": "A title", "category": "Business", "people_prompt_visible": False, "keywords": "One, TWO, three, four, five"}
        payload = {"after": {**side([row(1, "other.jpg"), row(2, "a.jpg")]), "targets": [target]}}
        expected = {"a.jpg": {"title": "A title", "category": "Business", "keywords": ["one", "two", "three", "four", "five"]}}
        parse = lambda ids: parsers.parse_upload_metadata(payload, 1, {"people_property_fictional": True}, ["a.jpg"], ids, expected)
        self.assertEqual(parse({"a.jpg": 2})["status"], "ok")
        self.assertNotEqual(parse({"a.jpg": 3})["status"], "ok")
        target["category"] = "Food"
        self.assertEqual(parse({"a.jpg": 2})["reason"], "metadata_content_mismatch")
        target["category"] = "Business"
        target["title"] = "Wrong"
        self.assertEqual(parse({"a.jpg": 2})["reason"], "metadata_content_mismatch")
        target["title"] = "A title"
        target["keywords"] = "two, one, three, four, five"
        self.assertEqual(parse({"a.jpg": 2})["reason"], "metadata_content_mismatch")
        target["keywords"] = "one, two, three, four, five"
        target["include_checked"] = False
        self.assertNotEqual(parse({"a.jpg": 2})["status"], "ok")
        self.assertNotEqual(parsers.parse_upload_metadata({"after": {"all_count": 1}}, 1, {}, ["a.jpg"])["status"], "ok")

    def test_old_extension_cannot_receive_scoped_job(self):
        cfg = {**CFG, "upload_stage": {**CFG["upload_stage"], "enabled": True}}
        q = Queue(new_store(), cfg, clock=lambda: 1700000000, rng=lambda: 0)
        q.enqueue("upload_stage", {"package_digest": "x", "files": [], "scope_names": ["a.jpg"]})
        self.assertEqual(q.next_job("0.10.7"), (None, "extension_upgrade_required"))
        self.assertEqual(q.next_job(None), (None, "extension_upgrade_required"))
        self.assertEqual(q.next_job("0.10.8")[0]["scope_names"], ["a.jpg"])
