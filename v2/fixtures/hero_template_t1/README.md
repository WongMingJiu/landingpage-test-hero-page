# T1 Hero Template Test Fixtures

## 用途

本目录存放 T1（问题 / 方法 / 四利益卡承接型）Hero 模板的**已验证测试文案 fixtures**，配合 [v2/prompts/hero_template_t1.md](../../prompts/hero_template_t1.md)（Canonical Runtime Prompt）与 [docs/templates/singing-hero-template-t1-contract-v1.0.md](../../../docs/templates/singing-hero-template-t1-contract-v1.0.md)（Contract）使用：

- 验证 prompt 的 12 个 `{{slot}}` 占位符替换链路正确；
- 验证不同 intent 类型的文案在固定模板下的渲染稳定性（结构 / 色系 / 人物不漂移）；
- 作为 T1 模板资产的回归基线。

**这些 fixtures 仅用于模板稳定性验证，不代表正式线上文案库。**

## A / B / C 测试意图

| Fixture | intent_type | 验证意图 |
|---|---|---|
| `slots_a.json`（t1_a） | 综合发声改善 | 泛改善型价值主张：不指向单一痛点，验证通用利益组合的承载稳定性 |
| `slots_b.json`（t1_b） | 零基础/中老年低门槛 | Barrier Reduction 型主张：年龄 / 基础门槛类文案的承载稳定性 |
| `slots_c.json`（t1_c） | 高音/挤嗓问题 | 具体问题型主张：指向明确发声痛点的文案承载稳定性 |

三组文案均已在 T1 Template Stability Validation 中人工验证通过，**不要继续"优化"这些文案**。

## 与生产链路的关系

生产链路中，**V2.3（Skeleton-aware Copy）将输出与本目录同结构的 slots**（`t1_hero_slots_v1`：12 个动态字段 + fixture_id / intent_type 元信息），走同一条 prompt 占位符替换链路。本目录的 fixtures 即该结构的首批样例。

## 字数预算

所有 slot values 必须符合 T1 Contract 的字数预算（见 prompt 文件头部的 Slot 契约 JSON）：

- `headline_line_1/2`：优先 ≤6 汉字，最多 7；
- `subheadline` ≤16；`benefit_n_title` ≤5；`benefit_n_desc` ≤11；`bottom_banner_text` ≤15。

超预算时先重写文案，不得交给图片模型自行解决。

## 当前固定信息（不属于动态 slots，任何 fixture / 生产 slots 均不得改写）

- 老师：**宋伶俐**（本阶段不可替换，不换老师形象）；
- 产品：**5 天身体唱歌体验营**（不允许带入 28 天正式营内容）；
- 价格徽章：**1 元**；
- 底部价格说明固定文案：**此价格为5天体验/试学课价格，具体收费以实际课程信息为准**（不得回退为“7 天”历史口径）。

## Replay 记录

### t1-replay-1（2026-09-01，slots_a 修订后）

- **输入**：`v2/prompts/hero_template_t1.md`（提取 BEGIN/END RUNTIME PROMPT 正文 + 12 个 `{{slot}}` 占位符替换，fixture 元数据不进入 prompt）+ 原始 T1 reference image（“模板 1.png”，即底部仍为“7 天”历史口径的来源图）；
- **模型**：gpt-image-2 @ `/v1/images/edits`，size 1024x1536，每 fixture 各 1 次；
- **结果**：**3/3 成功**（t1_a 47.8s / t1_b 52.9s / t1_c 3601.9s，后者含一次代理断连重试）；
- **验证结论**（逐张人工核验）：
  - 12 个 slot 文案均逐字正确渲染，包括 slots_a 本轮修订的 `headline_line_1 = "5天入门"`；
  - 模板结构完整保持：顶部 Logo、右侧宋伶俐人物与竖排姓名条、右下 1 元价格徽章、左侧 4 个利益卡（圆形音乐图标 + 标题 + 说明）、底部金色横幅、红橙暖色背景与音乐装饰；
  - **底部价格说明三张均为 5 天版本原文**（参考图上的“7 天”历史口径被正确覆盖）；
  - 未出现 28 天正式营、新模块、新人物、CTA 按钮等越界内容；
- **输出留存**：`output/t1-replay/t1_{a,b,c}.png` + `replay_log.json`（output/ 不进 git，本地留存）。
