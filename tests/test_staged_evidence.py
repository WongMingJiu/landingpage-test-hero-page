#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Unit tests for the structured staged-evidence layer (pure, no API).

Covers the stabilization iteration: free-text notes were replaced by
structured evidence extraction + constrained final adjudication.
"""
import json
import unittest

from v2 import tagging


class TimeParseTests(unittest.TestCase):
    def test_seconds_style(self):
        self.assertEqual(tagging._time_start_seconds("3.5-8s"), 3.5)

    def test_clock_style(self):
        self.assertEqual(tagging._time_start_seconds("00:12-00:15"), 12.0)

    def test_unparseable_sorts_last(self):
        self.assertEqual(tagging._time_start_seconds(""), 10 ** 6)
        self.assertEqual(tagging._time_start_seconds("未知"), 10 ** 6)


class NormalizeObservationsTests(unittest.TestCase):
    def test_valid_json_normalized(self):
        raw = json.dumps({"observations": [
            {"time": "00:02-00:05", "source": "subtitle", "fact": "小方法：抬眉瞪眼",
             "candidates": {"opening": ["教学演示型"], "value": ["方法简单易操作"]},
             "adjacent": "有跟做动作"},
            {"time": "00:00-00:02", "source": "visual", "fact": "两人持麦演唱"},
        ]}, ensure_ascii=False)
        obs = tagging._normalize_observations(raw, "秒0-10")
        self.assertEqual(len(obs), 2)
        self.assertEqual(obs[0]["source"], "subtitle")
        self.assertEqual(obs[0]["candidates"]["opening"], ["教学演示型"])
        self.assertIsNone(obs[1]["adjacent"])
        self.assertEqual(obs[0]["window"], "秒0-10")

    def test_invalid_source_coerced(self):
        raw = json.dumps({"observations": [
            {"time": "0s", "source": "audio", "fact": "推断在唱歌"}]})
        obs = tagging._normalize_observations(raw, "秒0-10")
        self.assertEqual(obs[0]["source"], "visual")  # audio never allowed

    def test_empty_fact_dropped(self):
        raw = json.dumps({"observations": [{"time": "0s", "source": "visual", "fact": "  "}]})
        self.assertEqual(tagging._normalize_observations(raw, "秒0-10"), [])

    def test_invalid_json_degrades_not_drops(self):
        obs = tagging._normalize_observations("完全不是 JSON 的笔记文本", "秒0-10")
        self.assertEqual(len(obs), 1)
        self.assertTrue(obs[0]["unparsed"])
        self.assertIn("笔记文本", obs[0]["fact"])

    def test_missing_observations_key_degrades(self):
        obs = tagging._normalize_observations('{"foo": 1}', "秒0-10")
        self.assertEqual(len(obs), 1)
        self.assertTrue(obs[0]["unparsed"])


class DeterministicMergeTests(unittest.TestCase):
    def _obs(self):
        return [
            {"time": "00:10-00:12", "source": "visual", "fact": "B 后段",
             "candidates": {}, "adjacent": None, "window": "秒10-20"},
            {"time": "00:00-00:03", "source": "subtitle", "fact": "A 开场横幅",
             "candidates": {"opening": ["低门槛领取型"]}, "adjacent": None, "window": "秒0-10"},
            {"time": "00:00-00:03", "source": "subtitle", "fact": "A 开场横幅",
             "candidates": {}, "adjacent": None, "window": "秒0-10"},
        ]

    def test_sort_and_dedupe(self):
        obs = sorted(self._obs(),
                     key=lambda o: (tagging._time_start_seconds(o["time"]), o["source"], o["fact"]))
        seen, deduped = set(), []
        for o in obs:
            k = (o["time"], o["source"], o["fact"])
            if k not in seen:
                seen.add(k)
                deduped.append(o)
        self.assertEqual(len(deduped), 2)
        self.assertEqual(deduped[0]["fact"], "A 开场横幅")  # time order, not input order

    def test_merge_content_deterministic(self):
        obs = tagging._normalize_observations(json.dumps({"observations": [
            {"time": "00:05-00:09", "source": "visual", "fact": "老师示范"},
            {"time": "00:00-00:04", "source": "transcript", "fact": "口播开场"}]},
            ensure_ascii=False), "秒0-10")
        c1 = tagging._merge_user_content(obs, [{"start": 0.0, "end": 2.0, "text": "你好"}])
        c2 = tagging._merge_user_content(list(obs), [{"start": 0.0, "end": 2.0, "text": "你好"}])
        t1 = json.dumps(c1, ensure_ascii=False)
        t2 = json.dumps(c2, ensure_ascii=False)
        self.assertEqual(t1, t2)

    def test_merge_content_no_benchmark_hardcoding(self):
        obs = tagging._normalize_observations(json.dumps({"observations": [
            {"time": "0s", "source": "visual", "fact": "x"}]}), "秒0-10")
        text = json.dumps(tagging._merge_user_content(obs, []), ensure_ascii=False)
        for vid in ("v01", "v02", "v03", "v04", "v05", "v06", "v07", "v08", "v09", "v10"):
            self.assertNotIn(vid, text)

    def test_render_one_line_per_observation(self):
        obs = tagging._normalize_observations(json.dumps({"observations": [
            {"time": "00:00-00:04", "source": "visual", "fact": "a",
             "candidates": {"value": ["零基础可学"]}, "adjacent": "无学员身份"},
            {"time": "00:05-00:09", "source": "subtitle", "fact": "b"}]},
            ensure_ascii=False), "秒0-10")
        rendered = tagging._render_observations(obs)
        self.assertEqual(rendered.count("\n"), 1)
        self.assertIn("候选信号", rendered)
        self.assertIn("相邻区分", rendered)


class StagedEvidenceCollectionTests(unittest.TestCase):
    def test_collect_dedupes_across_batches_and_orders(self):
        class FakeApi:
            def __init__(self):
                self.calls = 0

            def chat(self, system, content):
                self.calls += 1
                # both batches report the same observation -> must dedupe to 1
                return json.dumps({"observations": [
                    {"time": "00:00-00:02", "source": "visual", "fact": "同一事实"},
                    {"time": f"00:0{self.calls}-00:0{self.calls + 1}", "source": "visual",
                     "fact": f"批{self.calls}独有"}]}, ensure_ascii=False)

        fr = [{"sec": s, "b64": ""} for s in range(0, 8)]
        obs = tagging._collect_staged_evidence(FakeApi(), fr, [])
        facts = [o["fact"] for o in obs]
        self.assertEqual(facts.count("同一事实"), 1)
        # sorted by start second: 0s first
        self.assertEqual(obs[0]["fact"], "同一事实")


if __name__ == "__main__":
    unittest.main()
