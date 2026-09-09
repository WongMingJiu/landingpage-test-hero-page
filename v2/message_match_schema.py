#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V2.3 message_match_copy_v1 schema + contract validation.

Strict structural validation for the V2.3 output:
  - message_match_copy_v1 top-level shape (anchors / grounding pack / t1 / t2 / review)
  - T1 12-slot / T2 8-slot exact key sets, loaded from the Frozen Runtime Prompts'
    machine-readable "Slot 契约" JSON blocks (single source of truth — the contracts
    are NOT re-invented here);
  - char budgets, non-empty strings;
  - grounding trace: used_grounding_facts must be verbatim members of the pack;
    used_anchors must map to anchor values;
  - compliance: banned words (dictionary + KB §9 categories), scope and price guards.

First-round benchmark discipline: validators report findings as-is; they never
mutate or auto-fix the model output.
"""
from __future__ import annotations

import json
import os
import re

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
T1_PROMPT = os.path.join(_REPO, "v2", "prompts", "hero_template_t1.md")
T2_PROMPT = os.path.join(_REPO, "v2", "prompts", "hero_template_t2.md")
BANNED_DICT = os.path.join(_REPO, "v2", "compliance", "banned_words_common.json")

T1_SLOT_NAMES = [
    "headline_line_1", "headline_line_2", "subheadline",
    "benefit_1_title", "benefit_1_desc",
    "benefit_2_title", "benefit_2_desc",
    "benefit_3_title", "benefit_3_desc",
    "benefit_4_title", "benefit_4_desc",
    "bottom_banner_text",
]
T2_SLOT_NAMES = [
    "headline_line_1", "headline_line_2", "badge_right",
    "benefit_badge_1", "benefit_badge_2",
    "benefit_badge_3", "benefit_badge_4",
    "bottom_banner_text",
]

# --------------------------------------------------------------------------- #
# Slot contract loading (from the Frozen Runtime Prompts — single source of truth)
# --------------------------------------------------------------------------- #

def load_slot_contract(prompt_path: str) -> dict:
    """Parse the machine-readable ``Slot 契约`` JSON block of a frozen template prompt."""
    with open(prompt_path, encoding="utf-8") as f:
        text = f.read()
    m = re.search(r"## Slot 契约（机器可读）\s*```json\s*(\{.*?\})\s*```", text, re.DOTALL)
    if not m:
        raise ValueError(f"slot contract block not found in {prompt_path}")
    block = json.loads(m.group(1))
    return {s["name"]: s for s in block["dynamic_slots"]}


def load_compliance_lists() -> dict:
    """Load the common banned-words dictionary."""
    with open(BANNED_DICT, encoding="utf-8") as f:
        data = json.load(f)
    return data


# KB §9 / scope / price / CTA / health guards (mirrors the knowledge base text)
ABSOLUTE_WORDS = [
    "最佳", "最好", "最优", "最强", "第一", "唯一", "首选", "顶级", "顶尖",
    "极致", "绝对", "国家级", "世界级", "全网最低", "史无前例", "万能",
    "首席", "冠军", "全国领先", "全国第一",
]
FALSE_PROMISE_WORDS = [
    "保证", "100%", "包教包会", "包学会", "永远", "根治", "一步到位",
    "速成", "立竿见影", "药到病除", "零风险", "无副作用",
]
FEAR_MARKETING_WORDS = [
    "不买后悔", "错过再无", "限时秒杀", "仅剩", "不买就亏",
    "别人都在学", "不学就落后",
]
HEALTH_WORDS = [
    "肺功能", "老年痴呆", "抗衰老", "更年期", "治疗", "咽炎", "疾病",
    "缓解疼痛",
]
AUTHORITY_WORDS = [
    "驰名商标", "央视", "政府指定", "专家推荐", "名医", "大师", "人民大会堂",
]
CTA_WORDS = ["立即", "点击", "报名", "试听"]
SCOPE_OUT_WORDS = [
    "28天", "28 天", "21天", "21 天", "正式营", "1V9", "三师", "永久回放",
    "礼盒", "麦克风", "曲谱集", "K歌音箱", "识谱唱谱", "MV营",
]
PRICE_WORDS = ["免费领", "免费学", "优惠", "折扣", "限时价", "秒杀", "低价", "打折", "半价"]
_PRICE_PATTERN = re.compile(r"\d\s*元|[0-9一二三四五六七八九十百千万]+元")

# KB §13 legacy ruling: "告别" is restricted to neutral expressions in Hero copy
# (e.g. course title "告别大白嗓" must surface as "改善大白嗓问题" in Dynamic Copy).
NEUTRALIZATION_WORDS = ["告别"]


def validate_schema(obj: dict) -> list:
    """Structural validation of message_match_copy_v1. Returns a list of errors."""
    errs: list = []

    if obj.get("schema_version") != "message_match_copy_v1":
        errs.append(f"schema_version != message_match_copy_v1 (got {obj.get('schema_version')!r})")
    if not obj.get("creative_id"):
        errs.append("creative_id missing/empty")

    # -- creative anchors -------------------------------------------------- #
    anchors = obj.get("creative_anchors")
    if not isinstance(anchors, dict):
        errs.append("creative_anchors missing or not an object")
    else:
        for key in ("topics", "phrases"):
            items = anchors.get(key)
            if not isinstance(items, list) or not items:
                errs.append(f"creative_anchors.{key} missing/empty")
                continue
            for i, it in enumerate(items):
                if not isinstance(it, dict) or not it.get("value") or not it.get("evidence"):
                    errs.append(f"creative_anchors.{key}[{i}] needs value+evidence")
        for key in ("user_concern", "expectation"):
            it = anchors.get(key)
            if not isinstance(it, dict) or not it.get("value") or not it.get("evidence"):
                errs.append(f"creative_anchors.{key} needs value+evidence")

    # -- grounding pack ----------------------------------------------------- #
    pack = obj.get("product_grounding_pack")
    if not isinstance(pack, dict):
        errs.append("product_grounding_pack missing or not an object")
        pack = {}
    if pack.get("grounding_status") not in ("sufficient", "partial", "insufficient"):
        errs.append(f"grounding_status invalid: {pack.get('grounding_status')!r}")
    limits = {"course_facts": 3, "service_facts": 3, "teacher_facts": 2, "allowed_song_refs": 1}
    for key, cap in limits.items():
        items = pack.get(key)
        if not isinstance(items, list):
            errs.append(f"grounding_pack.{key} missing/not a list")
            continue
        if len(items) > cap:
            errs.append(f"grounding_pack.{key} exceeds cap ({len(items)} > {cap})")
        if key.endswith("_facts"):
            for i, it in enumerate(items):
                if (not isinstance(it, dict) or not it.get("statement")
                        or not it.get("source_section") or not it.get("relevance")):
                    errs.append(f"grounding_pack.{key}[{i}] needs statement+source_section+relevance")

    # -- t1 / t2 ------------------------------------------------------------ #
    expected = {
        "t1": ("hero_template_t1", T1_SLOT_NAMES),
        "t2": ("hero_template_t2", T2_SLOT_NAMES),
    }
    for side, (tid, slot_names) in expected.items():
        node = obj.get(side)
        if not isinstance(node, dict):
            errs.append(f"{side} missing or not an object")
            continue
        if node.get("template_id") != tid:
            errs.append(f"{side}.template_id != {tid} (got {node.get('template_id')!r})")
        slots = node.get("slots")
        if not isinstance(slots, dict):
            errs.append(f"{side}.slots missing or not an object")
            continue
        extra = set(slots) - set(slot_names)
        missing = set(slot_names) - set(slots)
        if extra:
            errs.append(f"{side}.slots has extra keys: {sorted(extra)}")
        if missing:
            errs.append(f"{side}.slots missing keys: {sorted(missing)}")
        for name in slot_names:
            v = slots.get(name)
            if not isinstance(v, str) or not v.strip():
                errs.append(f"{side}.slots.{name} empty/not a string")
        for key in ("used_anchors", "used_grounding_facts"):
            if not isinstance(node.get(key), list):
                errs.append(f"{side}.{key} missing/not a list")

    # -- review ------------------------------------------------------------- #
    review = obj.get("review")
    if not isinstance(review, dict) or not isinstance(review.get("needed"), bool):
        errs.append("review.needed must be a native boolean")
    return errs


def validate_slot_contract(obj: dict, t1_contract: dict, t2_contract: dict) -> list:
    """Char-budget validation directly from the Frozen contracts' dynamic_slots.

    Char count excludes whitespace (e.g. ``"身体\n发声"`` = 4 chars, within the
    ≤4 budget). The T2 "2+2 two-line" badge form is a downstream RENDERING
    concern — the Frozen contract's ``lines: 2`` refers to display lines, and
    fixture values carry no newline. Since round 2 the generation prompt
    requires single-line plain-text values, so a raw ``\n`` inside a slot value
    is reported as a contract violation.
    """
    errs: list = []
    for side, contract in (("t1", t1_contract), ("t2", t2_contract)):
        slots = (obj.get(side) or {}).get("slots") or {}
        for name, spec in contract.items():
            v = slots.get(name)
            if not isinstance(v, str) or not v.strip():
                continue  # already reported by validate_schema
            if "\n" in v:
                errs.append(f"{side}.slots.{name} contains a newline separator: {v!r}")
            n_chars = len(re.sub(r"\s+", "", v))
            if n_chars > spec["max_chars"]:
                errs.append(f"{side}.slots.{name} exceeds budget: {n_chars} > {spec['max_chars']} ({v!r})")
    return errs


def newline_slot_values(obj: dict) -> list:
    """Observation: slots whose raw value embeds a newline separator."""
    out: list = []
    for side in ("t1", "t2"):
        slots = (obj.get(side) or {}).get("slots") or {}
        for name, value in slots.items():
            if isinstance(value, str) and "\n" in value:
                out.append(f"{side}.slots.{name}={value!r}")
    return out


def validate_grounding_trace(obj: dict) -> list:
    """used_grounding_facts must be verbatim pack statements; used_anchors must map
    to anchor values."""
    errs: list = []
    pack = obj.get("product_grounding_pack") or {}
    statements = set()
    for key in ("course_facts", "service_facts", "teacher_facts"):
        for it in pack.get(key) or []:
            if isinstance(it, dict) and it.get("statement"):
                statements.add(it["statement"])
    anchors = obj.get("creative_anchors") or {}
    anchor_values = set()
    for it in anchors.get("topics") or []:
        if isinstance(it, dict) and it.get("value"):
            anchor_values.add(it["value"])
    for it in anchors.get("phrases") or []:
        if isinstance(it, dict) and it.get("value"):
            anchor_values.add(it["value"])
    for key in ("user_concern", "expectation"):
        it = anchors.get(key)
        if isinstance(it, dict) and it.get("value"):
            anchor_values.add(it["value"])
            # allow core words of the concern/expectation sentences as anchors too
            for ch in ("，", "。", "、", "；"):
                anchor_values.update(p.strip() for p in it["value"].split(ch) if p.strip())

    for side in ("t1", "t2"):
        node = obj.get(side) or {}
        for fact in node.get("used_grounding_facts") or []:
            if fact not in statements:
                errs.append(f"{side}.used_grounding_facts item not found in pack: {fact!r}")
        for anchor in node.get("used_anchors") or []:
            if anchor not in anchor_values:
                errs.append(f"{side}.used_anchors item not an anchor value: {anchor!r}")
    return errs


def validate_compliance(obj: dict, banned_dict: dict) -> list:
    """Banned/scope/price/CTA words across ALL T1+T2 dynamic slots."""
    errs: list = []
    dicts = banned_dict.get("banned_words", [])
    groups = {
        "banned_dict": dicts,
        "absolute": ABSOLUTE_WORDS,
        "false_promise": FALSE_PROMISE_WORDS,
        "fear_marketing": FEAR_MARKETING_WORDS,
        "health": HEALTH_WORDS,
        "authority": AUTHORITY_WORDS,
        "cta": CTA_WORDS,
        "scope_out": SCOPE_OUT_WORDS,
        "price": PRICE_WORDS,
        "neutralization": NEUTRALIZATION_WORDS,
    }
    for side in ("t1", "t2"):
        slots = (obj.get(side) or {}).get("slots") or {}
        for name, value in slots.items():
            if not isinstance(value, str):
                continue
            for group, words in groups.items():
                for w in words:
                    if w in value:
                        errs.append(f"{side}.slots.{name} contains [{group}] word {w!r}: {value!r}")
            if _PRICE_PATTERN.search(value):
                errs.append(f"{side}.slots.{name} contains a price-like pattern: {value!r}")
    return errs
