#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V2.1b Intent Decision pipeline.

    creative_tags.json (creative_tagging_v1)
        -> creative_intent.json (creative_intent_v1)

Text-only single LLM call over the frozen V2.1a output. No video access, no
V2.1a re-invocation, no structured_evidence dependency. The input is strictly
validated (fail fast on missing creative_tagging_v1 fields); the output is
strictly validated against the input (evidence grounding, single primary
driver, statement completeness). Only schema failures are retried, with the
error list fed back — semantics are never silently repaired.

Usage:
    python -m v2.intent_decision --tags output/v01/v2/creative_tags.json \
        [--output-dir output/v01/v2]
"""
from __future__ import annotations

import argparse
import json
import os
import sys

from . import intent_schema, schema as tagging_schema, taxonomy
from .tagging import ApiClient, TaggingConfig, extract_json

_PROMPT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "prompts", "intent_decision.md")


class TimeoutApiClient(ApiClient):
    """V2.1b-local provider: same surface as V2.1a's ApiClient but with a
    hard per-request timeout.

    Some gateways (observed: slb-v1.api.fan) hang pooled HTTP connections
    indefinitely while the same request succeeds via a fresh connection; the
    SDK default (600 s / no read timeout in practice) turns that into a
    multi-hour stall. V2.1a's frozen ApiClient stays untouched — this subclass
    only passes ``timeout=`` to the OpenAI client at construction.
    """

    def __init__(self, api_base: str, api_key: str, model: str,
                 temperature: float = 0.0, max_tokens: int = 16384,
                 max_retries: int = 3, timeout: float = 90.0):
        super().__init__(api_base, api_key, model,
                         temperature=temperature, max_tokens=max_tokens,
                         max_retries=max_retries)
        self.timeout = timeout

    def _ensure(self):
        if self._client is not None:
            return
        from openai import OpenAI  # type: ignore
        base = self.api_base.rstrip("/")
        if not base.endswith("/v1"):
            base = base + "/v1"
        self._client = OpenAI(api_key=self.api_key, base_url=base,
                              timeout=self.timeout)


def make_intent_provider(cfg: TaggingConfig) -> TimeoutApiClient:
    """Build the V2.1b provider (timeout-wrapped; V2.1a code untouched)."""
    timeout = float(os.environ.get("V2_INTENT_TIMEOUT", "90"))
    return TimeoutApiClient(cfg.api_base, cfg.api_key, cfg.model,
                            temperature=cfg.temperature,
                            max_retries=cfg.api_retries, timeout=timeout)

_REQUIRED_TAG_FIELDS = (
    "schema_version", "creative_id", "decision_window",
    "matched_value_tags", "active_value_tags",
    "opening_type", "user_expectation", "review",
)


def validate_input_tags(tags: object, tax: taxonomy.TaxonomyData) -> list[str]:
    """Fail-fast checks on the upstream creative_tags.json (spec §2)."""
    errs: list[str] = []
    if not isinstance(tags, dict):
        return ["input creative_tags.json must be a JSON object"]
    missing = [f for f in _REQUIRED_TAG_FIELDS if f not in tags]
    if missing:
        errs.append("input creative_tags.json missing required field(s): "
                    + ", ".join(missing))
        return errs
    if tags.get("schema_version") != tagging_schema.SCHEMA_VERSION:
        errs.append(f"input schema_version must be "
                    f"{tagging_schema.SCHEMA_VERSION!r}, got "
                    f"{tags.get('schema_version')!r}")
    errs.extend(tagging_schema.validate(tags, tax))
    return errs


class IntentDecisionPipeline:
    def __init__(self, cfg: TaggingConfig,
                 tax: taxonomy.TaxonomyData | None = None, api=None):
        self.cfg = cfg
        self.tax = tax or taxonomy.load_taxonomy("singing")
        with open(_PROMPT_PATH, "r", encoding="utf-8") as f:
            self.system = f.read()
        if api is None:
            api = make_intent_provider(cfg)  # timeout-wrapped, V2.1b-local
        self.api = api

    # ------------------------------------------------------------------ #
    def decide(self, tags: dict) -> dict:
        """Run intent decision over one creative_tags.json dict."""
        errs = validate_input_tags(tags, self.tax)
        if errs:
            raise ValueError(
                "invalid creative_tags.json input (fail fast, no silent "
                "repair): " + "; ".join(errs)
            )

        user = [
            {"type": "text",
             "text": ("以下是 V2.1a Creative Tagging 的输出 creative_tags.json"
                      "（唯一事实来源，含全部 evidence）：\n"
                      + json.dumps(tags, ensure_ascii=False, indent=2)
                      + "\n\n请基于以上输入进行 Intent Decision，"
                        "输出 creative_intent_v1 JSON。")},
        ]
        last_errs: list[str] = []
        for attempt in range(1, self.cfg.max_retries + 1):
            msg = list(user)
            if last_errs:
                msg.append({"type": "text",
                            "text": "你上一次输出未通过校验，错误如下：\n- "
                                    + "\n- ".join(last_errs)
                                    + "\n请修正并重新输出完整的 creative_intent_v1 JSON"
                                      "（evidence 必须逐字复制输入中已存在的条目）。"})
            raw = self.api.chat(self.system, msg)
            try:
                data = extract_json(raw)
            except Exception as e:
                last_errs = [f"JSON 解析失败: {e}"]
                print(f"[intent] parse failed (attempt {attempt}): {e}", flush=True)
                continue
            errs = intent_schema.validate(data, tags, self.tax)
            if not errs:
                return data
            last_errs = errs
            print(f"[intent] validation failed (attempt {attempt}): {errs}", flush=True)
        raise RuntimeError(
            f"intent decision failed validation after {self.cfg.max_retries} "
            f"attempts; last errs: {last_errs}"
        )

    # ------------------------------------------------------------------ #
    def run(self, tags_path: str, output_dir: str) -> dict:
        """Load creative_tags.json from disk, decide, write creative_intent.json."""
        with open(tags_path, "r", encoding="utf-8") as f:
            tags = json.load(f)
        data = self.decide(tags)
        os.makedirs(output_dir, exist_ok=True)
        out_path = os.path.join(output_dir, "creative_intent.json")
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"[intent] wrote {out_path}", flush=True)
        return data


def main() -> int:
    ap = argparse.ArgumentParser(prog="v2.intent_decision",
                                 description="V2.1b Intent Decision "
                                             "(creative_tags.json -> creative_intent.json)")
    ap.add_argument("--tags", required=True, help="path to creative_tags.json")
    ap.add_argument("--output-dir", default=None,
                    help="default: same directory as --tags (writes creative_intent.json)")
    ap.add_argument("--category", default="singing", help="taxonomy category")
    args = ap.parse_args()

    if not os.path.isfile(args.tags):
        print(f"error: creative_tags.json not found: {args.tags}", file=sys.stderr)
        return 1

    cfg = TaggingConfig.from_env()
    missing = [n for n, v in [("API_BASE_URL/V2_API_BASE_URL", cfg.api_base),
                              ("API_KEY/V2_API_KEY", cfg.api_key),
                              ("MODEL_NAME/V2_MODEL_NAME", cfg.model)] if not v]
    if missing:
        print("error: missing API config: " + ", ".join(missing), file=sys.stderr)
        return 2

    out_dir = args.output_dir or os.path.dirname(os.path.abspath(args.tags))
    pipe = IntentDecisionPipeline(cfg, taxonomy.load_taxonomy(args.category))
    try:
        data = pipe.run(args.tags, out_dir)
    except Exception as e:
        print(f"error: intent decision failed: {e}", file=sys.stderr)
        return 3

    print("\n========== V2.1b Intent Decision ==========")
    print(f"creative_id : {data.get('creative_id')}")
    pd = data.get("primary_driver", {})
    print(f"primary     : {pd.get('statement')} [conf={pd.get('confidence')}]")
    uq = data.get("unresolved_question", {})
    print(f"question    : {uq.get('statement')} [conf={uq.get('confidence')}]")
    print(f"strength    : {data.get('intent_strength')}")
    sup = data.get("supporting_drivers") or []
    print(f"supporting ({len(sup)}): " + ("; ".join(sup) if sup else "-"))
    print(f"evidence    : {len(data.get('evidence') or [])} item(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
