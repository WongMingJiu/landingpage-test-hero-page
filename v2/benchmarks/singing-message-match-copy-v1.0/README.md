# Singing Message Match Copy Benchmark v1.0（V2.3｜Prompt V1.2 已冻结 2026-09-09）

- 上游输入（仅实际输出，human GT 不进入生成）：
  - V2.1a：`output/benchmark-runs/v2.1a-val-phase2/{vXX}/run0/v2/creative_tags.json`（冻结 E2E run，10/10）；
  - V2.1b：`output/benchmark-runs/intent-b2/{vXX}/creative_intent.json`（canonical benchmark run，4/4 gates PASS）。
- Product Truth：`docs/knowledge/singing-5day-experience-camp-kb-v1.0.md`（知识库全文内联进生成 prompt）。
- 模板：Frozen T1 Contract v1.1（12 slots）+ Frozen T2 Contract v1.0（8 slots）；slot 字数契约直接从
  `v2/prompts/hero_template_t1.md` / `hero_template_t2.md` 的「Slot 契约（机器可读）」JSON 块解析，不在代码中另造一份。
- 生成：每个 creative 一次 LLM 调用完成 Step A（Creative Anchors）→ Step B（Product Grounding Pack）→
  Step C（T1 + T2 独立并行生成）；输出 `message_match_copy_v1`。
- 评价维度：
  - A. Schema Validity（程序化，20 units）
  - B. Slot Contract（程序化，字数/必填，20 units）
  - C. Compliance / Scope（程序化，banned_words_common + KB §9 边界，20 units）
  - D. Grounding Trace（程序化 + KB 回指 bigram 覆盖率，20 units）
  - E. Anchor Preservation（Semantic Judge，T1/T2 各 10）
  - F. Intent Continuity（Semantic Judge，T1/T2 各 10）
  - G. Template Differentiation（Semantic Judge，10）
  - H. Copy Quality（观察字段，不作为自动优化触发器）
- First-run Discipline：Build Once → Run Once → Record As-Is → 人工评审。语义失败禁止重试；
  engineering retry（API/JSON parse）有界并逐条记录。
- 运行：

```bash
python -m v2.benchmarks.run_message_match_copy_benchmark \
  --tags-root output/benchmark-runs/v2.1a-val-phase2 \
  --intent-root output/benchmark-runs/intent-b2 \
  --run-id v2.3-message-match-copy-first-pass
# 每条产出 vXX/{input.json, output.json, evaluation.json}；总览 summary.json
# dry-run（不调 API）：加 --dry-run
```

规则：第一轮结果如实记录，不为跑分自动调 Prompt / Schema / Retrieval / GT / Contract。

## Round 2（2026-09-09）

第一轮结果：`output/benchmark-runs/v2.3-message-match-copy-first-pass/report.md`。第二轮修复
仅动 V2.3 生成层与评价器（Frozen 资产零改动）：

- 生成 prompt V1.1：T1 benefit_title ≤5 字显式反例（禁 6 字双三字词）；T2 防同质化
  （headline_line_1 必须心理视角、方法语义须绑定老师/跟练、≥2 个 badge 含学习支持语义）；
  slot 单行纯文字（T2 badge 的 2+2 是下游渲染形态，JSON 输出连续 ≤4 汉字）；「告别」
  中性化约束（KB §13）；phrases 高画面感直用指引；输出前逐 slot 自检字数。
- 检查器：`validate_compliance` 补 KB §13 中性化词（告别）；`validate_slot_contract`
  将 slot 值内换行符升级为契约违规（fixtures 惯例：纯文字）。
- Runner：新增 T1/T2 headline bigram-Jaccard 相似度预警（≥0.60 记
  `differentiation_risk`，观察不 gate——G 维度仍由 judge 裁决）。
- 第二轮运行：`--run-id v2.3-message-match-copy-second-pass`（对照第一轮 As-Is 结果）。

## Round 3（2026-09-09）

第二轮结果：TD/Intent 修复，但 T2 anchor_preservation 退化至 6/10（「心理视角」规则被模型
执行成泛化顾虑「怕学不会/怕方法太难」，丢具体锚点）且 T1 subheadline/desc 超字 10 处
（注意力集中到 benefit_title 后其他槽位松弛）。第三轮 prompt V1.2：

- T2 `headline_line_1` 改为「**心理视角 + 当前广告最具体 Anchor 话题**」合成式要求，
  禁用泛化顾虑替代锚点（✗「怕学不会？」✓「怕卡喉学不会」）；`headline_line_2` 要求
  结合 Anchor 变体，不退化千篇一律「跟着老师练」；
- T1 subheadline ≤16 / benefit_desc ≤11 显式反例（✗ 17 字→✓ 13 字）。
- 第三轮运行：`--run-id v2.3-message-match-copy-third-pass`，**全维度 20/20、40/40 绿**
 （唯二 engineering 事件：v01 网关 timeout 内部重试、v03 JSON parse 重试 1 次，均成功）。

## Freeze（2026-09-09）

Prompt **V1.2 冻结**为 V2.3 当前生产版本（`v2/prompts/message_match_copy.md`，manifest
`status: frozen`）。Round 3 全维度绿：程序化 80/80（A-D）、语义 40/40（E/F/G）、
headline 相似度预警 0、review.needed 0/10；人工抽查（v03/v06/v10）文案质量与 Anchor 锚定俱佳。

- 冻结后 prompt 不再随意改动；后续修订须走新一轮 benchmark 验证并提升版本号。
- Frozen 资产（V2.1a/V2.1b、T1/T2 Contract/Prompt/Fixtures、KB、GT、config）三轮全程零改动。
- 次级观察（不阻塞）：bottom_banner“5天/五天”数字写法不一致；个别 T2 headline 语感稍口语化
  ——属文案语感层，可留待真实投放 A/B 验证。
