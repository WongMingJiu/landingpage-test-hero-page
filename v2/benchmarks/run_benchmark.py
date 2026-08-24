#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V2.1a Seed Benchmark runner + evaluator.

Ground Truth (SoT): docs/benchmarks/singing-creative-tagging-benchmark-v1.0.md
Machine-readable manifest: v2/benchmarks/singing-creative-tagging-v1.0/manifest.json
Local videos (gitignored): benchmarks-local/singing-creative-tagging-v1.0/videos/*.mp4

Acceptance (benchmark §5 / spec §13):
  JSON parseable 10/10; labels in taxonomy 100%; Opening >=9/10 (v02/v10 use
  acceptable_alternatives + human review); Expectation >=9/10; Decision Window
  no false extend 10/10; Primary Active core semantics >=8/10; Evidence 100%;
  stability 3 runs.

Note: GT v08/v09 active sets exceed the §6.4 per-category caps (informational,
recorded in manifest known_gt_notes). The pipeline enforces caps on OUTPUT, so
supporting tags may legitimately differ from GT; acceptance focuses on primary
core semantics + opening/expectation/window, not exact active-set match.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from typing import Any

from .. import taxonomy
from .. import schema
from ..tagging import TaggingConfig, TaggingPipeline

_MANIFEST = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                         "singing-creative-tagging-v1.0", "manifest.json")


def load_manifest(path: str = _MANIFEST) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def evaluate_sample(actual: dict | None, expected: dict, tax: taxonomy.TaxonomyData,
                    audio_enabled: bool = False) -> dict:
    """Pure comparison of one pipeline output vs GT. Testable without API."""
    res: dict[str, Any] = {
        "id": expected.get("id"),
        "skipped": actual is None,
        "parse_error": None,
        "schema_errors": [],
        "decision_window_ok": False,
        "opening_ok": False,
        "opening_actual": None,
        "opening_expected": expected["opening_type"],
        "opening_alternatives": expected.get("opening_acceptable_alternatives", []),
        "expectation_ok": False,
        "expectation_actual": None,
        "expectation_expected": expected["user_expectation"],
        "primary_exact": False,
        "primary_core_match": "wrong",
        "primary_actual": [],
        "primary_expected": expected.get("active_primary", []),
        "primary_missing": [],
        "primary_extra": [],
        "supporting_actual": [],
        "supporting_expected": expected.get("active_supporting", []),
        "supporting_overlap": [],
        "evidence_present": False,
        "confidence_actual": None,
        "confidence_expected": expected.get("confidence"),
        "core_pass": False,
    }
    if actual is None:
        return res

    # schema validation
    errs = schema.validate(actual, tax, audio_enabled=audio_enabled)
    res["schema_errors"] = errs

    # decision window (hard: extended=false, used=30)
    dw = actual.get("decision_window", {})
    res["decision_window_ok"] = (dw.get("used_seconds") == 30 and dw.get("extended") is False)

    # opening
    ot = actual.get("opening_type", {})
    res["opening_actual"] = ot.get("label")
    exp_op = expected["opening_type"]
    alts = expected.get("opening_acceptable_alternatives", [])
    res["opening_ok"] = res["opening_actual"] == exp_op or res["opening_actual"] in alts

    # expectation
    ue = actual.get("user_expectation", {})
    res["expectation_actual"] = ue.get("label")
    res["expectation_ok"] = res["expectation_actual"] == expected["user_expectation"]

    # active tags — derive primary/supporting from matched salience
    matched = {m.get("label"): m.get("salience") for m in actual.get("matched_value_tags", [])}
    active = actual.get("active_value_tags", [])
    res["primary_actual"] = [a for a in active if matched.get(a) == "primary"]
    res["supporting_actual"] = [a for a in active if matched.get(a) == "supporting"]
    exp_primary = set(expected.get("active_primary", []))
    act_primary = set(res["primary_actual"])
    res["primary_missing"] = sorted(exp_primary - act_primary)
    res["primary_extra"] = sorted(act_primary - exp_primary)
    res["primary_exact"] = (exp_primary == act_primary)
    overlap = exp_primary & act_primary
    if res["primary_exact"]:
        res["primary_core_match"] = "exact"
    elif overlap:
        res["primary_core_match"] = "partial"
    else:
        res["primary_core_match"] = "wrong"
    res["supporting_overlap"] = sorted(set(res["supporting_actual"]) & set(res["supporting_expected"]))

    # evidence present on every formal tag
    ev_ok = True
    for m in actual.get("matched_value_tags", []):
        if not m.get("evidence"):
            ev_ok = False
            break
    if not ot.get("evidence") or not ue.get("evidence"):
        ev_ok = False
    res["evidence_present"] = ev_ok
    res["confidence_actual"] = ot.get("confidence")

    # Core pass uses the acceptance-intent metric: at least partial Primary
    # semantic overlap. Strict primary_exact remains reported separately.
    res["core_pass"] = (not errs and res["decision_window_ok"] and res["opening_ok"]
                        and res["expectation_ok"]
                        and res["primary_core_match"] in ("exact", "partial")
                        and res["evidence_present"])
    return res


def _run_one(pipe: TaggingPipeline, video: str, cid: str, out_dir: str) -> dict | None:
    try:
        return pipe.run(video, cid, out_dir)
    except Exception as e:
        print(f"[bench] {cid}: FAILED ({e})", file=sys.stderr)
        return None

def _existing_valid_output(out_dir: str, tax: taxonomy.TaxonomyData,
                           audio_enabled: bool) -> dict | None:
    """Return a previously written creative_tags.json only if it is schema-valid."""
    path = os.path.join(out_dir, "creative_tags.json")
    if not os.path.isfile(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return None
    if schema.validate(data, tax, audio_enabled=audio_enabled):
        return None
    return data


def run_benchmark(videos_dir: str, runs: int = 1, manifest_path: str = _MANIFEST,
                  run_id: str | None = None, only: list[str] | None = None,
                  resume: bool = False) -> dict:
    manifest = load_manifest(manifest_path)
    tax = taxonomy.load_taxonomy("singing")
    cfg = TaggingConfig.from_env()

    items = manifest["items"]
    if only:
        wanted = set(only)
        items = [it for it in items if it["id"] in wanted]

    run_id = run_id or f"run-{int(time.time())}"
    out_root = os.path.join("output", "benchmark-runs", run_id)
    os.makedirs(out_root, exist_ok=True)
    pipe: TaggingPipeline | None = None

    def get_pipe() -> TaggingPipeline:
        nonlocal pipe
        if pipe is None:
            if not (cfg.api_base and cfg.api_key and cfg.model):
                raise SystemExit("missing API config (API_BASE_URL/API_KEY/MODEL_NAME or V2_ overrides)")
            pipe = TaggingPipeline(cfg, tax)
        return pipe

    missing: list[str] = []
    per_sample: list[dict] = []
    stability: dict[str, list[dict]] = {}

    for item in items:
        vid = item["id"]
        vpath = os.path.join(videos_dir, item["video"])
        if not os.path.isfile(vpath):
            missing.append(vid)
            per_sample.append(evaluate_sample(None, {"id": vid, **item["expected"]}, tax, cfg.audio_enabled))
            continue
        runs_res: list[dict] = []
        for r in range(runs):
            od = os.path.join(out_root, vid, f"run{r}", "v2")
            actual = None
            resumed = False
            if resume:
                cached = _existing_valid_output(od, tax, cfg.audio_enabled)
                if cached is not None:
                    actual, resumed = cached, True
            if not resumed:
                actual = _run_one(get_pipe(), vpath, vid, od)
            rr = evaluate_sample(actual, {"id": vid, **item["expected"]}, tax, cfg.audio_enabled)
            rr["run"] = r
            rr["resumed"] = resumed
            runs_res.append(rr)
        stability[vid] = runs_res
        per_sample.append(runs_res[-1])  # representative = last run

    # aggregate
    n = len(per_sample)
    n_run = sum(1 for r in per_sample if not r["skipped"])
    def cnt(pred): return sum(1 for r in per_sample if pred(r))
    agg = {
        "run_id": run_id, "videos_dir": videos_dir, "runs": runs,
        "only": only, "resume": resume,
        "total_samples": n, "ran": n_run, "missing": missing,
        "json_parseable": cnt(lambda r: not r["skipped"] and not r["parse_error"] and not r["schema_errors"]),
        "schema_valid": cnt(lambda r: not r["skipped"] and not r["schema_errors"]),
        "decision_window_ok": cnt(lambda r: r["decision_window_ok"]),
        "opening_ok": cnt(lambda r: r["opening_ok"]),
        "expectation_ok": cnt(lambda r: r["expectation_ok"]),
        "primary_exact": cnt(lambda r: r["primary_exact"]),
        "primary_core_exact": cnt(lambda r: r["primary_core_match"] == "exact"),
        "primary_core_partial": cnt(lambda r: r["primary_core_match"] == "partial"),
        "primary_core_wrong": cnt(lambda r: r["primary_core_match"] == "wrong"),
        "primary_core_aligned": cnt(lambda r: r["primary_core_match"] in ("exact", "partial")),
        "evidence_present": cnt(lambda r: r["evidence_present"]),
        "core_pass": cnt(lambda r: r["core_pass"]),
        "acceptance_targets": {
            "json_parseable_10_10": n,
            "labels_in_taxonomy_100pct": n,
            "opening_ge_9_10": 9,
            "expectation_ge_9_10": 9,
            "decision_window_10_10": n,
            "primary_core_ge_8_10": 8,
            "evidence_100pct": n,
        },
        "samples": per_sample,
        "stability_detail": {k: [{"run": x["run"], "opening": x["opening_actual"],
                                  "expectation": x["expectation_actual"],
                                  "primary": x["primary_actual"]} for x in v] for k, v in stability.items()},
    }
    with open(os.path.join(out_root, "report.json"), "w", encoding="utf-8") as f:
        json.dump(agg, f, ensure_ascii=False, indent=2)
    _write_md(agg, os.path.join(out_root, "report.md"))
    return agg


def _write_md(agg: dict, path: str) -> None:
    lines = [f"# V2.1a Seed Benchmark Report — {agg['run_id']}", "",
             f"- videos_dir: `{agg['videos_dir']}`", f"- runs per sample: {agg['runs']}",
             f"- ran: {agg['ran']}/{agg['total_samples']}",
             f"- missing: {agg['missing'] or 'none'}", "",
             "## Aggregate (last run as representative)", "",
             "| metric | actual | target |", "|---|---:|---:|"]
    mp = {"json_parseable": "JSON parseable", "schema_valid": "schema valid",
          "decision_window_ok": "Decision Window (no false extend)",
          "opening_ok": "Opening Type", "expectation_ok": "User Expectation",
          "primary_exact": "Primary Active exact",
          "primary_core_aligned": "Primary core match (exact+partial)",
          "evidence_present": "Evidence present", "core_pass": "core_pass (proxy)"}
    t = agg["acceptance_targets"]
    def tgt(k): return {"json_parseable": t["json_parseable_10_10"], "schema_valid": "-",
                        "decision_window_ok": t["decision_window_10_10"], "opening_ok": f">={t['opening_ge_9_10']}",
                        "expectation_ok": f">={t['expectation_ge_9_10']}", "primary_exact": "diagnostic",
                        "primary_core_aligned": f">={t['primary_core_ge_8_10']}",
                        "evidence_present": t["evidence_100pct"], "core_pass": "-"}[k]
    for k, label in mp.items():
        lines.append(f"| {label} | {agg[k]}/{agg['ran'] or agg['total_samples']} | {tgt(k)} |")
    lines += ["", "## Per-sample", "",
              "| id | window | opening (exp) | expectation (exp) | primary exact | primary core | schema |",
              "|---|---|---|---|---|---|---|"]
    for r in agg["samples"]:
        lines.append(f"| {r['id']} | {'OK' if r['decision_window_ok'] else 'X'} | "
                     f"{r['opening_actual']} ({r['opening_expected']}) | "
                     f"{r['expectation_actual']} ({r['expectation_expected']}) | "
                     f"{'Y' if r['primary_exact'] else 'N'} | {r['primary_core_match']} | "
                     f"{'OK' if not r['schema_errors'] else 'X'} |")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def main() -> int:
    ap = argparse.ArgumentParser(prog="v2.benchmarks.run_benchmark")
    ap.add_argument("--videos-dir", default="benchmarks-local/singing-creative-tagging-v1.0/videos")
    ap.add_argument("--runs", type=int, default=1, help="runs per sample (3 for stability)")
    ap.add_argument("--run-id", default=None)
    ap.add_argument("--only", default=None,
                    help="comma-separated sample ids to run (e.g. v03,v07)")
    ap.add_argument("--resume", action="store_true",
                    help="reuse existing schema-valid outputs instead of re-running them")
    args = ap.parse_args()
    only = [s.strip() for s in args.only.split(",")] if args.only else None
    agg = run_benchmark(args.videos_dir, runs=args.runs, run_id=args.run_id,
                        only=only, resume=args.resume)
    print(f"\n========== Benchmark {agg['run_id']} ==========")
    print(f"ran {agg['ran']}/{agg['total_samples']} (missing: {agg['missing']})")
    print(f"window OK: {agg['decision_window_ok']}  opening OK: {agg['opening_ok']}  "
          f"exp OK: {agg['expectation_ok']}  primary exact: {agg['primary_exact']}  "
          f"primary core aligned: {agg['primary_core_aligned']}  core_pass: {agg['core_pass']}")
    print(f"report: output/benchmark-runs/{agg['run_id']}/report.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
