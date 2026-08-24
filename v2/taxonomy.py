#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V2.1a taxonomy loader.

Faithfully loads the canonical taxonomy JSON (transcribed from
docs/taxonomy/*-v1.0.md) and enforces fail-fast completeness: a label with
empty description/examples/signals is a hard error — we never feed a bare
enum to the model.

Per Phase A correction #2 (Opening priority): the runtime conflict resolver
is the explicit ``decision_priority`` table (spec §8.6 / opening taxonomy
doc 决策优先级), NOT the ``default_priority`` column. ``default_priority``
is retained only as source metadata.
"""
from __future__ import annotations

import json
import os
from typing import Any

TAXONOMY_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "taxonomy")


class TaxonomyError(Exception):
    """Raised when taxonomy content is missing/malformed."""


def _load_json(path: str) -> dict:
    if not os.path.isfile(path):
        raise TaxonomyError(f"taxonomy file not found: {path}")
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        raise TaxonomyError(f"taxonomy JSON invalid: {path}: {e}") from e


def _require_nonempty_str(obj: dict, field: str, where: str) -> None:
    v = obj.get(field)
    if not isinstance(v, str) or not v.strip():
        raise TaxonomyError(f"taxonomy {where}: field '{field}' is missing/empty")


def _require_nonempty_list(obj: dict, field: str, where: str) -> None:
    v = obj.get(field)
    if not isinstance(v, list) or not v:
        raise TaxonomyError(f"taxonomy {where}: field '{field}' must be a non-empty list")


# --------------------------------------------------------------------------- #
# Value taxonomy
# --------------------------------------------------------------------------- #
def _validate_value(value: dict) -> None:
    cats = value.get("categories")
    if not isinstance(cats, list) or not cats:
        raise TaxonomyError("value taxonomy: 'categories' missing/empty")
    for c in cats:
        cw = f"value category '{c.get('category')}'"
        _require_nonempty_str(c, "category", cw)
        if not isinstance(c.get("active_limit"), int) or c["active_limit"] < 0:
            raise TaxonomyError(f"{cw}: 'active_limit' must be a non-negative int")
        labels = c.get("labels")
        if not isinstance(labels, list) or not labels:
            raise TaxonomyError(f"{cw}: 'labels' missing/empty")
        for lab in labels:
            lw = f"value label '{lab.get('label')}'"
            _require_nonempty_str(lab, "label", lw)
            _require_nonempty_str(lab, "description", lw)
            _require_nonempty_list(lab, "examples", lw)
            if lab.get("mvp_enabled") is not True:
                raise TaxonomyError(f"{lw}: 'mvp_enabled' must be true (only MVP-enabled labels are canonical)")


# --------------------------------------------------------------------------- #
# Opening taxonomy
# --------------------------------------------------------------------------- #
def _validate_opening(opening: dict) -> None:
    types = opening.get("types")
    if not isinstance(types, list) or not types:
        raise TaxonomyError("opening taxonomy: 'types' missing/empty")
    for t in types:
        tw = f"opening type '{t.get('label')}'"
        _require_nonempty_str(t, "label", tw)
        _require_nonempty_str(t, "definition", tw)
        _require_nonempty_list(t, "script_signals", tw)
        _require_nonempty_list(t, "visual_signals", tw)
        _require_nonempty_str(t, "user_expectation", tw)
        if not isinstance(t.get("default_priority"), int):
            raise TaxonomyError(f"{tw}: 'default_priority' must be int (source metadata)")
    dp = opening.get("decision_priority")
    if not isinstance(dp, list) or not dp:
        raise TaxonomyError("opening taxonomy: 'decision_priority' missing/empty")
    type_labels = {t["label"] for t in types}
    for row in dp:
        rw = f"decision_priority rank {row.get('rank')}"
        if not isinstance(row.get("rank"), int):
            raise TaxonomyError(f"{rw}: 'rank' must be int")
        for f in ("script_condition", "visual_condition", "output_type", "note"):
            _require_nonempty_str(row, f, rw)
        if row["output_type"] not in type_labels:
            raise TaxonomyError(f"{rw}: output_type '{row['output_type']}' not in opening types")


# --------------------------------------------------------------------------- #
# User expectation taxonomy
# --------------------------------------------------------------------------- #
def _validate_user_expectation(ue: dict) -> None:
    labels = ue.get("labels")
    if not isinstance(labels, list) or not labels:
        raise TaxonomyError("user_expectation taxonomy: 'labels' missing/empty")
    for lab in labels:
        lw = f"expectation label '{lab.get('label')}'"
        _require_nonempty_str(lab, "label", lw)
        _require_nonempty_str(lab, "description", lw)
        _require_nonempty_list(lab, "signals", lw)
        _require_nonempty_list(lab, "examples", lw)
        _require_nonempty_list(lab, "exclusion_rules", lw)


# --------------------------------------------------------------------------- #
# Container
# --------------------------------------------------------------------------- #
class TaxonomyData:
    """Loaded + validated taxonomy with fast lookup helpers and prompt rendering."""

    def __init__(self, value: dict, opening: dict, user_expectation: dict):
        self.value = value
        self.opening = opening
        self.user_expectation = user_expectation

        self.value_labels: list[str] = [
            lab["label"] for c in value["categories"] for lab in c["labels"]
        ]
        self.value_label_to_category: dict[str, str] = {
            lab["label"]: c["category"]
            for c in value["categories"]
            for lab in c["labels"]
        }
        self.value_label_defs: dict[str, dict] = {
            lab["label"]: lab for c in value["categories"] for lab in c["labels"]
        }
        self.active_limits: dict[str, int] = {
            c["category"]: c["active_limit"] for c in value["categories"]
        }

        self.opening_labels: list[str] = [t["label"] for t in opening["types"]]
        self.opening_defs: dict[str, dict] = {t["label"]: t for t in opening["types"]}
        self.opening_decision_priority: list[dict] = opening["decision_priority"]
        self.opening_recognition_rules: list[dict] = opening.get("recognition_rules", [])

        self.expectation_labels: list[str] = [l["label"] for l in user_expectation["labels"]]
        self.expectation_defs: dict[str, dict] = {l["label"]: l for l in user_expectation["labels"]}

        # sanity: no duplicate value labels
        if len(set(self.value_labels)) != len(self.value_labels):
            dupes = [x for x in self.value_labels if self.value_labels.count(x) > 1]
            raise TaxonomyError(f"duplicate value labels: {sorted(set(dupes))}")

    # membership ----------------------------------------------------------- #
    def is_value_label(self, label: str) -> bool:
        return label in self.value_label_to_category

    def value_category_of(self, label: str) -> str | None:
        return self.value_label_to_category.get(label)

    def is_opening_label(self, label: str) -> bool:
        return label in self.opening_defs

    def is_expectation_label(self, label: str) -> bool:
        return label in self.expectation_defs

    # --------------------------------------------------------------------- #
    # Prompt rendering — keeps a single source of truth; no label is reduced
    # to a bare enum in the prompt.
    # --------------------------------------------------------------------- #
    @staticmethod
    def _join(items: list[str]) -> str:
        return "、".join(items)

    def render_value(self) -> str:
        lines: list[str] = []
        for c in self.value["categories"]:
            lines.append(f"### 一级类：{c['category']}（Active 上限 {c['active_limit']}）")
            for lab in c["labels"]:
                ex = self._join(lab["examples"])
                lines.append(f"- **{lab['label']}**：{lab['description']}（识别示例：{ex}）")
            lines.append("")
        return "\n".join(lines).rstrip()

    def render_opening(self) -> str:
        lines: list[str] = ["### 片头综合类型定义", ""]
        for t in self.opening["types"]:
            lines.append(
                f"- **{t['label']}**（默认优先级 {t['default_priority']}，仅作元数据）："
                f"{t['definition']}"
            )
            lines.append(f"  - 主要脚本信号：{self._join(t['script_signals'])}")
            lines.append(f"  - 主要分镜信号：{self._join(t['visual_signals'])}")
            lines.append(f"  - 用户期待：{t['user_expectation']}")
            lines.append(f"  - 建议关注指标：{self._join(t['metrics'])}")
        lines.append("")
        lines.append("### 识别方式 / MVP 规则")
        for r in self.opening_recognition_rules:
            lines.append(f"- **{r['rule']}**：{r['mvp_rule']}")
        lines.append("")
        lines.append("### 决策优先级（运行时候选冲突解决依据；数值越小越优先）")
        for d in self.opening_decision_priority:
            lines.append(
                f"{d['rank']}. 脚本「{d['script_condition']}」+ 分镜「{d['visual_condition']}」"
                f" → **{d['output_type']}**（{d['note']}）"
            )
        lines.append("")
        lines.append(
            "注意：决策优先级仅用于**同一有效开头单元内多候选策略**的决胜，"
            "不允许后段信息覆盖已经成立的前段主权。"
        )
        return "\n".join(lines).rstrip()

    def render_expectation(self) -> str:
        lines: list[str] = ["### 用户期待标签定义", ""]
        for lab in self.user_expectation["labels"]:
            lines.append(f"- **{lab['label']}**：{lab['description']}")
            lines.append(f"  - 主要识别信号：{self._join(lab['signals'])}")
            lines.append(f"  - 识别示例：{self._join(lab['examples'])}")
            lines.append(f"  - 排除/边界规则：{self._join(lab['exclusion_rules'])}")
        return "\n".join(lines).rstrip()


def load_taxonomy(category: str = "singing") -> TaxonomyData:
    """Load and validate the three canonical taxonomy files for a category."""
    base = os.path.join(TAXONOMY_DIR, category)
    value = _load_json(os.path.join(base, "value.json"))
    opening = _load_json(os.path.join(base, "opening.json"))
    ue = _load_json(os.path.join(base, "user_expectation.json"))
    _validate_value(value)
    _validate_opening(opening)
    _validate_user_expectation(ue)
    return TaxonomyData(value, opening, ue)


if __name__ == "__main__":
    td = load_taxonomy("singing")
    print(f"value={len(td.value_labels)} opening={len(td.opening_labels)} "
          f"expectation={len(td.expectation_labels)} decision_priority={len(td.opening_decision_priority)}")
