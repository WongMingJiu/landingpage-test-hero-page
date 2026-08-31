#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V2.1b Intent Decision Seed Benchmark runner.

For each of the 10 GT items:
  1. load the frozen V2.1a creative_tags.json (from --tags-root),
  2. run IntentDecisionPipeline -> creative_intent.json (creative_intent_v1),
  3. programmatic gates: schema valid / primary uniqueness / evidence grounding,
  4. LLM semantic judge: primary driver + unresolved question vs GT.

First-round results are reported as-is (no gate-driven tuning).

Usage:
    python -m v2.benchmarks.run_intent_benchmark \
        --tags-root output/benchmark-runs/v2.1a-val-phase2 \
        --run-id intent-b1
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time

from v2 import intent_schema, taxonomy
from v2.intent_decision import IntentDecisionPipeline
from v2.tagging import TaggingConfig, extract_json

_MANIFEST = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                         "singing-intent-decision-v1.0", "manifest.json")

_JUDGE_SYSTEM = """你是 V2.1b Intent Decision Benchmark 的语义判定器（judge）。
你会收到：人工 Ground Truth、模型输出、以及该广告的 V2.1a creative_tags.json（上下文）。
逐项判定语义是否一致：

1. primary_match —— Primary Driver 核心点击因果是否与 GT 一致：
   - 一致：说服主体（谁/什么在承载说服）与因果方向（广告让用户相信了什么）相同；
     措辞、详略、句式不同不影响判定；
   - 不一致：说服主体不同（如 GT 是"学员证明可复制"而输出主体是"课程权益/老师权威/
     方法简单"），或因果错位（把 Opening/CTA/信任背书当成了 Driver）。

2. question_match —— Unresolved Question 是否与 GT 指向同一核心信息缺口：
   - 一致：继续了原广告的核心问题方向（通常是"具体怎么学/怎么练/对我是否有效"），
     且该问题确实未被广告明确回答（可对照 creative_tags.json 的 evidence 检查）；
   - 不一致：重复广告已经明确回答的问题（如广告已说"94岁能学"却问"我这个年龄能不能学"）、
     凭空创造新痛点、或指向完全不同的信息缺口。

只输出一个 JSON 对象，无解释文字：
{"primary_match": true|false, "question_match": true|false,
 "primary_reason": "一句话理由", "question_reason": "一句话理由"}"""


def _tags_path(tags_root: str, vid: str) -> str:
    for rel in (os.path.join(vid, "run0", "v2", "creative_tags.json"),
                os.path.join(vid, "v2", "creative_tags.json"),
                os.path.join(vid, "creative_tags.json")):
        p = os.path.join(tags_root, rel)
        if os.path.isfile(p):
            return p
    raise FileNotFoundError(f"creative_tags.json not found under {tags_root}/{vid}")


_JUDGE_MAX_ATTEMPTS = 3


def _judge_output_errors(data: object) -> list[str]:
    """Strict judge-output validation: primary_match / question_match must be
    native JSON booleans. bool("false") == True is exactly the silent
    coercion this forbids — strings, 1/0 and missing fields are all illegal."""
    if not isinstance(data, dict):
        return [f"judge output must be a JSON object, got {type(data).__name__}"]
    errs: list[str] = []
    for k in ("primary_match", "question_match"):
        if k not in data:
            errs.append(f"judge output missing field {k!r}")
        elif not isinstance(data[k], bool):
            errs.append(f"judge output {k!r} must be a native JSON boolean "
                        f"(true/false), got {data[k]!r} ({type(data[k]).__name__})")
    return errs


def judge_semantics(api, system: str, gt: dict, actual: dict, tags: dict) -> dict:
    """LLM judge call with strict boolean validation and bounded retries.

    Illegal outputs (missing / non-boolean match fields) are fed back to the
    judge for up to _JUDGE_MAX_ATTEMPTS attempts; exhaustion raises so the
    runner records judge_failed instead of silently counting it as pass."""
    base_user = [{"type": "text", "text":
                  "【人工 Ground Truth】\n"
                  f"primary_driver: {gt['primary_driver_gt']}\n"
                  f"unresolved_question: {gt['unresolved_question_gt']}\n\n"
                  "【模型输出】\n"
                  f"primary_driver: {actual['primary_driver']['statement']}\n"
                  f"unresolved_question: {actual['unresolved_question']['statement']}\n\n"
                  "【V2.1a creative_tags.json 上下文（判断“广告已回答/未回答”时使用）】\n"
                  + json.dumps(tags, ensure_ascii=False)}]
    last_errs: list[str] = []
    for attempt in range(1, _JUDGE_MAX_ATTEMPTS + 1):
        msg = list(base_user)
        if last_errs:
            msg.append({"type": "text",
                        "text": "你上一次的输出非法：\n- " + "\n- ".join(last_errs)
                            + "\nprimary_match / question_match 必须是原生 JSON boolean "
                              "（true 或 false，不要加引号、不要用 1/0）。"
                              "请重新输出完整 JSON。"})
        raw = api.chat(system, msg)
        data = extract_json(raw)
        errs = _judge_output_errors(data)
        if not errs:
            return data
        last_errs = errs
        print(f"[judge] invalid output (attempt {attempt}): {errs}", flush=True)
    raise ValueError(f"judge output invalid after {_JUDGE_MAX_ATTEMPTS} attempts: "
                     + "; ".join(last_errs))


def run_benchmark(tags_root: str, run_id: str, only: list[str] | None = None,
                  pipe: IntentDecisionPipeline | None = None) -> dict:
    """``pipe`` may be injected by tests (stub provider); production builds it."""
    with open(_MANIFEST, "r", encoding="utf-8") as f:
        manifest = json.load(f)
    items = manifest["items"]
    if only:
        wanted = set(only)
        items = [it for it in items if it["id"] in wanted]

    tax = taxonomy.load_taxonomy("singing")
    if pipe is None:
        cfg = TaggingConfig.from_env()
        if not (cfg.api_base and cfg.api_key and cfg.model):
            raise SystemExit("missing API config (API_BASE_URL/API_KEY/MODEL_NAME or V2_ overrides)")
        pipe = IntentDecisionPipeline(cfg, tax)

    out_root = os.path.join("output", "benchmark-runs", run_id)
    os.makedirs(out_root, exist_ok=True)

    # resume support: reuse judge verdicts from an existing report when the
    # judged statements are unchanged (decisions themselves are cached on disk
    # per sample as creative_intent.json)
    prior_report_path = os.path.join(out_root, "report.json")
    prior_verdicts: dict[str, dict] = {}
    if os.path.isfile(prior_report_path):
        try:
            with open(prior_report_path, "r", encoding="utf-8") as f:
                for r in json.load(f).get("samples", []):
                    if r.get("primary_match") is not None and r.get("primary_statement"):
                        prior_verdicts[r["id"]] = r
        except Exception:
            prior_verdicts = {}

    rows: list[dict] = []
    for it in items:
        vid = it["id"]
        t0 = time.time()
        row = {"id": vid, "error": None}
        try:
            tags_path = _tags_path(tags_root, vid)
            with open(tags_path, "r", encoding="utf-8") as f:
                tags = json.load(f)
            od = os.path.join(out_root, vid)
            intent_path = os.path.join(od, "creative_intent.json")
            if os.path.isfile(intent_path):
                with open(intent_path, "r", encoding="utf-8") as f:
                    actual = json.load(f)
            else:
                actual = pipe.decide(tags)
                os.makedirs(od, exist_ok=True)
                with open(intent_path, "w", encoding="utf-8") as f:
                    json.dump(actual, f, ensure_ascii=False, indent=2)

            errs = intent_schema.validate(actual, tags, tax)
            row["schema_valid"] = not errs
            row["schema_errors"] = errs
            # programmatic gates (already enforced by schema validation)
            row["primary_unique"] = isinstance(actual.get("primary_driver"), dict)
            row["evidence_grounded"] = not any(
                e.startswith("evidence[") for e in errs)
            row["primary_statement"] = actual["primary_driver"]["statement"]
            row["question_statement"] = actual["unresolved_question"]["statement"]
            row["intent_strength"] = actual.get("intent_strength")
            row["supporting_drivers"] = actual.get("supporting_drivers") or []

            try:
                cached_judge = prior_verdicts.get(vid)
                if (cached_judge
                        and cached_judge.get("primary_statement") == row["primary_statement"]
                        and cached_judge.get("question_statement") == row["question_statement"]):
                    for k in ("primary_match", "question_match", "primary_reason", "question_reason"):
                        row[k] = cached_judge.get(k)
                else:
                    verdict = judge_semantics(pipe.api, _JUDGE_SYSTEM, it, actual, tags)
                    row["primary_match"] = verdict["primary_match"]
                    row["question_match"] = verdict["question_match"]
                    row["primary_reason"] = verdict.get("primary_reason", "")
                    row["question_reason"] = verdict.get("question_reason", "")
            except Exception as e:
                row["primary_match"] = None
                row["question_match"] = None
                row["judge_error"] = str(e)[:300]
        except Exception as e:
            row["error"] = str(e)[:400]
        row["seconds"] = round(time.time() - t0, 1)
        rows.append(row)
        flag = "OK" if row.get("error") is None else "FAILED"
        print(f"[intent-bench] {vid}: {flag} "
              f"p={row.get('primary_match')} q={row.get('question_match')} "
              f"({row['seconds']}s)", flush=True)

    n = len(rows)
    def cnt(k): return sum(1 for r in rows if r.get(k) is True)
    agg = {
        "run_id": run_id, "tags_root": tags_root, "total": n,
        "completed": sum(1 for r in rows if r.get("error") is None),
        "schema_valid": cnt("schema_valid"),
        "primary_unique": cnt("primary_unique"),
        "evidence_grounded": cnt("evidence_grounded"),
        "primary_semantic_match": cnt("primary_match"),
        "question_semantic_match": cnt("question_match"),
        "judge_failed": sum(1 for r in rows if r.get("primary_match") is None
                            and r.get("error") is None),
        "strength_agreement": sum(1 for r, it in zip(rows, items)
                                  if r.get("intent_strength") == it["intent_strength_gt"]),
        "gates": {
            "primary_ge_8": cnt("primary_match") >= 8 and n >= 10,
            "question_ge_8": cnt("question_match") >= 8 and n >= 10,
            "uniqueness_10": cnt("primary_unique") == n,
            "grounding_10": cnt("evidence_grounded") == n,
        },
        "samples": rows,
    }
    with open(os.path.join(out_root, "report.json"), "w", encoding="utf-8") as f:
        json.dump(agg, f, ensure_ascii=False, indent=2)
    _write_md(agg, os.path.join(out_root, "report.md"))
    return agg


def _write_md(agg: dict, path: str) -> None:
    g = agg["gates"]
    lines = [
        f"# V2.1b Intent Decision Benchmark — {agg['run_id']}", "",
        f"- upstream tags: `{agg['tags_root']}`",
        f"- completed: {agg['completed']}/{agg['total']}"
        f"  (judge failed: {agg['judge_failed']})", "",
        "| gate | actual | target |", "|---|---:|---:|",
        f"| Primary Driver semantic match | {agg['primary_semantic_match']}/{agg['total']} | >=8/10 {'✓' if g['primary_ge_8'] else '✗'} |",
        f"| Unresolved Question semantic match | {agg['question_semantic_match']}/{agg['total']} | >=8/10 {'✓' if g['question_ge_8'] else '✗'} |",
        f"| Primary uniqueness | {agg['primary_unique']}/{agg['total']} | 10/10 {'✓' if g['uniqueness_10'] else '✗'} |",
        f"| Evidence grounding | {agg['evidence_grounded']}/{agg['total']} | 10/10 {'✓' if g['grounding_10'] else '✗'} |",
        f"| Intent strength agreement (observation) | {agg['strength_agreement']}/{agg['total']} | — |",
        "", "## Per-sample", "",
        "| id | P | Q | strength | primary (GT→actual) |",
        "|---|---|---|---|---|",
    ]
    for r in agg["samples"]:
        if r.get("error"):
            lines.append(f"| {r['id']} | ERR | ERR | — | {r['error'][:80]} |")
            continue
        p = r.get("primary_match")
        q = r.get("question_match")
        ps = "✓" if p is True else ("✗" if p is False else "?")
        qs = "✓" if q is True else ("✗" if q is False else "?")
        lines.append(f"| {r['id']} | {ps} | {qs} | {r.get('intent_strength')} "
                     f"| {r.get('primary_statement', '')[:120]} |")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def main() -> int:
    ap = argparse.ArgumentParser(prog="v2.benchmarks.run_intent_benchmark")
    ap.add_argument("--tags-root", default="output/benchmark-runs/v2.1a-val-phase2",
                    help="root containing <vid>/run0/v2/creative_tags.json")
    ap.add_argument("--run-id", default=f"intent-{int(time.time())}")
    ap.add_argument("--only", default=None, help="comma-separated ids, e.g. v01,v02")
    args = ap.parse_args()
    only = [s.strip() for s in args.only.split(",")] if args.only else None
    agg = run_benchmark(args.tags_root, args.run_id, only)
    print(f"\n========== Intent Benchmark {agg['run_id']} ==========")
    print(f"primary match: {agg['primary_semantic_match']}/{agg['total']}  "
          f"question match: {agg['question_semantic_match']}/{agg['total']}  "
          f"unique: {agg['primary_unique']}  grounded: {agg['evidence_grounded']}  "
          f"strength agree: {agg['strength_agreement']}")
    print(f"report: output/benchmark-runs/{agg['run_id']}/report.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
