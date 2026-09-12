"""B1 合成逻辑快速单测（不调 API，仅本地验证三态逻辑 + programmatic 信号）。"""
import json
import sys

sys.path.insert(0, ".")
from v2.benchmarks.run_semantic_calibration import programmatic_signals, synthesize_verdict

FIELDS = ["v2.1a_route_drift", "v2.1a_secondary_drift", "v2.1b_primary_route_drift",
          "v2.1b_question_route_drift", "v2.1b_secondary_drift",
          "v2.3_core_anchor_replaced", "cta_overrides_narrative"]


def j(**kw):
    d = {f: False for f in FIELDS}
    d["v2.3_same_answer_class"] = True
    d.update(kw)
    return d


for vid in ["v03", "v04", "v06"]:
    b = json.load(open(f"output/v2.5-same-model-replay/baseline/{vid}/v2.1a/creative_tags.json"))
    r = json.load(open(f"output/v2.5-same-model-replay/replay/{vid}/v2.1a/creative_tags.json"))
    p = programmatic_signals(b, r)
    print(vid, "opening_same=", p["opening_same"], "exp_same=", p["expectation_same"],
          "common=", p["primary_common"], "b-only=", p["primary_only_baseline"],
          "r-only=", p["primary_only_replay"], "full_repl=", p["primary_full_replacement"])

print()
print("PASS case:", synthesize_verdict(j(), {"primary_only_baseline": [], "primary_only_replay": []})["status"])
print("WARN v2.1b secondary:", synthesize_verdict(j(**{"v2.1b_secondary_drift": True}), {"primary_only_baseline": [], "primary_only_replay": []})["status"])
print("WARN v2.1a secondary:", synthesize_verdict(j(**{"v2.1a_secondary_drift": True}), {"primary_only_baseline": [], "primary_only_replay": []})["status"])
print("FAIL v2.1a route:", synthesize_verdict(j(**{"v2.1a_route_drift": True}), {})["status"])
print("FAIL same_answer_class=False:", synthesize_verdict(j(**{"v2.3_same_answer_class": False}), {})["status"])
print("FAIL anchor replaced:", synthesize_verdict(j(**{"v2.3_core_anchor_replaced": True}), {})["status"])
print("judge_failed 容错:", synthesize_verdict({"judge_failed": True}, {}).keys())
