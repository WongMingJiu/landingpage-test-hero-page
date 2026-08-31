#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V2.1b output schema validator (creative_intent_v1, spec §3).

Validates the Intent Decision output against the input creative_tags.json:
- closed schema: only the seven formal top-level fields are accepted;
  internal reasoning frames (core_need / barrier / ...) are rejected;
- primary_driver / unresolved_question are single closed objects with
  complete natural-language statements (a bare taxonomy label is rejected);
- supporting_drivers is 0-2 strings;
- intent_strength is a three-value enum, judged independently of confidence;
- every evidence item must be a verbatim item of the input's evidence
  (same time/source/content, no extra semantic fields) — no fabricated
  facts (Rule 7).

The validator never repairs business semantics; it only accepts or rejects.
"""
from __future__ import annotations

from typing import Any

from .taxonomy import TaxonomyData

SCHEMA_VERSION = "creative_intent_v1"

_CONFIDENCE = {"high", "medium", "low"}
_STRENGTH = {"strong", "medium", "weak"}
_MAX_SUPPORTING = 2
_MIN_STATEMENT_CHARS = 10  # a complete proposition, not a bare label

# Closed schema (spec §3): creative_intent_v1 accepts exactly these fields.
# Internal reasoning frames (core_need / barrier / persuasion_driver /
# hero_strategy / ...) may guide the model's thinking but must NOT surface
# in the formal interface.
_TOP_LEVEL_FIELDS = {"schema_version", "creative_id", "primary_driver",
                     "unresolved_question", "intent_strength",
                     "supporting_drivers", "evidence"}
_STATEMENT_FIELDS = {"statement", "confidence"}
# Evidence keeps the V2.1a structure verbatim: time / source / content.
_EVIDENCE_FIELDS = {"time", "source", "content"}


def input_evidence_index(tags: dict) -> list[dict]:
    """All evidence items of the input creative_tags.json, in stable order."""
    items: list[dict] = []
    for m in tags.get("matched_value_tags") or []:
        if isinstance(m, dict):
            items.extend(e for e in (m.get("evidence") or []) if isinstance(e, dict))
    for key in ("opening_type", "user_expectation"):
        node = tags.get(key)
        if isinstance(node, dict):
            items.extend(e for e in (node.get("evidence") or []) if isinstance(e, dict))
    return items


def _ev_key(item: dict) -> tuple:
    return (str(item.get("time") or ""), str(item.get("source") or ""),
            str(item.get("content") or ""))


def _validate_statement(node: Any, where: str, tax: TaxonomyData,
                        errs: list[str]) -> None:
    if not isinstance(node, dict):
        errs.append(f"{where}: must be an object")
        return
    extra = set(node.keys()) - _STATEMENT_FIELDS
    if extra:
        errs.append(f"{where}: unknown field(s) {sorted(extra)} — closed schema, "
                    f"only {sorted(_STATEMENT_FIELDS)} are allowed")
    s = node.get("statement")
    if not isinstance(s, str) or not s.strip():
        errs.append(f"{where}.statement: must be a non-empty string")
        s = None
    else:
        s = s.strip()
        if len(s) < _MIN_STATEMENT_CHARS:
            errs.append(f"{where}.statement: too short for a complete proposition "
                        f"(>= {_MIN_STATEMENT_CHARS} chars required, got {len(s)})")
        if tax.is_value_label(s) or tax.is_opening_label(s) or tax.is_expectation_label(s):
            errs.append(f"{where}.statement: bare taxonomy label {s!r} is not a "
                        f"complete natural-language proposition")
    if node.get("confidence") not in _CONFIDENCE:
        errs.append(f"{where}.confidence: must be one of {sorted(_CONFIDENCE)}, "
                    f"got {node.get('confidence')!r}")


def validate(data: Any, tags: dict, tax: TaxonomyData) -> list[str]:
    """Return error strings; empty list = valid. ``tags`` is the input
    creative_tags.json used for evidence grounding."""
    errs: list[str] = []
    if not isinstance(data, dict):
        return ["output must be a JSON object"]

    if data.get("schema_version") != SCHEMA_VERSION:
        errs.append(f"'schema_version' must be {SCHEMA_VERSION!r}, "
                    f"got {data.get('schema_version')!r}")

    # closed schema: no extra top-level fields (spec §3)
    extra_top = set(data.keys()) - _TOP_LEVEL_FIELDS
    if extra_top:
        errs.append(f"unknown top-level field(s) {sorted(extra_top)} — "
                    f"creative_intent_v1 is a closed schema; allowed fields are "
                    f"{sorted(_TOP_LEVEL_FIELDS)}; internal reasoning frames "
                    f"(core_need / barrier / persuasion_driver / hero_strategy ...) "
                    f"must not enter the formal interface")

    cid = data.get("creative_id")
    if not isinstance(cid, str) or not cid.strip():
        errs.append("'creative_id' must be a non-empty string")
    elif str(cid) != str(tags.get("creative_id") or ""):
        errs.append(f"'creative_id' {cid!r} does not match input "
                    f"{tags.get('creative_id')!r}")

    # primary_driver: exactly one object (uniqueness is structural)
    if "primary_driver" not in data:
        errs.append("'primary_driver' is required (exactly one)")
    else:
        _validate_statement(data.get("primary_driver"), "primary_driver", tax, errs)

    # unresolved_question: exactly one object
    if "unresolved_question" not in data:
        errs.append("'unresolved_question' is required (exactly one)")
    else:
        _validate_statement(data.get("unresolved_question"), "unresolved_question", tax, errs)

    # intent_strength enum (independent of confidence)
    if data.get("intent_strength") not in _STRENGTH:
        errs.append(f"'intent_strength' must be one of {sorted(_STRENGTH)}, "
                    f"got {data.get('intent_strength')!r}")

    # supporting_drivers: 0-2 non-empty strings
    sup = data.get("supporting_drivers")
    if not isinstance(sup, list):
        errs.append("'supporting_drivers' must be a list")
    else:
        if len(sup) > _MAX_SUPPORTING:
            errs.append(f"supporting_drivers: {len(sup)} exceeds limit {_MAX_SUPPORTING}")
        for i, s in enumerate(sup):
            if not isinstance(s, str) or not s.strip():
                errs.append(f"supporting_drivers[{i}]: must be a non-empty string")

    # evidence: non-empty, every item verbatim from the input (Rule 7)
    ev = data.get("evidence")
    if not isinstance(ev, list) or not ev:
        errs.append("'evidence' must be a non-empty list")
    else:
        allowed = {_ev_key(e) for e in input_evidence_index(tags)}
        for i, item in enumerate(ev):
            iw = f"evidence[{i}]"
            if not isinstance(item, dict):
                errs.append(f"{iw}: must be an object")
                continue
            extra = set(item.keys()) - _EVIDENCE_FIELDS
            if extra:
                errs.append(f"{iw}: unknown field(s) {sorted(extra)} — evidence "
                            f"must keep the V2.1a structure "
                            f"{sorted(_EVIDENCE_FIELDS)} without new semantic "
                            f"fields")
            if _ev_key(item) not in allowed:
                errs.append(f"{iw}: not present verbatim in the input "
                            f"creative_tags.json evidence (fabricated evidence is "
                            f"forbidden — Rule 7); got time={item.get('time')!r} "
                            f"source={item.get('source')!r}")

    return errs


def is_valid(data: Any, tags: dict, tax: TaxonomyData) -> bool:
    return not validate(data, tags, tax)
