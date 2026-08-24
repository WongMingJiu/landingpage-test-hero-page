#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Adjudication-only stability runner (validation tooling, not product code).

Runs the SAME cached structured-evidence artifact through the frozen final
adjudication N times and reports drift for Opening Type / User Expectation /
Primary Core. No video extraction and no multimodal evidence extraction are
repeated once the artifact exists. Diagnostic only — does not replace the
E2E benchmark.

Usage (artifact-first; recommended while the multimodal gateway is unstable):
  python -m v2.benchmarks.adjudication_stability \
      --evidence output/<creative>/v2/structured_evidence.json --repeats 3

Usage (build artifact first; requires the live multimodal provider):
  python -m v2.benchmarks.adjudication_stability \
      --evidence output/<creative>/v2/structured_evidence.json \
      --video videos/v02.mp4 --repeats 3
"""
from __future__ import annotations

import argparse
import json
import os
import sys

from v2 import taxonomy
from v2.tagging import (TaggingConfig, TaggingPipeline,
                        STRUCTURED_EVIDENCE_FILENAME,
                        load_structured_evidence)


def gt_primary_from_manifest(vid: str) -> list[str]:
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "singing-creative-tagging-v1.0", "manifest.json")
    try:
        with open(path, encoding="utf-8") as f:
            m = json.load(f)
        for it in m.get("items", []):
            if it.get("id") == vid:
                return list(it.get("expected", {}).get("active_primary", []))
    except Exception:
        pass
    return []


def primary_labels(out: dict) -> list[str]:
    matched = {t["label"]: t.get("salience") for t in out.get("matched_value_tags", [])
               if isinstance(t, dict)}
    return sorted(a for a in out.get("active_value_tags", []) if matched.get(a) == "primary")


def core_match(pred: list[str], gt: list[str]) -> str:
    p, g = set(pred), set(gt)
    return "exact" if p == g else ("partial" if p & g else "wrong")


def build_evidence_artifact(pipe: TaggingPipeline, video: str, artifact_path: str) -> None:
    """Full E2E extraction once, persisting the replayable artifact. Requires
    the live multimodal provider; skipped entirely when the artifact exists."""
    work_dir = os.path.dirname(os.path.abspath(artifact_path))
    vid = os.path.basename(os.path.dirname(work_dir))
    pipe.run(video, vid, work_dir)  # writes structured_evidence.json + creative_tags.json


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--evidence", required=True, help="structured_evidence.json path")
    ap.add_argument("--video", default=None,
                    help="if given and the artifact is missing, build it once via the "
                         "full pipeline (needs the live multimodal provider)")
    ap.add_argument("--creative-id", default=None)
    ap.add_argument("--repeats", type=int, default=3)
    args = ap.parse_args()

    if not os.path.exists(args.evidence):
        if not args.video:
            print(f"error: evidence artifact not found: {args.evidence} "
                  f"(pass --video to build it once)", file=sys.stderr)
            return 2
        cfg = TaggingConfig.from_env()
        pipe = TaggingPipeline(cfg, taxonomy.load_taxonomy("singing"))
        build_evidence_artifact(pipe, args.video, args.evidence)

    evidence = load_structured_evidence(args.evidence)
    vid = args.creative_id or evidence.get("creative_id") or "sample"

    cfg = TaggingConfig.from_env()
    pipe = TaggingPipeline(cfg, taxonomy.load_taxonomy("singing"))
    gt = gt_primary_from_manifest(vid)

    results = []
    for i in range(args.repeats):
        out = pipe.replay(evidence, vid)
        opening = out["opening_type"]
        opening = opening["label"] if isinstance(opening, dict) else opening
        expect = out["user_expectation"]
        expect = expect["label"] if isinstance(expect, dict) else expect
        prim = primary_labels(out)
        rec = {"run": i, "opening": opening, "expectation": expect,
               "primary": prim, "core": core_match(prim, gt) if gt else None}
        results.append(rec)
        print(f"[adj-stab] {vid} run{i}: opening={opening} expect={expect} "
              f"core={rec['core']} primary={prim}", flush=True)

    openings = {r["opening"] for r in results}
    expects = {r["expectation"] for r in results}
    cores = {r["core"] for r in results} - {None}
    summary = {
        "video": vid, "repeats": args.repeats,
        "evidence_artifact": os.path.abspath(args.evidence),
        "opening_values": sorted(openings), "opening_stable": len(openings) == 1,
        "expectation_values": sorted(expects), "expectation_stable": len(expects) == 1,
        "core_values": sorted(cores),
        "core_wrong_exact_oscillation": {"wrong", "exact"} <= cores,
        "gt_primary": gt,
        "runs": results,
    }
    out_path = os.path.join(os.path.dirname(os.path.abspath(args.evidence)),
                            "adjudication_stability.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    print(f"[adj-stab] {vid}: opening_stable={summary['opening_stable']} "
          f"expectation_stable={summary['expectation_stable']} "
          f"oscillation={summary['core_wrong_exact_oscillation']} -> {out_path}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
