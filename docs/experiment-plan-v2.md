# 素材 × 落地页承接实验计划 V2

## 1. 实验背景

当前线上落地页采用固定模板：

- Hero 区由运营配置图片；
- 底部 CTA 按钮由模板控制，并持续吸底展示；
- Hero 下方仍包含完整销售内容，包括痛点、课程表、老师介绍、品牌介绍、课程解决问题、学习收益等。

当前项目已具备从广告视频中提取画面、转写、痛点、卖点、老师、色彩等信息，并生成多套 Hero 方案的能力。

但现阶段需要优先回答的并不是“能否生成更多 Hero”，而是：

> **广告素材与落地页 Hero 的 Message Match，是否能够带来可量化的用户行为和转化增量。**

本计划聚焦 Phase 0～Phase 2。

---

## 2. 核心假设

### H1：广告点击动机可以被稳定识别

同一条广告虽然可能同时出现多个痛点、卖点和利益点，但通常存在一个主要说服命题，驱动用户继续了解。

### H2：Hero 对主要点击动机进行承接，会改善首屏行为

预期表现包括：

- 首屏退出下降；
- 第二屏曝光上升；
- 页面深度提升。

### H3：如果首屏承接能够持续保持销售效率，最终 CTA 与转化也会获得增量

如果只改善首屏行为但最终 CVR 不提升，则需要判断：

- 后续通用页面是否已经充分覆盖该需求；
- Hero 是否牺牲了原标准页的销售信息；
- 承接是否需要延长到第二屏及后续内容。

---

# 3. Phase 0：实验底座

## 3.1 固化 Control

明确当前标准 Hero 与完整标准页版本，避免实验期间同步修改 Control。

建议记录：

```text
control_version
hero_asset_id
landing_page_template_version
cta_version
publish_time
```

## 3.2 基础体验检查

上线实验前检查：

- 课程周期是否统一；
- Hero 与课程模块是否存在冲突信息；
- 老师姓名、头衔是否一致；
- 价格、赠品、课程节数是否一致；
- CTA 文案与实际转化动作是否一致；
- 图片中文字是否存在明显错字或不可读区域。

已发现的典型问题：标准样例 Hero 使用“5 天”，课程模块标题曾出现“4 天”，但课程内容实际包含第 1～5 天，应优先统一。

## 3.3 推荐埋点

### 必需

```text
lp_view
hero_view
second_section_view
sticky_cta_click
conversion
```

### 推荐

```text
scroll_25
scroll_50
scroll_75
page_exit
stay_3s
stay_10s
```

### 关键维度

```text
experiment_id
experiment_group
landing_page_version
hero_version
creative_id
creative_intent
channel
campaign_id
```

## 3.4 核心指标

### Primary

- 最终留资 / 下单 CVR（按当前业务目标选择）；

### Secondary

- Sticky CTA CTR；
- Second Section View Rate；
- 首屏退出率；
- 页面 25% / 50% 深度到达率。

### Guardrail

- 页面加载成功率；
- 首屏加载耗时；
- 图片加载失败率；
- 投诉 / 合规异常（如适用）。

---

# 4. Phase 1：Creative Intent V1

## 4.1 目标

建立广告素材与页面策略之间的统一中间语言。

现有 `analysis.json` 继续保留痛点、卖点、老师、色彩等信息，但增加一个独立的 `creative_intent` 区域。

## 4.2 推荐 Schema

```json
{
  "creative_intent": {
    "primary_intent": "高音/发声位置",
    "secondary_intents": ["气息", "0基础"],
    "creative_hook": "高音唱不上去，不是嗓子差，而是发声方法不对",
    "click_motivation": "想知道高音为什么唱不上去，以及普通人能否改善",
    "persuasion_type": "认知纠偏型",
    "core_proposition": "找到正确发声位置，比硬喊更重要",
    "user_question_after_click": "那我要怎么找到正确的发声位置？",
    "hero_continuation": "高音别再硬喊，先找到正确发声位置",
    "confidence": 0.87
  }
}
```

## 4.3 Primary Intent 选择原则

Primary Intent 不是“视频里出现最多的词”，而是：

> **最有可能解释用户为什么愿意从广告继续进入落地页的主要说服命题。**

判断优先级：

1. 前 3 秒 Hook；
2. 前 10 秒主要矛盾 / 承诺；
3. 视频反复强化的信息；
4. CTA 前最重要的未完成问题；
5. 其他辅助信息。

### 禁止

- 同时输出多个 Primary Intent；
- 把“红色背景”“老师穿蓝衣服”等视觉元素当成 Primary Intent；
- 仅复述痛点，不解释为什么用户会继续了解；
- 输出过于宽泛的“学唱歌”“提升唱歌水平”。

## 4.4 初始 Intent Taxonomy

### 技能问题

- 高音 / 发声位置
- 气息 / 唱不久
- 大白嗓 / 音色
- 五音不全 / 音准

### 心理与门槛

- 不敢唱 / 自信开口
- 0 基础 / 易学

### 内容兴趣

- 经典歌曲 / 情怀

### 信任

- 老师 IP / 权威

### 高阶价值

- 健康 / 身心
- 社交 / 兴趣生活

Taxonomy 不是固定真理，应根据真实广告样本持续调整。

## 4.5 样本验证

建议首轮选取 50～100 条真实素材，覆盖：

- 不同渠道；
- 不同投放账户；
- 高消耗与低消耗素材；
- 不同创意结构；
- 不同老师 / 不同脚本方向。

每条素材至少由 1 名业务人员进行人工复核。

建议记录：

```text
creative_id
model_primary_intent
human_primary_intent
agree_or_not
reason
model_confidence
```

## 4.6 Phase 1 验收标准

不追求模型绝对准确率，而追求：

- 分类可解释；
- 业务人员能快速判断对错；
- 绝大多数素材能够收敛到一个主要 Intent；
- 同类素材能够形成稳定的承接模式。

---

# 5. Phase 2：Message Match 实验

## 5.1 核心原则

这一阶段只验证“信息承接”，不同时验证“AI 重新设计 Hero”。

因此：

> **固定销售骨架，开放少量内容 Slot。**

## 5.2 固定项

建议尽量固定：

- Hero 尺寸；
- 品牌栏；
- 老师主体位置与占比；
- 整体色彩体系（首轮）；
- 主副标题区域位置；
- 利益点组件样式；
- 课程周期区域；
- 页面下方所有内容；
- Sticky CTA 文案、样式、位置、逻辑。

## 5.3 可变 Slot

首轮建议只开放：

```text
hero_title
hero_subtitle
hero_primary_benefit
hero_secondary_benefit
hero_continuation_line
```

如果现有 Hero 无法自然容纳所有 Slot，可减少，不应为了个性化增加信息密度。

## 5.4 示例

### Control

```text
宋伶俐教你学唱歌
0基础可学｜自信开口唱
```

### 高音素材

```text
高音总唱不上去？
宋老师教你找到正确发声位置
```

### 气息素材

```text
唱两句就没气？
学会正确用气，唱歌更轻松
```

### 大白嗓素材

```text
唱歌总像喊？
找对发声方式，让声音更明亮
```

### 自信素材

```text
想唱却总不敢开口？
从0基础开始，慢慢唱出自信
```

示例只说明承接逻辑，不作为最终运营文案。

## 5.5 实验分组

### A：Control

现有标准 Hero。

### B：Message Match

固定 Hero 骨架，仅替换与 Primary Intent 对应的 Slot。

如流量足够，Phase 2 后半程可加入：

### C：Message Match + Visual Match

但不要在首轮直接加入，以免无法判断 uplift 来源。

## 5.6 归因要求

每次实验必须能够回溯：

```text
creative_id
creative_intent
control_or_treatment
hero_asset_id
hero_copy_version
landing_page_version
```

禁止同一 Treatment 在实验期间被运营临时换图但不更新版本。

## 5.7 结果判断框架

### 情况 1：首屏行为改善 + CVR 改善

结论：Message Match 成立。

下一步：进入 Visual Match。

### 情况 2：首屏行为改善 + CVR 不变

结论：Hero 承接有效，但增量没有传递到最终转化。

优先检查：

- 后续标准页是否已经充分覆盖该 Intent；
- Hero 是否弱化了原有销售元素；
- 是否需要进入 Persuasion Path Match。

### 情况 3：首屏与 CVR 都无改善

优先检查：

- Intent 分类是否真的代表点击动机；
- 标准 Hero 是否已经足够 Broad-spectrum；
- Treatment 是否只是在换文案而没有形成明显认知差异；
- Hero 在该业务链路中的决策权重是否本身有限。

不要直接据此判定“千人千面无价值”。

### 情况 4：首屏改善但 CVR 下降

重点怀疑：

> Treatment 增加了承接价值，但损失了标准 Hero 原有销售价值。

此时应拆分 Hero 的两类价值：

```text
A. Continuity / Relevance
B. Sales Persuasion
```

个性化必须在不显著损害 B 的前提下增加 A。

---

# 6. Hero 生成策略建议

## 6.1 新增 `message_match` 模式

推荐输出：

```json
{
  "primary_intent": "...",
  "creative_hook": "...",
  "click_motivation": "...",
  "hero_title": "...",
  "hero_subtitle": "...",
  "hero_benefits": ["...", "..."],
  "visual_direction": "..."
}
```

默认生成 1 个推荐方案。

## 6.2 保留 `design_exploration` 模式

现有 10 套不同风格生成能力保留，但明确用途：

- 设计探索；
- 运营候选；
- 样式研究；
- 后续 Visual Match 阶段。

不作为 Phase 2 的默认线上实验策略。

---

# 7. 推荐开发顺序

## Sprint 1：实验准备

- 固化 Control；
- 修复页面基础口径问题；
- 明确埋点；
- 建立实验版本字段。

## Sprint 2：Creative Intent

- 修改 `analyze_prompt.md`；
- 扩展 `analysis.json`；
- 建立首版 Intent Taxonomy；
- 跑 50～100 条素材；
- 人工验收。

## Sprint 3：Message Match 输出

- 增加 `message_match` 模式；
- 固定 Hero 骨架；
- 生成少量可控 Slot；
- 建立素材 → Hero 版本映射。

## Sprint 4：线上实验

- Control / Treatment 分流；
- 按 Intent 分层观察；
- 同时看中间漏斗与最终 CVR；
- 输出实验复盘。

---

# 8. 本阶段不做

在 Phase 2 得出稳定结论前，本计划不建议优先推进：

- 完整整页 AI 自由生成；
- 用户级画像驱动页面；
- 大规模组件动态编排；
- 为追求 Hero 多样性继续扩充风格；
- 复杂的多目标策略模型。

当前最重要的产出不是更多页面，而是一个可信答案：

> **广告素材与落地页之间，什么样的连续性真正能够带来增量？**
