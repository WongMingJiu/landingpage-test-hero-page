#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V2.5-D Opening Type Decision Priority & Repeat Stability harness (V1).

本轮只改 V2.1a Prompt（§3.1.1 Opening Type 冲突仲裁四规则 A/B/C/D +
§3.2.2 家人/学员叙事认定加 Rule C 窗口前提），不修改 V2.1b / V2.3（§1）。

流程（§6/§12）：
  3 creatives（v03/v04/v06）× 3 repeats × 3 stages（V2.1a→V2.1b→V2.3）
  共 27 个 stage run，每样本连续 3 次相同配置（gpt-5.5/temp=0），
  禁止 semantic retry，工程 retry bounded + 记录。

评估：
  1. 程序硬指标（§8/§16）：opening_type_consistency=3/3（label==target），
     v04 primary 含 获得可复制学习范例 且承接类不得为唯一 primary；
     v06 primary 含 正确发声并保护嗓音。
  2. Opening evaluator（§11，测试内部信号）：first_sufficient_window /
     opening_candidates / winning_opening / winning_reason /
     later_override_attempt（每个 repeat 一次）。
  3. V2.1b route gate（§13）：3 次输出互比 primary_driver 同一转化路径 /
     unresolved_question 同一问题类型 / supporting 仅次级变化。
  4. V2.3 gate（§14）：3 次输出互比 anchor_preserved / intent_continuity /
     template_differentiation / same_answer_class（per-repeat，目标 9/9）。

判定（§15）：
  PASS  opening 3/3 + V2.1b route 3/3 + V2.3 sac 3/3 且无次级变化信号
  WARN  上述核心全稳，但存在次级变化（supporting 增删/非核心 primary 槽
        轮换/confidence 轻变/decision_window 轻变）
  FAIL  opening 非 3/3 / primary 主路径换轨 / expectation 换类 /
        V2.1b 点击因果或问题换轨 / V2.3 anchor 替换或 sac fail

v09 taxonomy 异议按 §20 记入 Taxonomy Review Backlog，本轮不处理。

用法：
    python -m v2.benchmarks.run_opening_stability --phase all
    python -m v2.benchmarks.run_opening_stability --phase run
    python -m v2.benchmarks.run_opening_stability --phase eval
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
    _tags_summary, stage_v21a, stage_v21b, stage_v23,
)
from v2.benchmarks.run_semantic_calibration import programmatic_signals  # noqa: E402

RUN_ROOT = _REPO / "output" / "v2.5-d-opening-stability"
REQUIRED_MODEL = "gpt-5.5"
REPEATS = 3

# §5/§16 硬性目标：样本 -> target opening（三角测试）
SAMPLES = {"v03": "演唱效果型", "v04": "学员故事证明型", "v06": "教学演示型"}

COURSE_BEARING_LABELS = ["获得课程与学习资源", "把握限时稀缺机会",
                         "便捷领取并快速开始", "获得专业指导"]

# §20：v09 taxonomy 异议 backlog（不处理，仅记录）
TAXONOMY_BACKLOG = {
    "issue": "v09「低门槛领取型」标签：素材无领取/报名动作，judge 认为真实机制为"
             "低门槛降阻主张；frozen 基线（qwen）与 V2.5-C 本轮同判该标签，"
             "属 taxonomy 标签定义与素材的错配，非 prompt 回归。",
    "scope": "taxonomy label 定义 / v09 frozen GT",
    "action": "Taxonomy Review Backlog，等人工评审；本轮不动 taxonomy。",
}

# --------------------------------------------------------------------------- #
# Judge prompts
# --------------------------------------------------------------------------- #
_JUDGE_OPENING = """你是 V2.5-D Opening Type Decision Priority 评价器。
评估一次 V2.1a Creative Tagging 输出（含 opening_type evidence 与全部 value
tag evidence）的 Opening Type 冲突仲裁是否符合「第一有效窗口优先权」原则：
Opening Type 只描述第一有效 Decision Window 内最先成立、最直接驱动用户继续
观看的开场机制；Persuasion Mechanism 可以来自后续更完整内容，不要求与
Opening Type 完全一致。

评估材料 = 该次 V2.1a 的标签输出 + 全部 evidence（时间戳/来源/内容）。

评估任务（基于素材 evidence 本身判读，不是复读模型输出）：
1. first_sufficient_window：素材中第一个足以形成明确开场机制的时间窗（如
   "00:00-00:08"），并说明该窗口内成立的机制是什么。
2. opening_candidates：素材中所有可成立的 opening 候选（含时间窗与置信度），
   按成立先后排列。
3. winning_opening：按 First Sufficient Signal Wins 原则应胜出的 opening 类型
   （来自 taxonomy：演唱效果型/学员故事证明型/教学演示型/权威背书型/
   低门槛领取型/反常识悬念型/效果对比型/剧情内容叙事型/其他）。
4. winning_reason：一句话胜出理由（哪个窗口先成立、为何后续不覆盖）。
5. later_override_attempt：模型输出是否存在「后续叙事反向覆盖先成立开场机制」
   的迹象（如先表演性演唱展示、后说明学员案例，却判了学员故事证明型）。

口径提醒：
- 表演性演唱展示（录音棚/持麦/舞台/面向观众的持续演唱）先成立 → 演唱效果型；
  叠加字幕的学员身份/学时说明（如「只跟X学了一个月」）不改变开场机制；
- 人物学习叙事主线（人物→报名/学习事实→结果→他人评价）在第一窗口贯穿
  （如「我妈报了训练营……后悔没早点让她学」）→ 学员故事证明型；
- 老师边讲边示范方法/原理 → 教学演示型，后续课程信息不覆盖。

只输出一个 JSON 对象，无解释文字：
{"first_sufficient_window": "00:00-00:XX",
 "opening_candidates": [{"label": "...", "window": "00:00-00:XX", "confidence": "high"}],
 "winning_opening": "...", "winning_reason": "...",
 "later_override_attempt": true|false,
 "differences": ["模型输出与判读的分歧（若有）"], "notes": "一句话总评"}"""

_OPENING_BOOL_FIELDS = ["later_override_attempt"]

_JUDGE_V21B_ROUTE = """你是 V2.5-D V2.1b Intent Decision 重复稳定性评价器。
同一条广告在相同配置（同模型/温度）下连续跑了 3 次 V2.1b（由各自 V2.1a 输出
驱动）。评估 3 次输出之间的 route 一致性，不要要求字符串一致：

1. primary_driver_same_route —— 3 次的 primary_driver 是否属于同一转化路径
   （同一个用户为什么点击；允许措辞不同）。
2. question_same_type —— 3 次的 unresolved_question 是否属于同一问题类型。
3. supporting_only_secondary —— 3 次之间 supporting_drivers 的变化（若有）
   是否只是次级（增删/换轨不影响主因果）。

口径：同一因果换措辞 = 稳定；点击因果本身改变（如从「怕学不会」变成「想抢课」）
= 换轨。

只输出一个 JSON 对象，无解释文字：
{"primary_driver_same_route": true|false, "question_same_type": true|false,
 "supporting_only_secondary": true|false,
 "differences": ["逐条列出 3 次之间的实质差异，标注 route/secondary 归类"],
 "notes": "一句话总评"}"""

_V21B_BOOL_FIELDS = ["primary_driver_same_route", "question_same_type",
                     "supporting_only_secondary"]

_JUDGE_V23_GATE = """你是 V2.5-D V2.3 Message Match Copy 重复稳定性评价器。
同一条广告在相同配置下连续跑了 3 次完整文本链（V2.1a→V2.1b→V2.3），以下是
3 次 V2.3 输出的摘要。评估 3 次输出之间的一致性（互相比较，无单一基准）：

1. anchor_preserved —— 3 次的 creative_anchors（topics/phrases/user_concern/
   expectation）是否保住同一组核心话题（允许措辞不同，核心话题必须相同）。
2. intent_continuity —— 3 次是否仍在回答同一 intent（同一用户问题）。
3. template_differentiation —— 3 次中 T1（问题→方法→利益卡）与 T2（顾虑→
   适配→老师→学习支持）是否都保持不同销售结构（不是同义改写）。
4. same_answer_class_repeat1/2/3 —— 每次输出是否都属于「同一类正确答案」
   （接住同一条广告的同一核心意图；文案可完全不同）。逐次判定。

只输出一个 JSON 对象，无解释文字：
{"anchor_preserved": true|false, "intent_continuity": true|false,
 "template_differentiation": true|false,
 "same_answer_class_repeat1": true|false,
 "same_answer_class_repeat2": true|false,
 "same_answer_class_repeat3": true|false,
 "differences": ["逐条列出 3 次之间的实质差异"], "notes": "一句话总评"}"""

_V23_BOOL_FIELDS = ["anchor_preserved", "intent_continuity",
                    "template_differentiation",
                    "same_answer_class_repeat1", "same_answer_class_repeat2",
                    "same_answer_class_repeat3"]


# --------------------------------------------------------------------------- #
# Preflight / 程序硬检查
# --------------------------------------------------------------------------- #
def preflight() -> dict:
    import hashlib
    from v2.benchmarks.run_full_pipeline_replay import CONFIG_ENV, parse_env_file
    tcfg = _load_text_config()
    env_cfg = parse_env_file(CONFIG_ENV)
    t_override = env_cfg.get("V2_TEMPERATURE")
    temp_ok = t_override in (None, "", "0")
    checks = {
        "model": tcfg["model"], "model_ok": tcfg["model"] == REQUIRED_MODEL,
        "temperature": 0.0 if temp_ok else t_override, "temperature_ok": temp_ok,
    }
    for name, p in (("v2.1a_prompt_sha16", _REPO / "v2/prompts/creative_tagging.md"),
                    ("v2.1b_prompt_sha16", _REPO / "v2/prompts/intent_decision.md"),
                    ("v2.3_prompt_sha16", _REPO / "v2/prompts/message_match_copy.md")):
        checks[name] = hashlib.sha256(p.read_bytes()).hexdigest()[:16]
    ok = checks["model_ok"] and checks["temperature_ok"]
    print(f"[d-preflight] model={checks['model']} temp={checks['temperature']} "
          f"v2.1a_sha={checks['v2.1a_prompt_sha16']} -> {'PASS' if ok else 'FAIL'}")
    if not ok:
        raise SystemExit("[d-preflight] FAIL: model/temperature 不满足 §6 要求")
    return checks


def _primary_labels(tags: dict) -> list[str]:
    return [t["label"] for t in tags.get("matched_value_tags", [])
            if t.get("salience") == "primary"]


def hard_checks(vid: str, target: str, tags: dict) -> list[str]:
    """§8/§16 程序硬检查（不依赖 judge）。返回 fail 信号列表。"""
    fails: list[str] = []
    opening = tags["opening_type"].get("label")
    primary = _primary_labels(tags)
    if opening != target:
        fails.append(f"§16: {vid} opening={opening}（目标 {target}）")
    if vid == "v04":
        if "获得可复制学习范例" not in primary:
            fails.append(f"§16: v04 primary 无 获得可复制学习范例（primary={primary}）")
        if len(primary) == 1 and primary[0] in COURSE_BEARING_LABELS:
            fails.append(f"§16: v04 唯一 primary 为课程承接类（{primary[0]}）")
    elif vid == "v06":
        if "正确发声并保护嗓音" not in primary:
            fails.append(f"§16: v06 核心主张丢失（primary={primary}，无 正确发声并保护嗓音）")
    return fails


def repeat_consistency(tags_list: list[dict], target: str | None = None) -> dict:
    """§8 程序一致性指标（3 次之间）。"""
    openings = [t["opening_type"].get("label") for t in tags_list]
    expectations = [t["user_expectation"].get("label") for t in tags_list]
    windows = [(t["decision_window"].get("used_seconds"),
                bool(t["decision_window"].get("extended"))) for t in tags_list]
    primaries = [_primary_labels(t) for t in tags_list]
    pairwise = []
    for i in range(len(tags_list)):
        for j in range(i + 1, len(tags_list)):
            pairwise.append(programmatic_signals(tags_list[i], tags_list[j]))
    full_replacement = [p["primary_full_replacement"] for p in pairwise]
    primary_sets = {frozenset(p) for p in primaries}
    # 核心槽稳定：任意两次 primary 交集非空（未完全替换）
    primary_core_stable = all(not p["primary_full_replacement"] for p in pairwise)
    # opening_consistency = 命中目标类型的 run 数（无 target 时 = 互相全同的 run 数）
    if target is not None:
        hits = sum(1 for o in openings if o == target)
    else:
        hits = len(openings) if len(set(openings)) == 1 else \
            max((openings.count(o) for o in set(openings)), default=0)
    return {
        "opening_labels": openings,
        "opening_consistency": f"{hits}/{len(openings)}",
        "opening_all_same": len(set(openings)) == 1,
        "expectation_labels": expectations,
        "expectation_all_same": len(set(expectations)) == 1,
        "windows": [list(w) for w in windows],
        "window_all_same": len(set(windows)) == 1,
        "primaries": primaries,
        "primary_core_stable": primary_core_stable,
        "primary_sets_identical": len(primary_sets) == 1,
        "pairwise_full_replacement": full_replacement,
    }


# --------------------------------------------------------------------------- #
# 加载器
# --------------------------------------------------------------------------- #
def load_repeat(vid: str, rep: int) -> dict:
    rdir = RUN_ROOT / vid / f"repeat-{rep}"
    tags = json.loads((rdir / "v2.1a" / "creative_tags.json").read_text(encoding="utf-8"))
    intent = json.loads((rdir / "v2.1b" / "creative_intent.json").read_text(encoding="utf-8"))
    copy_doc = json.loads((rdir / "v2.3" / "message_match_copy.json").read_text(encoding="utf-8"))
    return {"rdir": rdir, "tags": tags, "intent": intent, "copy": copy_doc["output"]}


def _evidence_detail(tags: dict) -> str:
    lines = [f"opening_type: {tags['opening_type'].get('label')}"
             f"（{tags['opening_type'].get('confidence')}，"
             f"source_mode={tags['opening_type'].get('source_mode')}）",
             f"user_expectation: {tags['user_expectation'].get('label')}",
             f"decision_window: used={tags['decision_window'].get('used_seconds')}s "
             f"extended={tags['decision_window'].get('extended')}",
             "opening_type evidence:"]
    for e in tags["opening_type"].get("evidence", []):
        lines.append(f"  [{e.get('time')}] {e.get('source')}: {e.get('content', '')[:110]}")
    lines.append("matched_value_tags（含 evidence）:")
    for t in tags.get("matched_value_tags", []):
        lines.append(f"  [{t.get('salience')}/{t.get('evidence_strength')}] {t.get('label')}")
        for e in t.get("evidence", [])[:3]:
            lines.append(f"      [{e.get('time')}] {e.get('source')}: {e.get('content', '')[:100]}")
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# 阶段 1：3×3 repeat 全流程 run
# --------------------------------------------------------------------------- #
def run_all(traces: dict) -> None:
    for vid in SAMPLES:
        for rep in range(1, REPEATS + 1):
            rdir = RUN_ROOT / vid / f"repeat-{rep}"
            rdir.mkdir(parents=True, exist_ok=True)
            key = f"{vid}/repeat-{rep}"
            traces.setdefault("samples", {}).setdefault(vid, {})[f"repeat-{rep}"] = {}
            for stage, fn in (("v2.1a", stage_v21a), ("v2.1b", stage_v21b),
                              ("v2.3", stage_v23)):
                res = fn(vid, rdir, force=True)
                traces["samples"][vid][f"repeat-{rep}"][stage] = {
                    "status": res["status"], "retries_used": res.get("retries_used", 0)}
                print(f"[d] {key}/{stage}: {res['status']} "
                      f"retries_used={res.get('retries_used', 0)} "
                      f"elapsed={res.get('elapsed_s', '?')}s", flush=True)
                if res["status"] != "ok":
                    raise SystemExit(f"[d] {key}/{stage} failed: {res}")


# --------------------------------------------------------------------------- #
# 阶段 2：评估
# --------------------------------------------------------------------------- #
def eval_opening(vid: str, rep: int, tags: dict, api: ApiClient) -> dict:
    """§11 opening evaluator（测试内部信号，不进生产 Schema）。"""
    ev_path = RUN_ROOT / "evaluation" / f"{vid}-opening-rep{rep}.json"
    if ev_path.is_file():
        try:
            cached = json.loads(ev_path.read_text(encoding="utf-8"))
            if "winning_opening" in cached and all(
                    f in cached for f in _OPENING_BOOL_FIELDS):
                print(f"[d] {vid}/rep{rep}: reuse cached opening judge")
                return cached
        except Exception:
            pass
    user_text = (f"【V2.1a 输出（creative {vid}，repeat {rep}，含全部 evidence）】\n"
                 + _evidence_detail(tags)
                 + "\n\n请按 system 指令判定，只输出 JSON 对象。")
    try:
        judge = _run_compare_judge(api, _JUDGE_OPENING, user_text,
                                   _OPENING_BOOL_FIELDS)
    except Exception as e:
        judge = {"judge_failed": True, "error": str(e)[:200]}
    ev_path.parent.mkdir(parents=True, exist_ok=True)
    ev_path.write_text(json.dumps(judge, ensure_ascii=False, indent=2),
                       encoding="utf-8")
    return judge


def eval_v21b_route(vid: str, repeats: list[dict], api: ApiClient) -> dict:
    """§13：3 次 V2.1b 输出互比。"""
    ev_path = RUN_ROOT / "evaluation" / f"{vid}-v21b-route.json"
    if ev_path.is_file():
        try:
            cached = json.loads(ev_path.read_text(encoding="utf-8"))
            if all(f in cached for f in _V21B_BOOL_FIELDS):
                print(f"[d] {vid}: reuse cached v2.1b route judge")
                return cached
        except Exception:
            pass
    blocks = []
    for i, r in enumerate(repeats, 1):
        blocks.append(f"【repeat-{i} V2.1b 输出】\n{_intent_summary(r['intent'])}")
    user_text = "\n\n".join(blocks) + "\n\n请按 system 指令判定，只输出 JSON 对象。"
    try:
        judge = _run_compare_judge(api, _JUDGE_V21B_ROUTE, user_text,
                                   _V21B_BOOL_FIELDS)
    except Exception as e:
        judge = {"judge_failed": True, "error": str(e)[:200]}
    ev_path.parent.mkdir(parents=True, exist_ok=True)
    ev_path.write_text(json.dumps(judge, ensure_ascii=False, indent=2),
                       encoding="utf-8")
    return judge


def eval_v23_gate(vid: str, repeats: list[dict], api: ApiClient) -> dict:
    """§14：3 次 V2.3 输出互比（per-repeat same answer class，目标 9/9）。"""
    ev_path = RUN_ROOT / "evaluation" / f"{vid}-v23-gate.json"
    if ev_path.is_file():
        try:
            cached = json.loads(ev_path.read_text(encoding="utf-8"))
            if all(f in cached for f in _V23_BOOL_FIELDS):
                print(f"[d] {vid}: reuse cached v2.3 gate judge")
                return cached
        except Exception:
            pass
    blocks = []
    for i, r in enumerate(repeats, 1):
        blocks.append(f"【repeat-{i} V2.3 输出摘要】\n{_copy_summary(r['copy'])}")
    user_text = "\n\n".join(blocks) + "\n\n请按 system 指令判定，只输出 JSON 对象。"
    try:
        judge = _run_compare_judge(api, _JUDGE_V23_GATE, user_text,
                                   _V23_BOOL_FIELDS)
    except Exception as e:
        judge = {"judge_failed": True, "error": str(e)[:200]}
    ev_path.parent.mkdir(parents=True, exist_ok=True)
    ev_path.write_text(json.dumps(judge, ensure_ascii=False, indent=2),
                       encoding="utf-8")
    return judge


def synthesize_d(vid: str, target: str, consist: dict, hard_fails: list[str],
                 opening_judges: list[dict], v21b_judge: dict,
                 v23_judge: dict) -> dict:
    """§15 三级合成（程序可审计）。"""
    fail: list[str] = list(hard_fails)
    warn: list[str] = []

    if not consist["opening_all_same"]:
        fail.append(f"Opening Type 换型（{consist['opening_labels']}，目标 {target}）")
    if not consist["expectation_all_same"]:
        fail.append(f"user_expectation 换类（{consist['expectation_labels']}）")
    if not consist["primary_core_stable"]:
        fail.append("Primary 主路径换轨（存在 primary 完全替换对）")

    if not v21b_judge.get("judge_failed"):
        if not v21b_judge.get("primary_driver_same_route"):
            fail.append("V2.1b Primary Driver 换轨（3 次非同一转化路径）")
        if not v21b_judge.get("question_same_type"):
            fail.append("V2.1b Unresolved Question 换问题类型")
    else:
        fail.append("V2.1b route judge 失败（工程异常）")

    if not v23_judge.get("judge_failed"):
        if not v23_judge.get("anchor_preserved"):
            fail.append("V2.3 core anchor 被替换（3 次核心话题不一致）")
        if not v23_judge.get("intent_continuity"):
            fail.append("V2.3 intent continuity 失败")
        if not v23_judge.get("template_differentiation"):
            fail.append("V2.3 template differentiation 失败")
        for i in (1, 2, 3):
            if not v23_judge.get(f"same_answer_class_repeat{i}"):
                fail.append(f"V2.3 same answer class fail（repeat-{i}）")
    else:
        fail.append("V2.3 gate judge 失败（工程异常）")

    if not fail:
        # 次级变化信号（§9 允许 → WARN）
        if not consist["primary_sets_identical"]:
            warn.append("primary 非核心槽轮换（3 次 primary 集合非全等，核心槽稳定）")
        if not consist["window_all_same"]:
            warn.append(f"decision_window 轻微变化（{consist['windows']}）")
        if not v21b_judge.get("supporting_only_secondary", True):
            fail.append("V2.1b supporting_drivers 变化超出次级范围")
        elif v21b_judge.get("supporting_only_secondary") and \
                any(v21b_judge.get("differences", [])):
            warn.append("V2.1b supporting 层存在次级差异")
        for i, j in enumerate(opening_judges, 1):
            if not j.get("judge_failed") and j.get("later_override_attempt"):
                warn.append(f"opening evaluator 判 later_override_attempt=true（rep{i}）")

    status = "FAIL" if fail else ("WARN" if warn else "PASS")
    return {
        "target_opening": target,
        "status": status,
        "opening_type_consistency": consist["opening_consistency"],
        "opening_all_same": consist["opening_all_same"],
        "expectation_consistency": consist["expectation_labels"],
        "primary_core_stable": consist["primary_core_stable"],
        "decision_window_consistency": consist["window_all_same"],
        "v2.1b_route_consistency": "3/3" if (
            v21b_judge.get("primary_driver_same_route")
            and v21b_judge.get("question_same_type")) else "x/3",
        "v2.3_same_answer_class": sum(
            1 for i in (1, 2, 3) if v23_judge.get(f"same_answer_class_repeat{i}")
        ) if not v23_judge.get("judge_failed") else 0,
        "fail_signals": fail,
        "warn_signals": warn,
    }


def evaluate_all(traces: dict) -> dict:
    tcfg = _load_text_config()
    api = ApiClient(model=tcfg["model"], api_base=tcfg["api_base"],
                    api_key=tcfg["api_key"])
    summary = {
        "run_id": "v2.5-d-opening-stability",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "model": tcfg["model"], "temperature": 0,
        "prompt_sha16": traces.get("preflight", {}),
        "repeats": REPEATS,
        "samples": {},
        "metrics": {},
        "taxonomy_review_backlog": TAXONOMY_BACKLOG,
    }
    opening_hits, route_stable, sac_total = 0, 0, 0
    # material_route_drift：route 类信号失败的样本所涉 run 数（样本级信号 ×3）
    drift_samples = 0
    for vid, target in SAMPLES.items():
        repeats = [load_repeat(vid, rep) for rep in range(1, REPEATS + 1)]
        tags_list = [r["tags"] for r in repeats]
        hard_fails = []
        for rep, tags in enumerate(tags_list, 1):
            hf = hard_checks(vid, target, tags)
            hard_fails.extend(f"rep{rep}: {f}" for f in hf)
        consist = repeat_consistency(tags_list, target)
        opening_judges = [eval_opening(vid, rep, r["tags"], api)
                          for rep, r in enumerate(repeats, 1)]
        v21b_judge = eval_v21b_route(vid, repeats, api)
        v23_judge = eval_v23_gate(vid, repeats, api)
        verdict = synthesize_d(vid, target, consist, hard_fails,
                               opening_judges, v21b_judge, v23_judge)
        verdict["opening_repeat_labels"] = consist["opening_labels"]
        verdict["primary_repeat_sets"] = consist["primaries"]
        verdict["opening_evaluators"] = [
            {k: j.get(k) for k in ("first_sufficient_window", "winning_opening",
                                   "winning_reason", "later_override_attempt",
                                   "judge_failed")}
            for j in opening_judges]
        verdict["v21b_route_judge"] = v21b_judge
        verdict["v23_gate_judge"] = v23_judge
        summary["samples"][vid] = verdict
        opening_hits += sum(1 for o in consist["opening_labels"] if o == target)
        route_stable += 3 if verdict["v2.1b_route_consistency"] == "3/3" else 0
        sac_total += verdict["v2.3_same_answer_class"]
        if verdict["status"] == "FAIL":
            drift_samples += 1
        print(f"[d] {vid}: {verdict['status']} "
              f"opening={verdict['opening_type_consistency']} "
              f"route={verdict['v2.1b_route_consistency']} "
              f"sac={verdict['v2.3_same_answer_class']}/3", flush=True)
    n = len(SAMPLES) * REPEATS
    summary["metrics"] = {
        "opening_type_target_hit": f"{opening_hits}/{n}",
        "v2.1b_route_stable": f"{route_stable}/{n}",
        "v2.3_same_answer_class": f"{sac_total}/{n}",
        # route 类信号失败的样本所涉 run 数（v04 anchor 波动样本 × 3）
        "material_route_drift": f"{drift_samples * REPEATS}/{n}",
        "status_counts": {
            s: sum(1 for v in summary["samples"].values() if v["status"] == s)
            for s in ("PASS", "WARN", "FAIL")},
    }
    out = RUN_ROOT / "evaluation" / "summary.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(summary, ensure_ascii=False, indent=2),
                   encoding="utf-8")
    print(f"[d] summary -> {out.relative_to(_REPO)}", flush=True)
    return summary


# --------------------------------------------------------------------------- #
def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--phase", choices=["all", "run", "eval"], default="all")
    args = ap.parse_args()

    traces_path = RUN_ROOT / "traces.json"
    traces: dict = {}
    if traces_path.is_file():
        try:
            traces = json.loads(traces_path.read_text(encoding="utf-8"))
        except Exception:
            traces = {}
    RUN_ROOT.mkdir(parents=True, exist_ok=True)

    if args.phase in ("all", "run"):
        traces["preflight"] = preflight()
        traces.setdefault("samples", {})
        run_all(traces)
    if args.phase in ("all", "eval"):
        if "preflight" not in traces:
            traces["preflight"] = preflight()
        evaluate_all(traces)

    traces["updated_at"] = datetime.now(timezone.utc).isoformat()
    traces_path.write_text(json.dumps(traces, ensure_ascii=False, indent=2),
                           encoding="utf-8")
    print("[d] done", flush=True)


if __name__ == "__main__":
    main()
