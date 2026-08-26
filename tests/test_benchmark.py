#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Unit tests for the benchmark evaluator (pure, no API)."""
import json
import os
import unittest

from v2 import taxonomy
from v2.benchmarks.run_benchmark import load_manifest, evaluate_sample


def _valid_v01():
    """Matches benchmark v01 GT: opening=学员故事证明型, exp=复制学员成功路径."""
    return {
        "schema_version": "creative_tagging_v1",
        "creative_id": "v01",
        "decision_window": {"primary_seconds": 30, "used_seconds": 30, "extended": False,
                            "extended_reason": None, "semantic_sufficiency": "sufficient"},
        "matched_value_tags": [
            {"category": "专业认知提升", "label": "获得可复制学习范例", "evidence_strength": "strong",
             "salience": "primary",
             "evidence": [{"time": "00:05-00:15", "source": "visual", "content": "老年学员对麦演唱"}]},
            {"category": "专业认知提升", "label": "获得演唱效果参照", "evidence_strength": "strong",
             "salience": "primary",
             "evidence": [{"time": "00:05-00:15", "source": "visual", "content": "学员演唱证明"}]},
            {"category": "演唱能力", "label": "正确发声并保护嗓音", "evidence_strength": "medium",
             "salience": "supporting",
             "evidence": [{"time": "00:05-00:15", "source": "subtitle", "content": "改掉喉咙唱歌"}]},
            {"category": "信任保障", "label": "获得专业指导", "evidence_strength": "medium",
             "salience": "supporting",
             "evidence": [{"time": "00:17-00:18", "source": "visual", "content": "国家一级演员"}]},
            {"category": "课程权益", "label": "获得课程与学习资源", "evidence_strength": "medium",
             "salience": "supporting",
             "evidence": [{"time": "00:20-00:27", "source": "visual", "content": "手机课程画面"}]},
        ],
        "active_value_tags": ["获得可复制学习范例", "获得演唱效果参照", "正确发声并保护嗓音",
                               "获得专业指导", "获得课程与学习资源"],
        "opening_type": {"label": "学员故事证明型", "source_mode": "script_and_visual",
                         "confidence": "high",
                         "evidence": [{"time": "00:00-00:15", "source": "visual", "content": "学员演唱与反馈"}]},
        "user_expectation": {"label": "复制学员成功路径", "candidate": None, "confidence": "high",
                             "evidence": [{"time": "00:00-00:02", "source": "transcript", "content": "轻松唱歌法有多神奇"}]},
        "review": {"needed": False, "reason": None},
    }


def _v01_expected():
    m = load_manifest()
    item = next(i for i in m["items"] if i["id"] == "v01")
    return {"id": "v01", **item["expected"]}


class EvaluatorTests(unittest.TestCase):
    def setUp(self):
        self.tax = taxonomy.load_taxonomy("singing")
        self.exp = _v01_expected()

    def test_manifest_has_10_items_all_extended_false(self):
        m = load_manifest()
        self.assertEqual(len(m["items"]), 10)
        for it in m["items"]:
            self.assertEqual(it["expected"]["used_seconds"], 30)
            self.assertFalse(it["expected"]["extended"])
        adjustments = {x["id"]: x for x in m.get("gt_adjustments", [])}
        self.assertIn("v08", adjustments)
        self.assertIn("v09", adjustments)
        # Corrected GT must satisfy active total/salience/category caps.
        for it in m["items"]:
            expected = it["expected"]
            values = expected["active_primary"] + expected["active_supporting"]
            self.assertLessEqual(len(values), 5)
            self.assertIn(len(expected["active_primary"]), (1, 2))
            self.assertLessEqual(len(expected["active_supporting"]), 3)
            counts = {}
            for label in values:
                category = self.tax.value_category_of(label)
                counts[category] = counts.get(category, 0) + 1
            for category, count in counts.items():
                self.assertLessEqual(count, self.tax.active_limits[category], (it["id"], category, count))

    def test_canonical_v01_passes_core(self):
        r = evaluate_sample(_valid_v01(), self.exp, self.tax)
        self.assertTrue(r["decision_window_ok"])
        self.assertTrue(r["opening_ok"])
        self.assertTrue(r["expectation_ok"])
        self.assertTrue(r["primary_exact"])
        self.assertTrue(r["evidence_present"])
        self.assertTrue(r["core_pass"], r)
        self.assertEqual(r["primary_core_match"], "exact")

    def test_false_extend_fails_window(self):
        d = _valid_v01()
        d["decision_window"] = {"primary_seconds": 30, "used_seconds": 60, "extended": True,
                                "extended_reason": "x", "semantic_sufficiency": "insufficient"}
        r = evaluate_sample(d, self.exp, self.tax)
        self.assertFalse(r["decision_window_ok"])
        self.assertFalse(r["core_pass"])

    def test_wrong_opening_with_acceptable_alternative(self):
        # v02 boundary: GT opening=教学演示型, alt=演唱效果型
        m = load_manifest()
        v02 = next(i for i in m["items"] if i["id"] == "v02")["expected"]
        d = _valid_v01()
        d["opening_type"]["label"] = "演唱效果型"
        r = evaluate_sample(d, {"id": "v02", **v02}, self.tax)
        self.assertTrue(r["opening_ok"])  # accepted as alternative
        # but expectation won't match v02 GT (掌握简单方法), so core_pass False
        self.assertFalse(r["core_pass"])

    def test_skipped_when_no_output(self):
        r = evaluate_sample(None, self.exp, self.tax)
        self.assertTrue(r["skipped"])
        self.assertFalse(r["core_pass"])

    def test_primary_mismatch_detected(self):
        d = _valid_v01()
        # swap one primary for a wrong one
        d["matched_value_tags"][1]["label"] = "稳定气息"
        d["matched_value_tags"][1]["category"] = "演唱能力"
        d["active_value_tags"][1] = "稳定气息"
        r = evaluate_sample(d, self.exp, self.tax)
        self.assertFalse(r["primary_exact"])
        self.assertIn("获得演唱效果参照", r["primary_missing"])
        self.assertEqual(r["primary_core_match"], "partial")

    def test_primary_zero_overlap_is_wrong(self):
        d = _valid_v01()
        d["matched_value_tags"][0]["label"] = "稳定气息"
        d["matched_value_tags"][0]["category"] = "演唱能力"
        d["matched_value_tags"][1]["label"] = "方法简单易操作"
        d["matched_value_tags"][1]["category"] = "学习降阻"
        d["active_value_tags"][0:2] = ["稳定气息", "方法简单易操作"]
        r = evaluate_sample(d, self.exp, self.tax)
        self.assertFalse(r["primary_exact"])
        self.assertEqual(r["primary_core_match"], "wrong")

    def test_existing_valid_output_roundtrip(self):
        import tempfile
        from v2.benchmarks.run_benchmark import _existing_valid_output
        with tempfile.TemporaryDirectory() as td:
            self.assertIsNone(_existing_valid_output(td, self.tax, False))
            path = os.path.join(td, "creative_tags.json")
            with open(path, "w", encoding="utf-8") as f:
                json.dump(_valid_v01(), f, ensure_ascii=False)
            data = _existing_valid_output(td, self.tax, False)
            self.assertIsNotNone(data)
            self.assertEqual(data["opening_type"]["label"], "学员故事证明型")
            with open(path, "w", encoding="utf-8") as f:
                f.write("{not json")
            self.assertIsNone(_existing_valid_output(td, self.tax, False))


if __name__ == "__main__":
    unittest.main()
