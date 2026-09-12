"""V2.5-D 合成逻辑快速单测（不调 API）。"""
import sys

sys.path.insert(0, ".")
from v2.benchmarks.run_opening_stability import hard_checks, repeat_consistency, synthesize_d


def tags(opening, primary, expectation="x", window=30):
    return {"opening_type": {"label": opening},
            "user_expectation": {"label": expectation},
            "decision_window": {"used_seconds": window, "extended": False},
            "matched_value_tags": [{"label": p, "salience": "primary"} for p in primary]}


# ---- hard_checks ----
assert hard_checks("v03", "演唱效果型", tags("演唱效果型", ["获得可复制学习范例"])) == []
assert hard_checks("v03", "演唱效果型", tags("学员故事证明型", ["获得可复制学习范例"])) != []
assert hard_checks("v04", "学员故事证明型",
                   tags("学员故事证明型", ["获得可复制学习范例"])) == []
# v04 primary 无可复制范例 -> fail
assert hard_checks("v04", "学员故事证明型",
                   tags("学员故事证明型", ["获得专业指导"])) != []
# v04 唯一 primary 为承接类 -> fail
assert hard_checks("v04", "学员故事证明型",
                   tags("学员故事证明型", ["把握限时稀缺机会"])) != []
# v06 核心丢失 -> fail
assert hard_checks("v06", "教学演示型", tags("教学演示型", ["理解发声原理"])) != []
assert hard_checks("v06", "教学演示型",
                   tags("教学演示型", ["正确发声并保护嗓音"])) == []

# ---- repeat_consistency ----
t1 = tags("演唱效果型", ["获得可复制学习范例", "获得演唱效果参照"])
t2 = tags("演唱效果型", ["获得可复制学习范例"])
t3 = tags("演唱效果型", ["获得可复制学习范例"])
c = repeat_consistency([t1, t2, t3])
assert c["opening_all_same"] is True
assert c["expectation_all_same"] is True
assert c["primary_core_stable"] is True  # 交集非空
assert c["primary_sets_identical"] is False  # 次级槽轮换
t_drift = tags("学员故事证明型", ["获得课程与学习资源"])
c2 = repeat_consistency([t1, t_drift, t2])
assert c2["opening_all_same"] is False
assert c2["primary_core_stable"] is False  # t1 vs t_drift 完全替换

# ---- synthesize_d ----
def judge_v21b(same=True, q=True, sup_sec=True):
    return {"primary_driver_same_route": same, "question_same_type": q,
            "supporting_only_secondary": sup_sec, "differences": [],
            "notes": ""}


def judge_v23(sac=(True, True, True), anchor=True, intent=True, diff=True):
    j = {"anchor_preserved": anchor, "intent_continuity": intent,
         "template_differentiation": diff,
         "differences": ["x"], "notes": ""}
    for i, v in enumerate(sac, 1):
        j[f"same_answer_class_repeat{i}"] = v
    return j


cons_ok = repeat_consistency([tags("学员故事证明型", ["获得可复制学习范例"]),
                              tags("学员故事证明型", ["获得可复制学习范例"]),
                              tags("学员故事证明型", ["获得可复制学习范例"])])
oj = [{"later_override_attempt": False} for _ in range(3)]

# 全稳 + 无次级变化 -> PASS
v = synthesize_d("v04", "学员故事证明型", cons_ok, [], oj, judge_v21b(), judge_v23())
assert v["status"] == "PASS", v
# 次级 primary 槽轮换 -> WARN
cons_sec = repeat_consistency([t1, t2, t3])
v = synthesize_d("v03", "演唱效果型", cons_sec, [], oj, judge_v21b(), judge_v23())
assert v["status"] == "WARN", v
# opening 换型 -> FAIL
v = synthesize_d("v03", "演唱效果型", c2, [], oj, judge_v21b(), judge_v23())
assert v["status"] == "FAIL", v
# V2.1b 换轨 -> FAIL
v = synthesize_d("v04", "学员故事证明型", cons_ok, [],
                 oj, judge_v21b(same=False), judge_v23())
assert v["status"] == "FAIL", v
# V2.3 sac 单次 fail -> FAIL
v = synthesize_d("v04", "学员故事证明型", cons_ok, [],
                 oj, judge_v21b(), judge_v23(sac=(True, False, True)))
assert v["status"] == "FAIL", v
# hard check fail -> FAIL
v = synthesize_d("v04", "学员故事证明型", cons_ok,
                 ["rep1: §16: v04 primary 无 获得可复制学习范例"],
                 oj, judge_v21b(), judge_v23())
assert v["status"] == "FAIL", v
# expectation 换类 -> FAIL
t_e1 = tags("演唱效果型", ["获得可复制学习范例"], expectation="复制学员成功路径")
t_e2 = tags("演唱效果型", ["获得可复制学习范例"], expectation="获得演唱效果")
cons_e = repeat_consistency([t_e1, t_e2, t_e1])
v = synthesize_d("v03", "演唱效果型", cons_e, [], oj, judge_v21b(), judge_v23())
assert v["status"] == "FAIL", v
# later_override_attempt 信号 -> WARN（核心仍稳）
oj_warn = [{"later_override_attempt": True}] * 3
v = synthesize_d("v04", "学员故事证明型", cons_ok, [], oj_warn,
                 judge_v21b(), judge_v23())
assert v["status"] == "WARN", v
print("all synthesis tests passed")
