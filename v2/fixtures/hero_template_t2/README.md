# T2 Hero Template Test Fixtures

> 状态：**已验证（Validated）**——A/B/C 文案已设计，Replay Validation **3/3 PASS**（2026-09-08/09）；T2 Contract V1.0 已转 **Frozen**（2026-09-09）。

## T2 定位

T2 是**老师 / 适配 / 低门槛承接型** Hero 模板，承接用户点击广告后的核心问题：

- 这个课程适合我吗？
- 这个老师值得信任吗？
- 我是否可以开始学习？

## T2 与 T1 的区别

| | T1 | T2 |
|---|---|---|
| 说服链路 | 问题 → 方法 → Benefit | 老师 → 适配 → 开始 |
| 用户心理 | "我的问题怎么办？" | "这个课程适合我吗？" |
| Dynamic Slots | 12 个（`t1_hero_slots_v1`） | 8 个（`t2_hero_slots_v1`） |
| Contract | `singing-hero-template-t1-contract-v1.1.md`（Frozen） | `singing-hero-template-t2-contract-v1.0.md`（Frozen 2026-09-09） |

## Dynamic Slot Schema（8 个）

```json
{
  "headline_line_1": "",
  "headline_line_2": "",
  "badge_right": "",
  "benefit_badge_1": "",
  "benefit_badge_2": "",
  "benefit_badge_3": "",
  "benefit_badge_4": "",
  "bottom_banner_text": ""
}
```

字数预算与语义职责见 [T2 Contract](../../../docs/templates/singing-hero-template-t2-contract-v1.0.md) §5 / §6；Runtime Prompt 见 [v2/prompts/hero_template_t2.md](../../prompts/hero_template_t2.md)。

## 与生产链路的关系

V2.3 生产输出 `t2_hero_slots_v1` 仅包含上述 8 个动态 Slot；`fixture_id` / `intent_type` 仅存在于测试 fixture wrapper，**不进入 Runtime Prompt 或生产 payload**。本目录的 fixtures 即该结构的占位样例。

## Fixture 用途

A/B/C 三组 fixture 已用于（2026-09-08/09 Replay Validation，3/3 PASS）：

- 验证 prompt 的 8 个 `{{slot}}` 占位符替换链路正确；
- 验证不同 intent 类型的文案在固定模板下的渲染稳定性（结构 / 色系 / 人物不漂移）；
- 作为 T2 模板资产的回归基线。

**这些 fixtures 仅用于模板稳定性验证，不代表正式线上文案库。**

## 当前固定信息（不属于动态 slots，任何 fixture / 生产 slots 均不得改写）

- 老师：**宋伶俐**（本阶段不可替换，不换老师形象）；
- 产品：**5 天身体唱歌体验营**（不允许带入 28 天正式营内容）；
- 左侧胶囊 Badge：**零基础可学**；
- 定位语行：**专为中老年人设计的唱歌训练法**；
- 价格信息：**无动态价格 / 优惠 / 折扣 / Offer**（T2 price = disabled；媒体或平台强制要求展示的合规免责声明属于固定 Compliance Layer，允许保留）。

## Replay Validation 流程（冻结前置条件，与 T1 同模式——已全部完成，2026-09-09 冻结）

1. ✅ Reference Image 定稿入库（`v2/templates/hero_template_t2/reference_v1.0.png`，1024x1728，2026-09-08）；
2. ✅ A/B/C 三组 fixture 文案设计（Contract §5 字数预算内，覆盖 trust_confirmation / beginner_anxiety / guided_learning 三种 intent）；
3. ✅ 提取 `hero_template_t2.md` 的 BEGIN/END RUNTIME PROMPT 正文，替换 8 个占位符（dry-run 校验 8 值全部注入）；
4. ✅ 每个 fixture 基于**同一定稿 Reference** 独立生成（无 A→B→C 连续迭代）；
5. ✅ 按 Contract §10 标准逐张人工核验（ROI 放大 + banner 几何量化）；
6. ✅ 3/3 PASS——T2 Contract V1.0 已于 2026-09-09 转 **Frozen**。

## Replay 记录

### t2-replay-fixture-a（2026-09-08，trust_confirmation，PASS ×2）

- **输入**：`v2/prompts/hero_template_t2.md`（提取 BEGIN/END RUNTIME PROMPT 正文 + 8 个 `{{slot}}` 占位符替换）+ `v2/templates/hero_template_t2/reference_v1.0.png` + `slots_a.json`（t2_a / trust_confirmation）；
- **模型**：gpt-image-2 @ `/v1/images/edits`；
- **Run #1**（旧 reference 1024x1727）：size=1024x1727 被 400 拒绝（宽高须 16 倍数，工程发现）→ auto 成功（88.6s，966x1629），**PASS**；
- **Run #2**（reference 重定 1024x1728 + 「零」字对齐修复后复验）：size=1024x1728 一次成功（84.5s，输出与 reference 同尺寸），**PASS**（以此为准，run_id: t2-replay-fixture-a-2）；
- **验证结论**（ROI 放大逐字核验）：8 slot 逐字正确（主标题「更」字高倍确认）、双胶囊（零基础可学 + 老师带练）、2×2 benefit（老师指导/循序教学/基础练习/轻松跟学）、Teacher Identity、合规边界全部保持；banner 几何 6.9%→6.2% H（reference 7.2%，重绘正常波动）；
- **输出留存**：`output/t2-replay-fixture-a/t2_a.png` + `replay_log.json`。

### t2-replay-fixture-b（2026-09-09，beginner_anxiety，PASS）

- **输入**：同上 + `slots_b.json`（t2_b / beginner_anxiety）；
- **模型**：gpt-image-2 @ `/v1/images/edits`；
- **size 链**：1024x1728 三次被网关 500 拒绝（"multipart file upload" 临时故障，与既往成功记录矛盾，判定网关侧异常，已如实记录）→ **auto fallback 成功**（65.9s，966x1629）；
- **验证结论**：8 slot 逐字正确（主标题「简」字高倍确认）、badge_right「中老年友好」5 字完整渲染、四枚 benefit 2×2（简单入门/有人带练/开口练习/动作好学）、Message Match 完整覆盖 User State 三点、合规通过；banner 几何 6.9% H；
- **输出留存**：`output/t2-replay-fixture-b/t2_b.png` + `replay_log.json`（run_id: t2-replay-fixture-b-1）。

### t2-replay-fixture-c（2026-09-09，guided_learning，PASS）

- **输入**：同上 + `slots_c.json`（t2_c / guided_learning）；
- **模型**：gpt-image-2 @ `/v1/images/edits`；
- **size**：1024x1728 一次成功（45.8s，网关故障已恢复，输出与 reference 同尺寸）；
- **验证结论**：8 slot 逐字正确、四枚 benefit 2×2（老师指导/跟练打卡/作业反馈/点评答疑）顺时针金箭头循环、banner「- 宋老师5天带你跟着练 -」（5天黄色）、Teacher Metadata 保持、Message Match 完整（自己练怕错→跟着老师练转折 + 过程支持四环节）；banner 几何 6.8% H；
- **输出留存**：`output/t2-replay-fixture-c/t2_c.png` + `replay_log.json`（run_id: t2-replay-fixture-c-1）。
