# Singing Intent Decision Benchmark V1.0

> 用途：V2.1b Intent Decision 的 Seed Ground Truth
>
> 样本：与 V2.1a 一致的 10 条真实唱歌投放素材
>
> 正式上游：`creative_tags.json`
>
> 上游 Ground Truth：`docs/benchmarks/singing-creative-tagging-benchmark-v1.0.md`

---

## 1. Benchmark 目标

本 Benchmark 不重新理解视频，也不重新裁决 V2.1a 标签。

V2.1b 只基于已经冻结的 V2.1a 输出判断：

1. **Primary Driver**：最能解释用户为什么继续点击的唯一核心说服命题；
2. **Unresolved Question**：用户点击后仍最需要继续确认的核心问题；
3. **Intent Strength**：素材本身的点击意图是否集中；
4. **Supporting Drivers**：0–2 个增强 Primary Driver 的次级说服因素；
5. **Evidence Grounding**：上述结论必须能够回溯到 V2.1a Evidence。

本 Benchmark 的判断口径以 `docs/v2.1b-intent-decision-spec-v1.0.md` 为准。

---

## 2. 验收口径

### Gate A — Primary Driver Semantic Match

```text
>= 8/10
```

语义因果一致即可，不做字符串完全匹配。

### Gate B — Unresolved Question Semantic Match

```text
>= 8/10
```

要求：

- 延续广告已建立的核心问题；
- 真的是尚未充分回答的问题；
- 不重复广告已经明确回答的内容；
- 不凭空创造新痛点。

### Gate C — Primary Uniqueness

```text
10/10
```

每条素材只能输出一个 Primary Driver。

### Gate D — Evidence Grounding

```text
10/10
```

不得出现 Marketing Imagination。

`intent_strength` 与 `supporting_drivers` 首版作为人工观察项，不做严格 Exact Match Gate。

---

## 3. Ground Truth 总表

| ID | Primary Driver 核心 | Unresolved Question 核心 | Strength |
|---|---|---|---|
| v01 | 真实学员证明方法有效，用户相信自己也可能复制学习结果 | 她具体怎么学的，我也能做到吗？ | strong |
| v02 | 专业老师直接进行简单歌曲带练，用户觉得自己也可能跟得上并学会 | 这个简化后的带练具体怎么做？ | medium |
| v03 | 普通人跟老师学习一个月就获得明显演唱提升，用户相信自己也可能复制学习路径 | 他这一个月具体怎么学、练了什么？ | strong |
| v04 | 普通妈妈参加唱歌训练后发生明显变化，用户相信中老年人也可能获得类似改善 | 她到底学了什么、为什么会产生这样的变化？ | strong |
| v05 | 身体发声机制可以解释并改善声音卡喉等发声问题 | 身体发声通道到底是什么、具体怎么打开？ | strong |
| v06 | 唱歌不是只靠嗓子用力，而可以借身体力量把声音送出去 | “后腰发动机”具体怎么使用？ | strong |
| v07 | 57 岁普通学习者学后获得明显演唱效果与真实社交认可，用户相信自己也可能获得类似改变 | 她怎么学、怎么练才达到这个效果？ | strong |
| v08 | 原本专业复杂的正确发声可以通过简单、直观、容易跟做的方法练习 | 这个简单方法具体怎么练？ | strong |
| v09 | 年龄大、零基础不意味着学不会，普通中老年人现在开始也来得及 | 我这个年龄和基础应该从哪里开始，真的能跟上吗？ | strong |
| v10 | 改掉喉咙唱歌坏习惯不需要复杂训练，一个简单可跟做的方法连高龄、零基础用户也能学习 | 这个方法应该怎么正确练，真的能改善喉咙发声吗？ | strong |

---

## 4. 逐条 Ground Truth

### v01

#### V2.1a 基线

```text
Opening Type: 学员故事证明型
User Expectation: 复制学员成功路径
Primary Values:
- 获得可复制学习范例
- 获得演唱效果参照
Supporting Values:
- 正确发声并保护嗓音
- 获得专业指导
- 获得课程与学习资源
```

#### V2.1b GT

```json
{
  "primary_driver": {
    "statement": "看到真实学员通过宋老师的轻松唱歌法改掉喉咙唱歌、获得明显演唱改善，让用户相信自己也可能复制这样的学习结果。",
    "confidence": "high"
  },
  "unresolved_question": {
    "statement": "她具体是怎么通过这套轻松唱歌法改掉喉咙唱歌的，我也能学会吗？",
    "confidence": "high"
  },
  "intent_strength": "strong",
  "supporting_drivers": [
    "宋老师的专业身份增强了这套方法的可信度。",
    "4天体验营让用户看到这套方法有明确的继续学习入口。"
  ]
}
```

判定要点：Primary Driver 的核心是“真实学员结果 → 可复制性”，不是单纯“正确发声”或“老师专业”。

---

### v02

#### V2.1a 基线

```text
Opening Type: 教学演示型
Opening Alternative: 演唱效果型
User Expectation: 掌握简单方法
Primary Values:
- 获得专业指导
- 获得演唱效果参照
Supporting Values:
- 方法简单易操作
- 降低时间与地点限制
```

#### V2.1b GT

```json
{
  "primary_driver": {
    "statement": "专业老师直接用歌曲示范带练，并把唱歌学习简化成容易跟做的过程，让用户相信自己也可以跟着老师一步步学会唱歌。",
    "confidence": "high"
  },
  "unresolved_question": {
    "statement": "老师这个简化后的带唱方法具体怎么练，我跟着学也能把歌唱好吗？",
    "confidence": "high"
  },
  "intent_strength": "medium",
  "supporting_drivers": [
    "专业老师身份与现场指导，使这种教学方式更可信。",
    "老师直接展示演唱效果，让用户看到跟着学习可能获得的结果。"
  ]
}
```

判定要点：v02 的核心是“简单带练、我可能跟得上”，不是单纯演唱效果。`intent_strength=medium` 是因为教学与效果均较强。

---

### v03

#### V2.1a 基线

```text
Opening Type: 演唱效果型
User Expectation: 复制学员成功路径
Primary Values:
- 获得演唱效果参照
- 获得可复制学习范例
Supporting Values:
- 获得他人认可
- 获得系统学习路径
- 获得专业指导
```

#### V2.1b GT

```json
{
  "primary_driver": {
    "statement": "普通人跟着宋老师系统学习一个月，就可能获得明显的演唱提升、甚至让家人刮目相看，让用户相信自己也有机会复制这样的学习结果。",
    "confidence": "high"
  },
  "unresolved_question": {
    "statement": "他这一个月到底是怎么学、练了什么，我跟着同样的课程也能达到这样的效果吗？",
    "confidence": "high"
  },
  "intent_strength": "strong",
  "supporting_drivers": [
    "家人的惊讶和认可强化了学习后确实发生明显变化的结果证明。",
    "宋老师和系统课程为这个结果提供了可复制的学习路径，而不是偶然天赋。"
  ]
}
```

判定要点：v03 与 v01 同属结果可复制，但“普通人 + 明确学习周期 + 学习后结果”更核心。

---

### v04

#### V2.1a 基线

```text
Opening Type: 学员故事证明型
User Expectation: 复制学员成功路径
Primary Values:
- 获得可复制学习范例
- 获得演唱效果参照
Supporting Values:
- 把握限时稀缺机会
- 获得课程与学习资源
```

#### V2.1b GT

```json
{
  "primary_driver": {
    "statement": "看到一个普通妈妈参加宋老师的唱歌训练后真的发生了明显变化，让用户相信中老年人通过学习也能获得类似的唱歌提升和积极改变。",
    "confidence": "high"
  },
  "unresolved_question": {
    "statement": "她参加训练营后到底学了什么、为什么会有这样的变化，我家里这个年龄的人也能做到吗？",
    "confidence": "high"
  },
  "intent_strength": "strong",
  "supporting_drivers": [
    "限时稀缺强化了现在就进一步了解或领取课程的行动动力。",
    "课程可以直接领取到手机，降低了继续学习的实际门槛。"
  ]
}
```

判定要点：后段 Offer 很强，但只能增强行动，不覆盖前段已经形成的“学员变化 / 可复制结果” Driver。

---

### v05

#### V2.1a 基线

```text
Opening Type: 演唱效果型
User Expectation: 理解专业原理
Primary Values:
- 正确发声并保护嗓音
- 理解发声原理
Supporting Values:
- 方法简单易操作
- 获得演唱效果参照
- 获得专业指导
```

#### V2.1b GT

```json
{
  "primary_driver": {
    "statement": "通过打开和使用正确的身体发声通道，可以让声音不再卡在喉咙、变得更顺畅好听，让用户相信自己的发声问题存在一个可以理解和改善的具体机制。",
    "confidence": "medium"
  },
  "unresolved_question": {
    "statement": "所谓“打开身体发声通道”具体是什么意思，我要怎么做才能让声音不再卡在喉咙？",
    "confidence": "high"
  },
  "intent_strength": "strong",
  "supporting_drivers": [
    "前段真实演唱效果，为这种发声方式确实能带来声音改善提供结果证明。",
    "“方法很简单”降低了用户对专业发声训练复杂难学的顾虑。"
  ]
}
```

判定要点：效果可以作为证据与机制揭秘共同形成 Driver，不需要机械二选一。

---

### v06

#### V2.1a 基线

```text
Opening Type: 教学演示型
User Expectation: 掌握简单方法
Primary Values:
- 正确发声并保护嗓音
- 纠正错误唱歌认知
Supporting Values:
- 理解发声原理
- 获得课程与学习资源
```

#### V2.1b GT

```json
{
  "primary_driver": {
    "statement": "唱歌不是只靠嗓子用力，而是可以借助后腰等身体力量把声音送出去；这个具体的新方法方向，让用户觉得自己原来的发声方式可能错了，而且存在一个可以直接学习的替代方法。",
    "confidence": "high"
  },
  "unresolved_question": {
    "statement": "具体要怎么找到并使用这个“后腰发动机”，才能真正把声音送出去而不是继续用嗓子挤？",
    "confidence": "high"
  },
  "intent_strength": "strong",
  "supporting_drivers": [
    "“后腰有个发动机”的形象解释，让抽象的发声原理变得容易理解和记忆。",
    "后续课程和学员练唱说明，这不是单纯的知识点，而是一套可以继续学习实践的方法。"
  ]
}
```

判定要点：v06 已经从“解释机制”进入“认知纠偏 + 方法方向”，Unresolved Question 应偏向“具体怎么做”。

---

### v07

#### V2.1a 基线

```text
Opening Type: 演唱效果型
User Expectation: 复制学员成功路径
Primary Values:
- 获得演唱效果参照
- 获得他人认可
Supporting Values:
- 获得可复制学习范例
- 方法简单易操作
```

#### V2.1b GT

```json
{
  "primary_driver": {
    "statement": "看到一位57岁的普通妈妈通过学习，不仅能在真实场合唱出明显更好的效果，还能获得家人和周围人的惊喜认可，让用户相信自己也可能通过学习获得类似的改变。",
    "confidence": "high"
  },
  "unresolved_question": {
    "statement": "她到底学了什么、怎么练，才会在这个年龄唱出这样的效果，我跟着学也能做到吗？",
    "confidence": "high"
  },
  "intent_strength": "strong",
  "supporting_drivers": [
    "宾客和家人的惊讶、鼓掌与称赞，让演唱改善从自我感觉变成了真实的外部验证。",
    "后续动作练习暗示这种变化来自可以学习的方法，而不是单纯个人天赋。"
  ]
}
```

判定要点：“获得他人认可”可以进入 Driver，但通常是对真实能力 / 结果变化的情绪与社会证明放大，不应脱离结果单独存在。

---

### v08

#### V2.1a 基线

```text
Opening Type: 教学演示型
User Expectation: 掌握简单方法
Primary Values:
- 方法简单易操作
- 正确发声并保护嗓音
Supporting Values:
- 纠正错误唱歌认知
- 获得演唱效果参照
```

#### V2.1b GT

```json
{
  "primary_driver": {
    "statement": "原本看起来专业复杂的正确发声，其实可以通过简单、直观、能马上跟着做的方法来练习，让用户觉得改善喉咙用力等发声问题并没有想象中那么难。",
    "confidence": "high"
  },
  "unresolved_question": {
    "statement": "这个简单方法具体该怎么做、怎么练，才能真的改善我唱歌时喉咙用力的问题？",
    "confidence": "high"
  },
  "intent_strength": "strong",
  "supporting_drivers": [
    "对原有发声认知的纠正，让用户意识到自己的问题可能来自发声方式本身。",
    "演唱效果展示为这个简单方法提供了直观的结果证明。"
  ]
}
```

判定要点：v08 的主轴是“简单、可操作的方法本身”，不是抽象原理。

---

### v09

#### V2.1a 基线

```text
Opening Type: 低门槛领取型
User Expectation: 低门槛开始学习
Primary Values:
- 降低年龄焦虑
- 方法简单易操作
Supporting Values:
- 零基础可学
- 获得专业指导
```

#### V2.1b GT

```json
{
  "primary_driver": {
    "statement": "年龄大、零基础并不意味着学不会唱歌，只要方法足够简单、容易开始，普通中老年人也可以跟着专业老师学习，让用户觉得“唱歌这件事我现在开始也来得及”。",
    "confidence": "high"
  },
  "unresolved_question": {
    "statement": "我这个年龄、又没有唱歌基础，具体该从哪里开始，真的能跟得上老师的学习方法吗？",
    "confidence": "high"
  },
  "intent_strength": "strong",
  "supporting_drivers": [
    "零基础也能开始进一步降低了没有音乐基础带来的学习顾虑。",
    "专业老师指导让用户觉得低门槛学习仍然有可靠的学习支持。"
  ]
}
```

判定要点：当广告主体持续解决“你是否适合 / 是否能开始”时，解除 Barrier 本身可以成为 Primary Driver。

---

### v10

#### V2.1a 基线

```text
Opening Type: 教学演示型
Opening Alternative: 演唱效果型
User Expectation: 掌握简单方法
Primary Values:
- 方法简单易操作
- 正确发声并保护嗓音
Supporting Values:
- 获得演唱效果参照
- 零基础可学
- 降低年龄焦虑
```

#### V2.1b GT

```json
{
  "primary_driver": {
    "statement": "改掉喉咙唱歌的坏习惯并不需要复杂训练，一个简单、可以马上跟做的发声小方法，连高龄和零基础的人也能学习，让用户觉得自己同样有机会轻松掌握正确发声。",
    "confidence": "high"
  },
  "unresolved_question": {
    "statement": "这个小方法应该怎么正确练习，跟着做以后真的能帮我改掉喉咙唱歌的习惯吗？",
    "confidence": "high"
  },
  "intent_strength": "strong",
  "supporting_drivers": [
    "“94岁也能学”和“不限年龄不限基础”显著降低了年龄和基础条件带来的学习顾虑。",
    "师生同框演唱为这个简单方法提供了直观的效果参照。"
  ]
}
```

判定要点：v10 的主轴是“具体、简单的方法 → 我也能做到”；年龄适配主要用于证明方法门槛低。广告已经回答“年龄大能不能学”，因此该问题不能再次成为 Unresolved Question。

---

## 5. 关键边界总结

### 5.1 结果可复制 vs 方法可执行

- v01 / v03 / v04 / v07：主要由学习者结果与可复制性驱动；
- v02 / v08 / v10：主要由简单、可执行、可跟练的方法驱动。

### 5.2 机制揭秘 vs 方法方向

- v05：主要是“这个问题背后存在一个可理解的发声机制”；
- v06：已经进一步给出“应该怎么发声”的新方法方向。

### 5.3 Barrier 何时可以成为 Driver

- v09：广告主体持续解决年龄、基础、能否开始，因此 Barrier Reduction 本身成为 Primary Driver；
- v10：年龄与零基础主要用于证明“方法很简单”，不是主 Driver。

### 5.4 Offer 何时不能抢 Driver

v04 的后段稀缺 Offer 只能增强行动，不应覆盖前段已经成立的学员结果 Driver。

### 5.5 Unresolved Question 必须是真问题

如果广告已经明确回答一个问题，V2.1b 不得机械把它继续作为 Unresolved Question。

---

## 6. Benchmark 使用要求

1. 必须以实际 V2.1a `creative_tags.json` 作为运行输入；
2. 不允许直接把本 GT 文本塞给模型作为答案模板；
3. 不允许根据 `creative_id` hardcode；
4. 不允许为了 Seed 10/10 自动循环调参；
5. 第一轮真实运行结果必须完整保留并如实汇报；
6. 如果模型输出与 GT 不一致，应区分：
   - Prompt / 决策规则问题；
   - Schema / Evidence 约束问题；
   - 模型能力问题；
   - GT 本身存在合理边界。

达到 Spec 中的首轮 Gate 后即可冻结 V2.1b，不追求机械 10/10。
