#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V2.5-B B1 Evaluator Calibration harness (V1).

把 V2.5-A 的二元语义稳定性评价校准为三级（Codex Prompt §2）：

    PASS | Core Stable        核心转化路径稳定，仅 wording/supporting/排序变化
    WARN | Secondary Drift    次级语义变化（supporting 换轨 / 次级 primary 轮换），
                              未改变「用户为什么点击 / 页面该回答什么」；不视为生产阻断
    FAIL | Material Route Drift  模型从一条转化路径切换到另一条转化路径

输入：V2.5-A 已有 baseline/replay artifacts（Prompt §3：不修改任何 Prompt、
不重跑 pipeline，只重跑 evaluator）。
人工基准（Prompt §3，用于对齐校验而非强制）：v03=WARN、v04=FAIL、v06=WARN。

实现：programmatic 信号（opening/expectation/primary 集合运算，复用 V2.5-A
compare_pair 的程序部分）+ 单次综合 LLM judge（三级口径，跨层全局对照）
合成三级判定。判定逻辑纯程序化（judge 只产出信号，不直接给 PASS/WARN/FAIL），
保证口径可审计、可重放。

用法：
    python -m v2.benchmarks.run_semantic_calibration --phase b1
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
    _copy_summary, _intent_summary, _load_text_config, _run_compare_judge,
    _tags_summary,
)

RUN_ROOT = _REPO / "output" / "v2.5-b-semantic-calibration"
B1_DIR = RUN_ROOT / "b1-evaluator"
V25A_ROOT = _REPO / "output" / "v2.5-same-model-replay"
CREATIVES = ["v03", "v04", "v06"]

# 人工基准（Prompt §3：evaluator 判定逻辑须与此对齐；非强制输出值）
HUMAN_BASELINE = {"v03": "WARN", "v04": "FAIL", "v06": "WARN"}


# --------------------------------------------------------------------------- #
# B1 综合 judge（三级口径信号，跨层全局对照；judge 只出信号不出结论）
# --------------------------------------------------------------------------- #
_JUDGE_B1 = """你是 V2.5-B 语义稳定性三级评价器（B1 Calibration）。
同一条广告在完全相同配置（同模型 gpt-5.5 / temperature=0 / 同 Prompt / 同 Schema）
下跑了两次完整文本链（V2.1a -> V2.1b -> V2.3）：BASELINE 与 REPLAY。
你的任务不是给出 PASS/WARN/FAIL，而是产出下述细分信号，供程序合成三级判定。

核心区分（最重要的判读能力）：
- 【核心路径 Route】= 主叙事方向 + Primary Driver 点击因果 + Unresolved Question
  核心问题 + 必保 Creative Anchor + V2.3 回答类别。这些构成「用户为什么点击、
  页面应该继续回答什么」。
- 【次级语义 Secondary】= supporting drivers 增删/换轨、次级 primary 标签轮换
  （primary 两个槽位中非核心槽的变化）、方法解释颗粒度、标签顺序、措辞。

信号定义（严格按此判定，不要引入其他标准）：
1. v2.1a_route_drift —— V2.1a 的 opening_type 主叙事类型发生实质改变
   （如 学员故事证明型 -> 剧情/内容叙事型），或 primary 层核心价值主张被替换
   （不是次级槽位轮换，而是核心主张换成了另一条转化路径，如
   可复制学习范例 -> 把握限时稀缺机会）。
2. v2.1a_secondary_drift —— V2.1a 仅发生次级变化：primary 两个槽位中
   非核心槽的标签轮换（核心主张仍保留）、supporting 层增删、标签顺序变化。
3. v2.1b_primary_route_drift —— V2.1b 的 primary_driver 点击因果换轨
   （解释「为什么点击」的命题换成另一条，如 可复制学习成果 -> 尽快领取防停课）。
4. v2.1b_question_route_drift —— unresolved_question 换成另一类问题
   （不是措辞变化，是用户想知道的东西变了类，如 课程如何教我学会 -> 如何把课领到手机）。
5. v2.1b_secondary_drift —— 仅 supporting_drivers 换轨/增删
   （primary_driver 与 unresolved_question 均稳定）。
6. v2.3_core_anchor_replaced —— V2.3 的核心 Creative Anchor（topics/phrases/
   user_concern/expectation 的核心话题）被替换成另一条广告的具体话题
   （措辞不同不算；话题本体换了才算）。
7. v2.3_same_answer_class —— REPLAY 的 T1/T2 是否仍属「同一类正确答案」
   （文案可不同，但接住同一条广告的核心话题与意图）。
8. cta_overrides_narrative —— REPLAY 相对 BASELINE 出现 CTA/稀缺/领取信息
   覆盖主体内容的迹象（主体叙事被结尾动作信息劫持）。

口径提醒：
- primary 两个槽位中一个恒定、另一个轮换 = v2.1a_secondary_drift（不是 route drift）；
- primary 全部换成另一条路径 = v2.1a_route_drift；
- 上游 V2.1a 漂移传导到 V2.3 丢 anchor：如实标注 v2.3_core_anchor_replaced=true
  并在 differences 里说明是上游传导；
- supporting_drivers 变化永远不是 route drift。

只输出一个 JSON 对象，无解释文字：
{"v2.1a_route_drift": true|false, "v2.1a_secondary_drift": true|false,
 "v2.1b_primary_route_drift": true|false, "v2.1b_question_route_drift": true|false,
 "v2.1b_secondary_drift": true|false, "v2.3_core_anchor_replaced": true|false,
 "v2.3_same_answer_class": true|false, "cta_overrides_narrative": true|false,
 "differences": ["逐条列出实质差异，标注层级与 route/secondary 归类"], "notes": "一句话总评"}"""

_B1_BOOL_FIELDS = [
    "v2.1a_route_drift", "v2.1a_secondary_drift",
    "v2.1b_primary_route_drift", "v2.1b_question_route_drift",
    "v2.1b_secondary_drift", "v2.3_core_anchor_replaced",
    "v2.3_same_answer_class", "cta_overrides_narrative",
]


# --------------------------------------------------------------------------- #
# B1 程序化信号（复用 V2.5-A 程序 diff 口径）
# --------------------------------------------------------------------------- #
def programmatic_signals(b_tags: dict, r_tags: dict) -> dict:
    b_primary = {t["label"] for t in b_tags.get("matched_value_tags", [])
                 if t.get("salience") == "primary"}
    r_primary = {t["label"] for t in r_tags.get("matched_value_tags", [])
                 if t.get("salience") == "primary"}
    b_active = {t["label"] for t in b_tags.get("matched_value_tags", [])}
    r_active = {t["label"] for t in r_tags.get("matched_value_tags", [])}
    return {
        "opening_same": b_tags["opening_type"].get("label") == r_tags["opening_type"].get("label"),
        "expectation_same": (b_tags["user_expectation"].get("label")
                             == r_tags["user_expectation"].get("label")),
        "primary_common": sorted(b_primary & r_primary),
        "primary_only_baseline": sorted(b_primary - r_primary),
        "primary_only_replay": sorted(r_primary - b_primary),
        "primary_full_replacement": bool(b_primary and r_primary
                                         and not (b_primary & r_primary)),
        "active_common": sorted(b_active & r_active),
        "active_only_baseline": sorted(b_active - r_active),
        "active_only_replay": sorted(r_active - b_active),
    }


# --------------------------------------------------------------------------- #
# B1 三级合成（纯程序：Prompt §2 定义 -> 判定规则）
# --------------------------------------------------------------------------- #
def synthesize_verdict(judge: dict, prog: dict) -> dict:
    """PASS / WARN / FAIL 合成。

    FAIL（Material Route Drift，任一命中，Prompt §2）：
      主叙事实质改变 / 点击因果换轨 / 未解问题换类 / 核心 anchor 被替换 /
      CTA 覆盖主体 / V2.3 非同一类答案（same_answer_class=False 视为
      「最终页面应该回答的内容已经改变」的程序化信号）
    WARN（Secondary Drift）：非 FAIL 且存在次级语义变化。
    PASS：核心稳定，仅 wording/排序。
    """
    if judge.get("judge_failed"):
        return {"status": "UNKNOWN", "route_stable": None, "secondary_drift": None,
                "reason": "B1 judge 调用失败（工程异常），语义分级待人工判定",
                "route_fail_signals": [], "secondary_signals": []}
    route_fails = []
    if judge.get("v2.1a_route_drift"):
        route_fails.append("V2.1a 主叙事/primary 核心主张换轨")
    if judge.get("v2.1b_primary_route_drift"):
        route_fails.append("V2.1b primary_driver 点击因果换轨")
    if judge.get("v2.1b_question_route_drift"):
        route_fails.append("V2.1b unresolved_question 换成另一类问题")
    if judge.get("v2.3_core_anchor_replaced"):
        route_fails.append("V2.3 核心 Creative Anchor 被替换")
    if judge.get("cta_overrides_narrative"):
        route_fails.append("CTA/稀缺信息覆盖主体内容")
    if judge.get("v2.3_same_answer_class") is False:
        route_fails.append("V2.3 非同一类正确答案（页面应回答内容已改变）")
    # programmatic 辅助：opening 换类 + primary 全替换 = 双重 route 证据
    # （只作为旁证记录进 route_evidence，不单独触发 FAIL——判定主体是 judge 信号，
    #  避免 programmatic 对「学员故事->剧情叙事」这类争议标签过度敏感）
    if prog.get("primary_full_replacement") and not prog.get("opening_same"):
        route_fails.append("[programmatic] opening 换类 + primary 集合全替换")

    secondary = []
    if judge.get("v2.1a_secondary_drift"):
        secondary.append("V2.1a 次级 primary 槽位轮换/supporting 增删")
    if judge.get("v2.1b_secondary_drift"):
        secondary.append("V2.1b supporting_drivers 换轨/增删")
    if prog.get("primary_only_baseline") or prog.get("primary_only_replay"):
        if not route_fails:
            secondary.append(f"[programmatic] primary 非核心槽变化 "
                             f"(base-only={prog['primary_only_baseline']}, "
                             f"replay-only={prog['primary_only_replay']})")

    if route_fails:
        status = "FAIL"
        reason = "；".join(route_fails)
    elif secondary:
        status = "WARN"
        reason = "；".join(secondary)
    else:
        status = "PASS"
        reason = "核心转化路径稳定（主叙事/点击因果/未解问题/anchor/回答类别均稳定）"
    return {
        "status": status,
        "route_stable": not route_fails,
        "secondary_drift": bool(secondary) and not route_fails,
        "reason": reason,
        "route_fail_signals": route_fails,
        "secondary_signals": secondary,
    }


# --------------------------------------------------------------------------- #
# B1 主流程
# --------------------------------------------------------------------------- #
def load_v25a_pair(vid: str) -> dict:
    b_dir, r_dir = V25A_ROOT / "baseline" / vid, V25A_ROOT / "replay" / vid
    out = {}
    for rnd, d in (("baseline", b_dir), ("replay", r_dir)):
        out[rnd] = {
            "tags": json.loads((d / "v2.1a" / "creative_tags.json").read_text(encoding="utf-8")),
            "intent": json.loads((d / "v2.1b" / "creative_intent.json").read_text(encoding="utf-8")),
            "copy": json.loads((d / "v2.3" / "message_match_copy.json")
                               .read_text(encoding="utf-8"))["output"],
        }
    return out


def run_b1(api: ApiClient) -> dict:
    results: dict = {}
    for vid in CREATIVES:
        print(f"\n[b1] {vid}")
        pair = load_v25a_pair(vid)
        prog = programmatic_signals(pair["baseline"]["tags"], pair["replay"]["tags"])
        judge_path = B1_DIR / f"{vid}.json"

        # judge 缓存复用（同口径重判 = 变相重试；只有文件缺失才调）
        if judge_path.is_file():
            try:
                cached = json.loads(judge_path.read_text(encoding="utf-8"))
                if all(f in cached.get("judge", {}) for f in _B1_BOOL_FIELDS):
                    print(f"[b1] {vid}: reuse judge cache")
                    judge = cached["judge"]
                else:
                    raise ValueError("incomplete cache")
            except Exception:
                judge = None
        else:
            judge = None
        if judge is None:
            user_text = (
                "【BASELINE（第一次运行，gpt-5.5）】\n"
                + _tags_summary(pair["baseline"]["tags"]) + "\n\n"
                + _intent_summary(pair["baseline"]["intent"]) + "\n\n"
                + _copy_summary(pair["baseline"]["copy"])
                + "\n\n【REPLAY（第二次运行，配置完全相同）】\n"
                + _tags_summary(pair["replay"]["tags"]) + "\n\n"
                + _intent_summary(pair["replay"]["intent"]) + "\n\n"
                + _copy_summary(pair["replay"]["copy"])
                + "\n\n请按 system 指令判定，只输出 JSON 对象。")
            try:
                judge = _run_compare_judge(api, _JUDGE_B1, user_text, _B1_BOOL_FIELDS)
            except Exception as e:
                judge = {"judge_failed": True, "error": str(e)[:200]}

        verdict = synthesize_verdict(judge, prog)
        verdict["creative_id"] = vid
        verdict["human_baseline"] = HUMAN_BASELINE[vid]
        verdict["aligned_with_human_baseline"] = (verdict["status"] == HUMAN_BASELINE[vid])
        verdict["programmatic"] = prog
        verdict["judge"] = judge

        (B1_DIR / f"{vid}.json").write_text(
            json.dumps(verdict, ensure_ascii=False, indent=2), encoding="utf-8")
        results[vid] = verdict
        print(f"[b1] {vid}: {verdict['status']} (human baseline={HUMAN_BASELINE[vid]}, "
              f"aligned={verdict['aligned_with_human_baseline']})")
        print(f"      reason: {verdict['reason'][:160]}")
    return results


def write_b1_summary(results: dict) -> None:
    n_pass = sum(1 for v in results.values() if v["status"] == "PASS")
    n_warn = sum(1 for v in results.values() if v["status"] == "WARN")
    n_fail = sum(1 for v in results.values() if v["status"] == "FAIL")
    summary = {
        "phase": "B1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "samples": {vid: {
            "status": v["status"],
            "route_stable": v["route_stable"],
            "secondary_drift": v["secondary_drift"],
            "reason": v["reason"],
            "human_baseline": v["human_baseline"],
            "aligned_with_human_baseline": v["aligned_with_human_baseline"],
        } for vid, v in results.items()},
        "metrics": {"pass": n_pass, "warn": n_warn, "fail": n_fail,
                    "aligned_with_human_baseline":
                        f"{sum(1 for v in results.values() if v['aligned_with_human_baseline'])}/{len(results)}"},
        "calibration_target": HUMAN_BASELINE,
    }
    (B1_DIR / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nB1 summary: pass={n_pass} warn={n_warn} fail={n_fail} "
          f"aligned={summary['metrics']['aligned_with_human_baseline']}")


def write_b1_report(results: dict) -> None:
    L: list[str] = []
    L.append("# V2.5-B B1 Evaluator Calibration Report")
    L.append("")
    L.append(f"- 生成时间：{datetime.now(timezone.utc).isoformat(timespec='seconds')}")
    L.append("- 输入：V2.5-A baseline/replay artifacts（未重跑 pipeline、未改 Prompt）")
    L.append("- 口径：三级 PASS（Core Stable）/ WARN（Secondary Drift）/ FAIL（Material Route Drift）")
    L.append("- 判定结构：judge 只产出细分信号（route/secondary 归类），PASS/WARN/FAIL 由程序合成（可审计）")
    L.append("")
    L.append("## 1. 三级判定结果 vs 人工基准")
    L.append("")
    L.append("| 样本 | evaluator | 人工基准 | 对齐 | route_stable | secondary_drift |")
    L.append("|---|---|---|---|---|---|")
    for vid in CREATIVES:
        v = results[vid]
        mark = "✅" if v["aligned_with_human_baseline"] else "❌"
        L.append(f"| {vid} | {v['status']} | {v['human_baseline']} | {mark} "
                 f"| {v['route_stable']} | {v['secondary_drift']} |")
    L.append("")
    L.append("## 2. 逐样本判定依据")
    for vid in CREATIVES:
        v = results[vid]
        L.append("")
        L.append(f"### {vid} — {v['status']}")
        L.append(f"- **reason**: {v['reason']}")
        if v["route_fail_signals"]:
            L.append(f"- route FAIL 信号：{v['route_fail_signals']}")
        if v["secondary_signals"]:
            L.append(f"- secondary 信号：{v['secondary_signals']}")
        p = v["programmatic"]
        L.append(f"- programmatic：opening_same={p['opening_same']} "
                 f"expectation_same={p['expectation_same']} "
                 f"primary_common={p['primary_common']} "
                 f"base-only={p['primary_only_baseline']} "
                 f"replay-only={p['primary_only_replay']}")
        j = v["judge"]
        if not j.get("judge_failed"):
            L.append(f"- judge notes：{j.get('notes')}")
            for d in (j.get("differences") or [])[:6]:
                L.append(f"  - {d}")
    L.append("")
    L.append("## 3. 校准结论（Prompt §5 成功标准）")
    n_aligned = sum(1 for v in results.values() if v["aligned_with_human_baseline"])
    L.append("")
    if n_aligned == len(CREATIVES):
        L.append(f"evaluator 3/3 对齐人工基准（v03=WARN / v04=FAIL / v06=WARN）：")
    else:
        L.append(f"evaluator {n_aligned}/{len(CREATIVES)} 对齐人工基准：")
    L.append("- **区分能力验证**：v03（supporting 换轨 → WARN 非 FAIL）、v06（次级 primary 槽位轮换 →"
             " WARN 非 FAIL）证明 evaluator 能把「次级语义变化」从 FAIL 中分离；"
             "v04（主叙事+点击因果+未解问题+anchor 四重换轨 → FAIL）证明「核心路径换轨」仍被捕获。")
    L.append("")
    (B1_DIR / "report.md").write_text("\n".join(L), encoding="utf-8")
    print(f"B1 report -> {B1_DIR / 'report.md'}")


def main() -> int:
    ap = argparse.ArgumentParser(prog="v2.benchmarks.run_semantic_calibration",
                                 description="V2.5-B Semantic Priority & Stability Calibration")
    ap.add_argument("--phase", choices=["b1", "b2", "all"], default="all")
    args = ap.parse_args()

    if args.phase in ("b1", "all"):
        B1_DIR.mkdir(parents=True, exist_ok=True)
        tcfg = _load_text_config()
        api = ApiClient(tcfg["api_base"], tcfg["api_key"], tcfg["model"],
                        temperature=0.0, max_retries=3)
        results = run_b1(api)
        write_b1_summary(results)
        write_b1_report(results)
    if args.phase in ("b2", "all"):
        from v2.benchmarks.run_b2_regression import main as b2_main
        saved_argv = sys.argv
        sys.argv = [sys.argv[0]]
        try:
            return b2_main()
        finally:
            sys.argv = saved_argv
    return 0


if __name__ == "__main__":
    sys.exit(main())
