#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V2.3 Message Match Copy pipeline.

Turns one creative's V2.1a creative_tags.json + V2.1b creative_intent.json into
a message_match_copy_v1 document (anchors + grounding pack + T1 copy + T2 copy).

Design notes (first round — keep it simple, debuggable, traceable):
  - Steps A/B/C run in ONE LLM call; intermediate artifacts stay in the output
    JSON for full traceability;
  - the system prompt comes from v2/prompts/message_match_copy.md with the
    knowledge base inlined (single product-truth source);
  - engineering retries (API failure / JSON parse failure) are bounded and
    explicitly recorded in run meta; semantic retries are forbidden.

Usage (see v2/benchmarks/run_message_match_copy_benchmark.py for the runner):
    python -m v2.message_match_copy --creative-id v01 \
        --tags output/benchmark-runs/v2.1a-val-phase2/v01/run0/v2/creative_tags.json \
        --intent output/benchmark-runs/intent-b2/v01/creative_intent.json
"""
from __future__ import annotations

import argparse
import json
import os
import time

from v2.message_match_schema import (
    load_slot_contract, T1_PROMPT, T2_PROMPT,
)
from v2.tagging import ApiClient, TaggingConfig, extract_json

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROMPT_PATH = os.path.join(_REPO, "v2", "prompts", "message_match_copy.md")
KB_PATH = os.path.join(_REPO, "docs", "knowledge",
                       "singing-5day-experience-camp-kb-v1.0.md")

_MAX_ENGINEERING_RETRIES = 2  # per creative, beyond the provider's own retries


class MessageMatchCopyPipeline:
    def __init__(self, provider: ApiClient, kb_path: str = KB_PATH,
                 prompt_path: str = PROMPT_PATH):
        self.provider = provider
        with open(kb_path, encoding="utf-8") as f:
            kb_text = f.read()
        with open(prompt_path, encoding="utf-8") as f:
            prompt_tpl = f.read()
        self.system = prompt_tpl.replace("{KNOWLEDGE_BASE}", kb_text)
        self.t1_contract = load_slot_contract(T1_PROMPT)
        self.t2_contract = load_slot_contract(T2_PROMPT)

    # ------------------------------------------------------------------ #
    def build_user_content(self, tags: dict, intent: dict) -> list:
        user_text = (
            "【creative_tags.json（V2.1a Creative Tagging 输出）】\n"
            + json.dumps(tags, ensure_ascii=False, indent=2)
            + "\n\n【creative_intent.json（V2.1b Creative Intent 输出）】\n"
            + json.dumps(intent, ensure_ascii=False, indent=2)
            + "\n\n请按 system 指令完成 Step A（Creative Anchor Extraction）、Step B（Product "
              "Grounding Pack）、Step C（T1 + T2 Message Match Copy）。T1 与 T2 从同一输入独立"
              "并行生成。只输出最终 JSON 对象，不要输出任何其他文字。"
        )
        return [{"type": "text", "text": user_text}]

    # ------------------------------------------------------------------ #
    def run(self, creative_id: str, tags: dict, intent: dict) -> tuple:
        """Returns (output dict, meta dict). Raises on unrecoverable failure."""
        user_content = self.build_user_content(tags, intent)
        attempts: list = []
        last_err: Exception | None = None
        t0 = time.time()
        for attempt in range(1, _MAX_ENGINEERING_RETRIES + 1):
            raw = self.provider.chat(self.system, user_content)
            try:
                output = extract_json(raw)
                if not isinstance(output, dict) or not output.get("schema_version"):
                    raise ValueError("model output is not a message_match_copy JSON object")
                output["creative_id"] = creative_id  # normalize id casing if drifted
                meta = {
                    "creative_id": creative_id,
                    "attempts": attempts,
                    "engineering_retries": attempt - 1,
                    "seconds": round(time.time() - t0, 1),
                }
                return output, meta
            except (ValueError, json.JSONDecodeError) as e:
                last_err = e
                attempts.append({"attempt": attempt, "error": f"json/shape: {e}",
                                 "type": "engineering_retry"})
                print(f"[v2.3] {creative_id}: JSON parse failed on attempt "
                      f"{attempt}/{_MAX_ENGINEERING_RETRIES}: {e}", flush=True)
        raise RuntimeError(
            f"{creative_id}: engineering retries exhausted ({_MAX_ENGINEERING_RETRIES}): {last_err}")


def main() -> None:
    ap = argparse.ArgumentParser(description="V2.3 single-creative copy generation")
    ap.add_argument("--creative-id", required=True)
    ap.add_argument("--tags", required=True, help="V2.1a creative_tags.json path")
    ap.add_argument("--intent", required=True, help="V2.1b creative_intent.json path")
    ap.add_argument("--out", default=None, help="optional output json path")
    args = ap.parse_args()

    cfg = TaggingConfig.from_env()
    provider = ApiClient(cfg.api_base, cfg.api_key, cfg.model,
                         temperature=cfg.temperature, max_retries=cfg.api_retries)
    pipe = MessageMatchCopyPipeline(provider)
    with open(args.tags, encoding="utf-8") as f:
        tags = json.load(f)
    with open(args.intent, encoding="utf-8") as f:
        intent = json.load(f)
    output, meta = pipe.run(args.creative_id, tags, intent)
    payload = {"output": output, "meta": meta}
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        print(f"[v2.3] wrote {args.out}")
    else:
        print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
