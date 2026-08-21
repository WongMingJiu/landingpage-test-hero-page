# 千人千面落地页项目路线图

## 1. 项目目标

本项目的核心目标，不是单纯生成更多 Hero 图片，而是持续验证并放大：

> **广告素材中的核心意图，是否可以通过落地页承接形成真实、稳定、可规模化的转化增量。**

当前线上落地页形态为：

- 页面模板固定；
- 运营主要配置页面图片；
- Hero 区是当前主要实验变量；
- 底部 CTA 按钮的文案、样式等由模板决定，并持续吸底展示；
- Hero 下方仍有完整销售内容，包括痛点、课程表、老师介绍、品牌介绍、课程解决问题、学习收益等。

因此，当前阶段应被定义为 **Hero-level Message Match（广告素材 → 首屏承接）实验**，而不是完整的“千人千面落地页”。

---

## 2. 当前核心判断

### 2.1 需要验证的不是“AI Hero 好不好看”

真正需要回答的是：

1. 用户为什么点击这条广告？
2. 用户进入落地页后，Hero 是否继续承接了这个点击动机？
3. 这种承接是否改善首屏行为与最终转化？
4. 如果首屏承接有效，将这种连续性延长到后续页面内容，是否能够进一步放大收益？

### 2.2 当前标准页本身已经具备较强通用说服力

标准页通常已经覆盖：

- 0 基础 / 自信开口；
- 气息、高音、音色、大白嗓等核心痛点；
- 课程内容与学习周期；
- 老师 IP 与专业背书；
- 品牌与学习收益。

因此，个性化 Hero 面对的并不是“弱通用页”，而是一个已经能覆盖大量需求的成熟 Control。个性化方案必须在保留原有销售效率的基础上增加承接价值。

### 2.3 “不同”不等于“匹配”

素材适配的核心不是给每条素材生成不同颜色、不同布局或不同风格，而是明确：

> **这条素材最核心的说服命题是什么，以及用户点击之后最想继续获得什么答案。**

因此项目需要从“素材信息提取”进一步演进到“Creative Intent / Click Motivation”决策层。

---

## 3. 路线总览

| Phase | 目标 | 核心实验问题 | 页面自由度 |
| --- | --- | --- | --- |
| Phase 0 | 实验底座 | 当前数据是否足以判断 Hero 好坏？ | 不做个性化 |
| Phase 1 | Creative Intent V1 | 能否稳定识别用户为什么点击？ | 不改页面 |
| Phase 2 | Message Match | 只改变核心承接信息是否有效？ | 固定 Hero 骨架，仅开放文案 Slot |
| Phase 3 | Visual Match | 视觉连续性能否带来额外增量？ | 固定结构，开放视觉表达 |
| Phase 4 | Persuasion Path Match | 将承接延长到页面后续内容是否更有效？ | 内容高亮 / 重排 |
| Phase 5 | Dynamic Landing Page | 动态组件组合是否值得规模化？ | 组件级动态编排 |
| Phase 6 | 千人千面 | 用户级信号是否带来额外增量？ | 素材 × 用户联合策略 |

---

# Phase 0：实验底座与 Control 基线

## 目标

确保之后所有实验结论可信。

## 重点工作

- 清理标准落地页中的基础口径问题，例如课程周期、文案不一致；
- 固化 Control 页面与版本；
- 确认广告素材到落地页版本的归因关系；
- 补齐 Hero 相关漏斗埋点。

## 推荐漏斗

广告点击
→ Hero 曝光
→ 首屏退出
→ 第二屏曝光
→ 页面 25% 深度
→ 页面 50% 深度
→ CTA 点击
→ 留资 / 下单

最终 CVR 仍是核心业务指标，但 Hero 实验必须同时观察中间指标，避免将“首屏有效、后链路未放大”误判为“Hero 无效”。

## Gate

进入 Phase 1 前，应确认：

- Control 页面版本稳定；
- Hero 实验流量能够准确区分；
- 至少能够获得首屏行为、CTA、最终转化三个层级的数据。

---

# Phase 1：Creative Intent V1

## 目标

将“广告讲了什么”升级为“广告为什么让用户点击”。

## 建议新增结构

每条素材至少形成以下决策字段：

```text
primary_intent
creative_hook
click_motivation
persuasion_type
core_proposition
user_question_after_click
hero_continuation
secondary_intents
confidence
```

### 关键原则

- 一条素材必须选出 **唯一 Primary Intent**；
- Secondary Intent 可以有多个，但不能平均用力；
- `hero_continuation` 必须回答“用户点击之后下一步最应该看到什么”；
- 不把色彩、老师服装、场景等视觉特征当作 Primary Intent。

## 唱歌品类初始 Intent Taxonomy（待样本验证）

- 高音 / 发声位置
- 气息 / 唱不久
- 大白嗓 / 音色
- 五音不全 / 音准
- 不敢唱 / 自信开口
- 经典歌曲 / 情怀
- 0 基础 / 易学
- 老师 IP / 权威
- 健康 / 身心价值
- 社交 / 兴趣生活
- 其他

## 验证方式

选取 50～100 条真实广告素材，由人工与模型共同标注，重点验证：

- Primary Intent 是否稳定；
- 人工是否认可“用户为什么会点”；
- 不同标注者之间是否存在一致性；
- 模型是否能把多信息素材收敛成一个主要说服命题。

## Gate

只有当 Intent 层具备可解释性与稳定性，才进入 Phase 2。

---

# Phase 2：固定 Hero 骨架的 Message Match 实验

## 目标

先验证最纯粹的问题：

> **广告点击动机被落地页首屏继续承接，本身有没有价值？**

## 核心策略

不要让 AI 自由重做 Hero。

保留现有成熟 Hero 的销售骨架，例如：

- 品牌区域；
- 老师主体位置；
- 整体布局；
- 字体层级；
- 课程周期表达；
- 主要利益点组件；
- 整体 CTA 机制。

只开放少量信息 Slot：

```text
hero_title
hero_subtitle
hero_primary_benefit
hero_secondary_benefit
hero_continuation_line
```

## 实验设计

Control：标准 Hero。

Treatment：同一 Hero 骨架，仅根据 Primary Intent 改变核心承接信息。

这一阶段尽量不改变：

- 背景风格；
- 老师位置；
- 信息密度；
- CTA；
- 页面下方内容。

## Gate

需要同时观察：

- 首屏退出 / 第二屏曝光；
- CTA 点击；
- 最终 CVR。

如果仅首屏指标改善，但最终转化未改善，不直接判定失败，应进入后链路诊断。

---

# Phase 3：Visual Match

## 目标

在 Message Match 已成立的前提下，验证视觉连续性是否存在额外增量。

## 可开放变量

- 素材主色域；
- 老师服装 / 人物参考；
- 场景氛围；
- 光线情绪；
- 局部装饰；
- 与素材相近的视觉表达。

## 仍保持固定

- Hero 信息架构；
- 核心销售元素；
- CTA；
- 页面下方内容。

当前仓库已有的视频抽帧、色彩分析、老师识别、生图能力，主要在这一阶段发挥价值。

---

# Phase 4：Persuasion Path Match

## 目标

从“首屏匹配”升级到“说服路径匹配”。

不需要立即生成整页新内容，优先使用已有成熟模块，通过：

- Highlight（高亮）；
- Reorder（排序）；
- Focus（聚焦）；

让素材核心意图在后续页面继续得到回答。

### 示例

高音素材：

Hero（高音）
→ 优先展示高音 / 气息相关痛点
→ 高亮课程中“高音准确”内容
→ 其他课程
→ 老师 / 品牌 / 学习收益

自信素材：

Hero（不敢唱 / 自信开口）
→ 优先展示五音不全 / 不敢开口
→ 课程
→ 高亮“自信开口 / 愉悦身心 / 社交”等收益
→ 其他信息

## Gate

若相比单 Hero 个性化获得进一步 uplift，则进入组件化阶段。

---

# Phase 5：Dynamic Landing Page

## 目标

从“图片级配置”演进为“组件级动态页面”。

建议组件化：

```text
Hero
Pain Point
Mechanism
Course
Teacher
Social Proof
Benefit
Brand
CTA
```

AI / 策略层负责：

- 选择组件；
- 选择内容；
- 决定强调重点；
- 决定排序。

确定性渲染负责：

- 字号；
- 间距；
- 品牌；
- CTA；
- 适老化；
- 合规；
- 页面稳定性。

长期不建议将完整 4000～5000px 落地页完全交给图片模型自由生成。

---

# Phase 6：真正的千人千面

前五个阶段主要解决 **千素材千面**。

只有当“Creative → Landing Page”已经被证明有效，再加入用户级信号：

```text
广告 Creative Intent
× 用户画像
× 渠道来源
× 用户生命周期
× 历史行为 / 已购品类
× 页面策略
```

此时才能回答：

> 同一条广告带来的不同用户，是否应该看到不同的页面说服路径？

---

## 4. 当前仓库的演进方向

当前仓库已有能力不废弃，而是重新定位。

### 当前能力

```text
Video
→ Frame / Transcript
→ Multimodal Analysis
→ 多套 Hero Design Prompt
→ Image Generation
```

### 下一阶段目标

```text
Video
→ Creative Understanding
→ Creative Intent
→ Hero Message Match
→ Experimental Delivery
```

### 推荐增加两种运行模式

#### 1. `message_match`

线上实验默认方向。

输出：

```text
primary_intent
creative_hook
click_motivation
hero_title
hero_subtitle
hero_benefits
visual_direction
```

默认只生成 **1 个推荐承接方案**。

#### 2. `design_exploration`

保留现有 10 套方案生成能力，用于设计探索、运营候选与视觉研究，不作为线上默认策略。

---

## 5. 当前阶段明确不做

在 Phase 2 得到可信结果之前，不优先投入：

- 用户级千人千面；
- 完整整页自由 AI 生图；
- 为追求多样性继续扩充 Hero 风格库；
- 大规模动态组件编排；
- 复杂用户画像与页面联合决策。

当前第一优先级只有一个：

> **用最小变量验证广告与落地页之间的 Message Match 是否能产生真实转化增量。**

---

## 6. 当前执行顺序

1. Phase 0：完成 Control 与数据底座检查；
2. Phase 1：定义 Creative Intent V1，并用真实素材验证；
3. Phase 2：固定 Hero 骨架，启动 Message Match 实验；
4. 根据实验结果决定是否进入 Visual Match；
5. 有明确增量后，再延长到后续页面内容；
6. 最后才进入动态落地页与真正千人千面。
