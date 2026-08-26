#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V2.1a Creative Tagging CLI.

Usage:
    python -m v2.run_creative_tagging <video> [options]

Output (spec §2): output/<creative_id>/v2/creative_tags.json
"""
from __future__ import annotations

import argparse
import json
import os
import sys

from . import taxonomy
from .tagging import TaggingConfig, TaggingPipeline


def main() -> int:
    ap = argparse.ArgumentParser(prog="v2.run_creative_tagging",
                                 description="V2.1a Creative Tagging (Value/Opening/Expectation)")
    ap.add_argument("video", help="path to the video file")
    ap.add_argument("--creative-id", default=None, help="creative id (default: video filename)")
    ap.add_argument("--output-dir", default=None, help="output dir (default: output/<id>/v2)")
    ap.add_argument("--category", default="singing", help="taxonomy category (default: singing)")
    args = ap.parse_args()

    if not os.path.isfile(args.video):
        print(f"error: video not found: {args.video}", file=sys.stderr)
        return 1

    cfg = TaggingConfig.from_env()
    missing = [n for n, v in [("API_BASE_URL/V2_API_BASE_URL", cfg.api_base),
                              ("API_KEY/V2_API_KEY", cfg.api_key),
                              ("MODEL_NAME/V2_MODEL_NAME", cfg.model)] if not v]
    if missing:
        print("error: missing API config (set in config.env or env): " + ", ".join(missing), file=sys.stderr)
        return 2

    creative_id = args.creative_id or os.path.splitext(os.path.basename(args.video))[0]
    out_dir = args.output_dir or os.path.join("output", creative_id, "v2")

    tax = taxonomy.load_taxonomy(args.category)
    pipe = TaggingPipeline(cfg, tax)
    try:
        data = pipe.run(args.video, creative_id, out_dir)
    except Exception as e:
        print(f"error: tagging failed: {e}", file=sys.stderr)
        return 3

    print("\n========== V2.1a Creative Tagging ==========")
    print(f"creative_id : {data.get('creative_id')}")
    dw = data.get("decision_window", {})
    print(f"window      : used={dw.get('used_seconds')}s extended={dw.get('extended')} sufficiency={dw.get('semantic_sufficiency')}")
    ot = data.get("opening_type", {})
    print(f"opening     : {ot.get('label')} [{ot.get('source_mode')}] conf={ot.get('confidence')}")
    ue = data.get("user_expectation", {})
    print(f"expectation : {ue.get('label')} (candidate={ue.get('candidate')}) conf={ue.get('confidence')}")
    act = data.get("active_value_tags", [])
    print(f"active ({len(act)}): {', '.join(act)}")
    rv = data.get("review", {})
    print(f"review      : needed={rv.get('needed')} reason={rv.get('reason')}")
    print(f"output      : {os.path.join(out_dir, 'creative_tags.json')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
