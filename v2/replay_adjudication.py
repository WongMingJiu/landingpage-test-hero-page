#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Adjudication-only replay (infrastructure; no decision-logic change).

Runs the frozen V2.1a constrained final adjudication over a previously saved
structured-evidence artifact:

    structured_evidence.json + timestamped transcript + taxonomy
        -> creative_tagging_v1

No video extraction, no multimodal evidence extraction.

Usage:
  python -m v2.replay_adjudication \
      --evidence output/<creative>/v2/structured_evidence.json \
      --creative-id v02 --output-dir output/replay-v02/v2
"""
from __future__ import annotations

import argparse
import json
import os
import sys

from v2 import taxonomy
from v2.tagging import (TaggingConfig, TaggingPipeline,
                        load_structured_evidence)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--evidence", required=True, help="path to structured_evidence.json")
    ap.add_argument("--creative-id", default=None,
                    help="defaults to the artifact's creative_id or the parent dir name")
    ap.add_argument("--output-dir", required=True)
    args = ap.parse_args()

    evidence = load_structured_evidence(args.evidence)
    creative_id = (args.creative_id or evidence.get("creative_id")
                   or os.path.basename(os.path.dirname(os.path.dirname(os.path.abspath(args.evidence)))))

    cfg = TaggingConfig.from_env()
    pipe = TaggingPipeline(cfg, taxonomy.load_taxonomy("singing"))
    data = pipe.replay(evidence, creative_id)

    os.makedirs(args.output_dir, exist_ok=True)
    out_path = os.path.join(args.output_dir, "creative_tags.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    opening = data["opening_type"]
    opening = opening["label"] if isinstance(opening, dict) else opening
    expect = data["user_expectation"]
    expect = expect["label"] if isinstance(expect, dict) else expect
    print(f"[replay] {creative_id}: opening={opening} expectation={expect} -> {out_path}",
          flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
