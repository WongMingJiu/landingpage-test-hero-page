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
- 底部价格说明固定文案：**此价格为5天体验/试学课价格，具体收费以实际课程信息为准**（不得回退为"7 天"历史口径）。
