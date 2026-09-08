# T2 Hero Template Test Fixtures

> 状态：**占位（Placeholder）**——A/B/C 文案尚未设计，当前仅有 Schema 与空 fixture 文件。

## T2 定位

T2 是**老师 / 结果 / 低门槛承接型** Hero 模板，承接用户点击广告后的核心问题：

- 这个课程适合我吗？
- 这个老师值得信任吗？
- 我是否可以开始学习？

## T2 与 T1 的区别

| | T1 | T2 |
|---|---|---|
| 说服链路 | 问题 → 方法 → Benefit | 老师 → 适配 → 开始 |
| 用户心理 | "我的问题怎么办？" | "这个课程适合我吗？" |
| Dynamic Slots | 12 个（`t1_hero_slots_v1`） | 8 个（`t2_hero_slots_v1`） |
| Contract | `singing-hero-template-t1-contract-v1.1.md`（Frozen） | `singing-hero-template-t2-contract-v1.0.md`（Draft） |

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

A/B/C 三组 fixture 将用于（文案设计完成后）：

- 验证 prompt 的 8 个 `{{slot}}` 占位符替换链路正确；
- 验证不同 intent 类型的文案在固定模板下的渲染稳定性（结构 / 色系 / 人物不漂移）；
- 作为 T2 模板资产的回归基线。

**这些 fixtures 仅用于模板稳定性验证，不代表正式线上文案库。**

## 当前固定信息（不属于动态 slots，任何 fixture / 生产 slots 均不得改写）

- 老师：**宋伶俐**（本阶段不可替换，不换老师形象）；
- 产品：**5 天身体唱歌体验营**（不允许带入 28 天正式营内容）；
- 左侧胶囊 Badge：**零基础可学**；
- 定位语行：**专为中老年人设计的唱歌训练法**；
- 价格信息：**无**（T2 price = disabled，不展示任何价格 / 优惠 / Offer / 价格免责声明，也不得由 Runtime 自行生成）。

## Replay Validation 流程（冻结前置条件，与 T1 同模式）

1. Reference Image 定稿入库（`v2/templates/hero_template_t2/reference_v1.0.png`，当前 pending）；
2. 设计 A/B/C 三组 fixture 文案（Contract §5 字数预算内，覆盖不同 intent 类型）；
3. 提取 `hero_template_t2.md` 的 BEGIN/END RUNTIME PROMPT 正文，替换 8 个占位符；
4. 每个 fixture 基于**同一定稿 Reference** 独立生成（禁止 A→B→C 连续迭代）；
5. 按 Contract §10 标准逐张人工核验；
6. 3/3 PASS 后 Contract V1.0 转为 **Frozen**，本 README 补录 replay 记录。

## Replay 记录

（暂无——T2 Replay Validation 未执行）
