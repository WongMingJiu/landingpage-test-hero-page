#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Import/structure smoke tests for the V2.1a pipeline (no API, no video)."""
import unittest
import os
from unittest.mock import patch

from v2 import taxonomy
from v2.tagging import TaggingConfig, TaggingPipeline, build_system_prompt, extract_json, _build_contact_sheet, _merge_user_content


class PipelineSmokeTests(unittest.TestCase):
    def setUp(self):
        self.tax = taxonomy.load_taxonomy("singing")

    def test_config_defaults_from_env(self):
        with patch.dict(os.environ, {}, clear=True):
            cfg = TaggingConfig.from_env()
        self.assertEqual(cfg.frame_budget, 20)
        self.assertEqual(cfg.compress_kb, 100)
        self.assertEqual(cfg.temperature, 0.0)
        self.assertFalse(cfg.audio_enabled)  # C2 default: no audio component

    def test_system_prompt_renders_full_taxonomy(self):
        sys_prompt = build_system_prompt(self.tax)
        # all labels present (not bare enums — definitions rendered)
        for lab in self.tax.value_labels:
            self.assertIn(lab, sys_prompt, f"value label {lab} missing from prompt")
        for lab in self.tax.opening_labels:
            self.assertIn(lab, sys_prompt, f"opening label {lab} missing from prompt")
        for lab in self.tax.expectation_labels:
            self.assertIn(lab, sys_prompt, f"expectation label {lab} missing from prompt")
        # decision priority table present
        self.assertIn("决策优先级", sys_prompt)
        # C2 audio rule present
        self.assertIn('source="audio"', sys_prompt)
        # no unresolved placeholders
        self.assertNotIn("{{", sys_prompt)
        self.assertNotIn("}}", sys_prompt)

    def test_pipeline_constructs_without_api(self):
        cfg = TaggingConfig()  # empty api config
        pipe = TaggingPipeline(cfg, self.tax)  # lazy client, no connection
        self.assertEqual(pipe.cfg.frame_budget, 20)
        self.assertFalse(pipe.cfg.audio_enabled)

    def test_extract_json_handles_fenced_and_bare(self):
        self.assertEqual(extract_json('```json\n{"a": 1}\n```'), {"a": 1})
        self.assertEqual(extract_json('prefix {"a": 2} suffix'), {"a": 2})
        self.assertEqual(extract_json('{"a": 3}'), {"a": 3})
    def test_staged_merge_includes_timestamped_contact_sheet(self):
        # A staged merge must re-see the raw visual evidence, not rely only on
        # lossy text notes. The contact sheet is one image with frame/time labels.
        from PIL import Image
        import base64
        import io

        buf = io.BytesIO()
        Image.new("RGB", (32, 24), (20, 80, 140)).save(buf, format="JPEG")
        b64 = base64.b64encode(buf.getvalue()).decode("ascii")
        fr = [{"sec": 0, "b64": b64}, {"sec": 19, "b64": b64}]
        sheet = _build_contact_sheet(fr)
        obs = [{"time": "00:00-00:02", "source": "visual", "fact": "开场事实",
                "candidates": {}, "adjacent": None, "window": "秒0-10"}]
        parts = _merge_user_content(obs, [], sheet)
        image_parts = [p for p in parts if p.get("type") == "image_url"]
        text = "\n".join(p.get("text", "") for p in parts)
        self.assertEqual(len(image_parts), 1)
        self.assertIn("frame_00", text)
        self.assertIn("第 19 秒", text)
        self.assertIn("开场事实", text)  # structured evidence rendered
        self.assertTrue(image_parts[0]["image_url"]["url"].startswith("data:image/jpeg;base64,"))
    def test_staged_merge_is_constrained_generic_adjudication(self):
        obs = [{"time": "00:00-00:02", "source": "visual", "fact": "事实",
                "candidates": {}, "adjacent": None, "window": "秒0-10"}]
        parts = _merge_user_content(obs, [], None)
        text = "\n".join(p.get("text", "") for p in parts)
        # independent Opening/Expectation judgment, no mechanical mapping
        self.assertIn("User Expectation 与 Opening 独立判断", text)
        self.assertIn("禁止机械映射", text)
        # method-over-principle adjudication principle
        self.assertIn("掌握简单方法", text)
        self.assertIn("理解专业原理", text)
        # evidence-constrained adjudication
        self.assertIn("不得补充清单之外的事实", text)
        # no benchmark-specific hardcoding in the adjudication layer
        for vid in ("v01", "v02", "v03", "v04", "v05", "v06", "v07", "v08", "v09", "v10"):
            self.assertNotIn(vid, text)
    def test_system_prompt_contains_primary_causal_consistency_rules(self):
        prompt = build_system_prompt(self.tax)
        self.assertIn("Primary consistency check", prompt)
        self.assertIn("为什么当前 Opening 能成立", prompt)
        self.assertIn("用户接下来真正会在意什么", prompt)
        self.assertIn("获得课程与学习资源", prompt)
        self.assertIn("通常是 supporting", prompt)
        self.assertIn("年龄可学", prompt)
        self.assertNotIn("如 v09", prompt)  # no benchmark ID hardcoding

    def test_system_prompt_contains_generic_learner_story_suspense_boundary(self):
        prompt = build_system_prompt(self.tax)
        self.assertIn("后悔", prompt)
        self.assertIn("信息缺口或答案揭晓本身", prompt)
        self.assertIn("学员故事证明型", prompt)
        self.assertIn("不要针对某个视频硬编码", prompt)
        # boundary must not override the decision-priority table
        self.assertIn("仍必须按决策优先级表决胜", prompt)
        self.assertIn("表演性演唱展示", prompt)

    def test_system_prompt_contains_method_vs_principle_expectation_boundary(self):
        prompt = build_system_prompt(self.tax)
        self.assertIn("任何要求观众模仿的动作时刻", prompt)
        self.assertIn("理解专业原理", prompt)


if __name__ == "__main__":
    unittest.main()
