#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V2.5-F used_anchors membership validator 单测（§7 Test 1-5，不触网）。

allowed set 按现有 V2.3 third-pass 冻结 contract（不擅自扩大）：
  topics[].value + phrases[].value + user_concern.value + expectation.value
  + user_concern/expectation 标点切分 core words；exact membership。
"""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO))

from v2 import message_match_schema as mms  # noqa: E402


def _copy_obj(topics=("宋老师唱歌训练营", "母亲在家唱歌"),
              phrases=("后悔没早点让她学",),
              user_concern="怕年纪大了学不会",
              expectation="在家学会唱歌",
              t1_anchors=("宋老师唱歌训练营", "后悔没早点让她学"),
              t2_anchors=("母亲在家唱歌", "在家学会唱歌")) -> dict:
    return {
        "creative_anchors": {
            "topics": [{"value": v} for v in topics],
            "phrases": [{"value": v} for v in phrases],
            "user_concern": {"value": user_concern},
            "expectation": {"value": expectation},
        },
        "t1": {"used_anchors": list(t1_anchors)},
        "t2": {"used_anchors": list(t2_anchors)},
    }


class TestCollectAnchorValues(unittest.TestCase):
    def test_null_and_empty_excluded(self):
        """Test 4a：null / 空串不进入 allowed set。"""
        obj = {
            "topics": [{"value": "妈妈"}, {"value": None}, {"value": ""}],
            "phrases": [],
            "user_concern": {"value": ""},
            "expectation": None,
        }
        self.assertEqual(mms.collect_anchor_values(obj), {"妈妈"})

    def test_concern_core_words_split(self):
        """Test 2a：user_concern/expectation 按标点切分的 core words 进入 allowed set。"""
        obj = {
            "topics": [],
            "phrases": [],
            "user_concern": {"value": "怕学不会，怕坚持不下来"},
            "expectation": {"value": "在家学会唱歌。唱给家人听"},
        }
        allowed = mms.collect_anchor_values(obj)
        self.assertIn("怕学不会", allowed)
        self.assertIn("怕坚持不下来", allowed)
        self.assertIn("在家学会唱歌", allowed)
        self.assertIn("唱给家人听", allowed)


class TestValidateUsedAnchorsMembership(unittest.TestCase):
    def test_1_exact_membership_pass(self):
        """Test 1：合法 exact membership → PASS。"""
        self.assertEqual(mms.validate_used_anchors_membership(_copy_obj()), [])

    def test_2_concern_expectation_reference_allowed(self):
        """Test 2：user_concern / expectation 引用按现有 contract 允许。"""
        obj = _copy_obj(t1_anchors=("怕年纪大了学不会",),
                        t2_anchors=("在家学会唱歌", "后悔没早点让她学"))
        self.assertEqual(mms.validate_used_anchors_membership(obj), [])

    def test_3_semantic_near_miss_fails(self):
        """Test 3：语义近似但不是 exact value → FAIL（V2.5-E v04 真实案例）。"""
        obj = _copy_obj(t1_anchors=("家人",), t2_anchors=("家人",))
        errors = mms.validate_used_anchors_membership(obj)
        self.assertEqual(len(errors), 2)
        for e in errors:
            self.assertEqual(e["type"], "INVALID_USED_ANCHOR")
            self.assertEqual(e["value"], "家人")
            self.assertIn("母亲在家唱歌", e["allowed_values"])
        self.assertEqual({e["template"] for e in errors}, {"t1", "t2"})

    def test_3b_substring_not_membership(self):
        """substring 不是 membership：allowed 含「母亲在家唱歌」不代表「母亲」合法。"""
        obj = _copy_obj(t1_anchors=("母亲",))
        errors = mms.validate_used_anchors_membership(obj)
        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0]["value"], "母亲")

    def test_4_empty_string_anchor_fails(self):
        """Test 4b：空串 used_anchor（不在 allowed set）→ FAIL。"""
        obj = _copy_obj(t1_anchors=("",))
        self.assertEqual(len(mms.validate_used_anchors_membership(obj)), 1)

    def test_5_either_template_fail_fails_whole_gate(self):
        """Test 5：T1 / T2 任一非法值 → 整个 structural gate FAIL。"""
        obj = _copy_obj(t1_anchors=("宋老师唱歌训练营", "不存在的锚"),
                        t2_anchors=("母亲在家唱歌",))
        errors = mms.validate_used_anchors_membership(obj)
        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0]["template"], "t1")


class TestGroundingTraceRegression(unittest.TestCase):
    """重构回归：collect_anchor_values 提取后 validate_grounding_trace 行为不变。"""

    def test_e_round_v04_rep1_real_artifact_still_fails(self):
        """E 轮 v04/repeat-1 真实 artifact 回放：仍报「家人」membership 错误。"""
        p = _REPO / "output" / "v2.5-e-full-repeat-stability" / "v04" / "repeat-1" \
            / "v2.3" / "message_match_copy.json"
        if not p.is_file():
            self.skipTest("V2.5-E artifacts 不在本机")
        output = json.loads(p.read_text(encoding="utf-8"))["output"]
        errs = mms.validate_grounding_trace(output)
        self.assertTrue(any("家人" in e for e in errs), errs)
        member = mms.validate_used_anchors_membership(output)
        self.assertEqual([e["value"] for e in member], ["家人", "家人"])
        self.assertEqual([e["template"] for e in member], ["t1", "t2"])

    def test_all_e_round_runs_only_v04r1_membership_fail(self):
        """E 轮 30 runs 全量回放：used_anchors membership 唯一违规 = v04 rep1。"""
        root = _REPO / "output" / "v2.5-e-full-repeat-stability"
        if not root.is_dir():
            self.skipTest("V2.5-E artifacts 不在本机")
        fails = []
        for vid in (f"v{i:02d}" for i in range(1, 11)):
            for rep in (1, 2, 3):
                p = root / vid / f"repeat-{rep}" / "v2.3" / "message_match_copy.json"
                if not p.is_file():
                    continue
                output = json.loads(p.read_text(encoding="utf-8"))["output"]
                if mms.validate_used_anchors_membership(output):
                    fails.append(f"{vid}/rep{rep}")
        self.assertEqual(fails, ["v04/rep1"])


if __name__ == "__main__":
    unittest.main()
