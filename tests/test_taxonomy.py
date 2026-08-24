#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Unit tests for v2.taxonomy (fail-fast completeness + prompt rendering)."""
import json
import os
import tempfile
import unittest

from v2 import taxonomy


class TaxonomyLoadTests(unittest.TestCase):
    def setUp(self):
        self.td = taxonomy.load_taxonomy("singing")

    def test_counts_match_spec(self):
        self.assertEqual(len(self.td.value_labels), 36)
        self.assertEqual(len(self.td.opening_labels), 18)
        self.assertEqual(len(self.td.expectation_labels), 15)
        self.assertEqual(len(self.td.opening_decision_priority), 18)
        self.assertEqual(len(self.td.active_limits), 7)

    def test_active_caps_match_spec_6_4(self):
        caps = self.td.active_limits
        self.assertEqual(caps["演唱能力"], 3)
        self.assertEqual(caps["心理障碍突破"], 2)
        self.assertEqual(caps["学习降阻"], 2)
        self.assertEqual(caps["专业认知提升"], 2)
        self.assertEqual(caps["社交价值"], 1)
        self.assertEqual(caps["信任保障"], 1)
        self.assertEqual(caps["课程权益"], 2)

    def test_value_category_lookup(self):
        self.assertEqual(self.td.value_category_of("获得专业指导"), "信任保障")
        self.assertEqual(self.td.value_category_of("方法简单易操作"), "学习降阻")
        self.assertIsNone(self.td.value_category_of("不存在的标签"))

    def test_undetermined_expectation_label_exact_string(self):
        self.assertIn("无法判断（对于这种情况给一个候选）", self.td.expectation_labels)

    def test_decision_priority_output_types_all_valid(self):
        for row in self.td.opening_decision_priority:
            self.assertTrue(self.td.is_opening_label(row["output_type"]), row)
        # correction #2: runtime order begins 强拦截口播型, 效果对比型, 教学演示型, 演唱效果型, 反常识/悬念型
        first_five = [r["output_type"] for r in self.td.opening_decision_priority[:5]]
        self.assertEqual(first_five,
                         ["强拦截口播型", "效果对比型", "教学演示型", "演唱效果型", "反常识/悬念型"])

    def test_render_blocks_contain_definitions_not_bare_enums(self):
        rv = self.td.render_value()
        ro = self.td.render_opening()
        re_ = self.td.render_expectation()
        for label in self.td.value_labels:
            self.assertIn(label, rv)
        for label in self.td.opening_labels:
            self.assertIn(label, ro)
        for label in self.td.expectation_labels:
            self.assertIn(label, re_)
        # descriptions present, not bare labels only
        self.assertIn("帮助用户", rv)  # description text marker
        self.assertIn("决策优先级", ro)


class TaxonomyFailFastTests(unittest.TestCase):
    def _write(self, obj, name):
        d = tempfile.mkdtemp()
        sub = os.path.join(d, "singing")
        os.makedirs(sub)
        with open(os.path.join(sub, name), "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False)
        return d

    def test_missing_description_raises(self):
        td = taxonomy.load_taxonomy("singing")
        bad_value = json.loads(json.dumps(td.value, ensure_ascii=False))
        bad_value["categories"][0]["labels"][0]["description"] = ""
        base = self._write(bad_value, "value.json")
        # copy the other two
        for fn in ("opening.json", "user_expectation.json"):
            with open(os.path.join(taxonomy.TAXONOMY_DIR, "singing", fn), encoding="utf-8") as f:
                data = json.load(f)
            with open(os.path.join(base, "singing", fn), "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False)
        old = taxonomy.TAXONOMY_DIR
        taxonomy.TAXONOMY_DIR = base
        try:
            with self.assertRaises(taxonomy.TaxonomyError):
                taxonomy.load_taxonomy("singing")
        finally:
            taxonomy.TAXONOMY_DIR = old


if __name__ == "__main__":
    unittest.main()
