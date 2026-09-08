# Singing Hero Template T2 Contract V1.0

> 状态：**Draft**（冻结前置条件：Reference Image 定稿入库 **✅ 已完成 2026-09-08** + A/B/C fixture 文案设计 + Replay Validation 3/3 PASS）
>
> 适用品类：唱歌
>
> 产品范围：**5 天身体唱歌体验营 Only**
>
> 模板定位：**T2 — 老师 / 适配 / 低门槛承接型**
>
> 下游用途：V2.2 Hero Strategy、V2.3 Skeleton-aware Copy、gpt-image-2 固定模板文案替换
>
> 工程模式：完全复用 T1 闭环（Contract → Runtime Prompt → Reference Image → Fixture → Replay Validation → Frozen）

---

# 0. 目标与当前状态

T2 的目标与 T1 一致：

> **以已验证的 Control Hero 为固定视觉骨架，只允许替换有限文案 Slot，在尽量不改变设计与排版的前提下完成 Message Match。**

当前状态 **Draft**，含义：

- 本 Contract 与 Runtime Prompt 已建立；
- Reference Image **已定稿入库**（`v2/templates/hero_template_t2/reference_v1.0.png`，2026-09-08 Reference Cleanup 完成，定稿记录见 `v2/templates/hero_template_t2/README.md`）；
- A/B/C fixture 文案**尚未设计**（当前仅有 schema 占位）；
- Replay Validation 未执行。

冻结条件（与 T1 同等级别）：

```text
Reference Image 定稿入库
        ↓
A/B/C fixture 文案设计（本 Contract §5 预算内）
        ↓
Replay Validation（每 fixture 独立生成）
        ↓
3/3 PASS → Frozen
```

---

# 1. 模板核心定位

T2 是一个**老师 / 适配 / 低门槛承接型** Hero Skeleton。

它承接用户点击广告后产生的核心问题：

- 这个课程适合我吗？
- 这个老师值得信任吗？
- 我是否可以开始学习？

T2 与 T1 的区别：

| | T1 | T2 |
|---|---|---|
| 说服链路 | 问题 → 方法 → Benefit | 老师 → 适配 → 开始 |
| 用户心理 | "我的问题怎么办？" | "这个课程适合我吗？" |
| 承接重心 | 痛点拆解、方法解释 | 老师背书、门槛消解、开始学习 |

在当前 Dual-Template Exploration 阶段，T2 **并不限制只能用于以上 Intent**。同一素材仍会与 T1 同时生成，用于探索模板路由规律。

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

**价格规则：T2 Hero 不承担价格展示职责（Price = disabled）。**

禁止：

- 动态价格；
- 优惠表达；
- 折扣表达；
- Offer Badge。

允许：

- 媒体或平台强制要求展示的合规免责声明。

说明：合规免责声明属于**固定 Compliance Layer**，不属于 Price Experiment Variable。

价格信息不进入 Dynamic Copy Slots。

---

# 3. Canonical Visual Skeleton

## 3.1 整体结构

T2 固定为竖版唱歌课程营销 Hero，视觉结构如下：

```text
顶部品牌栏（Logo + 品牌语 + 副标语）
        ↓
定位语行（固定文案）
        ↓
两行超大主标题
        ↓
左侧胶囊 Badge（固定「零基础可学」）+ 右侧胶囊 Badge（badge_right）
        ↓
左：四个圆形 Benefit Badge（2×2）      右：宋伶俐老师人物 + 竖排姓名条
        ↓
底部完整宽度 Bottom Banner（底部销售收束模块）
```

## 3.2 固定模块

必须保留：

1. 顶部品牌区域（Logo + 品牌语 + 副标语）；
2. 定位语行区域；
3. 两行超大主标题区域；
4. 左侧胶囊 Badge 与右侧胶囊 Badge（成对结构）；
5. 四个圆形 Benefit Badge（2×2 排列、数量与间距固定）；
6. 右侧宋伶俐老师人物；
7. 右侧竖排姓名条；
8. 底部完整宽度 Bottom Banner；
9. 米白暖色底 + 红色主视觉的整体背景气质。

不得增删模块，不得因动态文案重新安排整体布局。

---

# 4. 三类字段：Visual Locked / Business Locked / Dynamic

## 4.1 Visual Locked

以下视觉元素固定：

- 整体画布比例；
- 整体排版；
- 顶部品牌栏位置与构成；
- 定位语行位置；
- 主标题区域位置；
- 左右胶囊 Badge 的位置与成对结构；
- 四个圆形 Benefit Badge 的位置、尺寸、数量与 2×2 间距；
- 宋老师人物位置、服装、发型、饰品、姿态与大致占比；
- 右侧竖排姓名条位置；
- Bottom Banner 的完整宽度几何结构与居中平衡；
- 背景色系与主要装饰元素。

当前 Phase 2 **不替换老师形象**。

老师图片更换属于后续 Visual Match 变量，不进入 T2 当前 Message Match 实验。

## 4.2 Business Locked

以下业务事实固定，不允许 V2.2 / V2.3 动态改写：

- Teacher：`宋伶俐`；
- Product Scope：`5 天身体唱歌体验营`；
- Left Badge：`零基础可学`；
- 定位语行：`专为中老年人设计的唱歌训练法`；
- Price：`disabled`——不承担价格展示职责：禁止动态价格 / 优惠 / 折扣 / Offer Badge；媒体或平台强制要求展示的合规免责声明属于固定 Compliance Layer（见 §2 价格规则）。

候选 Reference 修正注记（Reference 定稿时必须处理）：

- 候选参考图（`模板 2.png`）上左侧胶囊为「0基础可学」，定稿时必须统一为 **`零基础可学`**；
- 候选参考图底部存在一行价格免责声明小字，属于**固定 Compliance Layer**（媒体 / 平台合规要求），Reference 定稿时按合规要求处理，不作为 Price Experiment Variable；
- 候选参考图竖排姓名条包含 Teacher Title 表述，该字段属于 **Teacher Identity Layer / Metadata**（见 §4.4），Reference 定稿时仅确认展示效果与业务要求，不修改 category config `title_pool` 与 Teacher Title 内容。

## 4.3 Dynamic Copy Slots

唯一允许个性化变化（共 8 个）：

```text
headline_line_1
headline_line_2
badge_right
benefit_badge_1
benefit_badge_2
benefit_badge_3
benefit_badge_4
bottom_banner_text
```

除以上字段外，模型不得自行创建新文案区域。

## Teacher Identity Layer

Teacher Name：`宋伶俐`

Teacher Title：由 `assets/categories/{category}/config.json` 中的 `title_pool` 提供（唱歌品类即 `assets/categories/singing/config.json`，当前为：`兴趣岛唱歌训练营首席讲师` / `身体唱歌法创始人`）。

规则：

- Teacher Title **不属于 Dynamic Copy Slots**；
- Teacher Title **不参与 Message Match Experiment**；
- Teacher Title **不由 LLM Copy Generation 生成**；
- Teacher Title **来源于 category config.json 的 `title_pool`**；
- Teacher Title **不应用 `banned_words_common.json` Copy Generation Filter**（该 Filter 仅作用于 §4.3 动态 Slot，见 `v2/compliance/banned_words_common.json`）。

Teacher Title 仅作为 Teacher Metadata 渲染；保留当前 category config 的 `title_pool` 机制——不修改 `title_pool` 内容，不修改 Teacher Title 内容。

---

# 5. Slot Contract

| Slot | 语义职责 | 硬字符预算 | 行数 |
|---|---|---:|---:|
| `headline_line_1` | 表达用户当前心理状态（顾虑 / 门槛） | ≤ 5 汉字为优先，最多 7 | 1 |
| `headline_line_2` | 推进到学习方向 / 目标 | ≤ 5 汉字为优先，最多 7 | 1 |
| `badge_right` | 第二层适配信号 | ≤ 5 汉字 | 1 |
| `benefit_badge_n` | 解释为什么用户可以开始学习 | ≤ 4 汉字（2+2 两行形态优先） | badge 内 ≤ 2 |
| `bottom_banner_text` | 产品收束：宋老师 + 5 天 + 学习方向 | ≤ 15 汉字 | 1 |

字数为 Draft 初版预算，基于候选 Reference 的视觉容量标定；Replay Validation 阶段可依据实际渲染结果校准，校准不改变 Slot 数量与语义职责。

## 5.1 字数处理原则

如果文案超过容量：

1. **先重写文案**；
2. 其次轻微压缩字距；
3. 最后才允许轻微缩字号；
4. 不允许通过改变模块、增加行数或重排版来容纳文案。

V2.3 应负责生成满足字数预算的文案，不应把超长文案交给图片模型自行解决。

---

# 6. Message Strategy Rules

## 6.1 Headline（headline_line_1 / headline_line_2）

职责：**表达用户当前心理状态**。

允许：

- 用户顾虑（没基础、年纪大、怕学不会）；
- 学习门槛（从哪里开始、能不能跟上）；
- 学习目标（开口唱、唱得轻松）。

禁止：

- 绝对结果承诺；
- 保证学会类表达。

推荐结构：

```text
顾虑 / 门槛承接
+
可开始的方向 / 下一步信念
```

示例方向（仅说明结构，不是固定文案库）：

- `没基础别怕 / 从简单练起`

## 6.2 badge_right

职责：**第二层适配信号**，与左侧固定 Badge「零基础可学」互补，进一步降低"不适合我"的顾虑。

示例方向：

- `中老年友好`
- `跟着老师练`

## 6.3 benefit_badge_1 ~ 4

职责：**解释为什么用户可以开始学习**。

允许：

- 学习方式（跟练、带练、点评）；
- 课程体验（简单、好学、轻松）；
- 方法特点（从基础开始、动作分解）。

禁止：

- 夸大效果；
- 结果保证。

四个 Badge 围绕当前 Creative Intent 选择，而不是罗列整个课程。

## 6.4 bottom_banner_text

职责：**产品收束**。

推荐结构：

```text
宋老师 + 5天 + 学习方向
```

示例方向：

- `宋老师5天带你轻松入门`

不得写成强按钮 CTA，不得使用"立即点击 / 马上领取 / 不买后悔"等表达。

---

# 7. Fixed Color Palette

颜色以 Canonical Reference Image 为视觉真值，以下色号作为辅助锁定值（基于候选 Reference 标定，Replay 阶段可校准）：

## Top Brand Bar

- 主红：`#E63329`
- 深红：`#D42B1E`
- 文字暖白：`#FFF8F0`

## Background

- 米白主底：`#FDF6EC`
- 暖杏过渡：`#FAF0DD`

## Headline

- 深红主色：`#C81623`
- 阴影暖棕：`#8C2F1B`

## 定位语行

- 深棕红：`#8C2F1B`

## Capsule Badges

- 左胶囊红：`#D42B1E`
- 右胶囊青绿：`#218C8C`
- 文字暖白：`#FFF8F0`

## Benefit Badges（圆形）

- 主红：`#D42B1E`
- 金色描边：`#F7C98A`
- 文字暖白：`#FFF8F0`

## Bottom Banner

- 主红：`#D42B1E`
- 白字：`#FFF8F0`
- 重点黄：`#FFD84A`

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
- 不买后悔 / 错过再无等恐惧诱导；
- 任何动态价格、优惠、折扣或 Offer 表达（媒体 / 平台强制要求展示的合规免责声明除外，见 §2 价格规则）。

不得将课程"可教授的方法"改写成"用户一定获得的固定结果"。

作用域说明：本节违禁表达约束作用于 **Copy Generation（§4.3 动态 Slot 文案）**；Teacher Name / Teacher Title / Teacher Metadata 属于 Teacher Identity Layer（见 §4.4），**不应用本节 Copy 约束**——与 `v2/compliance/banned_words_common.json` 的 `not_applied_to` 口径一致。

---

# 9. gpt-image-2 Rendering Contract

## 9.1 Input

生产调用至少包含：

```text
layout_ref = T2 Canonical Reference Image（v2/templates/hero_template_t2/reference_v1.0.png，已定稿 2026-09-08）
prompt_template = 本文第 9.2 节
slot_values = V2.3 输出的动态文案
```

当前阶段不传新的 `teacher_ref`；老师视觉固定使用 T2 Reference Image。

## 9.2 Canonical Prompt Template

Canonical Runtime Prompt 的独立生产版维护在：

`v2/prompts/hero_template_t2.md`

该文件为本节的完整生产实现（内联色板、Slot 契约与合规边界，不依赖"见上文"）。两文件语义必须保持一致；以本 Contract 为 Source of Truth。

核心要求摘要：

- Reference Image 是版式真值与视觉真值（Reference Image First Principle）；
- Layout Lock：页面结构、元素位置、尺寸比例、色彩体系、老师人物必须保持；
- 只替换 8 个 Dynamic Slot，禁止增加新文案区域、修改固定文案、修改老师信息、修改品牌元素；
- 只能使用 5 天身体唱歌体验营 Product Truth；
- 禁止动态价格 / 优惠 / 折扣信息、新增 CTA、新增价格 Badge / Offer Badge、自由重新设计 Hero（媒体 / 平台强制要求展示的合规免责声明除外）。

---

# 10. Stability Acceptance Criteria

T2 后续 Replay Validation 至少满足：

## Structure

- 顶部品牌栏完整；
- 定位语行保留；
- 两行大标题结构保留；
- 左右胶囊 Badge 成对结构保留；
- 4 个圆形 Benefit Badge 完整（2×2）；
- 老师位置 / 大致比例稳定；
- 竖排姓名条完整；
- Bottom Banner 完整宽度、视觉居中平衡；
- **无动态价格 / 优惠 / 折扣 / Offer 元素**（固定 Compliance Layer 的合规免责声明除外）。

## Copy

- 所有动态 Slot 文案准确；
- 无明显乱码 / 错字；
- 不明显溢出；
- 画面不得出现任何动态价格、优惠或折扣文字（合规免责声明层除外）。

## Visual

- 米白暖底 + 红色主视觉气质稳定；
- 不发生明显版式重构；
- 不随机替换老师服装与姿态。

## Business

- 只使用 5 天体验营 Product Truth；
- 无正式营信息；
- 无明显违禁表达。

生产上允许同一 Slot Values 生成 2～3 个 Candidate，再依据结构保真度与文字质量选取最佳结果；这不改变 T2 Contract 本身。

---

# 11. Versioning Rules

T2 版本管理：

- **V1.0（本文件，Draft）**：首个版本。冻结条件：Reference Image 定稿入库 + A/B/C fixture 文案设计 + Replay Validation 3/3 PASS。

冻结后允许：

- 修复明确的文字渲染问题；
- 修复产品口径错误；
- 修复合规问题；
- 在不改变结构的前提下优化 Prompt 对 Layout Lock 的稳定性。

不允许：

- 增删模块；
- 改布局；
- 改综合色系；
- 改老师；
- 改底部收束模块结构；
- 为个别 Creative Intent 增加专属模板结构。

如果必须发生以上变化，应建立 `T2 V2`，不得静默修改已冻结版本。

---

# 12. Next Step

T2 从 Draft 走向 Frozen 的前置工作（按序）：

1. **Reference Image 定稿**（**✅ 已完成，2026-09-08**）：以候选参考图为来源的修正版 T2 Reference——价格免责声明行按固定 Compliance Layer 保留、左胶囊统一为「零基础可学」、姓名条 Teacher Title 按 §4.4 确认展示效果——已入库为 `v2/templates/hero_template_t2/reference_v1.0.png`；
2. **A/B/C fixture 文案设计**：按 §5 字数预算设计三组不同 intent 的测试文案；
3. **Replay Validation**：每 fixture 基于同一定稿 Reference 独立生成，人工核验 §10 标准；
4. 3/3 PASS 后本 Contract 转为 **Frozen**，进入 T1 + T2 Dual-Template Exploration。

当前阶段不提前创建自动 Template Selector；先通过真实双模板结果学习路由规律。
