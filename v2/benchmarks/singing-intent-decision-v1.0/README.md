# Singing Intent Decision Benchmark v1.0（V2.1b Seed Benchmark）

- 上游输入：V2.1a 输出的 `creative_tags.json`（冻结 run：`output/benchmark-runs/v2.1a-val-phase2`，qwen3.7-plus E2E，10/10 完成）
- GT：10 条人工判定的 Primary Driver / Unresolved Question / Intent Strength，权威版本为 `docs/benchmarks/singing-intent-decision-benchmark-v1.0.md`；`manifest.json` 中的 GT 逐字对齐该文档（单一事实来源，勿单独修改）
- 验收 Gate（首轮）：
  - A. Primary Driver Semantic Match ≥ 8/10（核心点击因果一致，非字符串匹配）
  - B. Unresolved Question Semantic Match ≥ 8/10（继续原广告问题、真正未解决、无无依据新问题）
  - C. Primary Uniqueness 10/10（schema 硬校验）
  - D. Evidence Grounding 10/10（schema 硬校验）
  - Intent Strength / Supporting Drivers：首版仅观察，不设 Exact Match Gate
- 语义判定：LLM judge（与被测同 provider）对照 GT 做语义比对；`primary_match` / `question_match` 必须为原生 JSON boolean（字符串/数字/缺字段均非法，有限次重试后记 judge_failed，绝不静默转换）；唯一性与证据接地来自 `creative_intent_v1` schema 校验
- 运行：

```bash
python -m v2.benchmarks.run_intent_benchmark \
  --tags-root output/benchmark-runs/v2.1a-val-phase2 \
  --run-id intent-b2
# 报告：output/benchmark-runs/<run-id>/report.{json,md}
# 断点续跑：每样本决策落盘 creative_intent.json，judge 裁决按 statement 缓存复用
```

规则：第一版真实结果如实汇报，不为跑分调参、不做 benchmark-specific hardcode。
