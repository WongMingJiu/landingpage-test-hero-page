#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V2.5-E Full Benchmark Repeat Stability Test harness (V1).

本轮不修改任何 Prompt / Schema / taxonomy（§2 Frozen Discipline，纯 Validation）。
目标（§1/§26）：v01-v10 全量素材 × 3 repeats × 3 stages（V2.1a→V2.1b→V2.3）
共 30 full text runs / 90 stages，验证文本链是否达到「可冻结、可进入小流量
线上实验准备」的稳定性门槛（§17/§18）。

评估框架（§6）：语义漂移分四类——
  A. Material Route Drift   默认阻断型 FAIL（§7）
  B. Anchor Density Drift   WARN（§8：主题/sac 一致，锚颗粒度变）
  C. Supporting Drift       WARN（§9：次级信息增删轮换）
  D. Taxonomy Disagreement  WARN/Backlog（§10，不单独计作 MRD）

Per-run 判定（§15）PASS/WARN/FAIL；Per-creative 判定（§16）
STABLE/STABLE_WITH_WARN/UNSTABLE。门槛（§17/§18）：
  Opening ≥29/30, Primary Route ≥29/30, V2.1b ≥29/30, V2.3 SAC ≥29/30,
  Material Route Drift ≤1/30, UNSTABLE creative ≤1/10。

v03/v04/v06 保持 D 轮已验证 regression anchors（§12）；其余样本无 target，
只评估 3× 内部一致性与 MRD，不凭空创造 target。

用法：
    python3 -m v2.benchmarks.run_full_stability --phase all
    python3 -m v2.benchmarks.run_full_stability --phase run
    python3 -m v2.benchmarks.run_full_stability --phase eval
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO))

from v2.tagging import ApiClient  # noqa: E402
from v2.benchmarks.run_full_pipeline_replay import (  # noqa: E402
    CONFIG_ENV, VIDEOS_DIR, _copy_summary, _intent_summary, _load_text_config,
    _run_compare_judge, parse_env_file, probe_text_gateway,
    stage_v21a, stage_v21b, stage_v23,
)
from v2.benchmarks.run_semantic_calibration import programmatic_signals  # noqa: E402
from v2.benchmarks.run_message_match_copy_benchmark import (  # noqa: E402
    _KB_HIT_THRESHOLD, _kb_hit_ratio, _norm,
)
from v2 import message_match_schema as mms  # noqa: E402
from v2.message_match_copy import (  # noqa: E402
    KB_PATH, T1_PROMPT, T2_PROMPT, load_slot_contract,
)

RUN_ROOT = _REPO / "output" / "v2.5-e-full-repeat-stability"
RUN_ID = "v2.5-e-full-repeat-stability"
REQUIRED_MODEL = "gpt-5.5"
REPEATS = 3

SAMPLES = [f"v{i:02d}" for i in range(1, 11)]
# §12 已验证 regression anchors（D 轮）；其余样本不凭空创造 target
REGRESSION_TARGETS = {"v03": "演唱效果型", "v04": "学员故事证明型", "v06": "教学演示型"}

# §10 已知 taxonomy 异议（frozen 基线同判，属 taxonomy/GT 议题，非 MRD）
KNOWN_TAXONOMY_DISAGREEMENTS = {
    "v09": "「低门槛领取型」：素材无领取/报名动作，judge 历轮认为真实机制为低门槛"
           "降阻主张；frozen 基线与本轮同判该标签，属 taxonomy 标签定义与素材的"
           "错配（Taxonomy Review Backlog，本轮不改 taxonomy/GT）。",
}

# §1 版本指纹（实际 SHA 在 preflight 时计算落盘，此处仅声明文件清单）
SHA_FILES = {
    "v2.1a_prompt": "v2/prompts/creative_tagging.md",
    "v2.1b_prompt": "v2/prompts/intent_decision.md",
    "v2.3_prompt": "v2/prompts/message_match_copy.md",
    "v2.1a_schema": "v2/schema.py",
    "v2.1b_schema": "v2/intent_schema.py",
    "v2.3_schema": "v2/message_match_schema.py",
    "taxonomy_opening": "v2/taxonomy/singing/opening.json",
    "taxonomy_user_expectation": "v2/taxonomy/singing/user_expectation.json",
    "taxonomy_value": "v2/taxonomy/singing/value.json",
}

# --------------------------------------------------------------------------- #
# Judge prompts（口径同 D 轮互比评价器，抬头更新为 E 轮）
# --------------------------------------------------------------------------- #
_JUDGE_V21B_ROUTE = """你是 V2.5-E V2.1b Intent Decision 重复稳定性评价器。
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

_JUDGE_V23_GATE = """你是 V2.5-E V2.3 Message Match Copy 重复稳定性评价器。
同一条广告在相同配置下连续跑了 3 次完整文本链（V2.1a→V2.1b→V2.3），以下是
3 次 V2.3 输出的摘要。评估 3 次输出之间的一致性（互相比较，无单一基准）：

1. anchor_preserved —— 3 次的 creative_anchors（topics/phrases/user_concern/
   expectation）是否保住同一组核心话题（允许措辞不同，核心话题必须相同）。
2. intent_continuity —— 3 次是否仍在回答同一 intent（同一用户问题）。
3. template_differentiation —— 3 次中 T1（问题→方法→利益卡）与 T2（顾虑→
   适配→老师→学习支持）是否都保持不同销售结构（不是同义改写）。
4. same_answer_class_repeat1/2/3 —— 每次输出是否都属于「同一类正确答案」
   （接住同一条广告的同一核心意图；文案可完全不同）。逐次判定。

口径提醒：anchor_preserved=false 但 same_answer_class 全 true 且 intent
continuity=true 时，仅属 Anchor Density Drift（WARN），不是 Material Route
Drift。只有核心广告话题被替换成另一条广告主题才算 Route Drift。

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
# Preflight（§24）
# --------------------------------------------------------------------------- #
def _sha16(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]


def preflight() -> dict:
    tcfg = _load_text_config()
    env_cfg = parse_env_file(CONFIG_ENV)
    t_override = env_cfg.get("V2_TEMPERATURE")
    temp_ok = t_override in (None, "", "0")

    checks: list[dict] = []

    def check(name: str, ok: bool, detail: str) -> None:
        checks.append({"name": name, "ok": bool(ok), "detail": detail})
        print(f"  [{'OK' if ok else 'FAIL'}] {name}: {detail}", flush=True)

    print("=" * 70 + "\nPREFLIGHT (§24)\n" + "=" * 70, flush=True)
    # 1. 10 source videos + sha
    video_shas = {}
    for vid in SAMPLES:
        vp = VIDEOS_DIR / f"{vid}.mp4"
        ok = vp.is_file()
        check(f"video:{vid}", ok, str(vp.relative_to(_REPO)) +
              (f" ({vp.stat().st_size // 1024 // 1024}MB)" if ok else " MISSING"))
        if ok:
            video_shas[vid] = _sha16(vp)
    # 2. model / temperature
    check("model", tcfg["model"] == REQUIRED_MODEL,
          f"{tcfg['model']} (require {REQUIRED_MODEL})")
    check("temperature", temp_ok, f"V2_TEMPERATURE={t_override!r} (require 0/unset)")
    # 3. text API available（§24）
    ok, detail = probe_text_gateway(tcfg)
    check("text API available", ok, detail)
    # 4. prompt/schema/taxonomy SHA frozen for this run
    shas = {}
    for name, rel in SHA_FILES.items():
        fp = _REPO / rel
        ok = fp.is_file()
        check(f"sha:{name}", ok, rel + ("" if ok else " MISSING"))
        if ok:
            shas[f"{name}_sha16"] = _sha16(fp)
    # 5. output dir writable
    try:
        RUN_ROOT.mkdir(parents=True, exist_ok=True)
        probe = RUN_ROOT / ".preflight_probe"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        check("output dir writable", True, str(RUN_ROOT.relative_to(_REPO)))
    except Exception as e:  # noqa: BLE001
        check("output dir writable", False, str(e)[:200])
    # 6. no image stage（本轮不生图，§23：harness 无 hero stage 可调）
    check("no image stage", True, "harness 仅含 v2.1a/v2.1b/v2.3 三个文本 stage")

    result = {
        "run_id": RUN_ID,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "api_base": tcfg["api_base"],
        "model": tcfg["model"],
        "temperature": 0,
        "repeats": REPEATS,
        "creative_count": len(SAMPLES),
        "unit_count": len(SAMPLES) * REPEATS,
        "stage_count": len(SAMPLES) * REPEATS * 3,
        "source_video_sha16": video_shas,
        **shas,
        "checks": checks,
        "ok": all(c["ok"] for c in checks),
    }
    RUN_ROOT.mkdir(parents=True, exist_ok=True)
    (RUN_ROOT / "preflight.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    if not result["ok"]:
        raise SystemExit("[e-preflight] FAIL: 存在未通过检查项，按 §24 停止")
    print(f"[e-preflight] PASS -> {(RUN_ROOT / 'preflight.json').relative_to(_REPO)}",
          flush=True)
    return result


# --------------------------------------------------------------------------- #
# 程序指标
# --------------------------------------------------------------------------- #
def _primary_labels(tags: dict) -> list[str]:
    return [t["label"] for t in tags.get("matched_value_tags", [])
            if t.get("salience") == "primary"]


def _modal_hits(labels: list[str]) -> tuple[str, int]:
    """众数 label 与命中数。"""
    cnt = Counter(labels)
    modal, hits = cnt.most_common(1)[0]
    return modal, hits


def repeat_consistency(tags_list: list[dict]) -> dict:
    """§11 程序一致性指标（3 次之间，无 target 口径）。"""
    openings = [t["opening_type"].get("label") for t in tags_list]
    expectations = [t["user_expectation"].get("label") for t in tags_list]
    windows = [(t["decision_window"].get("used_seconds"),
                bool(t["decision_window"].get("extended"))) for t in tags_list]
    primaries = [_primary_labels(t) for t in tags_list]
    pairwise = []
    for i in range(len(tags_list)):
        for j in range(i + 1, len(tags_list)):
            pairwise.append(programmatic_signals(tags_list[i], tags_list[j]))
    primary_core_stable = all(not p["primary_full_replacement"] for p in pairwise)
    _, opening_hits = _modal_hits(openings)
    _, expectation_hits = _modal_hits(expectations)
    # primary route per-unit 稳定：与众数 primary 集合交集非空
    modal_primary, _ = Counter(map(frozenset, primaries)).most_common(1)[0] \
        if primaries else (frozenset(), 0)
    primary_hits = sum(1 for p in primaries if set(p) & set(modal_primary))
    return {
        "opening_labels": openings,
        "opening_all_same": len(set(openings)) == 1,
        "opening_modal_hits": opening_hits,
        "expectation_labels": expectations,
        "expectation_all_same": len(set(expectations)) == 1,
        "expectation_modal_hits": expectation_hits,
        "windows": [list(w) for w in windows],
        "window_all_same": len(set(windows)) == 1,
        "primaries": primaries,
        "primary_core_stable": primary_core_stable,
        "primary_route_hits": primary_hits,
        "primary_sets_identical": len({frozenset(p) for p in primaries}) == 1,
    }


def v23_programmatic_gate(output: dict, kb_norm: str, t1_contract: dict,
                          t2_contract: dict, banned_dict: dict) -> dict:
    """§14 程序化 gate（per-run）：schema/slot/compliance/grounding safety。

    hard fail：schema_errors / slot_contract_errors / newline_slot_values /
    compliance_errors / grounding_trace_errors。
    warn：grounding_status=partial（仍安全，§15 WARN 口径）、kb_weak_references。
    """
    hard: list[str] = []
    warn: list[str] = []
    errors = {
        "schema_errors": mms.validate_schema(output),
        "slot_contract_errors": mms.validate_slot_contract(output, t1_contract,
                                                           t2_contract),
        "newline_slot_values": mms.newline_slot_values(output),
        "compliance_errors": mms.validate_compliance(output, banned_dict),
        "grounding_trace_errors": mms.validate_grounding_trace(output),
    }
    for k, v in errors.items():
        if v:
            hard.append(f"{k}: {json.dumps(v, ensure_ascii=False)[:200]}")
    pack = output.get("product_grounding_pack", {})
    grounding_status = pack.get("grounding_status")
    if grounding_status == "partial":
        warn.append("grounding_status=partial（仍安全）")
    elif grounding_status not in (None, "sufficient"):
        hard.append(f"grounding_status={grounding_status}（非 sufficient/partial）")
    kb_weak = []
    for key in ("course_facts", "service_facts", "teacher_facts"):
        for it in pack.get(key) or []:
            if isinstance(it, dict) and it.get("statement"):
                ratio = _kb_hit_ratio(it["statement"], kb_norm)
                if ratio < _KB_HIT_THRESHOLD:
                    kb_weak.append({"statement": it["statement"],
                                    "kb_hit_ratio": round(ratio, 2)})
    if kb_weak:
        warn.append(f"kb_weak_references: {len(kb_weak)} 条")
    return {"hard_fails": hard, "warns": warn, "grounding_status": grounding_status,
            "kb_weak_references": kb_weak}


# --------------------------------------------------------------------------- #
# 阶段 1：30 runs / 90 stages（Run Once + bounded engineering retry）
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
                print(f"[e] {key}/{stage}: {res['status']} "
                      f"retries_used={res.get('retries_used', 0)} "
                      f"elapsed={res.get('elapsed_s', '?')}s", flush=True)
                if res["status"] != "ok":
                    raise SystemExit(f"[e] {key}/{stage} failed: {res}")


# --------------------------------------------------------------------------- #
# 阶段 2：评估
# --------------------------------------------------------------------------- #
def load_repeat(vid: str, rep: int) -> dict:
    rdir = RUN_ROOT / vid / f"repeat-{rep}"
    tags = json.loads((rdir / "v2.1a" / "creative_tags.json").read_text(encoding="utf-8"))
    intent = json.loads((rdir / "v2.1b" / "creative_intent.json").read_text(encoding="utf-8"))
    copy_doc = json.loads((rdir / "v2.3" / "message_match_copy.json").read_text(encoding="utf-8"))
    return {"rdir": rdir, "tags": tags, "intent": intent, "copy": copy_doc["output"]}


def eval_v21b_route(vid: str, repeats: list[dict], api: ApiClient) -> dict:
    ev_path = RUN_ROOT / "evaluation" / f"{vid}-v21b-route.json"
    if ev_path.is_file():
        try:
            cached = json.loads(ev_path.read_text(encoding="utf-8"))
            if all(f in cached for f in _V21B_BOOL_FIELDS):
                print(f"[e] {vid}: reuse cached v2.1b route judge")
                return cached
        except Exception:
            pass
    blocks = [f"【repeat-{i} V2.1b 输出】\n{_intent_summary(r['intent'])}"
              for i, r in enumerate(repeats, 1)]
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
    ev_path = RUN_ROOT / "evaluation" / f"{vid}-v23-gate.json"
    if ev_path.is_file():
        try:
            cached = json.loads(ev_path.read_text(encoding="utf-8"))
            if all(f in cached for f in _V23_BOOL_FIELDS):
                print(f"[e] {vid}: reuse cached v2.3 gate judge")
                return cached
        except Exception:
            pass
    blocks = [f"【repeat-{i} V2.3 输出摘要】\n{_copy_summary(r['copy'])}"
              for i, r in enumerate(repeats, 1)]
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


def classify_creative(vid: str, consist: dict, run_gates: list[dict],
                      v21b_judge: dict, v23_judge: dict) -> dict:
    """§6-§16 程序合成：四类漂移分类 + per-run/per-creative 判定（程序可审计）。

    run_gates[rep-1] = v23_programmatic_gate 结果（per-run hard fail 属 §15 FAIL）。
    """
    mrd_units: set[int] = set()          # Material Route Drift（阻断，unit=1..3）
    anchor_density = False               # B 类（creative 级 WARN）
    supporting = False                   # C 类（creative 级 WARN）
    taxonomy = vid in KNOWN_TAXONOMY_DISAGREEMENTS  # D 类
    fail_signals: list[str] = []
    warn_signals: list[str] = []

    # ---- A 类：Material Route Drift（§7） ----
    if not consist["opening_all_same"]:
        modal, _ = _modal_hits(consist["opening_labels"])
        bad = [i + 1 for i, o in enumerate(consist["opening_labels"]) if o != modal]
        mrd_units.update(bad)
        fail_signals.append(f"Opening Type 换型（{consist['opening_labels']}，"
                            f"偏离 unit={bad}）")
    if not consist["expectation_all_same"]:
        modal, _ = _modal_hits(consist["expectation_labels"])
        bad = [i + 1 for i, e in enumerate(consist["expectation_labels"]) if e != modal]
        mrd_units.update(bad)
        fail_signals.append(f"user_expectation 换类（{consist['expectation_labels']}）")
    if not consist["primary_core_stable"]:
        bad = [i + 1 for i, p in enumerate(consist["primaries"])
               if not _primary_intersects_modal(p, consist["primaries"])]
        mrd_units.update(bad or [1, 2, 3])
        fail_signals.append("Primary 主价值路径换轨（存在 primary 完全替换）")
    if not v21b_judge.get("judge_failed"):
        if not v21b_judge.get("primary_driver_same_route"):
            mrd_units.update((1, 2, 3))
            fail_signals.append("V2.1b Primary Driver 点击因果换轨")
        if not v21b_judge.get("question_same_type"):
            mrd_units.update((1, 2, 3))
            fail_signals.append("V2.1b Unresolved Question 换问题类型")
    else:
        mrd_units.update((1, 2, 3))
        fail_signals.append("V2.1b route judge 失败（工程异常）")
    if not v23_judge.get("judge_failed"):
        for i in (1, 2, 3):
            if not v23_judge.get(f"same_answer_class_repeat{i}"):
                mrd_units.add(i)
                fail_signals.append(f"V2.3 same answer class=false（repeat-{i}）")
        if not v23_judge.get("intent_continuity"):
            mrd_units.update((1, 2, 3))
            fail_signals.append("V2.3 intent continuity=false（核心问题改变）")
    else:
        mrd_units.update((1, 2, 3))
        fail_signals.append("V2.3 gate judge 失败（工程异常）")
    # per-run 程序化 hard fail（§15：Schema/Slot/Compliance/Grounding Safety）
    for rep, gate in enumerate(run_gates, 1):
        if gate["hard_fails"]:
            mrd_units.add(rep)
            fail_signals.extend(f"rep{rep}: {f}" for f in gate["hard_fails"])

    # ---- B 类：Anchor Density Drift（§8，sac/intent 均保持时的 WARN） ----
    if (not v23_judge.get("judge_failed")
            and not v23_judge.get("anchor_preserved")
            and v23_judge.get("intent_continuity")
            and all(v23_judge.get(f"same_answer_class_repeat{i}") for i in (1, 2, 3))):
        anchor_density = True
        warn_signals.append("B|Anchor Density Drift：V2.3 核心锚颗粒度/密度变化"
                            "（主题/sac/intent 一致）")

    # ---- C 类：Supporting Drift（§9，Core Route 不变的次级变化） ----
    if not consist["primary_sets_identical"] and consist["primary_core_stable"]:
        supporting = True
        warn_signals.append("C|Supporting Drift：primary 非核心槽轮换"
                            f"（{consist['primaries']}，核心槽稳定）")
    if not consist["window_all_same"]:
        supporting = True
        warn_signals.append(f"C|decision_window 轻变（{consist['windows']}）")
    if (not v21b_judge.get("judge_failed")
            and v21b_judge.get("primary_driver_same_route")
            and not v21b_judge.get("supporting_only_secondary", True)):
        supporting = True
        warn_signals.append("C|V2.1b supporting_drivers 差异（主 route 不变）")
    if (not v23_judge.get("judge_failed")
            and not v23_judge.get("template_differentiation")):
        supporting = True
        warn_signals.append("C|V2.3 template differentiation 减弱（非换轨）")
    for rep, gate in enumerate(run_gates, 1):
        for w in gate["warns"]:
            warn_signals.append(f"rep{rep}: {w}")
    if run_gates and any(g["warns"] for g in run_gates):
        supporting = True

    # ---- D 类：Taxonomy Disagreement（§10） ----
    if taxonomy:
        warn_signals.append(f"D|Taxonomy Disagreement："
                            f"{KNOWN_TAXONOMY_DISAGREEMENTS[vid]}")

    # ---- per-run / per-creative 判定 ----
    has_warn = anchor_density or supporting or taxonomy
    runs = []
    for rep in (1, 2, 3):
        if rep in mrd_units:
            runs.append({"repeat": rep, "status": "FAIL"})
        elif has_warn:
            runs.append({"repeat": rep, "status": "WARN"})
        else:
            runs.append({"repeat": rep, "status": "PASS"})
    if mrd_units:
        creative_status = "UNSTABLE"
    elif has_warn:
        creative_status = "STABLE_WITH_WARN"
    else:
        creative_status = "STABLE"

    target = REGRESSION_TARGETS.get(vid)
    target_hit = (sum(1 for o in consist["opening_labels"] if o == target)
                  if target else None)
    return {
        "creative_id": vid,
        "target_opening": target,
        "target_hit_count": (f"{target_hit}/{REPEATS}" if target else None),
        "status": creative_status,
        "runs": runs,
        "opening_labels": consist["opening_labels"],
        "opening_consistency": f"{consist['opening_modal_hits']}/{REPEATS}",
        "expectation_labels": consist["expectation_labels"],
        "expectation_consistency": f"{consist['expectation_modal_hits']}/{REPEATS}",
        "primaries": consist["primaries"],
        "primary_route_consistency": f"{consist['primary_route_hits']}/{REPEATS}",
        "decision_window_consistency": consist["window_all_same"],
        "v2.1b_route_consistency": ("3/3" if (
            v21b_judge.get("primary_driver_same_route")
            and v21b_judge.get("question_same_type")) else "0/3"),
        "v2.3_same_answer_class": (
            sum(1 for i in (1, 2, 3)
                if v23_judge.get(f"same_answer_class_repeat{i}"))
            if not v23_judge.get("judge_failed") else 0),
        "material_route_drift_units": sorted(mrd_units),
        "anchor_density_drift": anchor_density,
        "supporting_drift": supporting,
        "taxonomy_disagreement": taxonomy,
        "fail_signals": fail_signals,
        "warn_signals": warn_signals,
    }


def _primary_intersects_modal(primary: list[str], all_primaries: list[list[str]]) -> bool:
    modal, _ = Counter(map(frozenset, all_primaries)).most_common(1)[0]
    return bool(set(primary) & set(modal))


def evaluate_all(traces: dict) -> dict:
    tcfg = _load_text_config()
    api = ApiClient(model=tcfg["model"], api_base=tcfg["api_base"],
                    api_key=tcfg["api_key"])
    kb_norm = _norm(Path(KB_PATH).read_text(encoding="utf-8"))
    t1_contract = load_slot_contract(T1_PROMPT)
    t2_contract = load_slot_contract(T2_PROMPT)
    banned_dict = mms.load_compliance_lists()

    summary = {
        "run_id": RUN_ID,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "api_base": tcfg["api_base"],
        "model": tcfg["model"], "temperature": 0,
        "repeats": REPEATS,
        "creative_count": len(SAMPLES),
        "unit_count": len(SAMPLES) * REPEATS,
        "version_sha16": traces.get("preflight", {}),
        "metrics": {},
        "creative_level": {},
        "samples": {},
        "taxonomy_review_backlog": KNOWN_TAXONOMY_DISAGREEMENTS,
    }
    m_opening = m_primary = m_v21b = m_sac = 0
    m_mrd = m_anchor = m_support = m_tax = 0
    cl = {"STABLE": 0, "STABLE_WITH_WARN": 0, "UNSTABLE": 0}
    for vid in SAMPLES:
        repeats = [load_repeat(vid, rep) for rep in range(1, REPEATS + 1)]
        tags_list = [r["tags"] for r in repeats]
        consist = repeat_consistency(tags_list)
        run_gates = [v23_programmatic_gate(r["copy"], kb_norm, t1_contract,
                                           t2_contract, banned_dict)
                     for r in repeats]
        v21b_judge = eval_v21b_route(vid, repeats, api)
        v23_judge = eval_v23_gate(vid, repeats, api)
        verdict = classify_creative(vid, consist, run_gates, v21b_judge, v23_judge)
        verdict["v23_programmatic_gates"] = [
            {"repeat": i, "grounding_status": g["grounding_status"],
             "hard_fails": g["hard_fails"], "warns": g["warns"]}
            for i, g in enumerate(run_gates, 1)]
        verdict["v21b_route_judge"] = v21b_judge
        verdict["v23_gate_judge"] = v23_judge
        summary["samples"][vid] = verdict
        (RUN_ROOT / "evaluation" / f"{vid}.json").write_text(
            json.dumps(verdict, ensure_ascii=False, indent=2), encoding="utf-8")

        m_opening += consist["opening_modal_hits"]
        m_primary += consist["primary_route_hits"]
        m_v21b += 3 if verdict["v2.1b_route_consistency"] == "3/3" else 0
        m_sac += verdict["v2.3_same_answer_class"]
        m_mrd += len(verdict["material_route_drift_units"])
        if verdict["anchor_density_drift"]:
            m_anchor += REPEATS
        if verdict["supporting_drift"]:
            m_support += REPEATS
        if verdict["taxonomy_disagreement"]:
            m_tax += REPEATS
        cl[verdict["status"]] += 1
        print(f"[e] {vid}: {verdict['status']} "
              f"opening={verdict['opening_consistency']} "
              f"primary={verdict['primary_route_consistency']} "
              f"route={verdict['v2.1b_route_consistency']} "
              f"sac={verdict['v2.3_same_answer_class']}/3 "
              f"mrd_units={verdict['material_route_drift_units']}", flush=True)

    n = len(SAMPLES) * REPEATS
    frac = lambda x: f"{x}/{n}"  # noqa: E731
    pct = lambda x: round(100.0 * x / n, 1)  # noqa: E731
    summary["metrics"] = {
        "opening_type_stable": {"fraction": frac(m_opening), "percentage": pct(m_opening)},
        "primary_route_stable": {"fraction": frac(m_primary), "percentage": pct(m_primary)},
        "v2.1b_route_stable": {"fraction": frac(m_v21b), "percentage": pct(m_v21b)},
        "v2.3_same_answer_class": {"fraction": frac(m_sac), "percentage": pct(m_sac)},
        "material_route_drift": {"fraction": frac(m_mrd), "percentage": pct(m_mrd)},
        "anchor_density_drift": {"fraction": frac(m_anchor), "percentage": pct(m_anchor)},
        "supporting_drift": {"fraction": frac(m_support), "percentage": pct(m_support)},
        "taxonomy_disagreement": {"fraction": frac(m_tax), "percentage": pct(m_tax)},
    }
    summary["creative_level"] = {
        "stable": cl["STABLE"], "stable_with_warn": cl["STABLE_WITH_WARN"],
        "unstable": cl["UNSTABLE"],
        "unstable_fraction": f"{cl['UNSTABLE']}/{len(SAMPLES)}",
    }
    # §17/§18 门槛逐条判定
    gates = {
        "opening_type_stable>=29/30": m_opening >= n - 1,
        "primary_route_stable>=29/30": m_primary >= n - 1,
        "v2.1b_route_stable>=29/30": m_v21b >= n - 1,
        "v2.3_same_answer_class>=29/30": m_sac >= n - 1,
        "material_route_drift<=1/30": m_mrd <= 1,
        "unstable_creative<=1/10": cl["UNSTABLE"] <= 1,
    }
    summary["production_candidate_gates"] = {
        k: ("PASS" if v else "FAIL") for k, v in gates.items()}
    summary["freeze_decision"] = ("A|Freeze Candidate" if all(gates.values())
                                  else "B|Not Ready")
    out = RUN_ROOT / "evaluation" / "summary.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(summary, ensure_ascii=False, indent=2),
                   encoding="utf-8")
    print(f"[e] gates: {summary['production_candidate_gates']}", flush=True)
    print(f"[e] decision: {summary['freeze_decision']}", flush=True)
    print(f"[e] summary -> {out.relative_to(_REPO)}", flush=True)
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
    print("[e] done", flush=True)


if __name__ == "__main__":
    main()
