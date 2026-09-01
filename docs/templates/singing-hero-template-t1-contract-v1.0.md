# Singing Hero Template T1 Contract V1.0

> 状态：**Frozen / Template Stability Pass**
>
> 适用品类：唱歌
>
> 产品范围：**5 天身体唱歌体验营 Only**
>
> 模板定位：**T1 — 问题 / 方法 / 四利益卡承接型**
>
> 下游用途：V2.2 Hero Strategy、V2.3 Skeleton-aware Copy、gpt-image-2 固定模板文案替换

---

# 0. 目标与冻结结论

T1 的目标不是让模型重新设计 Hero，而是：

> **以已验证的 Control Hero 为固定视觉骨架，只允许替换有限文案 Slot，在尽量不改变设计与排版的前提下完成 Message Match。**

T1 已完成人工稳定性验证：

- 综合发声改善类文案可稳定承载；
- 零基础 / 中老年低门槛类文案可稳定承载；
- 高音 / 挤嗓等具体问题类文案可稳定承载；
- 同一类文案重复生成时，核心结构保持稳定；
- 老师人物、Logo、四利益卡、价格徽章、底部横幅、红橙综合色系整体保持稳定。

因此 T1 从本版本开始冻结为稳定模板资产。后续除真实线上问题外，不继续为了个别样本调整版式、色板或结构。

---

# 1. 模板核心定位

T1 是一个强问题承接 / 方法解释型 Hero Skeleton。

它最擅长承载：

- 高音上不去；
- 喉咙用力 / 挤嗓 / 卡嗓；
- 气息不足 / 气息不稳；
- 大白嗓；
- 发声位置不对；
- 身体发声 / 身体通道 / 气息等具体方法；
- 教学演示、方法教学、机制揭秘；
- 用户点击后希望继续知道“具体怎么练”的 Creative Intent。

但在当前 Dual-Template Exploration 阶段，T1 **并不限制只能用于以上 Intent**。同一素材仍会与 T2 同时生成，用于探索模板路由规律。

---

# 2. Hard Product Scope

本模板所有业务内容必须服从：

`docs/knowledge/singing-5day-experience-camp-kb-v1.0.md`

Hard Rule：

> **只允许使用 5 天身体唱歌体验营 Product Truth。**

禁止引入：

- 28 天正式营；
- 21 天课程；
- 正式营价格体系；
- 正式营礼盒 / 麦克风 / 音箱；
- 正式营三师服务；
- 正式营 1V9；
- 正式营永久回放；
- 正式营四周课程体系；
- 其他仅在正式营中成立的产品承诺。

---

# 3. Canonical Visual Skeleton

## 3.1 整体结构

T1 固定为竖版唱歌课程营销 Hero，视觉结构如下：

```text
顶部品牌 Logo
        ↓
两行超大主标题
        ↓
一行副标题 / 定位语
        ↓
左：4 个纵向利益卡      右：宋伶俐老师大幅人物
        ↓
底部大型横向价值 Banner
        ↓
右下 1 元价格徽章 + 底部价格说明
```

## 3.2 固定模块

必须保留：

1. 兴趣岛 / 兴趣学堂 Logo 区；
2. 两行超大主标题区域；
3. 单行副标题区域；
4. 左侧 4 个利益点卡片；
5. 每个卡片的圆形音乐类图标；
6. 右侧宋伶俐老师人物；
7. 右侧竖排姓名“宋伶俐”；
8. 底部大型价值 Banner；
9. 右下“1 元”价格徽章；
10. 底部价格说明；
11. 红橙暖色渐变、音乐元素、金色高光等背景气质。

不得增删模块，不得因动态文案重新安排整体布局。

---

# 4. 三类字段：Visual Locked / Business Locked / Dynamic

## 4.1 Visual Locked

以下视觉元素固定：

- 整体画布比例；
- 整体排版；
- Logo 位置与比例；
- 主标题区域位置；
- 副标题区域位置；
- 4 个利益卡位置、尺寸、数量与间距；
- 4 个圆形图标的位置与数量；
- 宋老师人物位置、服装、发型、饰品、姿态与大致占比；
- 右侧姓名条位置；
- Banner 几何结构；
- 价格徽章位置与几何结构；
- 背景综合色系与主要音乐装饰。

当前 Phase 2 **不替换老师形象**。

老师图片更换属于后续 Visual Match 变量，不进入 T1 当前 Message Match 实验。

## 4.2 Business Locked

以下业务事实固定，不允许 V2.2 / V2.3 动态改写：

- Teacher：`宋伶俐`；
- Product Scope：`5 天身体唱歌体验营`；
- Price Badge：`1 元`；
- 底部价格说明固定为：

> **此价格为5天体验/试学课价格，具体收费以实际课程信息为准**

特别说明：旧 Control 图中的“7 天体验/试学课”属于历史口径，从 T1 V1.0 起一律纠正为 5 天。

## 4.3 Dynamic Copy Slots

唯一允许个性化变化：

```text
headline_line_1
headline_line_2
subheadline
benefit_1_title
benefit_1_desc
benefit_2_title
benefit_2_desc
benefit_3_title
benefit_3_desc
benefit_4_title
benefit_4_desc
bottom_banner_text
```

除以上字段外，模型不得自行创建新文案区域。

---

# 5. Slot Contract

| Slot | 语义职责 | 硬字符预算 | 行数 |
|---|---|---:|---:|
| `headline_line_1` | 承接 Primary Driver / 核心问题或价值 | ≤ 6 汉字为优先，最多 7 | 1 |
| `headline_line_2` | 推进到方法 / 结果方向 | ≤ 6 汉字为优先，最多 7 | 1 |
| `subheadline` | 回答或推进 Unresolved Question | ≤ 16 汉字 | 1 |
| `benefit_n_title` | 具体利益 / 方法 / 降阻点 | ≤ 5 汉字 | 1 |
| `benefit_n_desc` | 对标题做具体解释 | ≤ 11 汉字 | 1 为优先 |
| `bottom_banner_text` | 收束 Hero，并保留课程 / 老师 / 5 天学习入口 | ≤ 15 汉字 | 1 |

## 5.1 字数处理原则

如果文案超过容量：

1. **先重写文案**；
2. 其次轻微压缩字距；
3. 最后才允许轻微缩字号；
4. 不允许通过改变模块、增加行数或重排版来容纳文案。

V2.3 应负责生成满足字数预算的文案，不应把超长文案交给图片模型自行解决。

---

# 6. Message Strategy Rules

## 6.1 Headline

Headline 应承接广告点击动机，而不是写成通用课程名。

推荐结构：

```text
问题 / Barrier / 核心期待
+
方法方向 / 可学习方向 / 下一步信念
```

示例方向：

- `高音别硬喊 / 轻松找位置`
- `零基础也能 / 轻松开唱`
- `5天学会 / 轻松发声`

示例仅用于说明结构，不是固定文案库。

## 6.2 Subheadline

Subheadline 的职责不是重复 Headline，而是：

> **把广告已经建立的信念往前推进一步，回答最重要的 Unresolved Question。**

例如广告已经说“别只靠嗓子”，Hero 应继续回答“那应该从哪里开始练”，而不是再次复读“不要靠嗓子”。

## 6.3 Four Benefit Cards

4 个卡片必须围绕当前 Creative Intent 选择，而不是罗列整个课程。

建议结构：

- 2～3 个 Creative-specific Benefit / Method；
- 1～2 个 Sales Insurance / Learning Friction Reduction。

典型 Sales Insurance：

- 零基础友好；
- 有人带练；
- 中老年友好；
- 动作可跟练；
- 点评答疑。

Presence ≠ 必须使用。只选当前广告最相关、Hero 容量内最有价值的信息。

## 6.4 Bottom Banner

Bottom Banner 应承担“销售收束”，避免再次堆叠新问题。

优先表达：

- 宋老师；
- 5 天；
- 从基础开始 / 练对方法 / 轻松学习等行动前信念。

不得写成强按钮 CTA，不得使用“立即点击 / 马上领取 / 不买后悔”等表达。

---

# 7. Fixed Color Palette

颜色以 Canonical Reference Image 为视觉真值，以下色号作为辅助锁定值。

## Background

- 主红橙：`#F24A3A`
- 中间暖橙：`#F57A45`
- 浅橙高光：`#F6A05A`
- 浅杏橙：`#FFD4A6`

## Headline

- 浅金白：`#FFF0D8`
- 高光白：`#FFF8EE`
- 暖金描边：`#E8A15A`
- 暖棕金阴影：`#C97C3C`

## Subheadline

- 主橙红：`#F45A2A`
- 暖白：`#FFF8F0`

## Benefit Cards

- 图标主红：`#E53922`
- 图标深红：`#C92C1B`
- 卡片浅米：`#FFF1E5`
- 卡片浅金描边：`#F7C98A`
- 标题深暖红：`#C92C1B`
- 说明暖深棕：`#7A3323`

## Bottom Banner

- 主红：`#E3361E`
- 高光红橙：`#F25A2D`
- 白字：`#FFF8F0`
- 重点黄：`#FFD84A`

## Price Badge

- 主红：`#D92F1A`
- 亮红：`#F25A2D`
- 数字黄：`#FFD84A`
- 黄色高光：`#FFF09A`
- “元”暖白：`#FFF8F0`

## Decoration

- 暖白：`#FFF8F0`
- 浅金：`#F9D28B`
- 暖棕：`#A85D2A`

原则：参考图优先于色号的微小偏差；色号主要用于防止整体漂向冷色 / 紫色 / 灰色 / 深色风格。

---

# 8. Compliance & Copy Constraints

必须继承知识库中的合规规则。

禁止：

- 全国领先 / 全国第一；
- 第一 / 唯一 / 首席；
- 最好 / 最佳 / 最强；
- 顶级 / 顶尖；
- 万能；
- 保证 / 保证效果；
- 包教包会 / 包学会；
- 100%；
- 速成 / 立竿见影；
- 医疗治疗 / 疾病改善 / 抗衰 / 防病等健康疗效表达；
- 不买后悔 / 错过再无等恐惧诱导。

不得将课程“可教授的方法”改写成“用户一定获得的固定结果”。

---

# 9. gpt-image-2 Rendering Contract

## 9.1 Input

生产调用至少包含：

```text
layout_ref = T1 Canonical Reference Image
prompt_template = 本文第 9.2 节
slot_values = V2.3 输出的动态文案
```

当前阶段不传新的 `teacher_ref`；老师视觉固定使用 T1 Reference Image。

## 9.2 Canonical Prompt Template

```text
请基于我提供的参考图，对这张唱歌课程 Hero 海报进行“固定模板下的局部文案替换式重绘”。

这不是重新设计新海报。
参考图是本次任务的版式真值与视觉真值。

【核心目标】
在最大程度保持参考图的整体设计风格、版式结构、人物位置、模块数量、综合色系和营销氛围不变的前提下，只替换下方明确指定的动态文字 Slot。

【必须保持不变】
- 竖版比例；
- 顶部兴趣岛 / 兴趣学堂 Logo；
- 两行大标题所在区域；
- 单行副标题区域；
- 左侧 4 个利益卡片的位置、数量、尺寸和图标；
- 右侧宋伶俐老师人物，包括服装、发型、饰品、姿态、位置和大致占比；
- 右侧竖排“宋伶俐”；
- 底部大型横幅的几何结构；
- 右下“1元”价格徽章；
- 红橙暖色背景、音乐元素与金色高光；
- 底部价格说明区域。

【固定业务文字】
Teacher：宋伶俐
Price Badge：1元
底部价格说明：此价格为5天体验/试学课价格，具体收费以实际课程信息为准

【综合色号辅助约束】
背景：#F24A3A / #F57A45 / #F6A05A / #FFD4A6
主标题：#FFF0D8 / #FFF8EE / #E8A15A / #C97C3C
副标题：#F45A2A / #FFF8F0
利益卡：#E53922 / #C92C1B / #FFF1E5 / #F7C98A / #7A3323
底部横幅：#E3361E / #F25A2D / #FFF8F0 / #FFD84A
价格徽章：#D92F1A / #F25A2D / #FFD84A / #FFF09A

颜色以参考图为第一依据，色号用于防止整体视觉漂移。
禁止改成冷色、深色、科技风、极简风或完全不同的视觉设计。

【唯一允许变化的 Slot】
headline_line_1 = “{{headline_line_1}}”
headline_line_2 = “{{headline_line_2}}”
subheadline = “{{subheadline}}”

benefit_1_title = “{{benefit_1_title}}”
benefit_1_desc = “{{benefit_1_desc}}”
benefit_2_title = “{{benefit_2_title}}”
benefit_2_desc = “{{benefit_2_desc}}”
benefit_3_title = “{{benefit_3_title}}”
benefit_3_desc = “{{benefit_3_desc}}”
benefit_4_title = “{{benefit_4_title}}”
benefit_4_desc = “{{benefit_4_desc}}”

bottom_banner_text = “{{bottom_banner_text}}”

【排版硬约束】
- headline 必须保持两行，不新增第三行；
- headline 每行优先 ≤6 汉字，最多 7；
- subheadline ≤16 汉字；
- benefit title ≤5 汉字；
- benefit desc ≤11 汉字，一行为优先；
- bottom banner ≤15 汉字；
- 如果长度发生冲突，优先轻微缩小字号或字距，不改变模块和整体排版。

【业务边界】
这是 5 天身体唱歌体验营。
只能使用 5 天体验营真实可兑现的课程、方法、服务与价值。
禁止加入 28 天正式营、21 天班、正式营价格、礼盒、1V9、三师服务、永久回放或其他正式营内容。
不得虚构课程承诺、老师头衔、医疗健康效果。

【禁止设计行为】
不要重新设计海报；
不要换老师；
不要换老师服装或姿势；
不要增加或减少利益卡；
不要移动价格徽章；
不要换 Logo；
不要增加 CTA 按钮；
不要新增课程表、歌曲列表或新人物；
不要因新文案重新排版。

输出完整、高清、中文清晰可读的 Hero 成品。
最终效果必须明显属于“同一个固定模板，只更换了文案”，而不是参考原图重新设计的新海报。
```

---

# 10. Stability Acceptance Criteria

T1 后续生产结果至少满足：

## Structure

- Logo 保留；
- 两行大标题结构保留；
- 4 利益卡完整；
- 老师位置 / 大致比例稳定；
- 姓名条完整；
- Banner 完整；
- 1 元徽章完整。

## Copy

- 所有动态 Slot 文案准确；
- 无明显乱码 / 错字；
- 不明显溢出；
- 固定业务文案不得错误回退为“7 天”。

## Visual

- 红橙暖色气质稳定；
- 不发生明显版式重构；
- 不随机替换老师服装与姿态。

## Business

- 只使用 5 天体验营 Product Truth；
- 无正式营信息；
- 无明显违禁表达。

生产上允许同一 Slot Values 生成 2～3 个 Candidate，再依据结构保真度与文字质量选取最佳结果；这不改变 T1 Contract 本身。

---

# 11. Versioning Rules

T1 V1.0 Frozen 后：

允许：

- 修复明确的文字渲染问题；
- 修复产品口径错误；
- 修复合规问题；
- 在不改变结构的前提下优化 Prompt 对 Layout Lock 的稳定性。

不允许：

- 增删卡片；
- 改布局；
- 改综合色系；
- 改老师；
- 改 Offer 结构；
- 为个别 Creative Intent 增加专属模板结构。

如果必须发生以上变化，应建立 `T1 V2`，不得静默修改 Frozen V1.0。

---

# 12. Next Step

T1 冻结后立即进入：

> **T2 — 老师 / 结果 / 低门槛承接型 Template Stability Validation**

T2 完成同等级别的 Contract 与稳定性验证后，进入：

```text
每条 Seed Creative
        ↓
V2.2 Hero Strategy
        ↓
T1 Hero + T2 Hero
        ↓
Dual-Template Exploration
        ↓
离线 / 在线比较模板适配规律
```

当前阶段不提前创建自动 Template Selector；先通过真实双模板结果学习路由规律。
