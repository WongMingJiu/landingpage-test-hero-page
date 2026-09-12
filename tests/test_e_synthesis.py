#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V2.5-E run_full_stability 合成逻辑单测（不触网）。

覆盖 classify_creative 的四类漂移分类与 per-run/per-creative 判定：
  STABLE / STABLE_WITH_WARN(B/C/D) / UNSTABLE(A 类 MRD 各信号)。
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO))

from v2.benchmarks.run_full_stability import (  # noqa: E402
    classify_creative, repeat_consistency,
)


def _tags(opening: str, expectation: str = "复制学员成功路径",
          primaries: list[str] | None = None, window: int = 8) -> dict:
    primaries = primaries if primaries is not None else ["获得可复制学习范例"]
    return {
        "opening_type": {"label": opening, "confidence": "high"},
        "user_expectation": {"label": expectation},
        "decision_window": {"used_seconds": window, "extended": False},
        "matched_value_tags": [
            {"label": p, "salience": "primary", "category": "c", "evidence": []}
            for p in primaries
        ],
    }


def _judge_v21b(ok: bool = True) -> dict:
    return {"primary_driver_same_route": ok, "question_same_type": ok,
            "supporting_only_secondary": True, "differences": [], "notes": ""}


def _judge_v23(sac=(True, True, True), anchor=True, intent=True, td=True) -> dict:
    return {"anchor_preserved": anchor, "intent_continuity": intent,
            "template_differentiation": td,
            "same_answer_class_repeat1": sac[0],
            "same_answer_class_repeat2": sac[1],
            "same_answer_class_repeat3": sac[2],
            "differences": [], "notes": ""}


def _gate(hard: list[str] | None = None, warns: list[str] | None = None) -> dict:
    return {"hard_fails": hard or [], "warns": warns or [],
            "grounding_status": "sufficient", "kb_weak_references": []}


class TestRepeatConsistency(unittest.TestCase):
    def test_all_same(self):
        tags = [_tags("演唱效果型") for _ in range(3)]
        c = repeat_consistency(tags)
        self.assertTrue(c["opening_all_same"])
        self.assertEqual(c["opening_modal_hits"], 3)
        self.assertEqual(c["primary_route_hits"], 3)
        self.assertTrue(c["primary_core_stable"])

    def test_one_deviation(self):
        tags = [_tags("演唱效果型"), _tags("学员故事证明型"), _tags("演唱效果型")]
        c = repeat_consistency(tags)
        self.assertFalse(c["opening_all_same"])
        self.assertEqual(c["opening_modal_hits"], 2)

    def test_primary_full_replacement(self):
        tags = [_tags("教学演示型", primaries=["正确发声并保护嗓音"]),
                _tags("教学演示型", primaries=["把握限时稀缺机会"]),
                _tags("教学演示型", primaries=["正确发声并保护嗓音"])]
        c = repeat_consistency(tags)
        self.assertFalse(c["primary_core_stable"])


class TestClassifyCreative(unittest.TestCase):
    def _classify(self, vid, tags_list, v21b=None, v23=None, gates=None):
        consist = repeat_consistency(tags_list)
        return classify_creative(
            vid, consist,
            gates or [_gate() for _ in range(3)],
            v21b or _judge_v21b(), v23 or _judge_v23())

    def test_stable(self):
        v = self._classify("v03", [_tags("演唱效果型")] * 3)
        self.assertEqual(v["status"], "STABLE")
        self.assertEqual([r["status"] for r in v["runs"]], ["PASS"] * 3)
        self.assertEqual(v["material_route_drift_units"], [])
        self.assertEqual(v["target_hit_count"], "3/3")

    def test_opening_switch_is_mrd(self):
        tags = [_tags("演唱效果型"), _tags("学员故事证明型"), _tags("演唱效果型")]
        v = self._classify("v03", tags)
        self.assertEqual(v["status"], "UNSTABLE")
        self.assertEqual(v["material_route_drift_units"], [2])
        self.assertEqual(v["runs"][1]["status"], "FAIL")
        self.assertEqual(v["target_hit_count"], "2/3")

    def test_v21b_route_switch_is_mrd_all_units(self):
        v = self._classify("v01", [_tags("教学演示型")] * 3,
                           v21b=_judge_v21b(ok=False))
        self.assertEqual(v["status"], "UNSTABLE")
        self.assertEqual(v["material_route_drift_units"], [1, 2, 3])

    def test_sac_false_single_unit(self):
        v = self._classify("v02", [_tags("演唱效果型")] * 3,
                           v23=_judge_v23(sac=(True, False, True)))
        self.assertEqual(v["status"], "UNSTABLE")
        self.assertEqual(v["material_route_drift_units"], [2])
        self.assertEqual(v["v2.3_same_answer_class"], 2)

    def test_anchor_density_is_warn_not_mrd(self):
        v = self._classify("v04", [_tags("学员故事证明型")] * 3,
                           v23=_judge_v23(anchor=False))
        self.assertEqual(v["status"], "STABLE_WITH_WARN")
        self.assertTrue(v["anchor_density_drift"])
        self.assertEqual(v["material_route_drift_units"], [])
        self.assertEqual([r["status"] for r in v["runs"]], ["WARN"] * 3)

    def test_anchor_false_with_sac_false_is_mrd(self):
        v = self._classify("v04", [_tags("学员故事证明型")] * 3,
                           v23=_judge_v23(anchor=False, sac=(True, False, True)))
        self.assertEqual(v["status"], "UNSTABLE")
        self.assertFalse(v["anchor_density_drift"])

    def test_supporting_slot_rotation_is_warn(self):
        tags = [_tags("演唱效果型", primaries=["获得可复制学习范例", "获得他人认可"]),
                _tags("演唱效果型", primaries=["获得可复制学习范例", "获得演唱效果参照"]),
                _tags("演唱效果型", primaries=["获得可复制学习范例", "获得他人认可"])]
        v = self._classify("v03", tags)
        self.assertEqual(v["status"], "STABLE_WITH_WARN")
        self.assertTrue(v["supporting_drift"])
        self.assertEqual(v["material_route_drift_units"], [])

    def test_hard_gate_fail_is_unit_fail(self):
        gates = [_gate(), _gate(hard=["schema_errors: x"]), _gate()]
        v = self._classify("v05", [_tags("教学演示型")] * 3, gates=gates)
        self.assertEqual(v["status"], "UNSTABLE")
        self.assertEqual(v["material_route_drift_units"], [2])
        self.assertEqual(v["runs"][1]["status"], "FAIL")

    def test_grounding_partial_is_warn(self):
        gates = [_gate(warns=["grounding_status=partial（仍安全）"])] * 3
        v = self._classify("v07", [_tags("权威背书型")] * 3, gates=gates)
        self.assertEqual(v["status"], "STABLE_WITH_WARN")
        self.assertTrue(v["supporting_drift"])

    def test_v09_taxonomy_disagreement(self):
        v = self._classify("v09", [_tags("低门槛领取型")] * 3)
        self.assertEqual(v["status"], "STABLE_WITH_WARN")
        self.assertTrue(v["taxonomy_disagreement"])
        self.assertEqual(v["material_route_drift_units"], [])

    def test_no_target_sample_has_no_hit_count(self):
        v = self._classify("v01", [_tags("教学演示型")] * 3)
        self.assertIsNone(v["target_opening"])
        self.assertIsNone(v["target_hit_count"])


if __name__ == "__main__":
    unittest.main()
