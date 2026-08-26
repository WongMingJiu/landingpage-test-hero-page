#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Unit tests for v2.frames (correction #1: opening 0-10s 1fps never degraded)."""
import unittest

from v2 import frames


class OpeningInvariantTests(unittest.TestCase):
    def test_default_budget_20_set(self):
        s = frames.select_primary_frames(n_frames=30, budget=20)
        self.assertEqual(s[:11], list(range(0, 11)))  # 0..10 1fps
        self.assertEqual(len(s), 20)
        self.assertEqual(s[11:], [12, 14, 16, 18, 20, 22, 24, 26, 28])

    def test_opening_never_degraded_small_budget(self):
        # budget=12 must still keep opening 0..10 intact (11 frames), tail=1
        s = frames.select_primary_frames(n_frames=30, budget=12)
        self.assertEqual(s[:11], list(range(0, 11)))
        self.assertEqual(len(s), 12)

    def test_budget_below_opening_returns_opening_only(self):
        s = frames.select_primary_frames(n_frames=30, budget=8)
        self.assertEqual(s, list(range(0, 11)))  # opening kept, no tail

    def test_short_video_opening_covers_all(self):
        s = frames.select_primary_frames(n_frames=8, budget=20)
        self.assertEqual(s, [0, 1, 2, 3, 4, 5, 6, 7])

    def test_invariant_helper_passes_contiguous(self):
        frames.assert_opening_invariant(list(range(0, 11)))
        frames.assert_opening_invariant([0, 1, 2, 3, 4, 5, 6, 7])

    def test_invariant_helper_catches_gap(self):
        with self.assertRaises(AssertionError):
            frames.assert_opening_invariant([0, 2, 3, 4, 5, 6, 7, 8, 9, 10])  # missing 1


class StagedBatchTests(unittest.TestCase):
    """Correction #1 staged fallback: all frames still seen across requests."""

    def test_staged_keeps_full_opening(self):
        b = frames.staged_batches(n_frames=30)
        self.assertEqual(b["opening"], list(range(0, 11)))  # 0..10 intact
        self.assertEqual(b["tail"], [12, 14, 16, 18, 20, 22, 24, 26, 28])
        # no frame lost: union is the full primary set
        self.assertEqual(sorted(set(b["opening"]) | set(b["tail"])),
                         frames.select_primary_frames(n_frames=30, budget=20))

    def test_extension_frames(self):
        e = frames.extension_frame_seconds(n_ext_frames=30, step=3, base=30)
        self.assertEqual(e, [30, 33, 36, 39, 42, 45, 48, 51, 54, 57])


if __name__ == "__main__":
    unittest.main()
