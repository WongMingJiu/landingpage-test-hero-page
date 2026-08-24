#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V2.1a output schema validator.

Validates ``creative_tagging_v1`` exactly as frozen in spec §11, with the
match/active constraints of §6.4, the extension consistency of §12, and the
Phase A correction #2 audio-evidence gate.

The schema itself is **not** changed. ``source`` stays the four-value enum
``{subtitle, audio, visual, transcript}`` (spec §11). The only addition is a
runtime gate: when no real audio-understanding component analyzed the audio
(MVP default), ``source="audio"`` is rejected because it would not reflect
what the system actually observed.
"""
from __future__ import annotations

from typing import Any

from .taxonomy import TaxonomyData

SCHEMA_VERSION = "creative_tagging_v1"

_EVIDENCE_STRENGTH = {"strong", "medium"}  # weak is forbidden (spec §6.2)
_SALIENCE = {"primary", "supporting"}
_CONFIDENCE = {"high", "medium", "low"}
_SOURCE_MODE = {"script_and_visual", "visual_only", "script_only"}
_SOURCE = {"subtitle", "audio", "visual", "transcript"}
_SUFFICIENCY = {"sufficient", "insufficient"}
_UNDETERMINED_UE = "无法判断（对于这种情况给一个候选）"


class ValidationError(Exception):
    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__("; ".join(errors) if errors else "validation error")


def _evidence_items(ev: Any, where: str, audio_enabled: bool) -> list[str]:
    """Validate a list of evidence items; return error strings."""
    errs: list[str] = []
    if not isinstance(ev, list) or not ev:
        errs.append(f"{where}: evidence must be a non-empty list")
        return errs
    for i, item in enumerate(ev):
        iw = f"{where}.evidence[{i}]"
        if not isinstance(item, dict):
            errs.append(f"{iw}: must be an object")
            continue
        t = item.get("time")
        if not isinstance(t, str) or not t.strip():
            errs.append(f"{iw}: 'time' must be a non-empty string")
        src = item.get("source")
        if src not in _SOURCE:
            errs.append(f"{iw}: 'source' must be one of {sorted(_SOURCE)}, got {src!r}")
        elif src == "audio" and not audio_enabled:
            errs.append(
                f"{iw}: 'source=audio' is illegal in MVP (no audio-understanding "
                f"component analyzed this evidence); use 'visual' for visual inference "
                f"or 'transcript' for Whisper output (correction #2)"
            )
        c = item.get("content")
        if not isinstance(c, str) or not c.strip():
            errs.append(f"{iw}: 'content' must be a non-empty string")
    return errs


def validate(data: Any, tax: TaxonomyData, audio_enabled: bool = False) -> list[str]:
    """Return a list of error strings; empty list means valid."""
    errs: list[str] = []
    if not isinstance(data, dict):
        return ["output must be a JSON object"]

    # schema_version -------------------------------------------------------- #
    if data.get("schema_version") != SCHEMA_VERSION:
        errs.append(f"'schema_version' must be {SCHEMA_VERSION!r}, got {data.get('schema_version')!r}")

    # creative_id ---------------------------------------------------------- #
    cid = data.get("creative_id")
    if not isinstance(cid, str) or not cid.strip():
        errs.append("'creative_id' must be a non-empty string")

    # decision_window ------------------------------------------------------- #
    dw = data.get("decision_window")
    if not isinstance(dw, dict):
        errs.append("'decision_window' must be an object")
        dw = {}
    if dw.get("primary_seconds") != 30:
        errs.append(f"decision_window.primary_seconds must be 30, got {dw.get('primary_seconds')!r}")
    used = dw.get("used_seconds")
    if used not in (30, 60):
        errs.append(f"decision_window.used_seconds must be 30 or 60, got {used!r}")
    extended = dw.get("extended")
    if not isinstance(extended, bool):
        errs.append("decision_window.extended must be boolean")
        extended = None
    suff = dw.get("semantic_sufficiency")
    if suff not in _SUFFICIENCY:
        errs.append(f"decision_window.semantic_sufficiency must be one of {sorted(_SUFFICIENCY)}, got {suff!r}")
    reason = dw.get("extended_reason")

    # cross-consistency (spec §12): extended == (used==60) == (sufficiency==insufficient)
    if extended is True and used != 60:
        errs.append("decision_window: extended=true requires used_seconds=60")
    if extended is False and used != 30:
        errs.append("decision_window: extended=false requires used_seconds=30")
    if suff == "insufficient" and extended is not True:
        errs.append("decision_window: semantic_sufficiency=insufficient requires extended=true")
    if suff == "sufficient" and extended is not False:
        errs.append("decision_window: semantic_sufficiency=sufficient requires extended=false")
    if extended is True:
        if not isinstance(reason, str) or not reason.strip():
            errs.append("decision_window.extended_reason must be a non-empty string when extended=true")
    elif extended is False:
        if reason is not None:
            errs.append("decision_window.extended_reason must be null when extended=false")

    # matched_value_tags --------------------------------------------------- #
    matched = data.get("matched_value_tags")
    if not isinstance(matched, list):
        errs.append("'matched_value_tags' must be a list")
        matched = []
    matched_salience: dict[str, str] = {}
    matched_labels_seen: set[str] = set()
    for i, m in enumerate(matched):
        mw = f"matched_value_tags[{i}]"
        if not isinstance(m, dict):
            errs.append(f"{mw}: must be an object")
            continue
        lab = m.get("label")
        cat = m.get("category")
        if not tax.is_value_label(lab):
            errs.append(f"{mw}: label {lab!r} not in Value Taxonomy")
        else:
            exp_cat = tax.value_category_of(lab)
            if cat != exp_cat:
                errs.append(f"{mw}: category {cat!r} does not match taxonomy category {exp_cat!r} for label {lab!r}")
        if lab in matched_labels_seen:
            errs.append(f"{mw}: duplicate label {lab!r}")
        matched_labels_seen.add(lab)
        es = m.get("evidence_strength")
        if es not in _EVIDENCE_STRENGTH:
            errs.append(f"{mw}: evidence_strength must be one of {sorted(_EVIDENCE_STRENGTH)}, got {es!r}")
        sal = m.get("salience")
        if sal not in _SALIENCE:
            errs.append(f"{mw}: salience must be one of {sorted(_SALIENCE)}, got {sal!r}")
        else:
            matched_salience[lab] = sal
        errs.extend(_evidence_items(m.get("evidence"), mw, audio_enabled))

    # active_value_tags ---------------------------------------------------- #
    active = data.get("active_value_tags")
    if not isinstance(active, list):
        errs.append("'active_value_tags' must be a list")
        active = []
    active_labels: list[str] = []
    for i, a in enumerate(active):
        if not isinstance(a, str):
            errs.append(f"active_value_tags[{i}]: must be a string label, got {a!r}")
            continue
        if a not in matched_labels_seen:
            errs.append(f"active_value_tags[{i}]: label {a!r} must be present in matched_value_tags")
        active_labels.append(a)
    if len(active_labels) != len(set(active_labels)):
        errs.append("active_value_tags: contains duplicate labels")
    if len(active_labels) > 5:
        errs.append(f"active_value_tags: total {len(active_labels)} exceeds limit 5 (spec §6.4)")
    # salience counts (derived from matched)
    n_primary = sum(1 for a in active_labels if matched_salience.get(a) == "primary")
    n_supporting = sum(1 for a in active_labels if matched_salience.get(a) == "supporting")
    if not (1 <= n_primary <= 2):
        errs.append(f"active_value_tags: primary salience count {n_primary} not in [1,2] (spec §6.4)")
    if not (0 <= n_supporting <= 3):
        errs.append(f"active_value_tags: supporting salience count {n_supporting} not in [0,3] (spec §6.4)")
    # per-category caps
    per_cat: dict[str, int] = {}
    for a in active_labels:
        c = tax.value_category_of(a)
        if c is not None:
            per_cat[c] = per_cat.get(c, 0) + 1
    for c, n in per_cat.items():
        limit = tax.active_limits.get(c, 0)
        if n > limit:
            errs.append(f"active_value_tags: category {c!r} has {n} active, exceeds limit {limit} (spec §6.4)")

    # opening_type --------------------------------------------------------- #
    ot = data.get("opening_type")
    if not isinstance(ot, dict):
        errs.append("'opening_type' must be an object")
        ot = {}
    if not tax.is_opening_label(ot.get("label")):
        errs.append(f"opening_type.label {ot.get('label')!r} not in Opening Taxonomy")
    if ot.get("source_mode") not in _SOURCE_MODE:
        errs.append(f"opening_type.source_mode must be one of {sorted(_SOURCE_MODE)}, got {ot.get('source_mode')!r}")
    if ot.get("confidence") not in _CONFIDENCE:
        errs.append(f"opening_type.confidence must be one of {sorted(_CONFIDENCE)}, got {ot.get('confidence')!r}")
    errs.extend(_evidence_items(ot.get("evidence"), "opening_type", audio_enabled))

    # user_expectation ----------------------------------------------------- #
    ue = data.get("user_expectation")
    if not isinstance(ue, dict):
        errs.append("'user_expectation' must be an object")
        ue = {}
    ue_label = ue.get("label")
    if not tax.is_expectation_label(ue_label):
        errs.append(f"user_expectation.label {ue_label!r} not in User Expectation Taxonomy")
    cand = ue.get("candidate")
    if ue_label == _UNDETERMINED_UE:
        if not isinstance(cand, str) or not cand.strip():
            errs.append("user_expectation.candidate must be a non-empty string when label is the undetermined label")
        elif not tax.is_expectation_label(cand):
            errs.append(f"user_expectation.candidate {cand!r} not in User Expectation Taxonomy")
        elif cand == ue_label:
            errs.append("user_expectation.candidate must differ from the undetermined label")
    else:
        if cand is not None:
            errs.append("user_expectation.candidate must be null when label is a concrete expectation")
    if ue.get("confidence") not in _CONFIDENCE:
        errs.append(f"user_expectation.confidence must be one of {sorted(_CONFIDENCE)}, got {ue.get('confidence')!r}")
    errs.extend(_evidence_items(ue.get("evidence"), "user_expectation", audio_enabled))

    # review --------------------------------------------------------------- #
    rv = data.get("review")
    if not isinstance(rv, dict):
        errs.append("'review' must be an object")
        rv = {}
    needed = rv.get("needed")
    if not isinstance(needed, bool):
        errs.append("review.needed must be boolean")
    rreason = rv.get("reason")
    if needed is True:
        if not isinstance(rreason, str) or not rreason.strip():
            errs.append("review.reason must be a non-empty string when review.needed=true")
    elif needed is False:
        if rreason is not None:
            errs.append("review.reason must be null when review.needed=false")

    return errs


def is_valid(data: Any, tax: TaxonomyData, audio_enabled: bool = False) -> bool:
    return not validate(data, tax, audio_enabled)
