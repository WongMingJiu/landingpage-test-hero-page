# T1 Hero Template Test Fixtures

## 用途

本目录存放 T1（问题 / 方法 / 四利益卡承接型）Hero 模板的**已验证测试文案 fixtures**，配合 [v2/prompts/hero_template_t1.md](../../prompts/hero_template_t1.md)（Canonical Runtime Prompt）与 [docs/templates/singing-hero-template-t1-contract-v1.1.md](../../../docs/templates/singing-hero-template-t1-contract-v1.1.md)（Contract，当前版本 V1.1）使用：

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

V2.3 生产输出 `t1_hero_slots_v1` 仅包含 12 个动态 Slot；`fixture_id` / `intent_type` 仅存在于测试 fixture wrapper，不进入 Runtime Prompt 或生产 payload。本目录的 fixtures 即该结构的首批样例。

## 字数预算

所有 slot values 必须符合 T1 Contract 的字数预算（见 prompt 文件头部的 Slot 契约 JSON）：

- `headline_line_1/2`：优先 ≤6 汉字，最多 7；
- `subheadline` ≤16；`benefit_n_title` ≤5；`benefit_n_desc` ≤11；`bottom_banner_text` ≤15。

超预算时先重写文案，不得交给图片模型自行解决。

## 当前固定信息（不属于动态 slots，任何 fixture / 生产 slots 均不得改写）

- 老师：**宋伶俐**（本阶段不可替换，不换老师形象）；
- 产品：**5 天身体唱歌体验营**（不允许带入 28 天正式营内容）；
- 价格信息：**无**（V1.1 起 Hero 画面不展示任何价格徽章 / 价格说明 / 优惠信息，也不得由 Runtime 自行生成；V1.0 时代的「1 元」徽章与 5 天价格免责声明已随 V1.1 移除，历史口径见 Contract V1.0）。

## Replay 记录

### t1-replay-1（2026-09-01，T1 V1.0 时代记录，保留备查）

> 注：本次 replay 基于 V1.0 Runtime Prompt + V1.0 原始 reference（含 1 元徽章与价格说明）。V1.1 已移除价格信息并生成新 reference（`v2/templates/hero_template_t1/reference_v1.1.png`）；V1.1 的 replay 验证见下节 t1-replay-v1.1-1。

- **输入**：`v2/prompts/hero_template_t1.md`（提取 BEGIN/END RUNTIME PROMPT 正文 + 12 个 `{{slot}}` 占位符替换，fixture 元数据不进入 prompt）+ 原始 T1 reference image（“模板 1.png”，即底部仍为“7 天”历史口径的来源图）；
- **模型**：gpt-image-2 @ `/v1/images/edits`，size 1024x1536，每 fixture 各 1 次；
- **结果**：**3/3 成功**（t1_a 47.8s / t1_b 52.9s / t1_c 3601.9s，后者含一次代理断连重试）；
- **验证结论**（逐张人工核验）：
  - 12 个 slot 文案均逐字正确渲染，包括 slots_a 本轮修订的 `headline_line_1 = "5天入门"`；
  - 模板结构完整保持：顶部 Logo、右侧宋伶俐人物与竖排姓名条、右下 1 元价格徽章、左侧 4 个利益卡（圆形音乐图标 + 标题 + 说明）、底部金色横幅、红橙暖色背景与音乐装饰；
  - **底部价格说明三张均为 5 天版本原文**（参考图上的“7 天”历史口径被正确覆盖）；
  - 未出现 28 天正式营、新模块、新人物、CTA 按钮等越界内容；
- **输出留存**：`output/t1-replay/t1_{a,b,c}.png` + `replay_log.json`（output/ 不进 git，本地留存）。

### t1-replay-v1.1-1（2026-09-08，T1 V1.1 冻结验证，3/3 PASS）

- **输入**：`v2/prompts/hero_template_t1.md`（V1.1 Runtime Prompt，提取 BEGIN/END 正文 + 12 个 `{{slot}}` 占位符替换）+ T1 V1.1 Reference（`v2/templates/hero_template_t1/reference_v1.1.png`）+ 本目录 A/B/C fixtures（12-slot payload 原文，未改动）；
- **模型**：gpt-image-2 @ `/v1/images/edits`，size 1024x1536；每个 fixture 基于同一 V1.1 Reference **独立生成**（无 A→B→C 连续迭代）；
- **结果**：**3/3 成功**（t1_a 58.6s / t1_b 55.6s / t1_c 56.2s）；
- **验证结论**（逐张人工核验）：
  - 12 个 slot 文案均逐字正确渲染，无漏字 / 错字 / 串 Slot；
  - Bottom Banner 完整宽度横贯底部，文字视觉居中平衡，未重新生成右下独立圆形 Badge；
  - 画面无「1元」、无任何价格 / 价格免责声明 / 优惠 / 折扣 / Offer 元素；
  - 模板保真：顶部 Logo、两行大标题、副标题、左侧 4 利益卡与圆形音乐图标、宋伶俐人物、右侧竖排姓名条、红橙暖色背景完整保持，无新增人物 / CTA / 模块；
  - 产品边界：仅 5 天身体唱歌体验营，无 28 天正式营等越界信息；
- **结论**：T1 V1.1 满足冻结条件，Contract V1.1 状态已更新为 **Frozen / Template Stability Pass**；
- **输出留存**：`output/t1-replay-v1.1/t1_{a,b,c}.png` + `replay_log.json`（output/ 不进 git，本地留存）。
