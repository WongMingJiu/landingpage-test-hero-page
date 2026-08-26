#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Targeted evidence-extraction stability diagnostic (validation tooling only).

Repeats ONLY the multimodal structured-evidence extraction N times for a
video (reusing the already-extracted frames + whisper transcript from a
previous run) and compares the normalized observation sets across rounds:
exact fact agreement, fuzzy containment, candidate-signal agreement.
No adjudication is performed here; product logic is untouched.

Usage:
  python -m v2.benchmarks.extraction_stability \
      --reuse output/benchmark-runs/<run-id>/v02/run0 --repeats 3 \
      --out-dir output/evidence-extraction-stability
"""
from __future__ import annotations

import argparse
import json
import os

from v2 import frames as frames_mod
from v2 import taxonomy
from v2.tagging import (TaggingConfig, TaggingPipeline, load_frames,
                        _collect_staged_evidence)


def load_segs(path: str) -> list[dict]:
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return data if isinstance(data, list) else data.get("segments", [])


def candidate_sets(obs: list[dict]) -> dict[str, set]:
    out: dict[str, set] = {"opening": set(), "value": set(), "expectation": set()}
    for o in obs:
        for k, vs in (o.get("candidates") or {}).items():
            if k in out:
                out[k].update(v for v in vs if v)
    return out


def compare_rounds(rounds: list[list[dict]]) -> dict:
    facts = [sorted({o["fact"] for o in r}) for r in rounds]
    exact = set(facts[0])
    agree = all(set(f) == exact for f in facts[1:])
    # fuzzy: every fact in every round is contained by (or contains) some
    # fact in every other round — tolerant to phrasing drift
    def contained(f: str, other: list[str]) -> bool:
        return any(f in g or g in f for g in other)
    fuzzy = all(contained(f, facts[j]) for i, fi in enumerate(facts)
                for f in fi for j in range(len(facts)) if j != i)
    cands = [candidate_sets(r) for r in rounds]
    cand_stable = all(cands[0][k] == c[k] for c in cands[1:] for k in cands[0])
    return {
        "counts": [len(r) for r in rounds],
        "fact_counts": [len(f) for f in facts],
        "exact_set_identical": agree,
        "fuzzy_containment": fuzzy,
        "candidate_sets_identical": cand_stable,
        "opening_candidates": [sorted(c["opening"]) for c in cands],
        "expectation_candidates": [sorted(c["expectation"]) for c in cands],
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--reuse", required=True,
                    help="work dir of a previous run containing frames/ + transcript_0_30.json")
    ap.add_argument("--creative-id", default=None)
    ap.add_argument("--repeats", type=int, default=3)
    ap.add_argument("--out-dir", default="output/evidence-extraction-stability")
    args = ap.parse_args()

    reuse = os.path.abspath(args.reuse)
    vid = args.creative_id or os.path.basename(os.path.dirname(os.path.dirname(reuse)))
    cfg = TaggingConfig.from_env()
    pipe = TaggingPipeline(cfg, taxonomy.load_taxonomy("singing"))

    frames_dir = os.path.join(reuse, "frames")
    n_frames = len([f for f in os.listdir(frames_dir) if f.endswith(".jpg")])
    secs = frames_mod.select_primary_frames(n_frames=n_frames, budget=cfg.frame_budget)
    fr = load_frames(secs, frames_dir)
    segs = load_segs(os.path.join(reuse, "transcript_0_30.json"))
    print(f"[ext-stab] {vid}: {len(fr)} frames, {len(segs)} transcript segs", flush=True)

    rounds: list[list[dict]] = []
    for i in range(args.repeats):
        obs = _collect_staged_evidence(pipe.api, fr, segs)
        rounds.append(obs)
        print(f"[ext-stab] {vid} round{i}: {len(obs)} observations", flush=True)

    cmp_ = compare_rounds(rounds)
    os.makedirs(args.out_dir, exist_ok=True)
    for i, obs in enumerate(rounds):
        p = os.path.join(args.out_dir, f"{vid}-round{i}.json")
        with open(p, "w", encoding="utf-8") as f:
            json.dump({"video": vid, "round": i, "observations": obs},
                      f, ensure_ascii=False, indent=1)
    summary = {"video": vid, "repeats": args.repeats, **cmp_}
    sp = os.path.join(args.out_dir, f"{vid}-summary.json")
    with open(sp, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    print(f"[ext-stab] {vid}: exact_identical={cmp_['exact_set_identical']} "
          f"fuzzy={cmp_['fuzzy_containment']} candidates_identical={cmp_['candidate_sets_identical']} "
          f"-> {sp}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
