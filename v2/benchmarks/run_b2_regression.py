#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V2.5-B B2 Semantic Priority Fix Regression harness (V1).

B2 修复（V2.1a §2.3.2 Semantic Priority + V2.1b Rule 3 继承约束）后的
Run Once 回归（Codex Prompt §12-§15）：

- 只跑 v03 / v04 / v06，文本链 V2.1a -> V2.1b -> V2.3，不生图
- model=gpt-5.5、temperature=0；每个 stage Run Once（禁 semantic retry，
  工程 retry 由 run_stage bounded 执行并记录 retries_used）
- 对比：V2.5-A baseline（修复前 gpt-5.5 第一轮）vs B2 regression（修复后本轮）
  —— 用 B1 三级口径 evaluator（judge 信号 + 程序合成）判 PASS/WARN/FAIL
- V2.3 Regression Gate（§15）：anchor_preserved / intent_continuity /
  product_grounding / slot_contract / template_differentiation /
  same_answer_class，要求无新增 FAIL

判定目标（§14）：v03/v06 ∈ {PASS, WARN}；v04 从 FAIL 修复为 {PASS, WARN}
且不再发生「学员故事/可复制成果 -> 限时领取/尽快抢课」Route Drift。

用法：
    python -m v2.benchmarks.run_semantic_calibration --phase b2
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO))

from v2.tagging import ApiClient  # noqa: E402
from v2.benchmarks.run_full_pipeline_replay import (  # noqa: E402
    STAGE_BUDGET, _copy_summary, _intent_summary, _load_text_config,
    _run_compare_judge, _tags_summary, stage_v21a, stage_v21b, stage_v23,
)
from v2.benchmarks.run_semantic_calibration import (  # noqa: E402
    B1_DIR, CREATIVES, _B1_BOOL_FIELDS, programmatic_signals, synthesize_verdict,
)

RUN_ROOT = _REPO / "output" / "v2.5-b-semantic-calibration"
B2_DIR = RUN_ROOT / "b2-regression"
V25A_ROOT = _REPO / "output" / "v2.5-same-model-replay"

REQUIRED_MODEL = "gpt-5.5"

# B2 语境版 judge：信号定义与 B1 完全一致，只换对照双方语义
_JUDGE_B2 = """你是 V2.5-B 修复回归（B2 Regression）的三级语义评价器。
同一条广告跑了两次完整文本链（V2.1a -> V2.1b -> V2.3）：
BEFORE = V2.5-A baseline（修复前 Prompt、gpt-5.5 第一轮，正确路径参考）；
AFTER  = V2.5-B regression（应用 Semantic Priority 修复后的本轮输出）。
你的任务不是给出 PASS/WARN/FAIL，而是产出下述细分信号，供程序合成三级判定。

核心区分（最重要的判读能力）：
- 【核心路径 Route】= 主叙事方向 + Primary Driver 点击因果 + Unresolved Question
  核心问题 + 必保 Creative Anchor + V2.3 回答类别。这些构成「用户为什么点击、
  页面应该继续回答什么」。
- 【次级语义 Secondary】= supporting drivers 增删/换轨、次级 primary 标签轮换
  （primary 两个槽位中非核心槽的变化）、方法解释颗粒度、标签顺序、措辞。

本轮特别关注（Semantic Priority 修复是否生效）：AFTER 若把主叙事从
「学员故事/教学演示/方法原理/演唱效果」类主体内容切换为「课程快停/限时领取/
尽快抢课」类 CTA/稀缺路径，必须如实标记（这是本轮要消除的 Material Route Drift）。

信号定义（严格按此判定，不要引入其他标准）：
1. v2.1a_route_drift —— V2.1a 的 opening_type 主叙事类型发生实质改变，
   或 primary 层核心价值主张被替换成另一条转化路径（如
   可复制学习范例 -> 把握限时稀缺机会）。
2. v2.1a_secondary_drift —— V2.1a 仅发生次级变化：primary 两个槽位中
   非核心槽的标签轮换（核心主张仍保留）、supporting 层增删、标签顺序变化。
3. v2.1b_primary_route_drift —— V2.1b 的 primary_driver 点击因果换轨
   （如 可复制学习成果 -> 因课程可能停止而尽快领取）。
4. v2.1b_question_route_drift —— unresolved_question 换成另一类问题
   （如 课程如何教我学会 -> 如何把课领到手机）。
5. v2.1b_secondary_drift —— 仅 supporting_drivers 换轨/增删。
6. v2.3_core_anchor_replaced —— V2.3 的核心 Creative Anchor 被替换成
   另一条广告的具体话题（措辞不同不算；话题本体换了才算）。
7. v2.3_same_answer_class —— AFTER 的 T1/T2 是否仍属「同一类正确答案」。
8. cta_overrides_narrative —— AFTER 出现 CTA/稀缺/领取信息覆盖主体内容的迹象。

口径提醒：
- primary 两个槽位中一个恒定、另一个轮换 = v2.1a_secondary_drift（不是 route drift）；
- supporting_drivers 变化永远不是 route drift；
- 修复允许 AFTER 比 BEFORE 更收敛/更少标签（如 CTA 类标签从 primary 降级到
  supporting 是修复生效的表现，不是漂移）。

只输出一个 JSON 对象，无解释文字：
{"v2.1a_route_drift": true|false, "v2.1a_secondary_drift": true|false,
 "v2.1b_primary_route_drift": true|false, "v2.1b_question_route_drift": true|false,
 "v2.1b_secondary_drift": true|false, "v2.3_core_anchor_replaced": true|false,
 "v2.3_same_answer_class": true|false, "cta_overrides_narrative": true|false,
 "differences": ["逐条列出实质差异，标注层级与 route/secondary 归类"], "notes": "一句话总评"}"""

_JUDGE_V23_GATE = """你是 V2.5-B B2 Regression 的 V2.3 下游安全 gate 判定器。
同一条广告跑了两次 V2.3 Message Match Copy：BEFORE（V2.5-A baseline，由修复前
V2.1a/V2.1b 驱动）与 AFTER（V2.5-B regression，由修复后 V2.1a/V2.1b 驱动）。
V2.3 本身未修改（Prompt V1.2 冻结）。请判定修复是否破坏下游，不要要求逐字一致：

1. anchor_preserved_t1 / anchor_preserved_t2 —— AFTER 的 T1/T2 是否保住与 BEFORE
   相同的核心 Anchor（topics / phrases / user_concern / expectation 允许措辞不同，
   核心话题必须相同；对含学员故事的素材，AFTER 必须接住妈妈/学员故事、可复制学习路径、
   普通人能否学会等主体语义）。
2. intent_continuity_t1 / intent_continuity_t2 —— AFTER 是否仍在回答同一 intent。
3. template_differentiation —— AFTER 的 T1（问题→方法→四利益卡）与 T2（顾虑→适配→
   老师→学习支持）是否仍呈现不同销售结构（不是同义改写）。
4. same_answer_class —— 综合：AFTER 是否是「同一类正确答案」（文案可完全不同，
   但接住同一条广告的核心话题与意图）。

只输出一个 JSON 对象，无解释文字：
{"anchor_preserved_t1": true|false, "anchor_preserved_t2": true|false,
 "intent_continuity_t1": true|false, "intent_continuity_t2": true|false,
 "template_differentiation": true|false, "same_answer_class": true|false,
 "differences": ["..."], "notes": "一句话总评"}"""

_V23_GATE_FIELDS = ["anchor_preserved_t1", "anchor_preserved_t2",
                    "intent_continuity_t1", "intent_continuity_t2",
                    "template_differentiation", "same_answer_class"]


# --------------------------------------------------------------------------- #
# Preflight（§12：model/temperature 自证 + 修复后 Prompt sha 快照）
# --------------------------------------------------------------------------- #
def preflight() -> dict:
    import hashlib
    from v2.benchmarks.run_full_pipeline_replay import CONFIG_ENV, parse_env_file
    tcfg = _load_text_config()
    env_cfg = parse_env_file(CONFIG_ENV)
    t_override = env_cfg.get("V2_TEMPERATURE")
    temp_ok = t_override in (None, "", "0")
    checks = {
        "model": tcfg["model"],
        "model_ok": tcfg["model"] == REQUIRED_MODEL,
        "temperature": 0.0 if temp_ok else t_override,
        "temperature_ok": temp_ok,
        "v2_temperature_override": t_override,
    }
    for name, p in (("v2.1a_prompt_sha16", _REPO / "v2/prompts/creative_tagging.md"),
                    ("v2.1b_prompt_sha16", _REPO / "v2/prompts/intent_decision.md")):
        checks[name] = hashlib.sha256(p.read_bytes()).hexdigest()[:16]
    # V2.3 frozen 不变自证（harness 侧快照，V2.3 prompt 本身未动）
    v23 = _REPO / "v2/prompts/message_match_copy.md"
    checks["v2.3_prompt_sha16"] = hashlib.sha256(v23.read_bytes()).hexdigest()[:16]
    ok = checks["model_ok"] and checks["temperature_ok"]
    print(f"[b2-preflight] model={checks['model']} temp={checks['temperature']} "
          f"v2.1a_sha={checks['v2.1a_prompt_sha16']} "
          f"v2.1b_sha={checks['v2.1b_prompt_sha16']} -> {'PASS' if ok else 'FAIL'}")
    if not ok:
        raise SystemExit("[b2-preflight] FAIL: model/temperature 不满足 §12 要求")
    return checks


# --------------------------------------------------------------------------- #
# Run Once 文本链（§13：禁 semantic retry；工程 retry 记录 retries_used）
# --------------------------------------------------------------------------- #
def run_once(vid: str) -> dict:
    vdir = B2_DIR / vid
    vdir.mkdir(parents=True, exist_ok=True)
    trace: dict = {"creative_id": vid, "stages": {}}
    for stage, fn in (("v2.1a", stage_v21a), ("v2.1b", stage_v21b), ("v2.3", stage_v23)):
        res = fn(vid, vdir, force=True)
        trace["stages"][stage] = res
        print(f"[b2] {vid}/{stage}: {res['status']} "
              f"retries_used={res.get('retries_used', 0)} "
              f"elapsed={res.get('elapsed_s', '?')}s")
        if res["status"] != "ok":
            raise SystemExit(f"[b2] {vid}/{stage} failed: {res}")
    trace["engineering_retry"] = any(
        s.get("retries_used", 0) > 0 for s in trace["stages"].values())
    return trace


# --------------------------------------------------------------------------- #
# Comparison：V2.5-A baseline vs B2（B1 三级口径）
# --------------------------------------------------------------------------- #
def compare_and_gate(vid: str, api: ApiClient) -> dict:
    cmp_path = B2_DIR / "comparison" / f"{vid}.json"
    # judge 落盘复用：已有完整判定结果时不重新调 judge（防变相语义重试）
    if cmp_path.is_file():
        try:
            cached = json.loads(cmp_path.read_text(encoding="utf-8"))
            if (all(f in cached.get("judge", {}) for f in _B1_BOOL_FIELDS)
                    and all(f in cached.get("v2_3_gate", {}).get("judge", {})
                            for f in _V23_GATE_FIELDS)):
                print(f"[b2-compare] {vid}: reuse cached judge verdict")
                return cached
        except Exception:
            pass
    b_dir = V25A_ROOT / "baseline" / vid
    a_dir = B2_DIR / vid
    before = {
        "tags": json.loads((b_dir / "v2.1a" / "creative_tags.json").read_text(encoding="utf-8")),
        "intent": json.loads((b_dir / "v2.1b" / "creative_intent.json").read_text(encoding="utf-8")),
        "copy": json.loads((b_dir / "v2.3" / "message_match_copy.json").read_text(encoding="utf-8"))["output"],
    }
    after = {
        "tags": json.loads((a_dir / "v2.1a" / "creative_tags.json").read_text(encoding="utf-8")),
        "intent": json.loads((a_dir / "v2.1b" / "creative_intent.json").read_text(encoding="utf-8")),
        "copy": json.loads((a_dir / "v2.3" / "message_match_copy.json").read_text(encoding="utf-8"))["output"],
    }

    prog = programmatic_signals(before["tags"], after["tags"])
    user_text = ("【BEFORE（V2.5-A baseline，修复前 gpt-5.5 第一轮）】\n"
                 + _tags_summary(before["tags"]) + "\n\n"
                 + _intent_summary(before["intent"]) + "\n\n"
                 + _copy_summary(before["copy"])
                 + "\n\n【AFTER（V2.5-B regression，Semantic Priority 修复后）】\n"
                 + _tags_summary(after["tags"]) + "\n\n"
                 + _intent_summary(after["intent"]) + "\n\n"
                 + _copy_summary(after["copy"])
                 + "\n\n请按 system 指令判定，只输出 JSON 对象。")
    try:
        judge = _run_compare_judge(api, _JUDGE_B2, user_text, _B1_BOOL_FIELDS)
    except Exception as e:
        judge = {"judge_failed": True, "error": str(e)[:200]}
    verdict = synthesize_verdict(judge, prog)
    verdict["creative_id"] = vid
    verdict["programmatic"] = prog
    verdict["judge"] = judge

    # ---- V2.3 gate（§15 六项 + 程序检查） ----
    gate_user = ("【BEFORE（V2.3 输出，修复前驱动）】\n" + _copy_summary(before["copy"])
                 + "\n\n【AFTER（V2.3 输出，修复后驱动）】\n" + _copy_summary(after["copy"])
                 + "\n\n请按 system 指令判定，只输出 JSON 对象。")
    try:
        gate_judge = _run_compare_judge(api, _JUDGE_V23_GATE, gate_user, _V23_GATE_FIELDS)
    except Exception as e:
        gate_judge = {"judge_failed": True, "error": str(e)[:200]}
    # 程序检查：grounding + slot contract
    g_status = after["copy"].get("product_grounding_pack", {}).get("grounding_status")
    b_status = before["copy"].get("product_grounding_pack", {}).get("grounding_status")
    slot_ok = True
    slot_detail = {}
    for side in ("t1", "t2"):
        b_keys = set(before["copy"].get(side, {}).get("slots", {}).keys())
        a_keys = set(after["copy"].get(side, {}).get("slots", {}).keys())
        same = b_keys == a_keys
        slot_detail[side] = {"same_keys": same,
                             "before": sorted(b_keys), "after": sorted(a_keys)}
        slot_ok = slot_ok and same
    gate = {
        "judge": gate_judge,
        "grounding_status_before": b_status,
        "grounding_status_after": g_status,
        "grounding_ok": g_status in ("grounded", b_status),
        "slot_contract_ok": slot_ok,
        "slot_detail": slot_detail,
    }
    if gate_judge.get("judge_failed"):
        gate["gate_pass"] = None
        gate["gate_reason"] = "V2.3 gate judge 失败（工程异常），待人工"
    else:
        gate["gate_pass"] = all(gate_judge[f] for f in _V23_GATE_FIELDS) \
            and gate["grounding_ok"] and slot_ok
        failed = [f for f in _V23_GATE_FIELDS if not gate_judge[f]]
        gate["gate_reason"] = ("全部通过" if not failed else f"未通过: {failed}")
        if not gate["grounding_ok"]:
            gate["gate_reason"] += f"; grounding {b_status}->{g_status}"
        if not slot_ok:
            gate["gate_reason"] += "; slot contract 变化"
    verdict["v2_3_gate"] = gate
    return verdict


# --------------------------------------------------------------------------- #
# §14 判定
# --------------------------------------------------------------------------- #
def judge_regression_target(verdict: dict) -> dict:
    vid = verdict["creative_id"]
    status = verdict["status"]
    ok = status in ("PASS", "WARN")
    tgt = {
        "v03": "允许 PASS/WARN，不能 FAIL",
        "v04": "必须从 FAIL 修复为 PASS/WARN（route drift 消除）",
        "v06": "允许 PASS/WARN，不能因 secondary 变化判 FAIL",
    }[vid]
    return {"target": tgt, "met": ok, "status": status}


def main() -> int:
    ap = argparse.ArgumentParser(prog="v2.benchmarks.run_b2_regression")
    ap.add_argument("--skip-run", action="store_true",
                    help="跳过 pipeline（artifacts 已存在），只跑 compare/report")
    args = ap.parse_args()

    B2_DIR.mkdir(parents=True, exist_ok=True)
    (B2_DIR / "comparison").mkdir(parents=True, exist_ok=True)
    pre = preflight()
    tcfg = _load_text_config()
    api = ApiClient(tcfg["api_base"], tcfg["api_key"], tcfg["model"],
                    temperature=0.0, max_retries=3)

    traces: dict = {}
    if not args.skip_run:
        for vid in CREATIVES:
            print(f"\n[b2-run] {vid}")
            traces[vid] = run_once(vid)
        (B2_DIR / "traces.json").write_text(
            json.dumps({"preflight": pre, "creatives": traces},
                       ensure_ascii=False, indent=2), encoding="utf-8")
    else:
        traces = json.loads((B2_DIR / "traces.json").read_text(encoding="utf-8"))["creatives"]

    verdicts: dict = {}
    for vid in CREATIVES:
        print(f"\n[b2-compare] {vid}")
        v = compare_and_gate(vid, api)
        v["regression_target"] = judge_regression_target(v)
        verdicts[vid] = v
        (B2_DIR / "comparison" / f"{vid}.json").write_text(
            json.dumps(v, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[b2] {vid}: {v['status']} (target={v['regression_target']['target']}, "
              f"met={v['regression_target']['met']})")
        print(f"      reason: {v['reason'][:160]}")
        g = v["v2_3_gate"]
        print(f"      v2.3 gate: {'PASS' if g['gate_pass'] else ('PENDING' if g['gate_pass'] is None else 'FAIL')}"
              f" ({g['gate_reason']})")

    write_summary(verdicts, pre, traces)
    write_report(verdicts, pre, traces)
    return 0


def write_summary(verdicts: dict, pre: dict, traces: dict) -> None:
    n = lambda s: sum(1 for v in verdicts.values() if v["status"] == s)  # noqa: E731
    eng = {vid: t.get("engineering_retry", False) for vid, t in traces.items()}
    summary = {
        "phase": "B2",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "model": pre["model"],
        "temperature": pre["temperature"],
        "prompt_sha16": {k: pre[k] for k in
                         ("v2.1a_prompt_sha16", "v2.1b_prompt_sha16", "v2.3_prompt_sha16")},
        "samples": {vid: {
            "status": v["status"],
            "route_stable": v["route_stable"],
            "v2.3_same_answer_class": (v["v2_3_gate"]["judge"].get("same_answer_class")
                                       if not v["v2_3_gate"]["judge"].get("judge_failed")
                                       else None),
            "v2_3_gate_pass": v["v2_3_gate"]["gate_pass"],
            "regression_target_met": v["regression_target"]["met"],
            "reason": v["reason"],
        } for vid, v in verdicts.items()},
        "metrics": {
            "pass": n("PASS"), "warn": n("WARN"), "fail": n("FAIL"),
            "route_stable": f"{sum(1 for v in verdicts.values() if v['route_stable'])}/{len(verdicts)}",
            "v2.3_same_answer_class":
                f"{sum(1 for v in verdicts.values() if v['v2_3_gate']['judge'].get('same_answer_class'))}/{len(verdicts)}",
            "v2_3_gate_pass":
                f"{sum(1 for v in verdicts.values() if v['v2_3_gate']['gate_pass'])}/{len(verdicts)}",
            "regression_target_met":
                f"{sum(1 for v in verdicts.values() if v['regression_target']['met'])}/{len(verdicts)}",
            "engineering_retry": eng,
        },
    }
    (B2_DIR / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nB2 summary: pass={n('PASS')} warn={n('WARN')} fail={n('FAIL')} "
          f"targets_met={summary['metrics']['regression_target_met']} "
          f"v2.3_gate={summary['metrics']['v2_3_gate_pass']}")


def write_report(verdicts: dict, pre: dict, traces: dict) -> None:
    L: list[str] = []
    L.append("# V2.5-B B2 Regression Report")
    L.append("")
    L.append(f"- 生成时间：{datetime.now(timezone.utc).isoformat(timespec='seconds')}")
    L.append(f"- 配置：model={pre['model']} temperature={pre['temperature']}"
             f"（Prompt §12）")
    L.append(f"- 修复后 Prompt sha16：v2.1a={pre['v2.1a_prompt_sha16']} "
             f"v2.1b={pre['v2.1b_prompt_sha16']}（V2.3 冻结未动 "
             f"sha16={pre['v2.3_prompt_sha16']}）")
    L.append("- 纪律：每 stage Run Once；工程重试全记录；禁 semantic retry")
    L.append("- 对比：BEFORE = V2.5-A baseline（修复前）vs AFTER = 本轮修复输出")
    L.append("")
    L.append("## 1. 回归判定结果（Prompt §14 目标）")
    L.append("")
    L.append("| 样本 | 三级判定 | route_stable | §14 目标 | 达标 | V2.3 gate |")
    L.append("|---|---|---|---|---|---|")
    for vid in CREATIVES:
        v = verdicts[vid]
        g = v["v2_3_gate"]
        gs = "PASS" if g["gate_pass"] else ("PENDING" if g["gate_pass"] is None else "FAIL")
        L.append(f"| {vid} | {v['status']} | {v['route_stable']} "
                 f"| {v['regression_target']['target']} | "
                 f"{'✅' if v['regression_target']['met'] else '❌'} | {gs} |")
    L.append("")
    L.append("## 2. 逐样本判定依据")
    for vid in CREATIVES:
        v = verdicts[vid]
        L.append("")
        L.append(f"### {vid} — {v['status']}（target met={v['regression_target']['met']}）")
        L.append(f"- **reason**: {v['reason']}")
        if v.get("route_fail_signals"):
            L.append(f"- route FAIL 信号：{v['route_fail_signals']}")
        if v.get("secondary_signals"):
            L.append(f"- secondary 信号：{v['secondary_signals']}")
        p = v["programmatic"]
        L.append(f"- programmatic：opening_same={p['opening_same']} "
                 f"expectation_same={p['expectation_same']} "
                 f"primary_common={p['primary_common']} "
                 f"before-only={p['primary_only_baseline']} "
                 f"after-only={p['primary_only_replay']}")
        j = v["judge"]
        if not j.get("judge_failed"):
            L.append(f"- judge notes：{j.get('notes')}")
            for d in (j.get("differences") or [])[:8]:
                L.append(f"  - {d}")
        g = v["v2_3_gate"]
        L.append(f"- V2.3 gate：{'PASS' if g['gate_pass'] else ('PENDING' if g['gate_pass'] is None else 'FAIL')}"
                 f"（{g['gate_reason']}；grounding {g['grounding_status_before']}"
                 f"->{g['grounding_status_after']}，slot_contract={g['slot_contract_ok']}）")
        gj = g["judge"]
        if not gj.get("judge_failed") and gj.get("notes"):
            L.append(f"  - gate judge notes：{gj['notes']}")
    L.append("")
    L.append("## 3. 执行纪律（Prompt §13）")
    eng_all = all(not t.get("engineering_retry", False) for t in traces.values())
    L.append(f"- 工程 retry：{('无（全部 attempt=1）' if eng_all else '存在，见 traces.json')}")
    L.append("- semantic retry：无（每样本每 stage 单次运行；judge 失败按 UNKNOWN/PENDING 报告，不重跑 pipeline）")
    L.append("- V2.3 / T1 / T2 / Schema / Knowledge Base：未修改（sha 见报告头）")
    L.append("")
    (B2_DIR / "report.md").write_text("\n".join(L), encoding="utf-8")
    print(f"B2 report -> {B2_DIR / 'report.md'}")


if __name__ == "__main__":
    sys.exit(main())
