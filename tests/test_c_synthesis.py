"""V2.5-C 合成逻辑快速单测（不调 API）。"""
import sys

sys.path.insert(0, ".")
from v2.benchmarks.run_narrative_calibration import hard_checks, synthesize_c


def nj(mech=True, misjudge=False, overreach=False, elig=None):
    return {"narrative_mechanism_correct": mech,
            "story_presentation_misjudged": misjudge,
            "course_bearing_overreach": overreach,
            "primary_eligibility": elig or [
                {"label": "获得可复制学习范例", "narrative_centrality": True,
                 "evidence_density": True, "persuasion_role": True,
                 "expectation_link": True, "eligible_for_primary": True}]}


def tags(opening, primary):
    return {"opening_type": {"label": opening}, "user_expectation": {"label": "x"},
            "matched_value_tags": [{"label": p, "salience": "primary"} for p in primary]}


# v04 硬检查：正确路径通过 / 剧情型+语义不认可 → fail / 唯一承接类 primary → fail
t_ok = tags("学员故事证明型", ["获得可复制学习范例"])
t_drift = tags("剧情/内容叙事型", ["获得课程与学习资源"])
assert hard_checks("v04", t_ok, nj()) == []
assert hard_checks("v04", t_drift, nj(mech=False)) != []
assert hard_checks("v04", tags("学员故事证明型", ["获得专业指导"]), nj()) != []

# v06：教学演示+核心在 → 过；核心丢 → fail
t6 = tags("教学演示型", ["正确发声并保护嗓音", "方法简单易操作"])
assert hard_checks("v06", t6, nj()) == []
assert hard_checks("v06", tags("教学演示型", ["理解发声原理"]), nj()) != []

# v09：低门槛 primary 在 → 过；误判故事型 → fail
t9 = tags("低门槛领取型", ["零基础可学"])
assert hard_checks("v09", t9, nj()) == []
assert hard_checks("v09", tags("剧情/内容叙事型", ["零基础可学"]), nj()) != []
assert hard_checks("v09", tags("低门槛领取型", ["获得课程与学习资源"]), nj()) != []

# 合成三态
def ev(nj_, hard=None, chain=None, gate=None, prog=None):
    return {"narrative_judge": nj_, "hard_check_fails": hard or [],
            "programmatic_vs_baseline": prog or {}, "chain_judge": chain or {},
            "gate_judge": gate or {}}


chain_ok = {f: False for f in ["v2.1a_route_drift", "v2.1a_secondary_drift",
                               "v2.1b_primary_route_drift", "v2.1b_question_route_drift",
                               "v2.1b_secondary_drift", "v2.3_core_anchor_replaced",
                               "cta_overrides_narrative"]}
chain_ok["v2.3_same_answer_class"] = True
gate_ok = {"anchor_preserved_t1": True, "anchor_preserved_t2": True,
           "intent_continuity_t1": True, "intent_continuity_t2": True,
           "template_differentiation": True, "same_answer_class": True}

assert synthesize_c("v04", "v04", ev(nj(), chain=chain_ok, gate=gate_ok))["status"] == "PASS"
assert synthesize_c("v04", "v04", ev(nj(), chain=dict(chain_ok, **{"v2.1a_secondary_drift": True}),
                                     gate=gate_ok))["status"] == "WARN"
assert synthesize_c("v04", "v04", ev(nj(mech=False), chain=chain_ok, gate=gate_ok))["status"] == "FAIL"
assert synthesize_c("v04", "v04", ev(nj(), chain=dict(chain_ok, **{"v2.1a_route_drift": True}),
                                     gate=gate_ok))["status"] == "FAIL"
assert synthesize_c("v04", "v04", ev(nj(), chain=chain_ok,
                                     gate=dict(gate_ok, same_answer_class=False)))["status"] == "FAIL"
assert synthesize_c("v04", "v04", ev(nj(), chain=chain_ok, gate=gate_ok,
                                     prog={"primary_full_replacement": True,
                                           "opening_same": False}))["status"] == "FAIL"
# v09 anchor false 降级为 WARN
assert synthesize_c("negative-sample", "v09",
                    ev(nj(), gate=dict(gate_ok, anchor_preserved_t1=False)))["status"] == "WARN"
print("all synthesis tests passed")
