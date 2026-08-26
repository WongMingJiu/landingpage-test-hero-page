# Singing Creative Intent Benchmark V0.1

## 1. 目的

这是 Creative Intent V1 的首批人工 Benchmark，用于后续验证 `intent_prompt.md` / Intent Decision Stage 是否能够稳定复现业务判断。

首批样本共 10 条唱歌投放视频脚本。

> 注意：本轮人工标注主要基于脚本与时间轴。部分素材前段包含演唱、动作演示、师生互动或学员效果展示，ASR 对歌词和演唱段识别不完整，因此涉及视觉主导判断的样本会主动降低置信度。正式模型验证必须保留多模态输入。

---

## 2. 标注字段

每条样本至少包含：

```text
Opening Strategy
Core Need
Barrier / Persuasion / Trust / Offer
Primary Driver Statement
Unresolved Question
Post-click Expectation
Hero Continuation
Confidence
```

其中：

- 标签用于解释；
- `Primary Driver Statement` 必须唯一；
- `Core Need` 可以是 `specific` 或 `broad`；
- `Post-click Expectation` 用于反向校验 Primary Driver 是否合理。

---

## 3. Benchmark 总表

| ID | Opening Strategy | Core Need | Supporting Drivers | Primary Driver Statement | Post-click Expectation | Confidence |
| --- | --- | --- | --- | --- | --- | ---: |
| v01 | 学员结果证明 | broad：掌握通用演唱能力 | 可复制学习范例、降低学习门槛 | **学了几年都没学明白，用简单方法反而能更快找到唱歌感觉** | 复制学员成功路径、掌握简单方法 | 0.88 |
| v02 | 演唱效果展示 | specific：改善音色与声音质感 / 建立自信 | 效果参照、经典歌曲带练 | **跟着经典老歌找到正确发声部位，也能唱出更有质感、让人惊艳的声音** | 获得 / 复制演唱效果 | 0.70 |
| v03 | 演唱展示 + 挑战式口播 | broad：掌握通用演唱能力 | 低时间成本、系统课程 | **用刷手机的时间，跟着几首歌练一套系统课程，可以一起改善大白嗓、气息、高音等问题** | 了解系统课程、低门槛开始学习 | 0.84 |
| v04 | 演唱展示 + 稀缺权益 | broad：掌握通用演唱能力 | 稀缺 Offer、效果承诺 | **课程机会可能停止，现在领取仍可以通过简单动作改善跑调、虚抖、高音等问题** | 获得课程权益 | 0.82 |
| v05 | 方法展示 | specific：正确发声 / 改善音色 | 方法揭秘、低门槛 | **把身体通道打开，声音就不再卡在喉咙里，唱歌方法其实可以很简单** | 掌握简单方法 | 0.93 |
| v06 | 方法教学 | specific：正确发声并保护嗓音 | 认知纠偏、方法揭秘 | **唱歌不是靠嗓子挤，而是可以借身体力量把声音送出去** | 理解专业原理、掌握简单方法 | 0.97 |
| v07 | 动作演示 + 方法承诺 | broad：掌握通用演唱能力 | 简单动作、系统课程、服务保障 | **几个看似简单的动作里有方法，跟着系统课程练可以解决多种唱歌问题** | 了解系统课程 | 0.78 |
| v08 | 方法演示 | broad：正确发声 / 掌握通用能力 | 身体唱歌法、学员证明、低门槛 | **不用喉咙硬唱，通过身体通道和动作训练，零基础也能让声音变好听** | 掌握简单方法、获得效果参照 | 0.72 |
| v09 | 人群资格问答 | broad：建立唱歌能力 | 降低年龄与学习门槛、权威方法 | **唱歌不该被年龄和复杂乐理挡住，年龄很大也可以通过简单动作学习** | 低门槛开始学习 | 0.98 |
| v10 | 学员演唱 / 师生效果展示 | broad：建立演唱自信 / 改善歌声 | 学员效果证明、降低年龄门槛 | **普通学员也能唱出让人惊艳的歌声，而且年龄大、零基础也能跟着动作学** | 复制学员成功路径 | 0.91 |

---

## 4. 样本明细

### v01

**关键脚本证据**

- 开场：学了四五年没学明白，在老师这里很快学明白；
- 后续：不需要复杂乐理、几个简单动作、每天 20 分钟、在家学、零基础也可以。

**人工标注**

```json
{
  "opening_strategy": "学员结果证明",
  "core_need": {
    "scope": "broad",
    "summary": "掌握通用演唱能力"
  },
  "barriers": ["降低学习难度", "零基础可学"],
  "persuasion_drivers": ["获得可复制学习范例"],
  "primary_driver": {
    "statement": "学了几年都没学明白，用简单方法反而能更快找到唱歌感觉",
    "unresolved_question": "老师到底用了什么简单方法，让以前学不会的人也能学明白？"
  },
  "post_click_expectation": ["复制学员成功路径", "掌握简单方法"],
  "hero_continuation": "承接‘不是学不会，而是方法可以更简单’这一认知，并继续给出简单学习路径",
  "confidence": 0.88
}
```

### v02

**关键脚本证据**

- 前段主要是演唱；
- 后续强调简单动作、打开身体通道、找到正确发声部位、歌声有混响 / 穿透力；
- 最终落到敢开口、惊艳别人。

**人工标注**

```json
{
  "opening_strategy": "演唱效果展示",
  "core_need": {
    "scope": "specific",
    "labels": ["改善音色与声音质感", "建立演唱自信"]
  },
  "persuasion_drivers": ["获得演唱效果参照", "明确问题解决路径"],
  "primary_driver": {
    "statement": "跟着经典老歌找到正确发声部位，也能唱出更有质感、让人惊艳的声音",
    "unresolved_question": "这些简单动作和发声部位具体怎么练？"
  },
  "post_click_expectation": ["获得/复制演唱效果"],
  "hero_continuation": "继续强化从正确发声到声音质感变化的结果感",
  "confidence": 0.70
}
```

> 该条前段主要是演唱，视觉信息可能显著影响真实 Opening Strategy，因此置信度较低。

### v03

**关键脚本证据**

- “敢不敢用玩手机的时间去学习唱歌”；
- 5 天 5 节课；
- 同时覆盖大白嗓、气息、高音、高低音转换、通俗演唱；
- 在家、每天约 20 分钟、没基础也能学。

**人工标注**

```json
{
  "opening_strategy": "演唱展示 + 挑战式口播",
  "core_need": {
    "scope": "broad",
    "labels": ["改善音色", "稳定气息", "突破高音", "顺畅音域转换"],
    "summary": "掌握通用演唱能力"
  },
  "barriers": ["降低时间成本", "零基础可学"],
  "persuasion_drivers": ["明确系统学习路径"],
  "primary_driver": {
    "statement": "用刷手机的时间，跟着几首歌练一套系统课程，可以一起改善大白嗓、气息、高音等问题",
    "unresolved_question": "这 5 天课程具体怎么把这些问题一起解决？"
  },
  "post_click_expectation": ["了解系统课程", "低门槛开始学习"],
  "hero_continuation": "突出短周期、系统解决多个唱歌问题，而不是强行单选某一个痛点",
  "confidence": 0.84
}
```

### v04

**关键脚本证据**

- “身体唱歌精品课程可能要停止了”；
- 紧接着强调抢到手机；
- 后续展示跑调、发虚发抖、音色、高音等多种变化；
- 方法面向年纪大 / 零基础用户，支持回放。

**人工标注**

```json
{
  "opening_strategy": "演唱展示 + 稀缺权益",
  "core_need": {
    "scope": "broad",
    "summary": "掌握通用演唱能力"
  },
  "barriers": ["降低年龄与学习门槛"],
  "offer_drivers": ["把握限时稀缺机会"],
  "primary_driver": {
    "statement": "课程机会可能停止，现在领取仍可以通过简单动作改善跑调、虚抖、高音等问题",
    "unresolved_question": "这个课程还来得及领取吗，它具体能怎么改善这些问题？"
  },
  "post_click_expectation": ["获得课程权益"],
  "hero_continuation": "优先承接领取机会，同时保留课程能解决多个问题的销售价值",
  "confidence": 0.82
}
```

### v05

**关键脚本证据**

- “打通身体的整个通道”；
- “声音出去就非常好听，它就不卡在喉咙”；
- “我的方法很简单”；
- 后续课程分别对应气息、大白嗓、高音、情感。

**人工标注**

```json
{
  "opening_strategy": "方法展示",
  "core_need": {
    "scope": "specific",
    "labels": ["正确发声并改善音色"]
  },
  "barriers": ["方法简单易操作", "零基础可学"],
  "persuasion_drivers": ["理解发声原理", "明确问题解决路径"],
  "primary_driver": {
    "statement": "把身体通道打开，声音就不再卡在喉咙里，唱歌方法其实可以很简单",
    "unresolved_question": "怎么把身体通道打开，让声音不再卡在喉咙？"
  },
  "post_click_expectation": ["掌握简单方法"],
  "hero_continuation": "继续承接‘身体通道 + 简单方法’这一机制，而不是泛化成普通唱歌课程",
  "confidence": 0.93
}
```

### v06

**关键脚本证据**

- “用后腰的力量把声音送出去”；
- “不是用嗓子挤出来的声音”；
- 后腰像发动机；
- 这样嗓子更舒服。

**人工标注**

```json
{
  "opening_strategy": "方法教学",
  "core_need": {
    "scope": "specific",
    "labels": ["正确发声并保护嗓音"]
  },
  "persuasion_drivers": ["纠正错误唱歌认知", "理解发声原理", "掌握简单方法"],
  "primary_driver": {
    "statement": "唱歌不是靠嗓子挤，而是可以借身体力量把声音送出去",
    "unresolved_question": "具体怎么用身体力量把声音送出去？"
  },
  "post_click_expectation": ["理解专业原理", "掌握简单方法"],
  "hero_continuation": "继续解释为什么不能只靠嗓子唱，并把身体发声作为核心解决方向",
  "confidence": 0.97
}
```

### v07

**关键脚本证据**

- “别看这个动作简单，里面大有乾坤”；
- 按方法练，歌声会越来越好听；
- 课程覆盖大白嗓、气息不足、高音；
- 还有助教复习、练习、答疑。

**人工标注**

```json
{
  "opening_strategy": "动作演示 + 方法承诺",
  "core_need": {
    "scope": "broad",
    "summary": "掌握通用演唱能力"
  },
  "barriers": ["方法简单易操作"],
  "persuasion_drivers": ["明确系统学习路径"],
  "trust_drivers": ["获得辅导答疑", "服务保障"],
  "primary_driver": {
    "statement": "几个看似简单的动作里有方法，跟着系统课程练可以解决多种唱歌问题",
    "unresolved_question": "这些动作和课程是怎么系统解决大白嗓、气息、高音等问题的？"
  },
  "post_click_expectation": ["了解系统课程"],
  "hero_continuation": "突出简单动作背后的系统方法，以及课程覆盖多个常见唱歌问题",
  "confidence": 0.78
}
```

### v08

**关键脚本证据**

- 开头：一吸，身体通道就通了；
- 中段强调不要用喉咙唱；
- 学员案例：大白嗓几十年也能变好听；
- 后续强调零基础、动作训练、经典歌曲。

**人工标注**

```json
{
  "opening_strategy": "方法演示",
  "core_need": {
    "scope": "broad",
    "labels": ["正确发声", "改善音色", "掌握通用演唱能力"]
  },
  "barriers": ["零基础可学"],
  "persuasion_drivers": ["纠正错误唱歌认知", "获得可复制学习范例", "掌握简单方法"],
  "primary_driver": {
    "statement": "不用喉咙硬唱，通过身体通道和动作训练，零基础也能让声音变好听",
    "unresolved_question": "身体唱歌法里的这些动作到底怎么练？"
  },
  "post_click_expectation": ["掌握简单方法", "获得效果参照"],
  "hero_continuation": "继续承接不用喉咙硬唱、身体通道和简单动作这一方法认知",
  "confidence": 0.72
}
```

> 该素材较长，且前段 / 中段存在演唱与展示，单靠脚本可能低估视觉影响。

### v09

**关键脚本证据**

- “什么类型的人适合学身体唱歌法？所有人”；
- “94 岁的老奶奶、老爷爷都可以学会”；
- 复杂乐理会把很多人挡在门外；
- 动作 + 歌唱让技巧不再复杂。

**人工标注**

```json
{
  "opening_strategy": "人群资格问答",
  "core_need": {
    "scope": "broad",
    "summary": "建立唱歌能力"
  },
  "barriers": ["降低年龄焦虑", "降低学习难度", "降低乐理与理解门槛"],
  "persuasion_drivers": ["掌握简单方法"],
  "primary_driver": {
    "statement": "唱歌不该被年龄和复杂乐理挡住，年龄很大也可以通过简单动作学习",
    "unresolved_question": "我这个年纪、这个基础真的能学吗，具体怎么开始？"
  },
  "post_click_expectation": ["低门槛开始学习"],
  "hero_continuation": "优先证明年龄大、零基础也能开始，而不是先讲某个具体唱歌技巧",
  "confidence": 0.98
}
```

### v10

**关键脚本证据**

- 开头包含学员演唱和老师正向反馈；
- “94 岁也可以学会”；
- 动作 + 歌唱让技巧变简单；
- 聚会时一开口让别人惊艳；
- 年龄大、零基础都能学。

**人工标注**

```json
{
  "opening_strategy": "学员演唱 / 师生效果展示",
  "core_need": {
    "scope": "broad",
    "labels": ["建立演唱自信", "改善歌声"]
  },
  "barriers": ["降低年龄焦虑", "零基础可学"],
  "persuasion_drivers": ["获得可复制学习范例", "获得演唱效果参照"],
  "primary_driver": {
    "statement": "普通学员也能唱出让人惊艳的歌声，而且年龄大、零基础也能跟着动作学",
    "unresolved_question": "我是不是也能像这个学员一样学会并唱出明显变化？"
  },
  "post_click_expectation": ["复制学员成功路径"],
  "hero_continuation": "优先承接‘普通人也能复制这个效果’，同时证明年龄和基础不是障碍",
  "confidence": 0.91
}
```

---

## 5. 首批样本得到的结构性结论

### 5.1 具体唱歌痛点并不总是 Primary Driver

首批样本中，真正以单一“高音 / 气息 / 大白嗓”为核心点击命题的素材并不多。

更常见的是：

- 以前觉得难 → 原来方法可以很简单；
- 普通人 / 老年人 → 也可以做到；
- 学员做到了 → 我也可能复制；
- 一套课程 → 系统解决多个问题。

因此不能把 Creative Intent 简化成“唱歌痛点分类器”。

### 5.2 `Core Need` 必须支持 broad

v03、v04、v07、v08 等素材本身就是系统解决方案型。

如果强迫模型从“高音 / 气息 / 大白嗓”中只选一个，会产生假精确。

### 5.3 `Primary Driver` 应该是完整命题

例如：

```text
Core Need：正确发声
Persuasion：纠正错误认知
Primary Driver：唱歌不是靠嗓子挤，而是借身体力量把声音送出去
```

标签负责解释，完整命题负责决定页面承接方向。

### 5.4 Post-click Expectation 是有效校验器

如果 `Primary Driver` 无法自然解释用户为什么会产生对应的下一步期待，应重新判断 Driver。

### 5.5 多模态输入必须保留

v02、v04、v08、v10 等素材的关键点击因素可能大量存在于演唱效果、人物、动作与互动中。纯脚本 Benchmark 只用于建立首版标准，正式模型必须同时使用视觉证据。

---

## 6. 下一轮 Benchmark 方式

首版 `intent_prompt.md` 完成后，对这 10 条素材逐条输出同一 Schema，与本文件人工结果对比。

建议至少记录：

```text
creative_id
human_primary_driver
model_primary_driver
primary_driver_match
human_core_need_scope
model_core_need_scope
post_click_expectation_match
hero_continuation_usable
evidence_quality
model_confidence
review_notes
```

第一轮不要求形成学术意义上的准确率模型，重点观察错误模式：

- 把 Opening Strategy 当成 Driver；
- 把 CTA / Offer 当成 Driver；
- 把老师权威当成 Driver；
- 过度单选具体 Need；
- 输出泛化的“学唱歌 / 唱得更好”；
- Driver 与 Post-click Expectation 不一致；
- 忽略视觉主导证据。

当这 10 条表现稳定后，再扩充到 50～100 条素材。
