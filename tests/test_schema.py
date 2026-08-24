#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Unit tests for v2.schema (frozen creative_tagging_v1 + correction #2 audio gate)."""
import copy
import unittest

from v2 import schema, taxonomy


def _valid():
    """A canonical valid output matching benchmark v01 semantics."""
    return {
        "schema_version": "creative_tagging_v1",
        "creative_id": "v01",
        "decision_window": {
            "primary_seconds": 30, "used_seconds": 30, "extended": False,
            "extended_reason": None, "semantic_sufficiency": "sufficient",
        },
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


class SchemaValidTests(unittest.TestCase):
    def setUp(self):
        self.tax = taxonomy.load_taxonomy("singing")

    def test_canonical_fixture_valid(self):
        self.assertEqual(schema.validate(_valid(), self.tax), [])

    def test_extended_consistent_valid(self):
        d = _valid()
        d["decision_window"] = {"primary_seconds": 30, "used_seconds": 60, "extended": True,
                                "extended_reason": "0-30s opening evidence inconclusive",
                                "semantic_sufficiency": "insufficient"}
        self.assertEqual(schema.validate(d, self.tax), [])


class SchemaInvalidTests(unittest.TestCase):
    def setUp(self):
        self.tax = taxonomy.load_taxonomy("singing")
        self.base = _valid()

    def _mut(self, **kw):
        d = copy.deepcopy(self.base)
        for k, v in kw.items():
            parts = k.split(".")
            obj = d
            for p in parts[:-1]:
                obj = obj[int(p)] if p.isdigit() else obj[p]
            last = parts[-1]
            if isinstance(obj, list):
                obj[int(last)] = v
            else:
                obj[last] = v
        return d

    def _expect(self, errs, marker):
        self.assertTrue(any(marker in e for e in errs), f"expected marker {marker!r} in {errs}")

    def test_bad_schema_version(self):
        errs = schema.validate(self._mut(schema_version="wrong"), self.tax)
        self._expect(errs, "schema_version")

    def test_empty_creative_id(self):
        errs = schema.validate(self._mut(creative_id=""), self.tax)
        self._expect(errs, "creative_id")

    def test_extended_true_but_used_30(self):
        d = self._mut(**{"decision_window.extended": True, "decision_window.used_seconds": 30,
                         "decision_window.semantic_sufficiency": "insufficient",
                         "decision_window.extended_reason": "x"})
        errs = schema.validate(d, self.tax)
        self._expect(errs, "extended=true requires used_seconds=60")

    def test_sufficient_but_extended(self):
        d = self._mut(**{"decision_window.extended": True, "decision_window.used_seconds": 60,
                         "decision_window.semantic_sufficiency": "sufficient",
                         "decision_window.extended_reason": "x"})
        errs = schema.validate(d, self.tax)
        self._expect(errs, "sufficiency=sufficient requires extended=false")

    def test_extended_true_no_reason(self):
        d = self._mut(**{"decision_window.extended": True, "decision_window.used_seconds": 60,
                         "decision_window.semantic_sufficiency": "insufficient",
                         "decision_window.extended_reason": None})
        errs = schema.validate(d, self.tax)
        self._expect(errs, "extended_reason")

    def test_weak_evidence_strength_rejected(self):
        errs = schema.validate(self._mut(**{"matched_value_tags.0.evidence_strength": "weak"}), self.tax)
        self._expect(errs, "evidence_strength")

    def test_active_not_in_matched(self):
        errs = schema.validate(self._mut(**{"active_value_tags.0": "稳定气息"}), self.tax)
        # 稳定气息 not in matched -> error
        self._expect(errs, "must be present in matched_value_tags")

    def test_active_total_exceeds_5(self):
        d = copy.deepcopy(self.base)
        d["matched_value_tags"].append(
            {"category": "演唱能力", "label": "稳定气息", "evidence_strength": "medium",
             "salience": "supporting",
             "evidence": [{"time": "00:05", "source": "visual", "content": "x"}]})
        d["active_value_tags"] = ["获得可复制学习范例", "获得演唱效果参照", "正确发声并保护嗓音",
                                  "获得专业指导", "获得课程与学习资源", "稳定气息"]
        errs = schema.validate(d, self.tax)
        self._expect(errs, "exceeds limit 5")

    def test_no_primary_salience(self):
        d = copy.deepcopy(self.base)
        for m in d["matched_value_tags"]:
            m["salience"] = "supporting"
        d["active_value_tags"] = ["获得可复制学习范例", "正确发声并保护嗓音"]
        errs = schema.validate(d, self.tax)
        self._expect(errs, "primary salience count")

    def test_too_many_primary(self):
        d = copy.deepcopy(self.base)
        # make 3 primaries across distinct categories to avoid per-cat cap
        for m in d["matched_value_tags"][:3]:
            m["salience"] = "primary"
        d["matched_value_tags"][0]["category"] = "演唱能力"
        d["matched_value_tags"][0]["label"] = "稳定气息"
        d["matched_value_tags"][1]["category"] = "学习降阻"
        d["matched_value_tags"][1]["label"] = "方法简单易操作"
        d["active_value_tags"] = ["稳定气息", "方法简单易操作", "正确发声并保护嗓音"]
        errs = schema.validate(d, self.tax)
        self._expect(errs, "primary salience count 3")

    def test_per_category_cap_exceeded(self):
        # 演唱能力 cap is 3
        d = copy.deepcopy(self.base)
        # reset matched to 4 演唱能力 primaries+supportings
        d["matched_value_tags"] = [
            {"category": "演唱能力", "label": l, "evidence_strength": "strong" if i < 2 else "medium",
             "salience": "primary" if i < 2 else "supporting",
             "evidence": [{"time": "00:05", "source": "visual", "content": "x"}]}
            for i, l in enumerate(["稳定气息", "改善音色与声音质感", "增强声音稳定与力量", "突破高音"])
        ]
        d["active_value_tags"] = ["稳定气息", "改善音色与声音质感", "增强声音稳定与力量", "突破高音"]
        errs = schema.validate(d, self.tax)
        self._expect(errs, "exceeds limit 3")

    def test_opening_label_not_in_taxonomy(self):
        errs = schema.validate(self._mut(**{"opening_type.label": "不存在"}), self.tax)
        self._expect(errs, "not in Opening Taxonomy")

    def test_opening_evidence_empty(self):
        errs = schema.validate(self._mut(**{"opening_type.evidence": []}), self.tax)
        self._expect(errs, "opening_type: evidence")

    def test_expectation_candidate_nonnull_when_concrete(self):
        errs = schema.validate(self._mut(**{"user_expectation.candidate": "掌握简单方法"}), self.tax)
        self._expect(errs, "candidate must be null")

    def test_undetermined_without_candidate(self):
        d = self._mut(**{"user_expectation.label": "无法判断（对于这种情况给一个候选）",
                         "user_expectation.candidate": None})
        errs = schema.validate(d, self.tax)
        self._expect(errs, "candidate must be a non-empty string")

    def test_review_needed_without_reason(self):
        d = self._mut(**{"review.needed": True, "review.reason": None})
        errs = schema.validate(d, self.tax)
        self._expect(errs, "review.reason")


class AudioGateTests(unittest.TestCase):
    """Correction #2: source=audio illegal in MVP (no audio-understanding component)."""

    def setUp(self):
        self.tax = taxonomy.load_taxonomy("singing")

    def test_audio_source_rejected_in_mvp(self):
        d = _valid()
        d["matched_value_tags"][0]["evidence"][0]["source"] = "audio"
        errs = schema.validate(d, self.tax, audio_enabled=False)
        self.assertTrue(any("source=audio" in e and "illegal in MVP" in e for e in errs), errs)

    def test_audio_source_allowed_when_component_present(self):
        d = _valid()
        d["matched_value_tags"][0]["evidence"][0]["source"] = "audio"
        errs = schema.validate(d, self.tax, audio_enabled=True)
        self.assertFalse(any("source=audio" in e for e in errs), errs)


if __name__ == "__main__":
    unittest.main()
