#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Unit tests for the replayable structured-evidence artifact + replay mode.

Infrastructure layer only: the artifact persists normalized observations
BEFORE final adjudication, and replay runs the same constrained adjudication
without any video/multimodal extraction. No API calls (FakeApi).
"""
import json
import os
import tempfile
import unittest

from v2 import tagging, taxonomy


def _valid_output():
    """Canonical valid creative_tagging_v1 payload (same fixture semantics as
    tests/test_schema.py)."""
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
        ],
        "active_value_tags": ["获得可复制学习范例"],
        "opening_type": {"label": "学员故事证明型", "source_mode": "script_and_visual",
                         "confidence": "high",
                         "evidence": [{"time": "00:00-00:15", "source": "visual", "content": "学员演唱与反馈"}]},
        "user_expectation": {"label": "复制学员成功路径", "candidate": None, "confidence": "high",
                             "evidence": [{"time": "00:00-00:02", "source": "transcript", "content": "口播"}]},
        "review": {"needed": False, "reason": None},
    }


def _obs():
    return [{"time": "00:00-00:04", "source": "visual", "fact": "学员对麦演唱",
             "candidates": {"opening": ["学员故事证明型"]}, "adjacent": None,
             "window": "秒0-10"}]


class ArtifactRoundTripTests(unittest.TestCase):
    def test_save_and_load_roundtrip(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "v2", tagging.STRUCTURED_EVIDENCE_FILENAME)
            sheet = {"b64": "abc", "labels": ["frame_00"], "width": 10, "height": 5}
            tagging.save_structured_evidence(path, _obs(), [{"start": 0.0, "end": 2.0, "text": "你好"}],
                                             sheet, creative_id="v01")
            art = tagging.load_structured_evidence(path)
            self.assertEqual(art["schema"], tagging.STRUCTURED_EVIDENCE_SCHEMA)
            self.assertEqual(art["creative_id"], "v01")
            self.assertEqual(art["observations"], _obs())
            self.assertEqual(art["transcript"][0]["text"], "你好")
            self.assertEqual(art["contact_sheet"]["b64"], "abc")

    def test_load_rejects_foreign_schema(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "x.json")
            with open(path, "w", encoding="utf-8") as f:
                json.dump({"schema": "other", "observations": _obs()}, f)
            with self.assertRaises(ValueError):
                tagging.load_structured_evidence(path)

    def test_load_rejects_empty_observations(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "x.json")
            with open(path, "w", encoding="utf-8") as f:
                json.dump({"schema": tagging.STRUCTURED_EVIDENCE_SCHEMA, "observations": []}, f)
            with self.assertRaises(ValueError):
                tagging.load_structured_evidence(path)


class ReplayTests(unittest.TestCase):
    class FakeApi:
        def __init__(self):
            self.calls = []

        def chat(self, system, user_content):
            self.calls.append(user_content)
            return json.dumps(_valid_output(), ensure_ascii=False)

    def setUp(self):
        self.tax = taxonomy.load_taxonomy("singing")
        self.cfg = tagging.TaggingConfig()
        self.cfg.api_base = "unused"
        self.cfg.api_key = "unused"
        self.cfg.model = "unused"

    def _pipe(self, api):
        pipe = tagging.TaggingPipeline(self.cfg, self.tax)
        pipe.api = api
        return pipe

    def test_replay_produces_valid_output_without_extraction(self):
        api = self.FakeApi()
        pipe = self._pipe(api)
        evidence = {"schema": tagging.STRUCTURED_EVIDENCE_SCHEMA, "creative_id": "v01",
                    "window": {"primary_seconds": 30, "used_seconds": 30},
                    "observations": _obs(),
                    "transcript": [{"start": 0.0, "end": 2.0, "text": "你好"}],
                    "contact_sheet": None}
        out = pipe.replay(evidence, "v01")
        self.assertEqual(out["creative_id"], "v01")
        self.assertEqual(out["schema_version"], "creative_tagging_v1")
        self.assertEqual(len(api.calls), 1)  # single adjudication call only

    def test_replay_adjudication_consumes_evidence_inventory(self):
        api = self.FakeApi()
        pipe = self._pipe(api)
        evidence = {"schema": tagging.STRUCTURED_EVIDENCE_SCHEMA, "creative_id": "v01",
                    "observations": _obs(), "transcript": [], "contact_sheet": None}
        pipe.replay(evidence, "v01")
        text = "\n".join(p.get("text", "") for p in api.calls[0] if p.get("type") == "text")
        self.assertIn("学员对麦演唱", text)          # evidence fact consumed
        self.assertIn("不得补充清单之外的事实", text)  # constrained adjudication

    def test_replay_deterministic_input_for_identical_evidence(self):
        api = self.FakeApi()
        pipe = self._pipe(api)
        evidence = {"schema": tagging.STRUCTURED_EVIDENCE_SCHEMA, "creative_id": "v01",
                    "observations": _obs(), "transcript": [], "contact_sheet": None}
        pipe.replay(evidence, "v01")
        pipe.replay(evidence, "v01")
        t1 = json.dumps(api.calls[0], ensure_ascii=False, sort_keys=True)
        t2 = json.dumps(api.calls[1], ensure_ascii=False, sort_keys=True)
        self.assertEqual(t1, t2)


class ProviderAdapterTests(unittest.TestCase):
    def test_make_provider_returns_chat_surface(self):
        from v2 import provider
        cfg = tagging.TaggingConfig()
        cfg.api_base, cfg.api_key, cfg.model = "b", "k", "m"
        p = provider.make_provider(cfg)
        self.assertTrue(hasattr(p, "chat"))


if __name__ == "__main__":
    unittest.main()
