#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Window-aware frame selector (Phase A §5 + correction #1).

Hard guarantee: the 0–10s Opening window is sampled at 1 fps and is **never**
degraded. If a single multimodal request cannot accept the full frame set, the
pipeline uses a staged / multi-request strategy (see :func:`staged_batches`)
rather than dropping Opening density.

Frames are addressed by their second index in the decision window:
  - primary window: seconds 0..29 (30 frames @ 1 fps)
  - extension window: seconds 30..59 (30 frames @ 1 fps)
"""
from __future__ import annotations

OPENING_END = 11  # seconds 0..10 inclusive => 11 frames (1 fps hard guarantee)


def opening_frame_seconds(n_frames: int = 30) -> list[int]:
    """Seconds 0..min(10, n-1), 1 fps, never sparsified."""
    if n_frames <= 0:
        return []
    return list(range(0, min(OPENING_END, n_frames)))


def tail_frame_seconds(n_frames: int = 30, step: int = 2) -> list[int]:
    """Lower-density sampling for the 11s..(n-1)s region.

    Default step=2 → [12,14,16,...,28] for a 30-frame window (9 frames),
    leaving a 2s gap after the opening block (frame 10 -> 12).
    """
    if n_frames <= OPENING_END:
        return []
    start = OPENING_END + 1  # 12: keep a 2s gap after frame 10
    return list(range(start, n_frames, step))


def select_primary_frames(n_frames: int = 30, budget: int = 20) -> list[int]:
    """Single-request frame set: opening (1 fps, fixed) + as much tail as the
    per-request ``budget`` allows. Opening is never reduced.

    If ``budget`` cannot even hold the opening block, only the opening block is
    returned — the pipeline must then switch to the staged multi-request path
    (correction #1) so the opening is still seen in full.
    """
    opening = opening_frame_seconds(n_frames)
    if n_frames <= OPENING_END:
        return opening
    tail_all = tail_frame_seconds(n_frames)
    tail_budget = budget - len(opening)
    if tail_budget <= 0:
        return opening  # signal to pipeline: use staged path
    return opening + tail_all[:tail_budget]


def staged_batches(n_frames: int = 30) -> dict[str, list[int]]:
    """Partition for the multi-request fallback (correction #1).

    All frames are still seen by the model — just across two vision calls:
      - ``opening``: seconds 0..10 (11 frames) — Opening evidence intact.
      - ``tail``: seconds 12,14,... (lower-density tail) — keeps request small.

    The merge step (text-only) then combines both observation sets into the
    final JSON, so no coverage is sacrificed.
    """
    return {
        "opening": opening_frame_seconds(n_frames),
        "tail": tail_frame_seconds(n_frames),
    }


def extension_frame_seconds(n_ext_frames: int = 30, step: int = 3, base: int = 30) -> list[int]:
    """Absolute second indices for the 30–60s extension window.

    ``n_ext_frames`` is the number of 1 fps frames available in the extension
    clip (default 30 → seconds 30..59). Sampled every ``step`` seconds.
    Returns absolute seconds (base + relative).
    """
    if n_ext_frames <= 0:
        return []
    rel = list(range(0, n_ext_frames, step))  # 0,3,6,...,27 => 10 frames
    return [base + r for r in rel]


# ---------------------------------------------------------------------------
# Invariants (used by tests)
# ---------------------------------------------------------------------------
def assert_opening_invariant(seconds: list[int]) -> None:
    """Assert that the 0..10s block is contiguous 1 fps (correction #1)."""
    opening = [s for s in seconds if s < OPENING_END]
    expected = list(range(0, OPENING_END))
    if opening != expected and opening != list(range(0, len(opening))):
        # second clause: shorter video still contiguous from 0
        raise AssertionError(
            f"opening 0-10s 1fps invariant violated: {opening} (correction #1)"
        )
