#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""A. Recognition vs Salience diagnostic for a benchmark run.

For each sample v01–v10 and each expected Primary label:
  - does it exist in matched_value_tags at all?          (recognition)
  - if yes, what salience/strength did it get?           (ranking)
  - classification: MISSING (recognition failure)
                  | DEMOTED (present-but-supporting => salience failure)
                  | OK      (present as primary)
Plus the reverse direction: wrongly promoted Primary labels
(predicted primary not in GT primary), classified as
  PROMOTED_MATCHED (present in GT supporting => over-promotion)
  PROMOTED_NOVEL   (not in GT active at all).

Usage:
  python -m v2.benchmarks.diagnose_salience <run_dir>
e.g. python -m v2.benchmarks.diagnose_salience output/benchmark-runs/v2.1a-final
"""
from __future__ import annotations

import json
import os
import sys

from .run_benchmark import load_manifest


def diagnose(run_dir: str, manifest_path: str | None = None) -> dict:
    manifest = load_manifest(manifest_path) if manifest_path else load_manifest()
    rows: list[dict] = []
    for item in manifest["items"]:
        vid = item["id"]
        exp = item["expected"]
        tags_path = os.path.join(run_dir, vid, "run0", "v2", "creative_tags.json")
        row = {"id": vid, "expected_primary": exp["active_primary"],
               "expected_supporting": exp["active_supporting"],
               "missing": False, "per_label": [], "promoted_wrong": [],
               "predicted_primary": [], "predicted_active": []}
        if not os.path.isfile(tags_path):
            row["missing"] = True
            rows.append(row)
            continue
        with open(tags_path, "r", encoding="utf-8") as f:
            actual = json.load(f)
        matched = {m["label"]: m for m in actual.get("matched_value_tags", [])}
        active = set(actual.get("active_value_tags", []))
        sal = {m["label"]: m.get("salience") for m in actual.get("matched_value_tags", [])}
        exp_primary = exp["active_primary"]
        exp_supporting = exp["active_supporting"]
        pred_primary = [a for a in actual.get("active_value_tags", []) if sal.get(a) == "primary"]
        row["predicted_primary"] = pred_primary
        row["predicted_active"] = actual.get("active_value_tags", [])

        # forward: each expected primary label
        for lab in exp_primary:
            if lab not in matched:
                cls = "MISSING"          # tag recognition failure
                detail = "not in matched_value_tags"
            elif lab not in active:
                cls = "DEMOTE_INACTIVE"  # recognized, dropped before active
                detail = f"matched({matched[lab].get('evidence_strength')}) but not active"
            elif sal.get(lab) != "primary":
                cls = "DEMOTED"          # salience ranking failure
                detail = f"active as {sal.get(lab)} ({matched[lab].get('evidence_strength')})"
            else:
                cls = "OK"
                detail = f"primary ({matched[lab].get('evidence_strength')})"
            row["per_label"].append({"label": lab, "class": cls, "detail": detail})

        # reverse: predicted primary labels not in GT primary
        for lab in pred_primary:
            if lab in exp_primary:
                continue
            if lab in exp_supporting:
                cls = "PROMOTED_MATCHED"  # GT supporting over-promoted
            elif lab in matched:
                cls = "PROMOTED_NOVEL"    # matched but GT kept it out of active
            else:
                cls = "PROMOTED_NOVEL_UNMATCHED"
            row["promoted_wrong"].append({"label": lab, "class": cls})
        rows.append(row)
    return {"run_dir": run_dir, "rows": rows}


def render_md(diag: dict) -> str:
    lines = ["# A. Recognition vs Salience Diagnostic", "",
             f"- run: `{diag['run_dir']}`", "",
             "## Expected Primary: recognition vs ranking", "",
             "| id | expected primary | status | detail |",
             "|---|---|---|---|"]
    for r in diag["rows"]:
        if r["missing"]:
            lines.append(f"| {r['id']} | {'、'.join(r['expected_primary'])} | NO_OUTPUT | run missing |")
            continue
        for pl in r["per_label"]:
            lines.append(f"| {r['id']} | {pl['label']} | {pl['class']} | {pl['detail']} |")
    lines += ["", "## Wrongly promoted Primary (predicted primary not in GT primary)", "",
              "| id | predicted primary (wrong) | class | predicted primary set |",
              "|---|---|---|---|"]
    for r in diag["rows"]:
        if r["missing"]:
            continue
        if not r["promoted_wrong"]:
            lines.append(f"| {r['id']} | - | - | {'、'.join(r['predicted_primary']) or '-'} |")
        for pw in r["promoted_wrong"]:
            lines.append(f"| {r['id']} | {pw['label']} | {pw['class']} | "
                         f"{'、'.join(r['predicted_primary'])} |")
    # summary counts
    cnt = {"OK": 0, "MISSING": 0, "DEMOTED": 0, "DEMOTE_INACTIVE": 0}
    for r in diag["rows"]:
        for pl in r["per_label"]:
            cnt[pl["class"]] = cnt.get(pl["class"], 0) + 1
    n_rec_fail = cnt["MISSING"]
    n_sal_fail = cnt["DEMOTED"] + cnt["DEMOTE_INACTIVE"]
    lines += ["", "## Summary", "",
              f"- expected-primary labels checked: {sum(cnt.values())}",
              f"- Tag Recognition failures (MISSING): {n_rec_fail}",
              f"- Salience Ranking failures (DEMOTED/DEMOTE_INACTIVE): {n_sal_fail}",
              f"- OK: {cnt['OK']}", ""]
    return "\n".join(lines)


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    diag = diagnose(sys.argv[1])
    out = os.path.join(sys.argv[1], "salience_diagnostic.md")
    md = render_md(diag)
    with open(out, "w", encoding="utf-8") as f:
        f.write(md)
    with open(os.path.join(sys.argv[1], "salience_diagnostic.json"), "w", encoding="utf-8") as f:
        json.dump(diag, f, ensure_ascii=False, indent=2)
    print(md)
    print(f"\nwritten: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
