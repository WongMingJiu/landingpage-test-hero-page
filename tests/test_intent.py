#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Unit tests for V2.1b Intent Decision (creative_intent_v1 + pipeline + benchmark)."""
import copy
import json
import os
import re
import tempfile
import unittest

from v2 import intent_decision, intent_schema, taxonomy
from v2.benchmarks import run_intent_benchmark
from v2.tagging import TaggingConfig


def _tags():
    """Minimal schema-valid creative_tagging_v1 input (v01-like)."""
    return {
        "schema_version": "creative_tagging_v1",
        "creative_id": "v01",
        "decision_window": {"primary_seconds": 30, "used_seconds": 30, "extended": False,
                            "extended_reason": None, "semantic_sufficiency": "sufficient"},
        "matched_value_tags": [
            {"category": "专业认知提升", "label": "获得可复制学习范例", "evidence_strength": "strong",
             "salience": "primary",
             "evidence": [{"time": "00:00-00:04", "source": "transcript",
                           "content": "几年没学明白的唱歌，在这里一个星期就学明白了"}]},
            {"category": "信任保障", "label": "获得专业指导", "evidence_strength": "medium",
             "salience": "supporting",
             "evidence": [{"time": "00:18-00:20", "source": "visual",
                           "content": "画面分屏展示讲师，旁注文字'国家一级演员'"}]},
        ],
        "active_value_tags": ["获得可复制学习范例", "获得专业指导"],
        "opening_type": {"label": "学员故事证明型", "source_mode": "script_and_visual",
                         "confidence": "high",
                         "evidence": [{"time": "00:00-00:04", "source": "visual",
                                       "content": "顶部横幅：宋老师收到学员反馈"}]},
        "user_expectation": {"label": "复制学员成功路径", "candidate": None, "confidence": "high",
                             "evidence": [{"time": "00:00-00:18", "source": "subtitle",
                                           "content": "学员表示身体唱歌法让她开了窍"}]},
        "review": {"needed": False, "reason": None},
    }


def _intent(tags=None):
    tags = tags or _tags()
    return {
        "schema_version": "creative_intent_v1",
        "creative_id": tags["creative_id"],
        "primary_driver": {
            "statement": "真实学员证明了这套方法有效，用户相信自己也可能复制学习结果",
            "confidence": "high"},
        "unresolved_question": {
            "statement": "她具体是怎么学的，我也能做到吗？",
            "confidence": "high"},
        "intent_strength": "strong",
        "supporting_drivers": [],
        "evidence": [tags["matched_value_tags"][0]["evidence"][0]],
    }


class _StubAPI:
    """Stub provider: returns a canned valid intent JSON."""

    def __init__(self, payload=None):
        self.payload = payload or _intent()
        self.calls = 0

    def chat(self, system, user_content):
        self.calls += 1
        return json.dumps(self.payload, ensure_ascii=False)


class IntentSchemaTests(unittest.TestCase):
    def setUp(self):
        self.tax = taxonomy.load_taxonomy("singing")
        self.tags = _tags()

    def test_valid_output(self):
        self.assertEqual(intent_schema.validate(_intent(self.tags), self.tags, self.tax), [])

    def test_primary_driver_required_and_unique(self):
        d = _intent(self.tags)
        del d["primary_driver"]
        errs = intent_schema.validate(d, self.tags, self.tax)
        self.assertTrue(any("primary_driver" in e for e in errs))
        # an array (multiple drivers) is also rejected
        d = _intent(self.tags)
        d["primary_driver"] = [d["primary_driver"], d["primary_driver"]]
        errs = intent_schema.validate(d, self.tags, self.tax)
        self.assertTrue(any("primary_driver" in e for e in errs))

    def test_statement_must_not_be_bare_label(self):
        d = _intent(self.tags)
        d["primary_driver"]["statement"] = "获得可复制学习范例"
        errs = intent_schema.validate(d, self.tags, self.tax)
        self.assertTrue(any("bare taxonomy label" in e for e in errs))

    def test_supporting_drivers_limit(self):
        d = _intent(self.tags)
        d["supporting_drivers"] = ["命题一：老师带练降低难度", "命题二：课程领取方便", "命题三：限时优惠"]
        errs = intent_schema.validate(d, self.tags, self.tax)
        self.assertTrue(any("exceeds limit 2" in e for e in errs))

    def test_supporting_drivers_empty_ok(self):
        d = _intent(self.tags)
        d["supporting_drivers"] = []
        self.assertEqual(intent_schema.validate(d, self.tags, self.tax), [])

    def test_evidence_must_come_from_input(self):
        d = _intent(self.tags)
        d["evidence"] = [{"time": "00:09-00:11", "source": "transcript",
                          "content": "这条证据是编造的，不在输入里"}]
        errs = intent_schema.validate(d, self.tags, self.tax)
        self.assertTrue(any("not present verbatim" in e for e in errs))
        # partially-modified copy also rejected (verbatim requirement)
        d = _intent(self.tags)
        ev = copy.deepcopy(d["evidence"][0])
        ev["content"] = ev["content"] + "（改写）"
        d["evidence"] = [ev]
        errs = intent_schema.validate(d, self.tags, self.tax)
        self.assertTrue(any("not present verbatim" in e for e in errs))

    def test_evidence_from_opening_and_expectation_allowed(self):
        d = _intent(self.tags)
        d["evidence"] = [self.tags["opening_type"]["evidence"][0],
                         self.tags["user_expectation"]["evidence"][0]]
        self.assertEqual(intent_schema.validate(d, self.tags, self.tax), [])

    def test_intent_strength_enum(self):
        for bad in ("very-strong", "HIGH", 1, None, " Strong "):
            d = _intent(self.tags)
            d["intent_strength"] = bad
            errs = intent_schema.validate(d, self.tags, self.tax)
            self.assertTrue(any("intent_strength" in e for e in errs), bad)
        for good in ("strong", "medium", "weak"):
            d = _intent(self.tags)
            d["intent_strength"] = good
            self.assertEqual(
                [e for e in intent_schema.validate(d, self.tags, self.tax)
                 if "intent_strength" in e], [], good)

    def test_creative_id_must_match_input(self):
        d = _intent(self.tags)
        d["creative_id"] = "v02"
        errs = intent_schema.validate(d, self.tags, self.tax)
        self.assertTrue(any("does not match input" in e for e in errs))


class IntentPipelineTests(unittest.TestCase):
    def setUp(self):
        self.tax = taxonomy.load_taxonomy("singing")
        self.cfg = TaggingConfig()

    def test_fail_fast_on_missing_required_fields(self):
        pipe = intent_decision.IntentDecisionPipeline(self.cfg, self.tax, api=_StubAPI())
        for missing in ("matched_value_tags", "opening_type", "user_expectation",
                        "decision_window", "review", "active_value_tags"):
            tags = _tags()
            del tags[missing]
            with self.assertRaises(ValueError) as cm:
                pipe.decide(tags)
            self.assertIn("missing required field", str(cm.exception))
            # no API call happened (fail fast precedes any LLM call)
            self.assertEqual(pipe.api.calls, 0)

    def test_fail_fast_on_wrong_schema_version(self):
        pipe = intent_decision.IntentDecisionPipeline(self.cfg, self.tax, api=_StubAPI())
        tags = _tags()
        tags["schema_version"] = "creative_tagging_v2"
        with self.assertRaises(ValueError):
            pipe.decide(tags)

    def test_decide_validates_output_against_input(self):
        pipe = intent_decision.IntentDecisionPipeline(self.cfg, self.tax, api=_StubAPI())
        out = pipe.decide(_tags())
        self.assertEqual(intent_schema.validate(out, _tags(), self.tax), [])

    def test_retries_on_schema_failure_then_raises(self):
        bad = _intent()
        bad["intent_strength"] = "very-strong"
        pipe = intent_decision.IntentDecisionPipeline(self.cfg, self.tax, api=_StubAPI(bad))
        with self.assertRaises(RuntimeError):
            pipe.decide(_tags())
        self.assertEqual(pipe.api.calls, self.cfg.max_retries)


class IntentBenchmarkTests(unittest.TestCase):
    """Seed benchmark integrity + runner mechanics (no real API)."""

    def setUp(self):
        self.tax = taxonomy.load_taxonomy("singing")

    def test_manifest_has_10_complete_items(self):
        with open(run_intent_benchmark._MANIFEST, "r", encoding="utf-8") as f:
            m = json.load(f)
        self.assertEqual(m["schema_version"], "creative_intent_v1")
        self.assertEqual(len(m["items"]), 10)
        for it in m["items"]:
            for k in ("id", "primary_driver_gt", "unresolved_question_gt",
                      "intent_strength_gt"):
                self.assertTrue(it.get(k), (it.get("id"), k))
            self.assertIn(it["intent_strength_gt"], ("strong", "medium", "weak"))
        self.assertEqual([it["id"] for it in m["items"]],
                         [f"v{i:02d}" for i in range(1, 11)])

    def test_runner_end_to_end_with_stub(self):
        class _BenchStub(_StubAPI):
            """Serves intent decisions (matching input creative_id) and judge verdicts."""

            def chat(self, system, user_content):
                if "语义判定器" in system:
                    return json.dumps({"primary_match": True, "question_match": True,
                                       "primary_reason": "stub", "question_reason": "stub"},
                                      ensure_ascii=False)
                text = " ".join(p.get("text", "") for p in user_content if isinstance(p, dict))
                m = re.search(r'"creative_id":\s*"([^"]+)"', text)
                payload = _intent()
                if m:
                    payload["creative_id"] = m.group(1)
                return json.dumps(payload, ensure_ascii=False)

        tags_root = tempfile.mkdtemp(prefix="intent-bench-tags-")
        for i in range(1, 11):
            od = os.path.join(tags_root, f"v{i:02d}", "run0", "v2")
            os.makedirs(od)
            tags = _tags()
            tags["creative_id"] = f"v{i:02d}"
            with open(os.path.join(od, "creative_tags.json"), "w", encoding="utf-8") as f:
                json.dump(tags, f, ensure_ascii=False)

        pipe = intent_decision.IntentDecisionPipeline(
            TaggingConfig(), self.tax, api=_BenchStub())
        agg = run_intent_benchmark.run_benchmark(
            tags_root, "intent-unit-test", pipe=pipe)
        self.assertEqual(agg["completed"], 10)
        self.assertEqual(agg["primary_semantic_match"], 10)
        self.assertEqual(agg["question_semantic_match"], 10)
        self.assertEqual(agg["primary_unique"], 10)
        self.assertEqual(agg["evidence_grounded"], 10)
        self.assertTrue(all(agg["gates"].values()))


class ClosedSchemaTests(unittest.TestCase):
    """creative_intent_v1 is a closed schema: extra fields are rejected at
    every level (top-level / statement objects / evidence items)."""

    def setUp(self):
        self.tax = taxonomy.load_taxonomy("singing")
        self.tags = _tags()

    def test_top_level_extra_fields_rejected(self):
        for extra in ("core_need", "barrier", "driver_type", "persuasion_driver",
                      "hero_strategy", "meta"):
            d = _intent(self.tags)
            d[extra] = "某内部推理字段不应出现在正式接口"
            errs = intent_schema.validate(d, self.tags, self.tax)
            self.assertTrue(any("unknown top-level field" in e for e in errs), extra)

    def test_valid_output_has_no_extra_field_errors(self):
        errs = intent_schema.validate(_intent(self.tags), self.tags, self.tax)
        self.assertEqual(errs, [])

    def test_primary_driver_extra_field_rejected(self):
        d = _intent(self.tags)
        d["primary_driver"]["core_need"] = "想学会唱歌"
        errs = intent_schema.validate(d, self.tags, self.tax)
        self.assertTrue(any("primary_driver: unknown field" in e for e in errs))

    def test_unresolved_question_extra_field_rejected(self):
        d = _intent(self.tags)
        d["unresolved_question"]["answer_status"] = "partially_answered"
        errs = intent_schema.validate(d, self.tags, self.tax)
        self.assertTrue(any("unresolved_question: unknown field" in e for e in errs))

    def test_evidence_extra_field_rejected(self):
        d = _intent(self.tags)
        ev = copy.deepcopy(d["evidence"][0])
        ev["role"] = "primary_proof"  # new semantic field smuggled into evidence
        d["evidence"] = [ev]
        errs = intent_schema.validate(d, self.tags, self.tax)
        self.assertTrue(any("evidence[0]: unknown field" in e for e in errs))


class _JudgeStub:
    """Stub judge API: returns scripted raw outputs, one per call."""

    def __init__(self, outputs):
        self.outputs = list(outputs)
        self.calls = 0

    def chat(self, system, user_content):
        out = self.outputs[min(self.calls, len(self.outputs) - 1)]
        self.calls += 1
        return out


def _judge_args():
    gt = {"primary_driver_gt": "GT primary", "unresolved_question_gt": "GT question"}
    actual = {"primary_driver": {"statement": "actual primary"},
              "unresolved_question": {"statement": "actual question"}}
    return gt, actual, {}


class JudgeBooleanValidationTests(unittest.TestCase):
    """Judge verdicts must be native JSON booleans — bool("false") == True is
    the silent coercion these tests forbid."""

    def _judge(self, outputs):
        gt, actual, tags = _judge_args()
        api = _JudgeStub(outputs)
        return api, run_intent_benchmark.judge_semantics(
            api, run_intent_benchmark._JUDGE_SYSTEM, gt, actual, tags)

    def test_native_booleans_accepted(self):
        for p, q in ((True, True), (True, False), (False, True), (False, False)):
            api, v = self._judge([json.dumps(
                {"primary_match": p, "question_match": q,
                 "primary_reason": "r", "question_reason": "r"})])
            self.assertIs(v["primary_match"], p)
            self.assertIs(v["question_match"], q)
            self.assertEqual(api.calls, 1)

    def test_string_booleans_rejected(self):
        outputs = [json.dumps({"primary_match": "true", "question_match": "false",
                               "primary_reason": "r", "question_reason": "r"})]
        api = _JudgeStub(outputs)
        gt, actual, tags = _judge_args()
        with self.assertRaises(ValueError) as cm:
            run_intent_benchmark.judge_semantics(
                api, run_intent_benchmark._JUDGE_SYSTEM, gt, actual, tags)
        self.assertIn("native JSON boolean", str(cm.exception))
        self.assertEqual(api.calls, run_intent_benchmark._JUDGE_MAX_ATTEMPTS)

    def test_integer_booleans_rejected(self):
        outputs = [json.dumps({"primary_match": 1, "question_match": 0,
                               "primary_reason": "r", "question_reason": "r"})]
        api = _JudgeStub(outputs)
        gt, actual, tags = _judge_args()
        with self.assertRaises(ValueError):
            run_intent_benchmark.judge_semantics(
                api, run_intent_benchmark._JUDGE_SYSTEM, gt, actual, tags)
        self.assertEqual(api.calls, run_intent_benchmark._JUDGE_MAX_ATTEMPTS)

    def test_missing_fields_rejected(self):
        outputs = [json.dumps({"primary_reason": "r"}),   # both missing
                   json.dumps({"primary_match": True}),     # question missing
                   "not even json"]
        api = _JudgeStub(outputs)
        gt, actual, tags = _judge_args()
        with self.assertRaises(ValueError):
            run_intent_benchmark.judge_semantics(
                api, run_intent_benchmark._JUDGE_SYSTEM, gt, actual, tags)
        self.assertEqual(api.calls, run_intent_benchmark._JUDGE_MAX_ATTEMPTS)

    def test_bounded_retry_recovers_legal_output(self):
        bad = json.dumps({"primary_match": "true", "question_match": "true",
                          "primary_reason": "r", "question_reason": "r"})
        good = json.dumps({"primary_match": True, "question_match": False,
                           "primary_reason": "r", "question_reason": "r"})
        api, v = self._judge([bad, good])
        self.assertIs(v["primary_match"], True)
        self.assertIs(v["question_match"], False)
        self.assertEqual(api.calls, 2)

    def test_runner_records_judge_failed_not_pass(self):
        """A persistently illegal judge output is recorded as judge_failed —
        never silently coerced into a pass."""
        import shutil

        class _IllegalJudgeStub(_StubAPI):
            def chat(self, system, user_content):
                if "语义判定器" in system:
                    return json.dumps({"primary_match": "true",
                                       "question_match": "false",
                                       "primary_reason": "r", "question_reason": "r"})
                text = " ".join(p.get("text", "") for p in user_content
                                 if isinstance(p, dict))
                m = re.search(r'"creative_id":\s*"([^"]+)"', text)
                payload = _intent()
                if m:
                    payload["creative_id"] = m.group(1)
                return json.dumps(payload, ensure_ascii=False)

        tags_root = tempfile.mkdtemp(prefix="intent-judge-tags-")
        od = os.path.join(tags_root, "v01", "run0", "v2")
        os.makedirs(od)
        tags = _tags()
        with open(os.path.join(od, "creative_tags.json"), "w", encoding="utf-8") as f:
            json.dump(tags, f, ensure_ascii=False)

        run_id = "intent-unit-judgefail"
        shutil.rmtree(os.path.join("output", "benchmark-runs", run_id),
                      ignore_errors=True)
        pipe = intent_decision.IntentDecisionPipeline(
            TaggingConfig(), taxonomy.load_taxonomy("singing"),
            api=_IllegalJudgeStub())
        agg = run_intent_benchmark.run_benchmark(tags_root, run_id,
                                                 only=["v01"], pipe=pipe)
        self.assertEqual(agg["completed"], 1)
        self.assertEqual(agg["judge_failed"], 1)
        self.assertEqual(agg["primary_semantic_match"], 0)
        self.assertEqual(agg["question_semantic_match"], 0)
        row = agg["samples"][0]
        self.assertIsNone(row["primary_match"])
        self.assertTrue(row["judge_error"])
        self.assertTrue(row["schema_valid"])  # the decision itself is fine


if __name__ == "__main__":
    unittest.main()
