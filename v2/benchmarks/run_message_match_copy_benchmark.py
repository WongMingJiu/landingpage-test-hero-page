#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V2.3 Message Match Copy — first-pass benchmark runner.

For each creative v01..v10:
  1. load frozen upstream outputs (V2.1a creative_tags.json + V2.1b
     creative_intent.json) — human GT is NEVER an input to generation;
  2. run MessageMatchCopyPipeline -> message_match_copy_v1
     (anchors + grounding pack + T1 copy + T2 copy, one call, as-is);
  3. programmatic gates:
       A. Schema validity (per template unit)
       B. Slot contract (char budgets, from the Frozen template prompts)
       C. Compliance / scope / price (banned_words_common + KB §9 guards)
       D. Grounding trace (used_facts ⊆ pack; pack statements must reference KB)
  4. LLM semantic judge (anchor preservation / intent continuity / template
     differentiation / copy-quality observation), native booleans only.

First-run discipline: Build Once -> Run v01-v10 Once -> Record As-Is.
Engineering retries (API / JSON parse) are bounded and logged; semantic
retries are forbidden. No prompt/schema tuning on failure.

Usage:
    python -m v2.benchmarks.run_message_match_copy_benchmark \
        --tags-root output/benchmark-runs/v2.1a-val-phase2 \
        --intent-root output/benchmark-runs/intent-b2 \
        --run-id v2.3-message-match-copy-first-pass
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import time

from v2 import message_match_schema as mms
from v2.message_match_copy import MessageMatchCopyPipeline, PROMPT_PATH, KB_PATH
from v2.tagging import ApiClient, TaggingConfig, extract_json

_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CREATIVES = [f"v{i:02d}" for i in range(1, 11)]

_JUDGE_SYSTEM = """你是 V2.3 Message Match Copy Benchmark 的语义判定器（judge）。
你会收到：一条广告的 V2.1a 价值标签摘要、V2.1b 意图（primary_driver / unresolved_question）、
以及同一广告生成的 T1 Copy 与 T2 Copy（含 Creative Anchors）。

逐项判定：

1. anchor_preserved_t1 / anchor_preserved_t2 —— 用户从原广告进入这张 Hero 时，
   是否明显感觉页面仍在继续谈同一个具体问题 / 期待（核心语义连续性，不是字符串一致）：
   - true：headline 或整体文案保留了广告最具体的 Anchor 语义（具体话题、具体提法）；
   - false：文案只谈泛泛的唱歌话题，或换成了与当前广告无关的其他卖点。

2. intent_continuity_t1 / intent_continuity_t2 —— Hero 是否仍在回答
   primary_driver / unresolved_question，而没有把用户带到另一个销售话题：
   - true：文案方向继续回答同一 Intent（怎么练 / 适不适合我 / 能不能学会等）；
   - false：另起完全不同的话题，或只重复广告已明确回答的问题。

3. template_differentiation —— 同一 Creative 的 T1 与 T2 是否明显体现不同的销售结构，
   但仍然承接同一广告：
   - true：T1 呈现 问题→方法→Benefit 结构，T2 呈现 顾虑/问题→适配/老师→学习支持
     结构，且两者不是同一句话换近义词；
   - false：两套只是同义改写，销售结构无差异。

只输出一个 JSON 对象，无解释文字：
{"anchor_preserved_t1": true|false, "anchor_reason_t1": "一句话理由",
 "anchor_preserved_t2": true|false, "anchor_reason_t2": "一句话理由",
 "intent_continuity_t1": true|false, "intent_reason_t1": "一句话理由",
 "intent_continuity_t2": true|false, "intent_reason_t2": "一句话理由",
 "template_differentiation": true|false, "differentiation_reason": "一句话理由",
 "quality_notes_t1": "一句话观察", "quality_notes_t2": "一句话观察"}"""

_JUDGE_BOOL_FIELDS = [
    "anchor_preserved_t1", "anchor_preserved_t2",
    "intent_continuity_t1", "intent_continuity_t2", "template_differentiation",
]

_KB_HIT_THRESHOLD = 0.30  # bigram coverage of a fact statement over the KB text
_SIMILARITY_WARN_THRESHOLD = 0.60  # T1/T2 headline bigram-Jaccard warning level


def _headline_similarity(output: dict) -> dict:
    """Bigram-Jaccard similarity between the COMBINED T1 vs T2 headline lines.

    Observation-level warning against same-surface rewrites (round-1 v06
    failure mode: T1 「别用嗓子挤/学后腰发力」 vs T2 「总用嗓子挤/学后腰发力」,
    J=0.80). The threshold is tuned so that legitimate Anchor sharing stays
    below (round-1 v01 「多年没学明白/用身体唱歌」 vs 「多年没学懂/身体唱歌法」,
    J=0.46 — both templates are SUPPOSED to keep the core Anchor 「身体唱歌」).
    NOT a gate — template differentiation is still adjudicated by the judge.
    """
    def _joined(side: str) -> str:
        slots = (output.get(side, {}).get("slots", {}) or {})
        return _norm(slots.get("headline_line_1", "") + slots.get("headline_line_2", ""))

    h1, h2 = _joined("t1"), _joined("t2")
    b1, b2 = _bigrams(h1), _bigrams(h2)
    j = round(len(b1 & b2) / len(b1 | b2), 2) if (b1 and b2) else 0.0
    return {"headline_jaccard": j,
            "differentiation_risk": j >= _SIMILARITY_WARN_THRESHOLD}


def _tags_path(tags_root: str, vid: str) -> str:
    for rel in (os.path.join(vid, "run0", "v2", "creative_tags.json"),
                os.path.join(vid, "v2", "creative_tags.json"),
                os.path.join(vid, "creative_tags.json")):
        p = os.path.join(tags_root, rel)
        if os.path.isfile(p):
            return p
    raise FileNotFoundError(f"creative_tags.json not found for {vid} under {tags_root}")


def _intent_path(intent_root: str, vid: str) -> str:
    p = os.path.join(intent_root, vid, "creative_intent.json")
    if os.path.isfile(p):
        return p
    raise FileNotFoundError(f"creative_intent.json not found for {vid} under {intent_root}")


def _norm(s: str) -> str:
    return re.sub(r"\s+", "", s or "")


def _bigrams(s: str) -> set:
    return {s[i:i + 2] for i in range(len(s) - 1)} if len(s) > 1 else {s} if s else set()


def _kb_hit_ratio(statement: str, kb_norm: str) -> float:
    bg = _bigrams(_norm(statement))
    if not bg:
        return 1.0
    hits = sum(1 for g in bg if g in kb_norm)
    return hits / len(bg)


def _side_errors(errors: list, side: str) -> list:
    return [e for e in errors if e.startswith(f"{side}.")]


def _judge_user_content(tags: dict, intent: dict, output: dict) -> list:
    tag_summary = [
        f"[{t.get('salience', '?')}] {t.get('label', '?')}（{t.get('category', '?')}）"
        for t in tags.get("matched_value_tags", [])
    ]
    anchors = output.get("creative_anchors", {})
    t1 = output.get("t1", {})
    t2 = output.get("t2", {})
    text = (
        "【广告 V2.1a 价值标签摘要】\n" + "\n".join(tag_summary)
        + "\n\n【V2.1b Creative Intent】\n"
          f"primary_driver: {intent['primary_driver']['statement']}\n"
          f"unresolved_question: {intent['unresolved_question']['statement']}\n"
          f"intent_strength: {intent.get('intent_strength', '?')}"
        + "\n\n【Creative Anchors（Step A 产物）】\n"
          f"topics: {'、'.join(t.get('value', '') for t in anchors.get('topics', []))}\n"
          f"phrases: {'、'.join(p.get('value', '') for p in anchors.get('phrases', []))}\n"
          f"user_concern: {anchors.get('user_concern', {}).get('value', '')}\n"
          f"expectation: {anchors.get('expectation', {}).get('value', '')}"
        + "\n\n【T1 Copy（问题→方法→四利益卡）】\n"
        + "\n".join(f"{k}: {v}" for k, v in t1.get("slots", {}).items())
        + "\n\n【T2 Copy（老师→适配→低门槛）】\n"
        + "\n".join(f"{k}: {v}" for k, v in t2.get("slots", {}).items())
        + "\n\n请按 system 指令逐项判定，只输出 JSON 对象。"
    )
    return [{"type": "text", "text": text}]


def _run_judge(provider, tags: dict, intent: dict, output: dict, max_retries: int = 2) -> dict:
    user = _judge_user_content(tags, intent, output)
    for attempt in range(1, max_retries + 1):
        raw = provider.chat(_JUDGE_SYSTEM, user)
        try:
            verdict = extract_json(raw)
        except (ValueError, json.JSONDecodeError) as e:
            print(f"[judge] JSON parse failed (attempt {attempt}/{max_retries}): {e}", flush=True)
            continue
        bad = [f for f in _JUDGE_BOOL_FIELDS if not isinstance(verdict.get(f), bool)]
        if bad:
            print(f"[judge] non-native boolean fields: {bad} "
                  f"(attempt {attempt}/{max_retries})", flush=True)
            continue
        verdict["_engineering_retries"] = attempt - 1
        return verdict
    raise RuntimeError("judge failed after bounded engineering retries")


def evaluate_creative(output: dict, tags: dict, intent: dict, judge: dict,
                      kb_norm: str, t1_contract: dict, t2_contract: dict,
                      banned_dict: dict) -> dict:
    """Programmatic gates A-D (per template unit) + judge verdicts E-G + notes H."""
    schema_errors = mms.validate_schema(output)
    contract_errors = mms.validate_slot_contract(output, t1_contract, t2_contract)
    compliance_errors = mms.validate_compliance(output, banned_dict)
    trace_errors = mms.validate_grounding_trace(output)

    # D-extension: KB reference check for every grounding-pack fact statement.
    pack = output.get("product_grounding_pack", {})
    kb_weak: list = []
    for key in ("course_facts", "service_facts", "teacher_facts"):
        for it in pack.get(key) or []:
            if isinstance(it, dict) and it.get("statement"):
                ratio = _kb_hit_ratio(it["statement"], kb_norm)
                if ratio < _KB_HIT_THRESHOLD:
                    kb_weak.append({"statement": it["statement"], "kb_hit_ratio": round(ratio, 2)})

    eval_result = {
        "schema_errors": schema_errors,
        "slot_contract_errors": contract_errors,
        "newline_slot_values": mms.newline_slot_values(output),
        "compliance_errors": compliance_errors,
        "grounding_trace_errors": trace_errors,
        "kb_weak_references": kb_weak,
        "headline_similarity": _headline_similarity(output),
        "review_needed": (output.get("review") or {}).get("needed"),
        "grounding_status": pack.get("grounding_status"),
        "unsupported_anchors": pack.get("unsupported_anchors", []),
        "judge": judge,
        "units": {},
    }
    for side in ("t1", "t2"):
        eval_result["units"][side] = {
            "schema_valid": not _side_errors(schema_errors, side),
            "slot_contract": not _side_errors(contract_errors, side),
            "compliance": not _side_errors(compliance_errors, side),
            "grounding_safe": (not _side_errors(trace_errors, side)) and not kb_weak,
        }
    return eval_result


def main() -> None:
    ap = argparse.ArgumentParser(description="V2.3 first-pass benchmark runner")
    ap.add_argument("--tags-root", default="output/benchmark-runs/v2.1a-val-phase2")
    ap.add_argument("--intent-root", default="output/benchmark-runs/intent-b2")
    ap.add_argument("--run-id", default="v2.3-message-match-copy-first-pass")
    ap.add_argument("--creatives", nargs="*", default=CREATIVES)
    ap.add_argument("--dry-run", action="store_true",
                    help="assemble inputs and print sizes only; no API calls")
    ap.add_argument("--re-evaluate", action="store_true",
                    help="recompute programmatic gates from existing output.json files "
                         "(judge verdicts reused; NO regeneration; for evaluation-"
                         "harness bugfix bookkeeping only, must be disclosed in the report)")
    args = ap.parse_args()

    out_root = os.path.join("output", "benchmark-runs", args.run_id)
    os.makedirs(out_root, exist_ok=True)

    cfg = TaggingConfig.from_env()
    with open(PROMPT_PATH, encoding="utf-8") as f:
        prompt_sha = hashlib.sha256(f.read().encode("utf-8")).hexdigest()[:12]
    with open(KB_PATH, encoding="utf-8") as f:
        kb_text = f.read()
    kb_norm = _norm(kb_text)

    print(f"[v2.3-bench] run-id={args.run_id}")
    print(f"[v2.3-bench] provider={cfg.api_base} model={cfg.model} "
          f"temperature={cfg.temperature} prompt_sha={prompt_sha}")

    if args.dry_run:
        for vid in args.creatives:
            tp, ip = _tags_path(args.tags_root, vid), _intent_path(args.intent_root, vid)
            with open(tp, encoding="utf-8") as f:
                tags = json.load(f)
            with open(ip, encoding="utf-8") as f:
                intent = json.load(f)
            pipe = MessageMatchCopyPipeline(ApiClient(cfg.api_base, cfg.api_key, cfg.model,
                                                       max_retries=1))
            user = pipe.build_user_content(tags, intent)
            print(f"[dry-run] {vid}: tags={os.path.getsize(tp)}B intent={os.path.getsize(ip)}B "
                  f"user_chars={sum(len(p['text']) for p in user if p.get('text'))} "
                  f"system_chars={len(pipe.system)}")
        print("[dry-run] OK — no API calls were made")
        return

    provider = ApiClient(cfg.api_base, cfg.api_key, cfg.model,
                         temperature=cfg.temperature, max_retries=cfg.api_retries)
    pipe = MessageMatchCopyPipeline(provider)
    t1_contract, t2_contract = pipe.t1_contract, pipe.t2_contract
    banned_dict = mms.load_compliance_lists()

    samples = []
    if args.re_evaluate:
        # Recompute programmatic gates from existing outputs only. Judge verdicts
        # are reused verbatim; nothing is regenerated. Used solely to correct an
        # evaluation-harness counting bug (whitespace-inclusive char count) — the
        # correction must be disclosed in the report.
        for vid in args.creatives:
            vdir = os.path.join(out_root, vid)
            out_path = os.path.join(vdir, "output.json")
            ev_path = os.path.join(vdir, "evaluation.json")
            if not (os.path.isfile(out_path) and os.path.isfile(ev_path)):
                print(f"[re-evaluate] {vid}: missing output.json/evaluation.json, skipped")
                continue
            with open(out_path, encoding="utf-8") as f:
                doc = json.load(f)
            with open(ev_path, encoding="utf-8") as f:
                old_ev = json.load(f)
            output, gen_meta = doc["output"], doc.get("meta", {})
            with open(_tags_path(args.tags_root, vid), encoding="utf-8") as f:
                tags = json.load(f)
            judge = old_ev.get("judge", {})
            ev = evaluate_creative(output, tags, {}, judge, kb_norm,
                                   t1_contract, t2_contract, banned_dict)
            with open(ev_path, "w", encoding="utf-8") as f:
                json.dump(ev, f, ensure_ascii=False, indent=2)
            samples.append({
                "id": vid, "error": None,
                "generation_seconds": gen_meta.get("seconds"),
                "engineering_retries": gen_meta.get("engineering_retries", 0),
                "judge_failed": bool(judge.get("judge_failed")),
                "grounding_status": ev["grounding_status"],
                "review_needed": ev["review_needed"],
                "units": ev["units"],
                "judge": {k: judge.get(k) for k in
                          _JUDGE_BOOL_FIELDS + ["differentiation_reason",
                                                "anchor_reason_t1", "anchor_reason_t2",
                                                "intent_reason_t1", "intent_reason_t2",
                                                "quality_notes_t1", "quality_notes_t2"]},
                "t1_headline": (output.get("t1", {}).get("slots", {}).get("headline_line_1", "") + "/" +
                                output.get("t1", {}).get("slots", {}).get("headline_line_2", "")),
                "t2_headline": (output.get("t2", {}).get("slots", {}).get("headline_line_1", "") + "/" +
                                output.get("t2", {}).get("slots", {}).get("headline_line_2", "")),
                "core_anchors": [t.get("value") for t in
                                 output.get("creative_anchors", {}).get("topics", [])]
                               + [p.get("value") for p in
                                  output.get("creative_anchors", {}).get("phrases", [])],
                "schema_errors": ev["schema_errors"],
                "slot_contract_errors": ev["slot_contract_errors"],
                "newline_slot_values": ev["newline_slot_values"],
                "compliance_errors": ev["compliance_errors"],
                "grounding_trace_errors": ev["grounding_trace_errors"],
                "kb_weak_references": ev["kb_weak_references"],
                "headline_similarity": ev["headline_similarity"],
                "re_evaluated": True,
            })
            print(f"[re-evaluate] {vid}: gates recomputed", flush=True)
    else:
      for vid in args.creatives:
        t0 = time.time()
        tp, ip = _tags_path(args.tags_root, vid), _intent_path(args.intent_root, vid)
        with open(tp, encoding="utf-8") as f:
            tags = json.load(f)
        with open(ip, encoding="utf-8") as f:
            intent = json.load(f)

        vdir = os.path.join(out_root, vid)
        os.makedirs(vdir, exist_ok=True)
        input_doc = {
            "creative_id": vid,
            "v2_1a_tags_path": tp,
            "v2_1b_intent_path": ip,
            "creative_tags": tags,
            "creative_intent": intent,
            "generation": {
                "prompt": "v2/prompts/message_match_copy.md",
                "prompt_sha256_12": prompt_sha,
                "model": cfg.model,
                "api_base": cfg.api_base,
                "temperature": cfg.temperature,
                "steps": "A+B+C in one call (anchors + grounding pack + t1 + t2 + review)",
            },
        }
        with open(os.path.join(vdir, "input.json"), "w", encoding="utf-8") as f:
            json.dump(input_doc, f, ensure_ascii=False, indent=2)

        rec: dict = {"id": vid, "error": None}
        try:
            output, gen_meta = pipe.run(vid, tags, intent)
            with open(os.path.join(vdir, "output.json"), "w", encoding="utf-8") as f:
                json.dump({"output": output, "meta": gen_meta}, f, ensure_ascii=False, indent=2)

            try:
                judge = _run_judge(provider, tags, intent, output)
            except RuntimeError as e:
                judge = {"judge_failed": str(e)}
            ev = evaluate_creative(output, tags, intent, judge, kb_norm,
                                   t1_contract, t2_contract, banned_dict)
            with open(os.path.join(vdir, "evaluation.json"), "w", encoding="utf-8") as f:
                json.dump(ev, f, ensure_ascii=False, indent=2)

            rec.update({
                "generation_seconds": gen_meta["seconds"],
                "engineering_retries": gen_meta["engineering_retries"],
                "judge_failed": bool(judge.get("judge_failed")),
                "grounding_status": ev["grounding_status"],
                "review_needed": ev["review_needed"],
                "units": ev["units"],
                "judge": {k: judge.get(k) for k in
                          _JUDGE_BOOL_FIELDS + ["differentiation_reason",
                                                "anchor_reason_t1", "anchor_reason_t2",
                                                "intent_reason_t1", "intent_reason_t2",
                                                "quality_notes_t1", "quality_notes_t2"]},
                "t1_headline": (output.get("t1", {}).get("slots", {})
                                .get("headline_line_1", "") + "/" +
                                output.get("t1", {}).get("slots", {}).get("headline_line_2", "")),
                "t2_headline": (output.get("t2", {}).get("slots", {})
                                .get("headline_line_1", "") + "/" +
                                output.get("t2", {}).get("slots", {}).get("headline_line_2", "")),
                "core_anchors": [t.get("value") for t in
                                 output.get("creative_anchors", {}).get("topics", [])]
                               + [p.get("value") for p in
                                  output.get("creative_anchors", {}).get("phrases", [])],
                "schema_errors": ev["schema_errors"],
                "slot_contract_errors": ev["slot_contract_errors"],
                "newline_slot_values": ev["newline_slot_values"],
                "compliance_errors": ev["compliance_errors"],
                "grounding_trace_errors": ev["grounding_trace_errors"],
                "kb_weak_references": ev["kb_weak_references"],
                "headline_similarity": ev["headline_similarity"],
            })
        except Exception as e:  # engineering failure — record as-is, keep going
            rec["error"] = f"{type(e).__name__}: {e}"
        rec["wall_seconds"] = round(time.time() - t0, 1)
        samples.append(rec)
        print(f"[v2.3-bench] {vid}: done in {rec['wall_seconds']}s "
              f"({'error: ' + rec['error'] if rec['error'] else 'ok'})", flush=True)

    # ---- summary ------------------------------------------------------------ #
    def _count(field: str, side: str) -> int:
        return sum(1 for s in samples if not s.get("error")
                   and s.get("units", {}).get(side, {}).get(field))

    def _jcount(field: str) -> int:
        return sum(1 for s in samples if not s.get("error")
                   and isinstance(s.get("judge", {}).get(field), bool)
                   and s["judge"][field])

    total_units = 2 * len([s for s in samples if not s.get("error")])
    completed = len([s for s in samples if not s.get("error")])
    summary = {
        "run_id": args.run_id,
        "tags_root": args.tags_root,
        "intent_root": args.intent_root,
        "model": cfg.model,
        "api_base": cfg.api_base,
        "temperature": cfg.temperature,
        "prompt_sha256_12": prompt_sha,
        "completed": completed,
        "engineering_failures": len(samples) - completed,
        "metrics": {
            "schema_validity": f"{_count('schema_valid', 't1') + _count('schema_valid', 't2')}/{total_units}",
            "slot_contract": f"{_count('slot_contract', 't1') + _count('slot_contract', 't2')}/{total_units}",
            "compliance_scope": f"{_count('compliance', 't1') + _count('compliance', 't2')}/{total_units}",
            "grounding_safety": f"{_count('grounding_safe', 't1') + _count('grounding_safe', 't2')}/{total_units}",
            "anchor_preservation_t1": f"{_jcount('anchor_preserved_t1')}/{completed}",
            "anchor_preservation_t2": f"{_jcount('anchor_preserved_t2')}/{completed}",
            "intent_continuity_t1": f"{_jcount('intent_continuity_t1')}/{completed}",
            "intent_continuity_t2": f"{_jcount('intent_continuity_t2')}/{completed}",
            "template_differentiation": f"{_jcount('template_differentiation')}/{completed}",
            "review_needed": f"{sum(1 for s in samples if s.get('review_needed'))}/{completed}",
            "judge_failed": sum(1 for s in samples if s.get("judge_failed")),
            "headline_similarity_warnings": sum(
                1 for s in samples if not s.get("error")
                and s.get("headline_similarity", {}).get("differentiation_risk")),
        },
        "samples": samples,
    }
    with open(os.path.join(out_root, "summary.json"), "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    print(f"[v2.3-bench] summary -> {os.path.join(out_root, 'summary.json')}")
    print(json.dumps(summary["metrics"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
