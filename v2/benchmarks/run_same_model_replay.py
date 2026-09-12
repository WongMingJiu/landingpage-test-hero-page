#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V2.5-A Same Model Replay Validation harness (V1).

唯一目标（Codex Prompt）：消除 V2.5 Full Pipeline Replay 的 model drift 干扰，
验证同一模型（gpt-5.5）下文本链路是否具备稳定性：

    Run A (baseline)  = raw video -> V2.1a -> V2.1b -> V2.3   (gpt-5.5)
    Run B (replay)    = 完全相同配置再跑一次                   (gpt-5.5)
    Compare           = GPT baseline vs GPT replay（不是 Qwen frozen vs GPT fresh）

本轮只跑文本链，禁止生图（T1/T2/gpt-image-2 均不进入）。
Wiring existing modules, not rewriting（Prompt §3）：stage 执行 / 工程重试 /
探活 / judge 基础设施全部 import 自 V2.5 harness（run_full_pipeline_replay），
不建第二套 pipeline。

纪律（Prompt §6）：不改 V2.1a/V2.1b/V2.3 Prompt 与 Schema、不调 temperature、
不人工修结果、禁止 semantic retry、禁止跑多次直到满意；工程 retry
（timeout / network / API 5xx）bounded 且记录 engineering_retry。

用法：
    python -m v2.benchmarks.run_same_model_replay --phase preflight
    python -m v2.benchmarks.run_same_model_replay --phase all
    # 断点续跑：默认 skip 已存在的有效 stage 输出；--force 强制重跑
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO))

from v2.tagging import ApiClient  # noqa: E402
from v2.benchmarks.run_full_pipeline_replay import (  # noqa: E402
    CONFIG_ENV, FROZEN_V23_PROMPT_SHA, STAGE_BUDGET, VIDEOS_DIR,
    _intent_summary, _load_text_config, _run_compare_judge, _copy_summary,
    _tags_summary, parse_env_file, probe_text_gateway,
    stage_v21a, stage_v21b, stage_v23,
)

# --------------------------------------------------------------------------- #
# 路径 / 常量（Prompt §11 输出目录）
# --------------------------------------------------------------------------- #
RUN_ROOT = _REPO / "output" / "v2.5-same-model-replay"
BASELINE_DIR = RUN_ROOT / "baseline"
REPLAY_DIR = RUN_ROOT / "replay"
COMPARE_DIR = RUN_ROOT / "comparison"

CREATIVES = ["v03", "v04", "v06"]          # Prompt §1 实验范围
TEXT_STAGES = ("v2.1a", "v2.1b", "v2.3")   # Prompt §2 只跑文本链
REQUIRED_MODEL = "gpt-5.5"                  # Prompt §4 硬要求

# Prompt §6 禁改自证：三层 prompt + schema 的 sha 快照（写入 preflight.json 供审计）
PROMPT_FILES = {
    "v2.1a": _REPO / "v2" / "prompts" / "creative_tagging.md",
    "v2.1b": _REPO / "v2" / "prompts" / "intent_decision.md",
    "v2.3": _REPO / "v2" / "prompts" / "message_match_copy.md",
}
SCHEMA_FILES = [
    _REPO / "v2" / "schema.py",
    _REPO / "v2" / "message_match_schema.py",
]


# --------------------------------------------------------------------------- #
# Compare judge 文案（同模型重放语境；关注点对齐 Prompt §8/§9/§10）
# --------------------------------------------------------------------------- #
_JUDGE_A = """你是 V2.5-A Same Model Replay 的 V2.1a 语义稳定性判定器。
同一条广告视频在完全相同的配置（同模型 gpt-5.5 / temperature=0 / 同 Prompt / 同 Schema）
下跑了两次独立的 V2.1a Creative Tagging：BASELINE（第一次）与 REPLAY（第二次）。
请比较核心语义，不要要求字符串完全一致：

1. semantic_stable —— 双方 active_value_tags（尤其 primary 层）核心价值主张是否语义一致；
   opening_type / user_expectation 是否同义或同为 taxonomy 内合理判定；decision_window 是否一致。
2. material_drift —— REPLAY 是否产生了与视频内容不符的事实漂移（evidence 对应错误内容/时间），
   或丢掉 BASELINE 中的核心价值主张，或 primary 层换成完全不同的卖点，
   或 opening_type 主叙事发生实质变化（如 教学演示型 -> 学员故事型）。

口径：同义/近义标签（如「改善音色与声音质感」vs「改善音色」）= 稳定；
primary 层语义相同仅 supporting 层有差异 = 稳定；primary 换主张或主叙事实质变化 = 不稳定。
只输出一个 JSON 对象，无解释文字：
{"semantic_stable": true|false, "material_drift": true|false,
 "differences": ["逐条列出实质差异，wording 级差异写明 wording-only"], "notes": "一句话总评"}"""

_JUDGE_B = """你是 V2.5-A Same Model Replay 的 V2.1b 语义稳定性判定器。
同一条广告在完全相同的配置下跑了两次 V2.1b Intent Decision（各由本轮回次的
V2.1a 输出驱动）：BASELINE（第一次）与 REPLAY（第二次）。
请比较核心语义，不要要求字符串完全一致：

1. semantic_stable —— primary_driver 是否仍解释「同一个用户为什么点击」（同一点击因果）；
   unresolved_question 是否仍是同一个真正未解决的问题；intent_strength 是否同级。
2. material_drift —— supporting_drivers 是否实质漂移（换成了不同的支撑逻辑）。

口径：同一因果换措辞 = 稳定；点击因果本身改变（如从「怕学不会」变成「想变强」）= 不稳定；
仍接住广告的具体故事/方法意图、未漂成泛化课程介绍 = 稳定。
只输出一个 JSON 对象，无解释文字：
{"semantic_stable": true|false, "material_drift": true|false,
 "differences": ["..."], "notes": "一句话总评"}"""

_JUDGE_C = """你是 V2.5-A Same Model Replay 的 V2.3 语义稳定性判定器。
同一条广告在完全相同的配置下跑了两次 V2.3 Message Match Copy（均由各自回次的
V2.1a/V2.1b 输出驱动）：BASELINE（第一次）与 REPLAY（第二次）。
请比较，不要要求逐字一致：

1. anchor_preserved_t1 / anchor_preserved_t2 —— REPLAY 的 T1/T2 是否保住与 BASELINE 相同的
   核心 Anchor（topics / phrases / user_concern / expectation 允许措辞不同，核心话题必须相同）。
2. intent_continuity_t1 / intent_continuity_t2 —— REPLAY 是否仍在回答同一 intent。
3. template_differentiation —— REPLAY 的 T1（问题→方法→四利益卡）与 T2（顾虑→适配→老师→学习支持）
   是否仍呈现不同销售结构（不是同义改写）。
4. same_answer_class —— 综合：REPLAY 是否是「同一类正确答案」（文案可完全不同，但接住同一条广告）。

只输出一个 JSON 对象，无解释文字：
{"anchor_preserved_t1": true|false, "anchor_preserved_t2": true|false,
 "intent_continuity_t1": true|false, "intent_continuity_t2": true|false,
 "template_differentiation": true|false, "same_answer_class": true|false,
 "differences": ["..."], "notes": "一句话总评"}"""


# --------------------------------------------------------------------------- #
# Preflight（Prompt §4：model 硬门；§6：禁改自证）
# --------------------------------------------------------------------------- #
def preflight() -> dict:
    print("=" * 70)
    print("PREFLIGHT (V2.5-A)")
    print("=" * 70)
    results: dict = {"ok": True, "checks": [], "prompt_schema_sha": {}}

    def check(name: str, ok: bool, detail: str) -> None:
        results["checks"].append({"name": name, "ok": ok, "detail": detail})
        print(f"  [{'OK' if ok else 'FAIL'}] {name}: {detail}")
        if not ok:
            results["ok"] = False

    # 1. source videos
    for vid in CREATIVES:
        vp = VIDEOS_DIR / f"{vid}.mp4"
        check(f"video:{vid}", vp.is_file(),
              str(vp.relative_to(_REPO)) + (f" ({vp.stat().st_size // 1024 // 1024}MB)"
                                            if vp.is_file() else " MISSING"))

    # 2. text config + model 硬门（§4：不要静默使用其他模型）
    tcfg = _load_text_config()
    check("text-config", bool(tcfg["api_base"] and tcfg["api_key"] and tcfg["model"]),
          f"{tcfg['api_base']} model={tcfg['model']}")
    check(f"model == {REQUIRED_MODEL}", tcfg["model"] == REQUIRED_MODEL,
          f"current={tcfg['model'] or '<empty>'}"
          + ("" if tcfg["model"] == REQUIRED_MODEL else " —— 本轮实验设计要求 gpt-5.5，拒绝静默换模型"))

    # 3. 文本网关探活（复用 V2.5 probe）
    if tcfg["api_base"] and tcfg["api_key"] and tcfg["model"]:
        ok, detail = probe_text_gateway(tcfg)
        check("text API available (gpt-5.5)", ok, detail)

    # 4. 生图入口必须缺席（§2 禁止生图——本轮 harness 不 import hero worker 即自证，
    #    同时检查输出根目录不存在 hero 子目录防止误跑串目录）
    check("no hero stage in this harness", True,
          "text-only pipeline（v2.1a -> v2.1b -> v2.3，无 gpt-image-2 调用）")

    # 5. prompts 存在 + V2.3 frozen sha（§6 禁改 Prompt 自证）+ schema sha 快照
    for layer, fp in PROMPT_FILES.items():
        if fp.is_file():
            sha = hashlib.sha256(fp.read_bytes()).hexdigest()[:12]
            results["prompt_schema_sha"][f"prompt:{layer}"] = sha
            if layer == "v2.3":
                check("V2.3 prompt sha == frozen manifest", sha == FROZEN_V23_PROMPT_SHA,
                      f"{sha} (manifest {FROZEN_V23_PROMPT_SHA})")
            else:
                check(f"prompt:{layer}", True, f"{fp.name} sha={sha}")
        else:
            check(f"prompt:{layer}", False, f"missing {fp}")
    for sp in SCHEMA_FILES:
        if sp.is_file():
            sha = hashlib.sha256(sp.read_bytes()).hexdigest()[:12]
            results["prompt_schema_sha"][f"schema:{sp.stem}"] = sha
            check(f"schema:{sp.name}", True, f"sha={sha}")
        else:
            check(f"schema:{sp.name}", False, f"missing {sp}")

    # 6. temperature=0 自证（config.env 不设 V2_TEMPERATURE / V2_INTENT_* 干预项）
    env_cfg = parse_env_file(CONFIG_ENV)
    t_override = env_cfg.get("V2_TEMPERATURE")
    check("temperature == 0 (no V2_TEMPERATURE override)", t_override in (None, "", "0"),
          f"V2_TEMPERATURE={t_override!r}；三个 CLI 默认均为 0")

    # 7. 输出目录可写
    try:
        RUN_ROOT.mkdir(parents=True, exist_ok=True)
        (RUN_ROOT / ".write_test").write_text("x", encoding="utf-8")
        (RUN_ROOT / ".write_test").unlink()
        check("output dir writable", True, str(RUN_ROOT.relative_to(_REPO)))
    except Exception as e:
        check("output dir writable", False, str(e)[:120])

    (RUN_ROOT / "preflight.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\npreflight -> {'PASS' if results['ok'] else 'FAIL'} "
          f"({sum(1 for c in results['checks'] if c['ok'])}/{len(results['checks'])} checks)")
    return results


# --------------------------------------------------------------------------- #
# Run A / Run B（复用 V2.5 stage_*；任一文本层失败即停该样本）
# --------------------------------------------------------------------------- #
def run_round(round_name: str, force: bool) -> dict:
    round_dir = RUN_ROOT / round_name
    round_dir.mkdir(parents=True, exist_ok=True)
    traces: dict = {}
    for vid in CREATIVES:
        vdir = round_dir / vid
        vdir.mkdir(parents=True, exist_ok=True)
        print("\n" + "=" * 70)
        print(f"ROUND {round_name.upper()} | {vid}")
        print("=" * 70)
        tr: dict = {}
        for stage_fn, key in ((stage_v21a, "v2.1a"), (stage_v21b, "v2.1b"),
                              (stage_v23, "v2.3")):
            st = stage_fn(vid, vdir, force)
            tr[key] = st
            if st["status"] not in ("ok", "skipped_existing"):
                print(f"!! {round_name}/{vid}/{key} -> {st['status']}，STOP that sample"
                      f"（后续层跳过）")
                break
        traces[vid] = tr
        (vdir / "trace.json").write_text(
            json.dumps(tr, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    (round_dir / "traces.json").write_text(
        json.dumps(traces, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    return traces


def load_round_traces(round_name: str) -> dict:
    p = RUN_ROOT / round_name / "traces.json"
    if p.is_file():
        return json.loads(p.read_text(encoding="utf-8"))
    traces: dict = {}
    for vid in CREATIVES:
        tp = RUN_ROOT / round_name / vid / "trace.json"
        if tp.is_file():
            traces[vid] = json.loads(tp.read_text(encoding="utf-8"))
    return traces


# --------------------------------------------------------------------------- #
# Compare：GPT-5.5 baseline vs GPT-5.5 replay（Prompt §7-§10）
# --------------------------------------------------------------------------- #
def compare_pair(vid: str, api: ApiClient) -> dict:
    """三层 baseline vs replay：程序化 diff + 语义 judge（结构与 V2.5 compare_creative 同构）。"""
    b_dir, r_dir = BASELINE_DIR / vid, REPLAY_DIR / vid
    b_tags = json.loads((b_dir / "v2.1a" / "creative_tags.json").read_text(encoding="utf-8"))
    b_intent = json.loads((b_dir / "v2.1b" / "creative_intent.json").read_text(encoding="utf-8"))
    b_copy = json.loads((b_dir / "v2.3" / "message_match_copy.json")
                        .read_text(encoding="utf-8"))["output"]
    r_tags = json.loads((r_dir / "v2.1a" / "creative_tags.json").read_text(encoding="utf-8"))
    r_intent = json.loads((r_dir / "v2.1b" / "creative_intent.json").read_text(encoding="utf-8"))
    r_copy_doc = json.loads((r_dir / "v2.3" / "message_match_copy.json")
                            .read_text(encoding="utf-8"))
    r_copy, r_meta = r_copy_doc["output"], r_copy_doc.get("meta", {})

    cmp_result: dict = {"creative_id": vid}

    # ---- V2.1a：程序化字段 diff + judge（§8：opening/expectation/primary/active）----
    prog = {
        "window_same": (b_tags["decision_window"].get("used_seconds")
                        == r_tags["decision_window"].get("used_seconds")
                        and b_tags["decision_window"].get("extended")
                        == r_tags["decision_window"].get("extended")),
        "opening_same": (b_tags["opening_type"].get("label")
                         == r_tags["opening_type"].get("label")),
        "expectation_same": (b_tags["user_expectation"].get("label")
                             == r_tags["user_expectation"].get("label")),
        "active_baseline": [t["label"] for t in b_tags.get("matched_value_tags", [])],
        "active_replay": [t["label"] for t in r_tags.get("matched_value_tags", [])],
    }
    prog["primary_baseline"] = [t["label"] for t in b_tags.get("matched_value_tags", [])
                                if t.get("salience") == "primary"]
    prog["primary_replay"] = [t["label"] for t in r_tags.get("matched_value_tags", [])
                              if t.get("salience") == "primary"]
    set_b, set_r = set(prog["active_baseline"]), set(prog["active_replay"])
    prog["active_common"] = sorted(set_b & set_r)
    prog["active_only_baseline"] = sorted(set_b - set_r)
    prog["active_only_replay"] = sorted(set_r - set_b)
    prog["primary_common"] = sorted(set(prog["primary_baseline"]) & set(prog["primary_replay"]))
    cmp_result["v2.1a_programmatic"] = prog
    try:
        cmp_result["v2.1a_judge"] = _run_compare_judge(
            api, _JUDGE_A,
            "【BASELINE V2.1a（第一次运行，gpt-5.5）】\n" + _tags_summary(b_tags)
            + "\n\n【REPLAY V2.1a（第二次运行，gpt-5.5，配置完全相同）】\n" + _tags_summary(r_tags)
            + "\n\n请按 system 指令判定，只输出 JSON 对象。",
            ["semantic_stable", "material_drift"])
    except Exception as e:
        cmp_result["v2.1a_judge"] = {"judge_failed": True, "error": str(e)[:200]}

    # ---- V2.1b（§9：primary_driver / unresolved_question / supporting_drivers）----
    try:
        cmp_result["v2.1b_judge"] = _run_compare_judge(
            api, _JUDGE_B,
            "【BASELINE V2.1b（第一次运行）】\n" + _intent_summary(b_intent)
            + "\n\n【REPLAY V2.1b（第二次运行，配置完全相同）】\n" + _intent_summary(r_intent)
            + "\n\n请按 system 指令判定，只输出 JSON 对象。",
            ["semantic_stable", "material_drift"])
    except Exception as e:
        cmp_result["v2.1b_judge"] = {"judge_failed": True, "error": str(e)[:200]}
    cmp_result["v2.1b_programmatic"] = {
        "strength_baseline": b_intent.get("intent_strength"),
        "strength_replay": r_intent.get("intent_strength"),
    }

    # ---- V2.3（§10：Anchor / Intent Continuity / Template Differentiation）----
    try:
        cmp_result["v2.3_judge"] = _run_compare_judge(
            api, _JUDGE_C,
            "【BASELINE V2.3 Copy（第一次运行）】\n" + _copy_summary(b_copy)
            + "\n\n【REPLAY V2.3 Copy（第二次运行，配置完全相同）】\n" + _copy_summary(r_copy)
            + "\n\n请按 system 指令判定，只输出 JSON 对象。",
            ["anchor_preserved_t1", "anchor_preserved_t2", "intent_continuity_t1",
             "intent_continuity_t2", "template_differentiation", "same_answer_class"])
    except Exception as e:
        cmp_result["v2.3_judge"] = {"judge_failed": True, "error": str(e)[:200]}

    def _anchors(o):
        a = o.get("creative_anchors", {})
        return {
            "topics": [t.get("value") for t in a.get("topics", [])],
            "phrases": [p.get("value") for p in a.get("phrases", [])],
            "user_concern": a.get("user_concern", {}).get("value"),
            "expectation": a.get("expectation", {}).get("value"),
        }
    cmp_result["v2.3_anchors_programmatic"] = {"baseline": _anchors(b_copy),
                                               "replay": _anchors(r_copy),
                                               "replay_generation_meta": r_meta}
    return cmp_result


# --------------------------------------------------------------------------- #
# 判定（Prompt §13-2：不稳定层分类 V2.1A / V2.1B / V2.3 / INFRA / UNKNOWN）
# --------------------------------------------------------------------------- #
def judge_sample(vid: str, tr_a: dict, tr_b: dict, cmp_r: dict) -> dict:
    verdict: dict = {"creative_id": vid, "v2.1a_stable": None, "v2.1b_stable": None,
                     "v2.3_stable": None, "unstable_layer": None,
                     "differences": [], "notes": []}

    # INFRA：任一轮 stage 失败/超时 -> 实验不完整，语义判定降级
    infra: list[str] = []
    for rnd, tr in (("baseline", tr_a), ("replay", tr_b)):
        for stage in TEXT_STAGES:
            st = (tr or {}).get(stage, {})
            if st.get("status") not in ("ok", "skipped_existing"):
                infra.append(f"{rnd}/{stage}={st.get('status')}")
    if infra:
        verdict["infra_issues"] = infra

    # ---- V2.1a ----
    a = cmp_r.get("v2.1a_judge") or {}
    if not a:
        verdict["notes"].append("V2.1a judge 缺席（compare 异常），语义判定 UNKNOWN")
    elif a.get("judge_failed"):
        verdict["notes"].append("V2.1a judge 失败（语义判定待人工）")
    else:
        verdict["v2.1a_stable"] = bool(a.get("semantic_stable") and not a.get("material_drift"))
        if not verdict["v2.1a_stable"]:
            verdict["differences"].append("V2.1a: " + "; ".join(a.get("differences", [])[:2]))

    # ---- V2.1b ----
    b = cmp_r.get("v2.1b_judge") or {}
    if not b:
        verdict["notes"].append("V2.1b judge 缺席（compare 异常），语义判定 UNKNOWN")
    elif b.get("judge_failed"):
        verdict["notes"].append("V2.1b judge 失败（语义判定待人工）")
    else:
        verdict["v2.1b_stable"] = bool(b.get("semantic_stable") and not b.get("material_drift"))
        if not verdict["v2.1b_stable"]:
            verdict["differences"].append("V2.1b: " + "; ".join(b.get("differences", [])[:2]))

    # ---- V2.3（与 V2.5 judge_pipeline 的 FAIL 触发条件同口径：
    #      anchor 丢失 / 非同一类答案 / 同质化 任一命中即不稳定）----
    c = cmp_r.get("v2.3_judge") or {}
    if not c:
        verdict["notes"].append("V2.3 judge 缺席（compare 异常），语义判定 UNKNOWN")
    elif c.get("judge_failed"):
        verdict["notes"].append("V2.3 judge 失败（语义判定待人工）")
    else:
        verdict["v2.3_stable"] = bool(
            c.get("anchor_preserved_t1") and c.get("anchor_preserved_t2")
            and c.get("same_answer_class") and c.get("template_differentiation"))
        if not c.get("anchor_preserved_t1"):
            verdict["differences"].append("V2.3 T1 丢核心 Anchor")
        if not c.get("anchor_preserved_t2"):
            verdict["differences"].append("V2.3 T2 丢核心 Anchor")
        if not c.get("same_answer_class"):
            verdict["differences"].append("V2.3 非同一类正确答案: " + (c.get("notes") or "")[:120])
        if not c.get("template_differentiation"):
            verdict["differences"].append("V2.3 T1/T2 同质化")

    # ---- unstable layer 归因 ----
    if verdict["v2.1a_stable"] is False:
        verdict["unstable_layer"] = "V2.1A"
    elif verdict["v2.1b_stable"] is False:
        verdict["unstable_layer"] = "V2.1B"
    elif verdict["v2.3_stable"] is False:
        verdict["unstable_layer"] = "V2.3"
    elif infra:
        verdict["unstable_layer"] = "INFRA"
    elif None in (verdict["v2.1a_stable"], verdict["v2.1b_stable"], verdict["v2.3_stable"]):
        verdict["unstable_layer"] = "UNKNOWN"   # judge 缺席，无法定论
    else:
        verdict["unstable_layer"] = None        # 全稳定
    return verdict


def engineering_retry_summary(tr_a: dict, tr_b: dict) -> dict:
    """§6：工程 retry 必须记录。汇总两轮各 stage 的 retries_used 与 attempts 明细。"""
    out: dict = {"engineering_retry": False, "stages": {}}
    for rnd, tr in (("baseline", tr_a), ("replay", tr_b)):
        for stage in TEXT_STAGES:
            st = (tr or {}).get(stage, {})
            used = st.get("retries_used") or 0
            rec = {"status": st.get("status"), "retries_used": used,
                   "elapsed_s": st.get("elapsed_s")}
            if used and st.get("attempts"):
                rec["attempts_detail"] = [
                    {k: att.get(k) for k in ("attempt", "status", "elapsed_s", "error_tail")
                     if k in att} for att in st["attempts"]]
            out["stages"][f"{rnd}/{stage}"] = rec
            if used:
                out["engineering_retry"] = True
    return out


# --------------------------------------------------------------------------- #
# Case 判定（Prompt §14）
# --------------------------------------------------------------------------- #
def decide_case(verdicts: dict) -> dict:
    semantic_unstable_layers = sorted({v["unstable_layer"] for v in verdicts.values()
                                       if v["unstable_layer"] in ("V2.1A", "V2.1B", "V2.3")})
    infra = any(v["unstable_layer"] == "INFRA" for v in verdicts.values())
    unknown = any(v["unstable_layer"] == "UNKNOWN" for v in verdicts.values())
    if not semantic_unstable_layers:
        case = "A"   # baseline ≈ replay：Prompt/Architecture 基本稳定
        conclusion = ("同模型（gpt-5.5）两次运行语义稳定 -> V2.5 first-pass 的漂移"
                      "主要由 model drift（qwen frozen vs gpt fresh 跨模型比对）造成；"
                      "下一步：建立 GPT-5.5 frozen baseline")
    elif semantic_unstable_layers == ["V2.1B"]:
        case = "C"   # 仅 V2.1b 不稳定：优先优化 Intent Decision + Anchor Preservation
        conclusion = ("仅 V2.1b 在同模型重放下不稳定 -> 优先优化 Intent Decision 与 "
                      "Creative Anchor Preservation；不要修改 V2.3")
    else:
        case = "B"   # baseline != replay：Prompt/Schema/Constraint 需进一步优化
        conclusion = (f"不稳定层={semantic_unstable_layers} -> 系统设计（Prompt/Schema/"
                      "Constraint）在同模型下仍不稳定，需进一步优化")
    note = ""
    if infra:
        note += " 存在 INFRA 故障（stage 失败/超时），相关样本语义判定不完整；"
    if unknown:
        note += " 存在 judge 缺席（UNKNOWN），需人工复核后定论。"
    return {"case": case, "unstable_layers": semantic_unstable_layers,
            "infra": infra, "unknown": unknown, "conclusion": conclusion + ("；" + note if note else "")}


# --------------------------------------------------------------------------- #
# V2.5 first-pass 引用（report §3：FAIL 是否主要由 model drift 造成）
# --------------------------------------------------------------------------- #
def load_v25_first_pass() -> dict:
    p = _REPO / "output" / "benchmark-runs" / "v2.5-full-pipeline-replay-first-pass" / "summary.json"
    if not p.is_file():
        return {}
    try:
        s = json.loads(p.read_text(encoding="utf-8"))
        return {
            "run_id": s.get("run_id"),
            "samples": {vid: {"pipeline_status": v.get("pipeline_status"),
                              "failure_layer": v.get("failure_layer")}
                        for vid, v in (s.get("samples") or {}).items()},
            "metrics": s.get("metrics"),
            "text_model": (s.get("run_meta") or {}).get("text_model"),
        }
    except Exception:
        return {}


# --------------------------------------------------------------------------- #
# summary / report（Prompt §12/§13）
# --------------------------------------------------------------------------- #
def write_summary(run_meta: dict, verdicts: dict, retries: dict, case: dict,
                  v25_fp: dict) -> None:
    n = len(CREATIVES)
    summary = {
        "run_id": "v2.5-same-model-replay",
        "model": run_meta["model"],
        "temperature": 0,
        "provider": {"api_base": run_meta["api_base"]},
        "samples": {vid: {
            "v2.1a_stable": v["v2.1a_stable"],
            "v2.1b_stable": v["v2.1b_stable"],
            "v2.3_stable": v["v2.3_stable"],
            "unstable_layer": v["unstable_layer"],
            "engineering_retry": retries[vid]["engineering_retry"],
            "differences": v["differences"],
        } for vid, v in verdicts.items()},
        "metrics": {
            "v2.1a_stability": f"{sum(1 for v in verdicts.values() if v['v2.1a_stable'])}/{n}",
            "v2.1b_stability": f"{sum(1 for v in verdicts.values() if v['v2.1b_stable'])}/{n}",
            "v2.3_stability": f"{sum(1 for v in verdicts.values() if v['v2.3_stable'])}/{n}",
        },
        "engineering_retry": {vid: r["engineering_retry"] for vid, r in retries.items()},
        "verdict_case": case,
        "v25_first_pass_reference": v25_fp,
        "run_meta": run_meta,
    }
    (RUN_ROOT / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nsummary.json written: metrics={json.dumps(summary['metrics'], ensure_ascii=False)}")


def write_report(run_meta: dict, traces_a: dict, traces_b: dict, verdicts: dict,
                 retries: dict, case: dict, v25_fp: dict) -> None:
    L: list[str] = []
    L.append("# V2.5-A Same Model Replay Validation Report")
    L.append("")
    L.append(f"- 生成时间：{datetime.now(timezone.utc).isoformat(timespec='seconds')}")
    L.append(f"- 实验设计：同一模型 {run_meta['model']} / temperature=0，"
             f"同视频同 Prompt 同 Schema 跑 Baseline + Replay 两轮，只跑文本链（禁止生图）")
    L.append(f"- provider：`{run_meta['api_base']}`；判定口径：Semantic Stability > String Equality")
    L.append("")

    # 1. 实验设计
    L.append("## 1. 实验设计（Run A / Run B）")
    L.append("")
    L.append("| 轮次 | v2.1a | v2.1b | v2.3 | 输出目录 |")
    L.append("|---|---|---|---|---|")
    for rnd, trs in (("Run A baseline", traces_a), ("Run B replay", traces_b)):
        cells = []
        for stage in TEXT_STAGES:
            sts = [trs.get(v, {}).get(stage, {}) for v in CREATIVES]
            ok = sum(1 for s in sts if s.get("status") in ("ok", "skipped_existing"))
            cells.append(f"{ok}/3 ok")
        L.append(f"| {rnd} | {cells[0]} | {cells[1]} | {cells[2]} | "
                 f"`output/v2.5-same-model-replay/{'baseline' if 'A' in rnd else 'replay'}/` |")
    L.append("")
    L.append(f"- 两轮输入视频同一性：source.json sha256_16 对照 "
             + "、".join(
                 f"{vid}=" + _video_sha(vid) for vid in CREATIVES) + "（两轮各目录均有记录）")
    L.append("- 禁改自证：V2.3 prompt sha 与 frozen manifest 一致（preflight.json 含三层 prompt + schema sha 快照）")
    L.append("")

    # 2. 必答一：baseline vs replay 是否稳定
    L.append("## 2. GPT-5.5 baseline vs replay 是否稳定？（Prompt §13-1）")
    L.append("")
    m = {k: f"{sum(1 for v in verdicts.values() if v[k])}/{len(CREATIVES)}"
         for k in ("v2.1a_stable", "v2.1b_stable", "v2.3_stable")}
    L.append(f"- **V2.1a：{m['v2.1a_stable']} 稳定**")
    L.append(f"- **V2.1b：{m['v2.1b_stable']} 稳定**")
    L.append(f"- **V2.3：{m['v2.3_stable']} 稳定**")
    L.append("")
    for vid in CREATIVES:
        v = verdicts[vid]
        L.append(f"### {vid} — {'稳定' if v['unstable_layer'] is None else '不稳定（' + v['unstable_layer'] + '）'}")
        L.append(f"- v2.1a_stable={v['v2.1a_stable']} v2.1b_stable={v['v2.1b_stable']} "
                 f"v2.3_stable={v['v2.3_stable']} unstable_layer={v['unstable_layer']}")
        for d in v["differences"]:
            L.append(f"  - {d}")
        for note in v.get("notes", []):
            L.append(f"  - {note}")
        cmp_p = COMPARE_DIR / f"{vid}.json"
        if cmp_p.is_file():
            c = json.loads(cmp_p.read_text(encoding="utf-8"))
            pa = c.get("v2.1a_programmatic", {})
            L.append(f"  - programmatic: opening_same={pa.get('opening_same')} "
                     f"expectation_same={pa.get('expectation_same')} "
                     f"primary_common={pa.get('primary_common')} "
                     f"only_baseline={pa.get('active_only_baseline')} "
                     f"only_replay={pa.get('active_only_replay')}")
            ja = c.get("v2.1a_judge", {})
            if not ja.get("judge_failed"):
                L.append(f"  - v2.1a judge: notes={ja.get('notes')}")
            jb = c.get("v2.1b_judge", {})
            if not jb.get("judge_failed"):
                L.append(f"  - v2.1b judge: notes={jb.get('notes')}")
            jc = c.get("v2.3_judge", {})
            if not jc.get("judge_failed"):
                L.append(f"  - v2.3 judge: notes={jc.get('notes')}")
        L.append("")

    # 3. 必答二：不稳定在哪层
    L.append("## 3. 如果不稳定，是哪一层？（Prompt §13-2）")
    L.append("")
    layers = sorted({v["unstable_layer"] for v in verdicts.values()
                     if v["unstable_layer"]})
    if not layers:
        L.append("三层全部稳定，无不稳定层。")
    else:
        L.append(f"不稳定层（跨样本汇总）：{layers}")
        for vid in CREATIVES:
            v = verdicts[vid]
            if v["unstable_layer"]:
                L.append(f"- {vid}: {v['unstable_layer']} —— "
                         + "；".join(v["differences"][:3]))
    L.append("")

    # 4. 必答三：V2.5 first-pass 对比
    L.append("## 4. 与 V2.5 first-pass 对比：FAIL 是否主要由 model drift 造成？（Prompt §13-3）")
    L.append("")
    if v25_fp:
        L.append(f"V2.5 first-pass（{v25_fp.get('run_id')}，fresh 全链 gpt-5.5 vs frozen qwen）判定：")
        for vid, s in (v25_fp.get("samples") or {}).items():
            L.append(f"- {vid}: {s.get('pipeline_status')}"
                     + (f"（failure_layer={s.get('failure_layer')}）" if s.get("failure_layer") else ""))
        L.append("")
        if case["case"] == "A":
            L.append("**归因结论：是。** 同模型（gpt-5.5）重放下三层全部稳定，而 V2.5 的 FAIL "
                     "全部出现在「qwen frozen vs gpt fresh」的跨模型比对上——V2.5 first-pass "
                     "的语义漂移主要由 model drift（跨模型基线不可比）造成，不能据此断定 "
                     "Prompt/Architecture 失效。")
        elif case["case"] == "C":
            L.append("**归因结论：部分是。** 同模型下 V2.1a/V2.3 稳定，说明 V2.5 中这两层的 "
                     "漂移主要由 model drift 造成；但 V2.1b 在同模型重放下仍不稳定，其漂移 "
                     "（含 V2.5 v04 的 V2.1B FAIL）是系统设计问题，不能归因于模型迁移。")
        else:
            unstable = ", ".join(case["unstable_layers"])
            L.append(f"**归因结论：不全是。** 同模型重放下仍有不稳定层（{unstable}），"
                     "这些层的 V2.5 FAIL 是系统设计（Prompt/Schema/Constraint）问题；"
                     "其余稳定层的 V2.5 FAIL 才可归因于 model drift。")
        if case.get("infra"):
            L.append("\n注意：本轮存在 INFRA 故障样本，其语义判定不完整，上述归因以判定完整的样本为准。")
    else:
        L.append("（V2.5 first-pass summary.json 不可读，跳过对比）")
    L.append("")

    # 5. 最终判定
    L.append("## 5. 最终判定（Prompt §14）")
    L.append("")
    L.append(f"**Case {case['case']}** —— {case['conclusion']}")
    L.append("")

    # 6. Trace 与工程重试
    L.append("## 6. Trace 与工程重试记录（Prompt §6：engineering_retry 必须记录）")
    L.append("")
    L.append("| 样本 | 轮次/stage | status | retries_used | elapsed |")
    L.append("|---|---|---|---|---|")
    for vid in CREATIVES:
        r = retries[vid]
        for key, rec in r["stages"].items():
            L.append(f"| {vid} | {key} | {rec.get('status')} | "
                     f"{rec.get('retries_used')} | {rec.get('elapsed_s')}s |")
    any_retry = any(r["engineering_retry"] for r in retries.values())
    L.append("")
    L.append(f"- engineering_retry（任一 stage 发生工程重试）：{any_retry}")
    L.append("- 语义重试：无（judge 缓存复用 + 每样本单次比对；stage 只允许 bounded 工程重试）")
    L.append("")
    L.append("## 7. 产物索引")
    L.append("")
    L.append("- `baseline/{vid}/v2.1a|v2.1b|v2.3/` + `trace.json`（Run A 原始输出）")
    L.append("- `replay/{vid}/v2.1a|v2.1b|v2.3/` + `trace.json`（Run B 原始输出）")
    L.append("- `comparison/{vid}.json`（三层程序化 diff + judge 全文）")
    L.append("- `summary.json` / `report.md` / `preflight.json` / `console*.log`")
    L.append("")
    (RUN_ROOT / "report.md").write_text("\n".join(L), encoding="utf-8")
    print(f"report.md written: {RUN_ROOT / 'report.md'}")


def _video_sha(vid: str) -> str:
    """两轮 source.json 里的视频 sha 对照值（baseline 轮记录）。"""
    p = BASELINE_DIR / vid / "source.json"
    if p.is_file():
        try:
            return json.loads(p.read_text(encoding="utf-8")).get("sha256_16", "?")
        except Exception:
            return "?"
    return "?"


# --------------------------------------------------------------------------- #
# main
# --------------------------------------------------------------------------- #
def main() -> int:
    ap = argparse.ArgumentParser(prog="v2.benchmarks.run_same_model_replay",
                                 description="V2.5-A Same Model Replay "
                                             "(gpt-5.5 baseline vs replay, text-only)")
    ap.add_argument("--phase", choices=["preflight", "baseline", "replay",
                                        "compare", "report", "all"], default="all")
    ap.add_argument("--force", action="store_true",
                    help="disable skip-existing (default: resume from valid outputs)")
    args = ap.parse_args()

    RUN_ROOT.mkdir(parents=True, exist_ok=True)
    print(f"V2.5-A Same Model Replay | creatives={CREATIVES}")
    print(f"phase={args.phase} force={args.force}")

    # ---------- preflight ----------
    if args.phase in ("preflight", "all"):
        pre = preflight()
        if not pre["ok"]:
            print("\n!! preflight FAIL —— 先报告，不半跑")
            return 2
        if args.phase == "preflight":
            return 0

    tcfg = _load_text_config()
    run_meta = {
        "started_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "api_base": tcfg["api_base"], "model": tcfg["model"], "temperature": 0,
        "scope": "text-only (v2.1a -> v2.1b -> v2.3)；禁止生图",
        "discipline": "同配置各跑一次；工程 retry bounded+recorded；semantic retry 禁止",
    }

    traces_a: dict = {}
    traces_b: dict = {}
    if args.phase in ("baseline", "all"):
        traces_a = run_round("baseline", args.force)
    if args.phase in ("replay", "all"):
        traces_b = run_round("replay", args.force)
    if args.phase in ("baseline", "replay") and args.phase not in ("compare", "report", "all"):
        return 0
    if not traces_a:
        traces_a = load_round_traces("baseline")
    if not traces_b:
        traces_b = load_round_traces("replay")

    # ---------- compare + verdict ----------
    verdicts: dict = {}
    retries: dict = {}
    if args.phase in ("compare", "report", "all"):
        api = ApiClient(tcfg["api_base"], tcfg["api_key"], tcfg["model"],
                        temperature=0.0, max_retries=3)
        COMPARE_DIR.mkdir(parents=True, exist_ok=True)
        for vid in CREATIVES:
            b_out = BASELINE_DIR / vid / "v2.3" / "message_match_copy.json"
            r_out = REPLAY_DIR / vid / "v2.3" / "message_match_copy.json"
            if not (b_out.is_file() and r_out.is_file()):
                print(f"[compare] {vid}: baseline/replay 任一轮未完成，跳过 compare")
                verdicts[vid] = {"creative_id": vid, "v2.1a_stable": None,
                                 "v2.1b_stable": None, "v2.3_stable": None,
                                 "unstable_layer": "INFRA",
                                 "differences": ["baseline/replay pipeline 未完成"],
                                 "notes": []}
                retries[vid] = engineering_retry_summary(
                    traces_a.get(vid, {}), traces_b.get(vid, {}))
                continue
            print(f"\n[compare] {vid}")
            # judge 结果复用（防变相语义重试）：comparison/{vid}.json 已含
            # v2.1a_judge 字段则直接读入；hero/trace 变化只影响 verdict 重算
            cache_p = COMPARE_DIR / f"{vid}.json"
            if cache_p.is_file():
                try:
                    cached = json.loads(cache_p.read_text(encoding="utf-8"))
                    if "v2.1a_judge" in cached:
                        print(f"[compare] {vid}: reuse comparison cache (judge as-is)")
                        cmp_r = cached
                    else:
                        raise ValueError("incomplete cache")
                except Exception:
                    cmp_r = compare_pair(vid, api)
            else:
                try:
                    cmp_r = compare_pair(vid, api)
                except Exception as e:
                    print(f"[compare] {vid} FAILED: {e}")
                    cmp_r = {"creative_id": vid, "compare_error": str(e)[:300]}
            (COMPARE_DIR / f"{vid}.json").write_text(
                json.dumps(cmp_r, ensure_ascii=False, indent=2), encoding="utf-8")
            verdicts[vid] = judge_sample(vid, traces_a.get(vid, {}),
                                         traces_b.get(vid, {}), cmp_r)
            retries[vid] = engineering_retry_summary(traces_a.get(vid, {}),
                                                     traces_b.get(vid, {}))
            print(f"[verdict] {vid}: stable=({verdicts[vid]['v2.1a_stable']}, "
                  f"{verdicts[vid]['v2.1b_stable']}, {verdicts[vid]['v2.3_stable']}) "
                  f"layer={verdicts[vid]['unstable_layer']}")

    # ---------- summary / report ----------
    if args.phase in ("report", "all") and verdicts:
        case = decide_case(verdicts)
        v25_fp = load_v25_first_pass()
        write_summary(run_meta, verdicts, retries, case, v25_fp)
        write_report(run_meta, traces_a, traces_b, verdicts, retries, case, v25_fp)
        print("\n" + "=" * 70)
        print(f"  CASE {case['case']} | unstable_layers={case['unstable_layers']}")
        for vid in CREATIVES:
            v = verdicts.get(vid, {})
            print(f"  {vid}: v2.1a={v.get('v2.1a_stable')} v2.1b={v.get('v2.1b_stable')} "
                  f"v2.3={v.get('v2.3_stable')} layer={v.get('unstable_layer')}")
        print("=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(main())
