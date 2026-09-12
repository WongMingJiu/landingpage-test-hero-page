#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V2.5-C Narrative Dominance & Value Tagging Calibration harness (V1).

本轮只改 V2.1a Prompt（Narrative Dominance 硬规则 + §2.3.3 Primary
Eligibility），不修改 V2.1b / V2.3（Codex Prompt §1）。

流程（§11 两阶段）：
  阶段 1  V2.1a Run Once（v04 正向修复 / v06 方法保护 / v09 承接语境保护
          / v03 可选保护）→ narrative evaluator（judge 信号 + 程序硬检查）
  阶段 2  同一批 V2.1a 输出 → V2.1b → V2.3 Run Once → 下游 compatibility
          gate（Primary Driver 承接 / 期待延续 / anchor / grounding /
          template / same answer class）

判定（§14 三级口径，沿用 V2.5-B）：
  FAIL  学员案例漂成剧情内容 / 主价值漂成课程资源获取 / 课程承接类无主体
        证据进 Primary / 下游换轨 / V2.3 same answer class 失败
  WARN  secondary 增删 / primary 次序轻微变化 / wording 变化
  PASS  主叙事稳定 + 机制正确 + Primary 有资格 + 承接类未越级 + 下游同路径

对比基线：v03/v04/v06 用 V2.5-A baseline（同模型 gpt-5.5，干净对比）；
v09（negative-sample，无 gpt-5.5 基线）用 qwen frozen 三层并在 gate 中
标注跨模型噪声——v09 是保护样本，不跑三层 chain 对比，只做 V2.3 gate
（anchor 不作为 v09 的 FAIL 条件）。

用法：
    python -m v2.benchmarks.run_narrative_calibration --phase all
    python -m v2.benchmarks.run_narrative_calibration --phase v21a
    python -m v2.benchmarks.run_narrative_calibration --phase downstream
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
from v2.benchmarks.run_b2_regression import _JUDGE_V23_GATE, _V23_GATE_FIELDS  # noqa: E402

RUN_ROOT = _REPO / "output" / "v2.5-c-narrative-calibration"
V25A_ROOT = _REPO / "output" / "v2.5-same-model-replay"
REQUIRED_MODEL = "gpt-5.5"

# 样本名 -> creative_id（§9/§10：v04 正向 + v09 承接语境保护 + v06 方法保护 + v03 可选）
SAMPLES = {"v04": "v04", "negative-sample": "v09", "v06": "v06", "optional-v03": "v03"}

# v09 frozen 基线（qwen，跨模型；仅保护性对比）
FROZEN_V09 = {
    "tags": _REPO / "output/benchmark-runs/v2.1a-val-phase2/v09/run0/v2/creative_tags.json",
    "intent": _REPO / "output/benchmark-runs/intent-b2/v09/creative_intent.json",
    "copy": _REPO / "output/benchmark-runs/v2.3-message-match-copy-third-pass/v09/output.json",
}

COURSE_BEARING_LABELS = ["获得课程与学习资源", "把握限时稀缺机会",
                         "便捷领取并快速开始", "获得专业指导"]
V04_SOLO_PRIMARY_BAN = COURSE_BEARING_LABELS  # §15：不得作为唯一 Primary

# --------------------------------------------------------------------------- #
# Judge prompts
# --------------------------------------------------------------------------- #
_JUDGE_NARRATIVE = """你是 V2.5-C Narrative Dominance & Value Tagging 校准的评价器。
评估一次 V2.1a Creative Tagging 输出（AFTER，本轮 Prompt 修复后）的叙事机制识别
与 Primary 资格。评估材料 = AFTER 的标签输出 + 其全部 evidence（时间戳/来源/内容）。

评估任务：
A. Narrative Mechanism（先判说服机制，再判类型）：
   - presentation_form：素材的呈现形式（剧情/家人故事/教学演示/口播/演唱展示/图文等，一句话）
   - persuasion_mechanism：素材真正靠什么说服用户继续看/点击（一句话）
   - narrative_mechanism_correct：AFTER 的 opening_type 与 primary 层是否与真实说服机制一致。
     重点检测「故事呈现被误当成故事说服机制」：素材以剧情/家人叙事呈现、但说服靠
     「人物+学习事实+学习后变化/结果+他人反应」的案例证明时，应识别为 学员故事证明型
     + 获得可复制学习范例，而非 剧情/内容叙事型 或课程资源获取。
   - story_presentation_misjudged：是否发生上述误判（把案例证明素材判成剧情/内容叙事型）。
B. Primary Eligibility（对 AFTER 的每个 primary 标签逐个判定）：
   - narrative_centrality：是主体叙事的一部分，而非结尾承接
   - evidence_density：有多处 evidence，而非单点出现
   - persuasion_role：直接解释用户为什么继续看/点击
   - expectation_link：与用户被唤起的核心期待直接相关
   - eligible_for_primary：以上四项的综合（满足大部分才 eligible）
C. course_bearing_overreach：课程承接类标签（获得课程与学习资源/获得专业指导/
   便捷领取并快速开始/领取/报名/限时稀缺名额截止）是否在无主体叙事持续展开证据的
   情况下进入 Primary。

口径提醒：
- 教学演示/方法型素材的 persuasion mechanism 是方法教学演示——opening=教学演示型正确，
  不要把一切往「案例证明」上判；
- 低门槛主张素材（零基础可学/方法简单为主体）的 mechanism 是低门槛降阻主张——
  相关标签为 Primary 正确，不算 overreach；
- 只有素材主体本身持续围绕课程资源/领取/Offer 展开时，承接类标签进 Primary 才不算
  overreach（默认 Supporting 不是禁止）。

只输出一个 JSON 对象，无解释文字：
{"presentation_form": "...", "persuasion_mechanism": "...",
 "narrative_mechanism_correct": true|false, "story_presentation_misjudged": true|false,
 "primary_eligibility": [{"label": "...", "narrative_centrality": true|false,
   "evidence_density": true|false, "persuasion_role": true|false,
   "expectation_link": true|false, "eligible_for_primary": true|false}],
 "course_bearing_overreach": true|false,
 "differences": ["逐条列出问题（若有）"], "notes": "一句话总评"}"""

_NARRATIVE_BOOL_FIELDS = ["narrative_mechanism_correct",
                          "story_presentation_misjudged", "course_bearing_overreach"]

_JUDGE_C_CHAIN = """你是 V2.5-C 修复回归的三级语义评价器。
同一条广告跑了两次完整文本链（V2.1a -> V2.1b -> V2.3）：
BEFORE = V2.5-A baseline（修复前 Prompt、gpt-5.5 第一轮，正确路径参考）；
AFTER  = V2.5-C regression（应用 Narrative Dominance & Primary Eligibility
修复后的本轮输出，V2.1b/V2.3 未修改）。
你的任务不是给出 PASS/WARN/FAIL，而是产出下述细分信号，供程序合成三级判定。

核心区分（最重要的判读能力）：
- 【核心路径 Route】= 主叙事方向 + Primary Driver 点击因果 + Unresolved Question
  核心问题 + 必保 Creative Anchor + V2.3 回答类别。
- 【次级语义 Secondary】= supporting drivers 增删/换轨、次级 primary 标签轮换
  （primary 两个槽位中非核心槽的变化）、方法解释颗粒度、标签顺序、措辞。

本轮特别关注（Narrative Dominance 修复是否生效）：
- AFTER 若把「人物+学习事实+变化结果+他人反应」的案例证明素材判成剧情/内容叙事型，
  必须如实标记（v2.1a_route_drift）；
- AFTER 若把主价值从主体叙事主张（可复制学习范例/方法/效果）换成课程资源获取
  （获得课程与学习资源/领取/稀缺），必须如实标记；
- 修复允许 AFTER 比 BEFORE 更收敛（如承接类标签降级到 supporting 是修复生效的表现，
  不是漂移）。

信号定义（严格按此判定）：
1. v2.1a_route_drift —— V2.1a 的 opening_type 主叙事类型发生实质改变，或 primary 层
   核心价值主张被替换成另一条转化路径。
2. v2.1a_secondary_drift —— V2.1a 仅发生次级变化：非核心槽轮换、supporting 增删、
   标签顺序变化。
3. v2.1b_primary_route_drift —— primary_driver 点击因果换轨。
4. v2.1b_question_route_drift —— unresolved_question 换成另一类问题。
5. v2.1b_secondary_drift —— 仅 supporting_drivers 换轨/增删。
6. v2.3_core_anchor_replaced —— V2.3 核心 Creative Anchor 被替换成另一条广告话题。
7. v2.3_same_answer_class —— AFTER 的 T1/T2 是否仍属「同一类正确答案」。
8. cta_overrides_narrative —— AFTER 出现 CTA/稀缺/领取信息覆盖主体内容的迹象。

口径提醒：primary 两槽位中一个恒定另一个轮换 = secondary（不是 route drift）；
supporting_drivers 变化永远不是 route drift。

只输出一个 JSON 对象，无解释文字：
{"v2.1a_route_drift": true|false, "v2.1a_secondary_drift": true|false,
 "v2.1b_primary_route_drift": true|false, "v2.1b_question_route_drift": true|false,
 "v2.1b_secondary_drift": true|false, "v2.3_core_anchor_replaced": true|false,
 "v2.3_same_answer_class": true|false, "cta_overrides_narrative": true|false,
 "differences": ["逐条列出实质差异，标注层级与 route/secondary 归类"], "notes": "一句话总评"}"""

_CHAIN_BOOL_FIELDS = ["v2.1a_route_drift", "v2.1a_secondary_drift",
                      "v2.1b_primary_route_drift", "v2.1b_question_route_drift",
                      "v2.1b_secondary_drift", "v2.3_core_anchor_replaced",
                      "v2.3_same_answer_class", "cta_overrides_narrative"]

_JUDGE_V23_GATE_V09 = _JUDGE_V23_GATE + """

补充说明：本样本的 BEFORE 为跨模型冻结基线（qwen 系列），与 AFTER（gpt-5.5）存在
模型措辞差异。anchor_preserved 判定只看核心话题是否保住（如 零基础可学/方法简单/
低门槛开始），不要求措辞接近；same_answer_class 仍按「同一类正确答案」判定。"""


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
    print(f"[c-preflight] model={checks['model']} temp={checks['temperature']} "
          f"v2.1a_sha={checks['v2.1a_prompt_sha16']} -> {'PASS' if ok else 'FAIL'}")
    if not ok:
        raise SystemExit("[c-preflight] FAIL: model/temperature 不满足 §11 要求")
    return checks


def _primary_labels(tags: dict) -> list[str]:
    return [t["label"] for t in tags.get("matched_value_tags", [])
            if t.get("salience") == "primary"]


def hard_checks(vid: str, tags: dict, judge: dict) -> list[str]:
    """§15/§16/§17 程序硬检查；judge 语义信号做等价兜底。返回 fail 信号列表。"""
    fails: list[str] = []
    opening = tags["opening_type"].get("label")
    primary = _primary_labels(tags)
    mech_ok = bool(judge.get("narrative_mechanism_correct"))
    overreach = bool(judge.get("course_bearing_overreach"))

    if vid == "v04":
        if opening != "学员故事证明型" and not mech_ok:
            fails.append(f"§15: v04 opening={opening}（非学员故事证明型且语义评估未认可等价）")
        if "获得可复制学习范例" not in primary and overreach:
            fails.append(f"§15: v04 primary 无可复制学习范例且存在承接类越级（primary={primary}）")
        if len(primary) == 1 and primary[0] in V04_SOLO_PRIMARY_BAN:
            fails.append(f"§15: v04 唯一 primary 为课程承接类（{primary[0]}）")
    elif vid == "v06":
        if opening != "教学演示型" and not mech_ok:
            fails.append(f"§16: v06 opening={opening}（非教学演示型且语义评估未认可等价）")
        if "正确发声并保护嗓音" not in primary:
            fails.append(f"§16: v06 核心主张丢失（primary={primary}，无 正确发声并保护嗓音）")
    elif vid == "v09":
        if opening in ("学员故事证明型", "剧情/内容叙事型"):
            fails.append(f"§17: v09 被误判成故事类（opening={opening}，主体是低门槛主张）")
        if not ({"零基础可学", "方法简单易操作"} & set(primary)):
            fails.append(f"§17: v09 低门槛主张 primary 全丢（primary={primary}）")
    elif vid == "v03":
        if not ({"获得可复制学习范例", "获得演唱效果参照"} & set(primary)):
            fails.append(f"v03 核心主张丢失（primary={primary}）")
    return fails


# --------------------------------------------------------------------------- #
# 加载器
# --------------------------------------------------------------------------- #
def load_pair(name: str, vid: str, rdir: Path) -> dict:
    """BEFORE 基线 + AFTER 本轮（v2.1a 段必在；v2.1b/v2.3 段下游阶段补齐）。"""
    if vid == "v09":
        before = {
            "tags": json.loads(FROZEN_V09["tags"].read_text(encoding="utf-8")),
            "intent": json.loads(FROZEN_V09["intent"].read_text(encoding="utf-8")),
            "copy": json.loads(FROZEN_V09["copy"].read_text(encoding="utf-8"))["output"],
            "baseline_note": "qwen frozen（跨模型基线，仅保护性对比）",
        }
    else:
        b = V25A_ROOT / "baseline" / vid
        before = {
            "tags": json.loads((b / "v2.1a" / "creative_tags.json").read_text(encoding="utf-8")),
            "intent": json.loads((b / "v2.1b" / "creative_intent.json").read_text(encoding="utf-8")),
            "copy": json.loads((b / "v2.3" / "message_match_copy.json").read_text(encoding="utf-8"))["output"],
            "baseline_note": "V2.5-A baseline（同模型 gpt-5.5）",
        }
    after = {"tags": json.loads((rdir / "v2.1a" / "creative_tags.json").read_text(encoding="utf-8"))}
    for stage, fname, dname in (("intent", "creative_intent.json", "v2.1b"),
                                ("copy", "message_match_copy.json", "v2.3")):
        p = rdir / dname / fname
        if p.is_file():
            doc = json.loads(p.read_text(encoding="utf-8"))
            after[stage] = doc["output"] if fname == "message_match_copy.json" else doc
    return {"before": before, "after": after}


def _evidence_detail(tags: dict) -> str:
    lines = [f"opening_type: {tags['opening_type'].get('label')}",
             f"user_expectation: {tags['user_expectation'].get('label')}",
             "matched_value_tags（含全部 evidence）:"]
    for t in tags.get("matched_value_tags", []):
        lines.append(f"  [{t.get('salience')}/{t.get('evidence_strength')}] {t.get('label')}"
                     f"（{t.get('category')}）")
        for e in t.get("evidence", []):
            lines.append(f"      [{e.get('time')}] {e.get('source')}: {e.get('content', '')[:110]}")
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# 阶段 1：V2.1a Run Once + narrative 评估
# --------------------------------------------------------------------------- #
def run_v21a(name: str, vid: str) -> dict:
    rdir = RUN_ROOT / "regression" / name
    rdir.mkdir(parents=True, exist_ok=True)
    res = stage_v21a(vid, rdir, force=True)
    print(f"[c] {name}/v2.1a: {res['status']} retries_used={res.get('retries_used', 0)} "
          f"elapsed={res.get('elapsed_s', '?')}s")
    if res["status"] != "ok":
        raise SystemExit(f"[c] {name}/v2.1a failed: {res}")
    return res


def eval_narrative(name: str, vid: str, pair: dict, api: ApiClient) -> dict:
    """§13 evaluator：narrative mechanism + primary eligibility（judge 信号+硬检查）。"""
    ev_path = RUN_ROOT / "evaluation" / f"{name}.json"
    if ev_path.is_file():
        try:
            cached = json.loads(ev_path.read_text(encoding="utf-8"))
            if all(f in cached.get("narrative_judge", {}) for f in _NARRATIVE_BOOL_FIELDS):
                print(f"[c] {name}: reuse cached narrative judge")
                return cached
        except Exception:
            pass
    user_text = ("【AFTER（V2.5-C 修复后本轮 V2.1a 输出，含全部 evidence）】\n"
                 + _evidence_detail(pair["after"]["tags"])
                 + "\n\n请按 system 指令判定，只输出 JSON 对象。")
    try:
        judge = _run_compare_judge(api, _JUDGE_NARRATIVE, user_text,
                                   _NARRATIVE_BOOL_FIELDS)
    except Exception as e:
        judge = {"judge_failed": True, "error": str(e)[:200]}

    # primary_eligibility 数组校验
    elig_ok = True
    elig = judge.get("primary_eligibility")
    if judge.get("judge_failed") or not isinstance(elig, list) or not elig:
        elig_ok = False if not judge.get("judge_failed") else None
    else:
        for item in elig:
            if not isinstance(item, dict) or "label" not in item \
                    or not isinstance(item.get("eligible_for_primary"), bool):
                elig_ok = False
                break

    hard = hard_checks(vid, pair["after"]["tags"], judge) if not judge.get("judge_failed") \
        else [f"judge 失败（工程异常），硬检查无法完成：{judge.get('error', '')}"]
    return {
        "narrative_judge": judge,
        "primary_eligibility_valid": elig_ok,
        "hard_check_fails": hard,
        "programmatic_vs_baseline": programmatic_signals(pair["before"]["tags"],
                                                         pair["after"]["tags"]),
    }


# --------------------------------------------------------------------------- #
# 阶段 2：下游 Run Once + compatibility gate
# --------------------------------------------------------------------------- #
def run_downstream(name: str, vid: str) -> dict:
    rdir = RUN_ROOT / "regression" / name
    out = {}
    for stage, fn in (("v2.1b", stage_v21b), ("v2.3", stage_v23)):
        res = fn(vid, rdir, force=True)
        print(f"[c] {name}/{stage}: {res['status']} retries_used={res.get('retries_used', 0)} "
              f"elapsed={res.get('elapsed_s', '?')}s")
        if res["status"] != "ok":
            raise SystemExit(f"[c] {name}/{stage} failed: {res}")
        out[stage] = res
    return out


def eval_downstream(name: str, vid: str, pair: dict, api: ApiClient,
                    cached: dict | None) -> dict:
    """§18 gate：v03/04/06 跑 chain 对比 + V2.3 gate；v09 只跑 V2.3 gate。"""
    if cached and cached.get("chain_judge") and cached.get("gate_judge"):
        print(f"[c] {name}: reuse cached downstream judges")
        return {"chain_judge": cached["chain_judge"], "gate_judge": cached["gate_judge"]}
    result: dict = {}
    b, a = pair["before"], pair["after"]

    if vid != "v09":
        user_text = (f"【BEFORE（{b['baseline_note']}）】\n"
                     + _tags_summary(b["tags"]) + "\n\n" + _intent_summary(b["intent"]) + "\n\n"
                     + _copy_summary(b["copy"])
                     + "\n\n【AFTER（V2.5-C regression，Narrative Dominance 修复后；"
                       "V2.1b/V2.3 未修改）】\n"
                     + _tags_summary(a["tags"]) + "\n\n" + _intent_summary(a["intent"]) + "\n\n"
                     + _copy_summary(a["copy"])
                     + "\n\n请按 system 指令判定，只输出 JSON 对象。")
        try:
            result["chain_judge"] = _run_compare_judge(api, _JUDGE_C_CHAIN, user_text,
                                                       _CHAIN_BOOL_FIELDS)
        except Exception as e:
            result["chain_judge"] = {"judge_failed": True, "error": str(e)[:200]}
    else:
        result["chain_judge"] = {"skipped": "v09 无 gpt-5.5 三层基线（保护样本不跑 chain 对比）"}

    gate_system = _JUDGE_V23_GATE_V09 if vid == "v09" else _JUDGE_V23_GATE
    gate_user = (f"【BEFORE（{b['baseline_note']}，V2.3 输出）】\n" + _copy_summary(b["copy"])
                 + "\n\n【AFTER（V2.5-C 本轮 V2.3 输出，由修复后上游驱动；V2.3 未修改）】\n"
                 + _copy_summary(a["copy"])
                 + "\n\n请按 system 指令判定，只输出 JSON 对象。")
    try:
        result["gate_judge"] = _run_compare_judge(api, gate_system, gate_user,
                                                  _V23_GATE_FIELDS)
    except Exception as e:
        result["gate_judge"] = {"judge_failed": True, "error": str(e)[:200]}
    return result


# --------------------------------------------------------------------------- #
# 三级合成（§14）
# --------------------------------------------------------------------------- #
def synthesize_c(name: str, vid: str, ev: dict) -> dict:
    fails: list[str] = []
    warns: list[str] = []
    nj = ev["narrative_judge"]
    prog = ev.get("programmatic_vs_baseline", {})
    chain = ev.get("chain_judge") or {}
    gate = ev.get("gate_judge") or {}

    # 1. 程序硬检查（§15/16/17）
    fails.extend(ev.get("hard_check_fails", []))
    # 2. narrative judge（§13）
    if nj.get("judge_failed"):
        fails.append("narrative judge 失败（工程异常），待人工")
    else:
        if not nj.get("narrative_mechanism_correct"):
            fails.append("说服机制识别不正确（narrative_mechanism_correct=false）")
        if nj.get("story_presentation_misjudged"):
            fails.append("故事呈现被误当成故事说服机制（story_presentation_misjudged）")
        if nj.get("course_bearing_overreach"):
            fails.append("课程承接类无主体证据进入 Primary（course_bearing_overreach）")
        for item in (nj.get("primary_eligibility") or []):
            if isinstance(item, dict) and item.get("eligible_for_primary") is False:
                fails.append(f"Primary 资格不足：{item.get('label')}")
    # 3. chain judge（v03/04/06）
    if chain.get("judge_failed"):
        fails.append("chain judge 失败（工程异常），待人工")
    elif not chain.get("skipped"):
        if chain.get("v2.1a_route_drift"):
            fails.append("V2.1a 主叙事/primary 核心主张换轨")
        if chain.get("v2.1b_primary_route_drift"):
            fails.append("V2.1b primary_driver 点击因果换轨")
        if chain.get("v2.1b_question_route_drift"):
            fails.append("V2.1b unresolved_question 换成另一类问题")
        if chain.get("cta_overrides_narrative"):
            fails.append("CTA/稀缺信息覆盖主体内容")
        if chain.get("v2.3_core_anchor_replaced"):
            fails.append("V2.3 核心 Creative Anchor 被替换")
        if chain.get("v2.1a_secondary_drift"):
            warns.append("V2.1a 次级变化（非核心槽轮换/supporting 增删）")
        if chain.get("v2.1b_secondary_drift"):
            warns.append("V2.1b supporting_drivers 换轨/增删")
    # 4. programmatic（v03/04/06）
    if prog.get("primary_full_replacement") and not prog.get("opening_same"):
        fails.append("[programmatic] opening 换类 + primary 集合全替换")
    elif (prog.get("primary_only_baseline") or prog.get("primary_only_replay")) and vid != "v09":
        if not fails:
            warns.append(f"[programmatic] primary 非核心槽变化 "
                         f"(before-only={prog.get('primary_only_baseline')}, "
                         f"after-only={prog.get('primary_only_replay')})")
    # 5. V2.3 gate（§18）
    if gate.get("judge_failed"):
        fails.append("V2.3 gate judge 失败（工程异常），待人工")
    else:
        if gate.get("same_answer_class") is False:
            fails.append("V2.3 same answer class 失败")
        if vid != "v09":  # v09 跨模型基线，anchor 不作为 FAIL（记录在案）
            for side in ("t1", "t2"):
                if gate.get(f"anchor_preserved_{side}") is False:
                    fails.append(f"V2.3 anchor_preserved_{side} 失败")
        else:
            for side in ("t1", "t2"):
                if gate.get(f"anchor_preserved_{side}") is False:
                    warns.append(f"v09 anchor_preserved_{side}=false（跨模型基线，降级记录）")

    status = "FAIL" if fails else ("WARN" if warns else "PASS")
    route_fails = [f for f in fails if "次级" not in f and "secondary" not in f]
    return {
        "status": status, "route_stable": not route_fails,
        "narrative_mechanism_correct": (None if nj.get("judge_failed")
                                        else bool(nj.get("narrative_mechanism_correct"))),
        "primary_eligibility_correct": (None if nj.get("judge_failed") else (
            bool(ev.get("primary_eligibility_valid"))
            and not nj.get("course_bearing_overreach")
            and all(item.get("eligible_for_primary") is not False
                    for item in (nj.get("primary_eligibility") or [])))),
        "v2.3_same_answer_class": (None if gate.get("judge_failed")
                                   else gate.get("same_answer_class")),
        "fail_signals": fails, "warn_signals": warns,
    }


# --------------------------------------------------------------------------- #
# 主流程
# --------------------------------------------------------------------------- #
def main() -> int:
    ap = argparse.ArgumentParser(prog="v2.benchmarks.run_narrative_calibration")
    ap.add_argument("--phase", choices=["v21a", "downstream", "all"], default="all")
    args = ap.parse_args()

    RUN_ROOT.mkdir(parents=True, exist_ok=True)
    (RUN_ROOT / "evaluation").mkdir(exist_ok=True)
    pre = preflight()
    tcfg = _load_text_config()
    api = ApiClient(tcfg["api_base"], tcfg["api_key"], tcfg["model"],
                    temperature=0.0, max_retries=3)

    traces: dict = {"preflight": pre, "samples": {}}
    tpath = RUN_ROOT / "traces.json"
    if tpath.is_file() and args.phase == "downstream":
        traces = json.loads(tpath.read_text(encoding="utf-8"))

    evaluations: dict = {}
    for name, vid in SAMPLES.items():
        ev_path = RUN_ROOT / "evaluation" / f"{name}.json"
        cached = json.loads(ev_path.read_text(encoding="utf-8")) if ev_path.is_file() else None

        if args.phase in ("v21a", "all"):
            print(f"\n[c-run] {name} ({vid}) v2.1a")
            traces["samples"].setdefault(name, {})["v2.1a"] = run_v21a(name, vid)
        pair = load_pair(name, vid, RUN_ROOT / "regression" / name)
        if args.phase in ("v21a", "all") or cached is None:
            print(f"[c-eval] {name}: narrative")
            ev = eval_narrative(name, vid, pair, api)
            evaluations[name] = ev
        else:
            evaluations[name] = cached

        if args.phase in ("downstream", "all"):
            print(f"\n[c-run] {name} ({vid}) downstream")
            st = run_downstream(name, vid)
            traces["samples"].setdefault(name, {}).update(st)
            pair = load_pair(name, vid, RUN_ROOT / "regression" / name)
            print(f"[c-eval] {name}: downstream gate")
            ds = eval_downstream(name, vid, pair, api, evaluations[name])
            evaluations[name].update(ds)

    tpath.write_text(json.dumps(traces, ensure_ascii=False, indent=2), encoding="utf-8")

    # 合成 + 落盘
    summary_samples: dict = {}
    for name, vid in SAMPLES.items():
        ev = evaluations[name]
        verdict = synthesize_c(name, vid, ev)
        ev["verdict"] = verdict
        ev["creative_id"] = vid
        ev["baseline_note"] = ("qwen frozen（跨模型基线）" if vid == "v09"
                               else "V2.5-A baseline（gpt-5.5）")
        (RUN_ROOT / "evaluation" / f"{name}.json").write_text(
            json.dumps(ev, ensure_ascii=False, indent=2), encoding="utf-8")
        summary_samples[vid] = {
            "name": name, "status": verdict["status"],
            "narrative_mechanism_correct": verdict["narrative_mechanism_correct"],
            "primary_eligibility_correct": verdict["primary_eligibility_correct"],
            "route_stable": verdict["route_stable"],
            "v2.3_same_answer_class": verdict["v2.3_same_answer_class"],
            "fail_signals": verdict["fail_signals"],
            "warn_signals": verdict["warn_signals"],
        }
        print(f"[c] {name}({vid}): {verdict['status']} "
              f"route_stable={verdict['route_stable']}")
        for f in verdict["fail_signals"]:
            print(f"    FAIL: {f}")

    n = lambda s: sum(1 for v in summary_samples.values()  # noqa: E731
                      if v["status"] == s)
    n_route = sum(1 for v in summary_samples.values() if v["route_stable"])
    n_mech = sum(1 for v in summary_samples.values()
                 if v["narrative_mechanism_correct"] is True)
    n_elig = sum(1 for v in summary_samples.values()
                 if v["primary_eligibility_correct"] is True)
    n_sac = sum(1 for v in summary_samples.values()
                if v["v2.3_same_answer_class"] is True)
    total = len(summary_samples)
    summary = {
        "run_id": "v2.5-c-narrative-calibration",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "model": pre["model"], "temperature": pre["temperature"],
        "prompt_sha16": {k: pre[k] for k in ("v2.1a_prompt_sha16",
                                             "v2.1b_prompt_sha16", "v2.3_prompt_sha16")},
        "samples": summary_samples,
        "metrics": {
            "pass": n("PASS"), "warn": n("WARN"), "fail": n("FAIL"),
            "material_route_drift": f"{total - n_route}/{total}",
            "narrative_mechanism_correct": f"{n_mech}/{total}",
            "primary_eligibility_correct": f"{n_elig}/{total}",
            "v2.3_same_answer_class": f"{n_sac}/{total}",
        },
        "engineering_retry": {vid: any(
            (s or {}).get("retries_used", 0) > 0
            for s in traces["samples"].get(name, {}).values())
            for name, vid in SAMPLES.items()},
        "negative_sample_note": ("v01-v10 中无课程权益类标签进入 frozen Primary 的纯 "
                                 "Offer 素材；v09（低门槛领取型 opening）为最接近的真实"
                                 "承接语境样本，验证低门槛主张不被误伤，"
                                 "「Offer 主体允许 Primary」正向验证为 no_valid_negative_sample"),
    }
    (RUN_ROOT / "evaluation" / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nC summary: pass={n('PASS')} warn={n('WARN')} fail={n('FAIL')} | "
          f"route_drift={summary['metrics']['material_route_drift']} "
          f"mech={summary['metrics']['narrative_mechanism_correct']} "
          f"elig={summary['metrics']['primary_eligibility_correct']} "
          f"sac={summary['metrics']['v2.3_same_answer_class']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
