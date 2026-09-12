#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V2.5-F Production Gate Calibration & Structural Hardening harness.

Part A（§2-§8）：used_anchors membership 结构约束已落在
v2/message_match_schema.py（collect_anchor_values / validate_used_anchors_membership，
exact membership、只报告不修复），本 harness 执行 v04 × 3 structural
regression（完整文本链 Raw Video→V2.1a→V2.1b→V2.3，gpt-5.5/temp=0，
禁止 semantic retry），目标是 Structural Hard Fail = 0/3。

Part B（§9-§20）：用新 Production Gate 口径重算 V2.5-E 30 units
（不重跑模型，直接读 artifacts + 落盘 judge）：
  - Intermediate Drift（V2.1a opening/primary/expectation 漂移）在下游
    route/sac 稳定时 → WARN/observability，不计 E2E MRD；
  - E2E MRD 只含 V2.1b Core Route Drift / V2.3 SAC fail / 页面回答方向改变；
  - Structural Hard Fail 单独统计（schema/slot/compliance/grounding trace/
    used_anchors membership），不与 semantic MRD 混同。

用法：
    python3 -m v2.benchmarks.run_production_gate --phase all
    python3 -m v2.benchmarks.run_production_gate --phase regression
    python3 -m v2.benchmarks.run_production_gate --phase recalc
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
    CONFIG_ENV, _copy_summary, _intent_summary, _load_text_config,
    _run_compare_judge, parse_env_file, probe_text_gateway,
    stage_v21a, stage_v21b, stage_v23,
)
from v2.benchmarks.run_full_stability import (  # noqa: E402
    REGRESSION_TARGETS, REPEATS, SAMPLES, _primary_labels, _modal_hits,
)
from v2.benchmarks.run_message_match_copy_benchmark import (  # noqa: E402
    _KB_HIT_THRESHOLD, _kb_hit_ratio, _norm,
)
from v2 import message_match_schema as mms  # noqa: E402
from v2.message_match_copy import KB_PATH, T1_PROMPT, T2_PROMPT, load_slot_contract  # noqa: E402

RUN_ROOT = _REPO / "output" / "v2.5-f-production-gate"
E_ROOT = _REPO / "output" / "v2.5-e-full-repeat-stability"
RUN_ID = "v2.5-f-production-gate"
REQUIRED_MODEL = "gpt-5.5"

# --------------------------------------------------------------------------- #
# Judge prompts
# --------------------------------------------------------------------------- #
_JUDGE_V21B_ROUTE = """你是 V2.5-F V2.1b Intent Decision 重复稳定性评价器。
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

_JUDGE_V23_GATE = """你是 V2.5-F V2.3 Message Match Copy 重复稳定性评价器。
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
# Preflight
# --------------------------------------------------------------------------- #
def preflight() -> dict:
    import hashlib

    tcfg = _load_text_config()
    env_cfg = parse_env_file(CONFIG_ENV)
    t_override = env_cfg.get("V2_TEMPERATURE")
    temp_ok = t_override in (None, "", "0")
    checks: list[dict] = []

    def check(name: str, ok: bool, detail: str) -> None:
        checks.append({"name": name, "ok": bool(ok), "detail": detail})
        print(f"  [{'OK' if ok else 'FAIL'}] {name}: {detail}", flush=True)

    print("=" * 70 + "\nPREFLIGHT\n" + "=" * 70, flush=True)
    check("model", tcfg["model"] == REQUIRED_MODEL,
          f"{tcfg['model']} (require {REQUIRED_MODEL})")
    check("temperature", temp_ok, f"V2_TEMPERATURE={t_override!r}")
    ok, detail = probe_text_gateway(tcfg)
    check("text API available", ok, detail)
    check("V2.5-E artifacts found", E_ROOT.is_dir(),
          str(E_ROOT.relative_to(_REPO)) if E_ROOT.is_dir() else "MISSING")
    for vid in ("v01", "v04", "v07"):
        p = E_ROOT / vid / "repeat-1" / "v2.1a" / "creative_tags.json"
        check(f"E-artifact:{vid}", p.is_file(), p.relative_to(_REPO).as_posix())
    video = _REPO / "benchmarks-local" / "singing-creative-tagging-v1.0" / "videos" / "v04.mp4"
    check("video:v04", video.is_file(),
          str(video.relative_to(_REPO)) if video.is_file() else "MISSING")
    # validator 就位（§6）
    check("validator:validate_used_anchors_membership",
          hasattr(mms, "validate_used_anchors_membership")
          and hasattr(mms, "collect_anchor_values"), "message_match_schema.py")
    # 输出可写
    try:
        RUN_ROOT.mkdir(parents=True, exist_ok=True)
        probe = RUN_ROOT / ".probe"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        check("output dir writable", True, str(RUN_ROOT.relative_to(_REPO)))
    except Exception as e:  # noqa: BLE001
        check("output dir writable", False, str(e)[:200])

    sha_files = {
        "v2.3_schema_sha16": "v2/message_match_schema.py",
        "v2.1a_prompt_sha16": "v2/prompts/creative_tagging.md",
        "v2.1b_prompt_sha16": "v2/prompts/intent_decision.md",
        "v2.3_prompt_sha16": "v2/prompts/message_match_copy.md",
    }
    shas = {}
    for name, rel in sha_files.items():
        fp = _REPO / rel
        if fp.is_file():
            shas[name] = hashlib.sha256(fp.read_bytes()).hexdigest()[:16]
    result = {
        "run_id": RUN_ID,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "api_base": tcfg["api_base"], "model": tcfg["model"], "temperature": 0,
        "e_artifacts_root": str(E_ROOT.relative_to(_REPO)),
        **shas,
        "checks": checks,
        "ok": all(c["ok"] for c in checks),
    }
    RUN_ROOT.mkdir(parents=True, exist_ok=True)
    (RUN_ROOT / "preflight.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    if not result["ok"]:
        raise SystemExit("[f-preflight] FAIL: 存在未通过检查项，停止")
    print(f"[f-preflight] PASS -> {(RUN_ROOT / 'preflight.json').relative_to(_REPO)}",
          flush=True)
    return result


# --------------------------------------------------------------------------- #
# Part A：v04 × 3 structural regression
# --------------------------------------------------------------------------- #
def run_v04_regression(traces: dict) -> None:
    vid = "v04"
    for rep in range(1, REPEATS + 1):
        rdir = RUN_ROOT / "structural-regression" / vid / f"repeat-{rep}"
        rdir.mkdir(parents=True, exist_ok=True)
        traces.setdefault("regression", {})[f"repeat-{rep}"] = {}
        for stage, fn in (("v2.1a", stage_v21a), ("v2.1b", stage_v21b),
                          ("v2.3", stage_v23)):
            res = fn(vid, rdir, force=True)
            traces["regression"][f"repeat-{rep}"][stage] = {
                "status": res["status"], "retries_used": res.get("retries_used", 0)}
            print(f"[f] {vid}/repeat-{rep}/{stage}: {res['status']} "
                  f"retries_used={res.get('retries_used', 0)} "
                  f"elapsed={res.get('elapsed_s', '?')}s", flush=True)
            if res["status"] != "ok":
                raise SystemExit(f"[f] {vid}/repeat-{rep}/{stage} failed: {res}")


def evaluate_v04_regression(traces: dict) -> dict:
    """§8 目标：Schema hard fail 0/3、Grounding trace fail 0/3、
    V2.1b Route 3/3、V2.3 SAC 3/3。结构 gate 全程序化；route/sac 用互比 judge。"""
    tcfg = _load_text_config()
    api = ApiClient(model=tcfg["model"], api_base=tcfg["api_base"],
                    api_key=tcfg["api_key"])
    banned_dict = mms.load_compliance_lists()
    t1c, t2c = load_slot_contract(T1_PROMPT), load_slot_contract(T2_PROMPT)
    vid = "v04"
    repeats = []
    structural = []
    for rep in range(1, REPEATS + 1):
        rdir = RUN_ROOT / "structural-regression" / vid / f"repeat-{rep}"
        tags = json.loads((rdir / "v2.1a" / "creative_tags.json").read_text(encoding="utf-8"))
        intent = json.loads((rdir / "v2.1b" / "creative_intent.json").read_text(encoding="utf-8"))
        copy_doc = json.loads((rdir / "v2.3" / "message_match_copy.json").read_text(encoding="utf-8"))
        output = copy_doc["output"]
        repeats.append({"rdir": rdir, "tags": tags, "intent": intent, "copy": output})
        # 结构 hard gate（程序化，0 tolerance）
        schema_errors = mms.validate_schema(output)
        slot_errors = mms.validate_slot_contract(output, t1c, t2c)
        compliance_errors = mms.validate_compliance(output, banned_dict)
        trace_errors = mms.validate_grounding_trace(output)
        member_errors = mms.validate_used_anchors_membership(output)
        grounding_status = output.get("product_grounding_pack", {}).get("grounding_status")
        grounding_safety_fail = grounding_status not in (None, "sufficient", "partial")
        structural.append({
            "repeat": rep,
            "schema_errors": schema_errors,
            "slot_contract_errors": slot_errors,
            "compliance_errors": compliance_errors,
            "grounding_trace_errors": trace_errors,
            "used_anchors_membership_errors": member_errors,
            "grounding_status": grounding_status,
            "grounding_safety_fail": grounding_safety_fail,
            "hard_fail": bool(schema_errors or slot_errors or compliance_errors
                              or trace_errors or member_errors or grounding_safety_fail),
        })
        print(f"[f] v04/rep{rep}: structural hard_fail="
              f"{structural[-1]['hard_fail']} "
              f"(trace={len(trace_errors)} member={len(member_errors)})", flush=True)

    # semantic gate（judge 落盘复用）
    v21b_judge = _judged(RUN_ROOT / "structural-regression" / vid,
                         f"{vid}-v21b-route.json", _JUDGE_V21B_ROUTE,
                         _V21B_BOOL_FIELDS,
                         [f"【repeat-{i} V2.1b 输出】\n{_intent_summary(r['intent'])}"
                          for i, r in enumerate(repeats, 1)], api)
    v23_judge = _judged(RUN_ROOT / "structural-regression" / vid,
                        f"{vid}-v23-gate.json", _JUDGE_V23_GATE,
                        _V23_BOOL_FIELDS,
                        [f"【repeat-{i} V2.3 输出摘要】\n{_copy_summary(r['copy'])}"
                         for i, r in enumerate(repeats, 1)], api)
    openings = [r["tags"]["opening_type"].get("label") for r in repeats]
    primaries = [_primary_labels(r["tags"]) for r in repeats]
    result = {
        "creative_id": vid,
        "target_opening": REGRESSION_TARGETS["v04"],
        "opening_labels": openings,
        "opening_consistency": f"{_modal_hits(openings)[1]}/{REPEATS}",
        "primaries": primaries,
        "structural_gates": structural,
        "structural_hard_fail": f"{sum(1 for s in structural if s['hard_fail'])}/{REPEATS}",
        "v2.1b_route_consistency": "3/3" if (
            v21b_judge.get("primary_driver_same_route")
            and v21b_judge.get("question_same_type")) else "0/3",
        "v2.3_same_answer_class": sum(
            1 for i in (1, 2, 3) if v23_judge.get(f"same_answer_class_repeat{i}")),
        "v21b_route_judge": v21b_judge,
        "v23_gate_judge": v23_judge,
    }
    out = RUN_ROOT / "structural-regression" / f"{vid}.json"
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[f] v04 regression: structural={result['structural_hard_fail']} "
          f"route={result['v2.1b_route_consistency']} "
          f"sac={result['v2.3_same_answer_class']}/3", flush=True)
    return result


def _judged(base: Path, name: str, system: str, bool_fields: list[str],
            blocks: list[str], api: ApiClient) -> dict:
    ev_path = base / name
    if ev_path.is_file():
        try:
            cached = json.loads(ev_path.read_text(encoding="utf-8"))
            if all(f in cached for f in bool_fields):
                print(f"[f] reuse cached judge: {ev_path.name}")
                return cached
        except Exception:
            pass
    user_text = "\n\n".join(blocks) + "\n\n请按 system 指令判定，只输出 JSON 对象。"
    try:
        judge = _run_compare_judge(api, system, user_text, bool_fields)
    except Exception as e:  # noqa: BLE001
        judge = {"judge_failed": True, "error": str(e)[:200]}
    base.mkdir(parents=True, exist_ok=True)
    ev_path.write_text(json.dumps(judge, ensure_ascii=False, indent=2),
                       encoding="utf-8")
    return judge


# --------------------------------------------------------------------------- #
# Part B：V2.5-E 30 units 重算（新 Production Gate 口径）
# --------------------------------------------------------------------------- #
def _load_e_repeat(vid: str, rep: int) -> dict:
    rdir = E_ROOT / vid / f"repeat-{rep}"
    return {
        "rdir": rdir,
        "tags": json.loads((rdir / "v2.1a" / "creative_tags.json").read_text(encoding="utf-8")),
        "intent": json.loads((rdir / "v2.1b" / "creative_intent.json").read_text(encoding="utf-8")),
        "copy": json.loads((rdir / "v2.3" / "message_match_copy.json")
                           .read_text(encoding="utf-8"))["output"],
    }


def recalc_sample(vid: str, api: ApiClient, kb_norm: str, t1c: dict,
                  t2c: dict, banned_dict: dict) -> dict:
    """新 Gate 口径重算单个 creative（30 units 中的 3 个）。

    Semantic E2E MRD（§11）：V2.1b Core Route Drift（creative 级，记 3 units）
    / V2.3 SAC fail（unit 级）/ intent continuity fail（creative 级，记 3 units）。
    Structural Hard Fail（§11-D，单独统计）：schema/slot/compliance/grounding
    safety/grounding trace/used_anchors membership（unit 级）。
    Intermediate Drift（§10，observability）：V2.1a opening/primary/expectation
    漂移 + anchor density/supporting/taxonomy——仅当下游稳定时降级 WARN。
    """
    repeats = [_load_e_repeat(vid, rep) for rep in range(1, REPEATS + 1)]
    tags_list = [r["tags"] for r in repeats]
    openings = [t["opening_type"].get("label") for t in tags_list]
    expectations = [t["user_expectation"].get("label") for t in tags_list]
    primaries = [_primary_labels(t) for t in tags_list]

    # ---- semantic E2E MRD ----
    e2e_mrd_units: set[int] = set()
    mrd_signals: list[str] = []
    v21b_judge = _judged(RUN_ROOT / "recalculation", f"{vid}-v21b-route.json",
                         _JUDGE_V21B_ROUTE, _V21B_BOOL_FIELDS,
                         [f"【repeat-{i} V2.1b 输出】\n{_intent_summary(r['intent'])}"
                          for i, r in enumerate(repeats, 1)], api)
    v23_judge = _judged(RUN_ROOT / "recalculation", f"{vid}-v23-gate.json",
                        _JUDGE_V23_GATE, _V23_BOOL_FIELDS,
                        [f"【repeat-{i} V2.3 输出摘要】\n{_copy_summary(r['copy'])}"
                         for i, r in enumerate(repeats, 1)], api)
    if v21b_judge.get("judge_failed"):
        e2e_mrd_units.update((1, 2, 3))
        mrd_signals.append("V2.1b route judge 失败（工程异常）")
    else:
        if not v21b_judge.get("primary_driver_same_route"):
            e2e_mrd_units.update((1, 2, 3))
            mrd_signals.append("V2.1b Primary Driver 换轨（E2E MRD）")
        if not v21b_judge.get("question_same_type"):
            e2e_mrd_units.update((1, 2, 3))
            mrd_signals.append("V2.1b Unresolved Question 换类（E2E MRD）")
    if v23_judge.get("judge_failed"):
        e2e_mrd_units.update((1, 2, 3))
        mrd_signals.append("V2.3 gate judge 失败（工程异常）")
    else:
        for i in (1, 2, 3):
            if not v23_judge.get(f"same_answer_class_repeat{i}"):
                e2e_mrd_units.add(i)
                mrd_signals.append(f"V2.3 same answer class=false（repeat-{i}，E2E MRD）")
        if not v23_judge.get("intent_continuity"):
            e2e_mrd_units.update((1, 2, 3))
            mrd_signals.append("V2.3 intent continuity=false（页面核心回答方向改变）")

    # ---- structural hard fail（unit 级） ----
    structural_units: list[int] = []
    structural_detail = []
    for rep, r in enumerate(repeats, 1):
        output = r["copy"]
        schema_errors = mms.validate_schema(output)
        slot_errors = mms.validate_slot_contract(output, t1c, t2c)
        compliance_errors = mms.validate_compliance(output, banned_dict)
        trace_errors = mms.validate_grounding_trace(output)
        member_errors = mms.validate_used_anchors_membership(output)
        gs = output.get("product_grounding_pack", {}).get("grounding_status")
        safety_fail = gs not in (None, "sufficient", "partial")
        hard = bool(schema_errors or slot_errors or compliance_errors
                    or trace_errors or member_errors or safety_fail)
        if hard:
            structural_units.append(rep)
        structural_detail.append({
            "repeat": rep,
            "schema_errors": schema_errors,
            "slot_contract_errors": slot_errors,
            "compliance_errors": compliance_errors,
            "grounding_trace_errors": trace_errors,
            "used_anchors_membership_errors": member_errors,
            "grounding_status": gs,
            "grounding_safety_fail": safety_fail,
            "hard_fail": hard,
        })

    # ---- intermediate drift（observability，§10） ----
    downstream_stable = not e2e_mrd_units
    intermediate: dict = {
        "opening_drift": len(set(openings)) > 1,
        "opening_labels": openings,
        "expectation_drift": len(set(expectations)) > 1,
        "expectation_labels": expectations,
        "primary_drift": len({frozenset(p) for p in primaries}) > 1,
        "primaries": primaries,
    }
    obs_warns: list[str] = []
    if intermediate["opening_drift"]:
        obs_warns.append(f"Intermediate Opening Drift（{openings}）")
    if intermediate["expectation_drift"]:
        obs_warns.append(f"Intermediate Expectation Drift（{expectations}）")
    if intermediate["primary_drift"]:
        obs_warns.append("Intermediate Primary Tag Set Drift")
    anchor_density = (not v23_judge.get("judge_failed")
                      and not v23_judge.get("anchor_preserved"))
    if anchor_density:
        obs_warns.append("Anchor Density Drift（V2.3 锚颗粒度变化）")
    supporting = (not v21b_judge.get("judge_failed")
                  and not v21b_judge.get("supporting_only_secondary", True))
    if supporting:
        obs_warns.append("Supporting Drift（V2.1b supporting 超次级）")
    if vid == "v09":
        obs_warns.append("Taxonomy Disagreement（低门槛领取型 backlog）")

    # ---- per-unit / creative 判定（新 Gate） ----
    # blocking = e2e_mrd_units ∪ structural_units
    blocking = e2e_mrd_units | set(structural_units)
    runs = [{"repeat": rep,
             "status": "FAIL" if rep in blocking else
                       ("WARN" if (obs_warns or not downstream_stable) else "PASS")}
            for rep in (1, 2, 3)]
    if blocking:
        status = "UNSTABLE"
    elif obs_warns:
        status = "STABLE_WITH_WARN"
    else:
        status = "STABLE"

    e_eval = json.loads((E_ROOT / "evaluation" / f"{vid}.json").read_text(encoding="utf-8"))
    return {
        "creative_id": vid,
        "new_gate": {
            "status": status,
            "runs": runs,
            "semantic_mrd_units": sorted(e2e_mrd_units),
            "structural_hard_fail_units": structural_units,
            "mrd_signals": mrd_signals,
            "intermediate_drift": intermediate,
            "downstream_stable": downstream_stable,
            "observability_warns": obs_warns,
            "v2.1b_route_consistency": "3/3" if (
                v21b_judge.get("primary_driver_same_route")
                and v21b_judge.get("question_same_type")) else "0/3",
            "v2.3_same_answer_class": sum(
                1 for i in (1, 2, 3) if v23_judge.get(f"same_answer_class_repeat{i}")),
        },
        "structural_detail": structural_detail,
        "original_v2_5_e": {
            "status": e_eval.get("status"),
            "material_route_drift_units": e_eval.get("material_route_drift_units"),
            "fail_signals": e_eval.get("fail_signals"),
        },
        "v21b_route_judge": v21b_judge,
        "v23_gate_judge": v23_judge,
    }


def recalc_all() -> dict:
    tcfg = _load_text_config()
    api = ApiClient(model=tcfg["model"], api_base=tcfg["api_base"],
                    api_key=tcfg["api_key"])
    kb_norm = _norm(Path(KB_PATH).read_text(encoding="utf-8"))
    t1c, t2c = load_slot_contract(T1_PROMPT), load_slot_contract(T2_PROMPT)
    banned_dict = mms.load_compliance_lists()

    per_creative = {}
    semantic_mrd_units = 0
    structural_units = 0
    obs_counts = {k: 0 for k in ("opening_type_drift", "primary_tag_drift",
                                 "expectation_drift", "anchor_density_drift",
                                 "supporting_drift", "taxonomy_disagreement")}
    cl = {"STABLE": 0, "STABLE_WITH_WARN": 0, "UNSTABLE": 0}
    for vid in SAMPLES:
        result = recalc_sample(vid, api, kb_norm, t1c, t2c, banned_dict)
        per_creative[vid] = result
        (RUN_ROOT / "recalculation").mkdir(parents=True, exist_ok=True)
        (RUN_ROOT / "recalculation" / f"{vid}.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        ng = result["new_gate"]
        semantic_mrd_units += len(ng["semantic_mrd_units"])
        structural_units += len(ng["structural_hard_fail_units"])
        cl[ng["status"]] += 1
        inter = ng["intermediate_drift"]
        obs_counts["opening_type_drift"] += REPEATS if inter["opening_drift"] else 0
        obs_counts["primary_tag_drift"] += REPEATS if inter["primary_drift"] else 0
        obs_counts["expectation_drift"] += REPEATS if inter["expectation_drift"] else 0
        obs_counts["anchor_density_drift"] += REPEATS if any(
            "Anchor Density" in w for w in ng["observability_warns"]) else 0
        obs_counts["supporting_drift"] += REPEATS if any(
            "Supporting" in w for w in ng["observability_warns"]) else 0
        obs_counts["taxonomy_disagreement"] += REPEATS if any(
            "Taxonomy" in w for w in ng["observability_warns"]) else 0
        print(f"[f] {vid}: new={ng['status']} "
              f"semantic_mrd={ng['semantic_mrd_units']} "
              f"structural={ng['structural_hard_fail_units']} "
              f"(E 轮 {result['original_v2_5_e']['status']}, "
              f"mrd={result['original_v2_5_e']['material_route_drift_units']})", flush=True)

    n = len(SAMPLES) * REPEATS
    v21b_stable = sum(3 for r in per_creative.values()
                      if r["new_gate"]["v2.1b_route_consistency"] == "3/3")
    sac = sum(r["new_gate"]["v2.3_same_answer_class"] for r in per_creative.values())
    summary = {
        "run_id": RUN_ID,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "model": tcfg["model"], "temperature": 0,
        "unit_count": n,
        "semantic_gate": {
            "v2.1b_route_stable": f"{v21b_stable}/{n}",
            "v2.3_same_answer_class": f"{sac}/{n}",
            "e2e_material_route_drift": f"{semantic_mrd_units}/{n}",
        },
        "structural_gate": {
            "structural_hard_fail": f"{structural_units}/{n}",
            "e_round_structural_hard_fail": "1/30 (v04/rep1 grounding trace)",
        },
        "observability": {k: f"{v}/{n}" for k, v in obs_counts.items()},
        "creative_level": {"stable": cl["STABLE"],
                           "stable_with_warn": cl["STABLE_WITH_WARN"],
                           "unstable": cl["UNSTABLE"]},
        "samples": {vid: {
            "original_v2_5_e_status": r["original_v2_5_e"]["status"],
            "new_gate_status": r["new_gate"]["status"],
            "semantic_mrd_units": r["new_gate"]["semantic_mrd_units"],
            "structural_hard_fail_units": r["new_gate"]["structural_hard_fail_units"],
        } for vid, r in per_creative.items()},
    }
    (RUN_ROOT / "recalculation" / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[f] recalc: semantic MRD={semantic_mrd_units}/{n} "
          f"structural={structural_units}/{n}", flush=True)
    return summary


# --------------------------------------------------------------------------- #
def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--phase", choices=["all", "preflight", "regression", "recalc"],
                    default="all")
    args = ap.parse_args()

    traces_path = RUN_ROOT / "traces.json"
    traces: dict = {}
    if traces_path.is_file():
        try:
            traces = json.loads(traces_path.read_text(encoding="utf-8"))
        except Exception:
            traces = {}
    RUN_ROOT.mkdir(parents=True, exist_ok=True)

    if args.phase in ("all", "preflight", "regression", "recalc"):
        if "preflight" not in traces:
            traces["preflight"] = preflight()
    if args.phase in ("all", "regression"):
        run_v04_regression(traces)
        traces["v04_regression_eval"] = evaluate_v04_regression(traces)
    if args.phase in ("all", "recalc"):
        traces["recalc"] = recalc_all()

    traces["updated_at"] = datetime.now(timezone.utc).isoformat()
    traces_path.write_text(json.dumps(traces, ensure_ascii=False, indent=2),
                           encoding="utf-8")
    print("[f] done", flush=True)


if __name__ == "__main__":
    main()
