# Creative Intent V1

## 1. 目的

Creative Intent 是广告素材与落地页策略之间的中间决策层。

它不负责重新总结素材，也不负责直接生成 Hero 文案；它负责从现有素材分析结果中回答：

> **这条广告真正依靠什么核心说服命题，让用户觉得“这跟我有关 / 我想继续了解”，以及用户点击后还期待页面继续回答什么。**

现有 `analysis.json` 中的痛点、卖点、利益点、老师、色彩、构图、AIDA 等信息继续保留。Creative Intent 负责在这些信息之上做“选择与裁决”。

---

## 2. 基础原则

### 2.1 标签用于解释，Primary Driver Statement 用于决策

一条素材可以同时命中多个需求、障碍和说服机制，但线上页面必须有一个主要承接方向。

因此：

- `core_need`、`barriers`、`persuasion_drivers`、`trust_drivers`、`offer_drivers`：允许多标签；
- `primary_driver.statement`：必须唯一；
- 不强迫某一个单独标签承担全部 Creative Intent。

例如：

```text
Core Need：突破高音
Persuasion Driver：纠正错误唱歌认知
Primary Driver Statement：高音唱不上去，不一定是嗓子条件差，而可能是发声方法不对
```

真正用于 Hero 承接的是最后这一条完整命题。

### 2.2 Opening Strategy 不等于 Primary Driver

必须区分三层：

```text
Opening Strategy
= 广告怎么把人拦下来

Primary Driver
= 什么核心命题让用户觉得值得继续了解

Post-click Expectation
= 点击之后用户还期待页面继续给什么
```

“别划走”“50 岁以上注意”等强拦截话术可以属于 Opening Strategy，但默认不能成为 Primary Driver。

### 2.3 真正必须唯一的是 Driver Statement，不是 Core Need 标签

部分广告只解决一个明确需求，例如“正确发声”；部分广告会同时覆盖大白嗓、气息、高音、音域转换等多个问题。

因此 `core_need` 支持：

- `specific`：明确单一/少量具体需求；
- `broad`：系统解决一组相关问题。

禁止为了强行单选而制造假精确。

### 2.4 Creative Intent 必须保留多模态输入

仅依赖转写脚本不足以判断所有广告的点击动机，尤其是：

- 演唱效果展示；
- 学员 / 老师身份；
- 师生互动；
- 动作演示；
- 前后效果对比；
- 画面大字 / 标题卡。

因此正式实现不得退化成纯 transcript classifier。

---

## 3. 标签角色

现有唱歌标签体系继续复用，不重新造一套平行标签。不同标签按照其决策作用拆成以下角色。

### 3.1 Core Need

回答：**用户最终想解决什么问题 / 得到什么变化？**

主要包括：

- 演唱能力类；
- 心理突破类；
- 社交与自我表达价值类。

例如：

- 稳定气息；
- 改善音色与声音质感；
- 正确发声并保护嗓音；
- 突破高音；
- 改善音准；
- 增强情感表达；
- 掌握通用演唱能力；
- 敢于开口演唱；
- 建立演唱自信。

### 3.2 Barrier

回答：**用户为什么觉得自己学不会 / 不适合 / 不方便开始？**

例如：

- 降低年龄焦虑；
- 降低天赋与嗓音条件焦虑；
- 零基础可学；
- 方法简单易操作；
- 降低乐理与理解门槛；
- 降低时间地点限制；
- 支持反复学习；
- 获得辅导答疑。

### 3.3 Persuasion Driver

回答：**广告通过什么认知或证明机制，让用户相信这个问题有解？**

例如：

- 识别自身唱歌问题；
- 纠正错误唱歌认知；
- 理解发声原理；
- 明确问题解决路径；
- 获得演唱效果参照；
- 获得可复制学习范例。

### 3.4 Trust Driver

回答：**为什么用户应该相信老师 / 方法 / 课程？**

例如：

- 获得专业指导；
- 获得效果与服务保障；
- 减少试错与选择成本。

老师头衔、教学年限通常属于 Trust / Evidence，默认不升级成 Primary Driver；只有素材主体本身围绕老师身份或权威故事展开时才可能成为核心命题。

### 3.5 Offer Driver

回答：**什么权益或机会推动用户现在行动？**

例如：

- 获得课程与学习资源；
- 便捷领取并快速开始；
- 把握限时稀缺机会；
- 明确学习入口。

结尾 CTA 本身不等于 Primary Driver。只有广告主体持续围绕免费、稀缺、资格、领取机会等展开，Offer 才可能成为核心驱动力。

---

## 4. 推荐 Schema V1

```json
{
  "creative_intent": {
    "opening_strategy": {
      "label": "方法演示型",
      "summary": "开场直接展示用身体力量发声的动作"
    },

    "core_need": {
      "scope": "specific",
      "labels": ["正确发声并保护嗓音"],
      "summary": "希望改善只靠嗓子挤压发声的问题"
    },

    "barriers": ["方法简单易操作"],
    "persuasion_drivers": ["纠正错误唱歌认知", "理解发声原理"],
    "trust_drivers": [],
    "offer_drivers": [],

    "primary_driver": {
      "statement": "唱歌不是靠嗓子挤，而是可以借身体力量把声音送出去",
      "unresolved_question": "那具体要怎么用身体把声音送出去？",
      "evidence": [
        {
          "time": "0-7s",
          "content": "用后腰的力量把声音送出去，不是用嗓子挤出来",
          "role": "reframe"
        }
      ]
    },

    "post_click_expectation": ["理解专业原理", "掌握简单方法"],

    "hero_continuation": "继续解释为什么不能只靠嗓子唱，并给出身体发声这一可学习方向",

    "confidence": 0.97
  }
}
```

---

## 5. Primary Driver 决策规则 V0.1

### 5.1 候选来源

从以下信息中形成候选核心命题：

- 前段 Hook / 开场大字；
- 具体痛点与欲望；
- Barrier；
- Persuasion Driver；
- Trust Evidence；
- Offer；
- 演示 / 案例 / 结果证明；
- CTA 前仍未完成的核心问题。

### 5.2 六个判断维度

| 维度 | 判断问题 | 参考权重 |
| --- | --- | ---: |
| Hook Centrality | 是否位于开场核心位置？ | 25% |
| Problem Relevance | 用户是否容易觉得“说的就是我”？ | 20% |
| Persuasion Centrality | 后续内容是否围绕它展开？ | 20% |
| Post-click Continuity | 点击后是否仍自然期待继续得到答案？ | 15% |
| Evidence Strength | 是否有演示、案例、画面或结果强化？ | 10% |
| Repetition / Emphasis | 是否反复强调、字幕放大、重读？ | 10% |

权重用于帮助模型做比较，不要求实现为严格数学公式。

### 5.3 五条硬规则

#### Rule 1：强拦截词本身不能成为 Primary Driver

例如“别划走”“50 岁以上注意”“我只说一次”等仅属于 Attention / Opening Strategy。

#### Rule 2：纯 CTA 默认不能覆盖主体 Driver

“点击领取”“免费领课”等若只出现在结尾，属于 Offer / Action，而不是核心点击动机。

#### Rule 3：老师身份通常是 Evidence，不默认是 Driver

“国家一级演员”“30 年经验”等通常负责建立信任。只有素材主体围绕老师身份、经历或权威故事展开时才升级为核心命题。

#### Rule 4：具体问题优先于泛化结果

当“突破高音”与“唱歌更好听”同时存在时，优先保留信息量更高、与用户自我识别更强的具体问题；除非素材本身明确是系统解决方案型。

#### Rule 5：必须形成一个明确的悬而未决问题

Primary Driver 必须能自然推导出：

> **用户点进去时，脑子里还挂着什么问题？**

如果无法形成明确问题，说明 Driver 通常过于宽泛或只是素材中的辅助信息。

---

## 6. Post-click Expectation 自校验

`post_click_expectation` 不只是输出字段，也是 Primary Driver 的校验器。

要求：

> **Primary Driver 必须能够自然解释为什么用户会产生该 Post-click Expectation。**

例如：

```text
Opening Strategy：知识 / 方法型
Primary Driver：唱高音不是靠喊，而是发声方法不对
Post-click Expectation：理解专业原理 / 掌握简单方法
```

逻辑一致，置信度可以较高。

反例：

```text
Primary Driver：免费领取课程
Post-click Expectation：理解专业原理
```

如果素材主体并未围绕课程权益展开，应重新裁决 Primary Driver。

---

## 7. 首轮真实样本得到的 Driver Cluster

首批 10 条唱歌素材人工验证后，暂时观察到以下五类真实 Driver Cluster：

1. **方法揭秘 / 认知纠偏**：原来唱歌可以通过另一种更简单、更符合身体机制的方法完成；
2. **结果证明 / 可复制效果**：别人能做到，我也可能做到；
3. **低门槛 / 人群适配**：年龄大、零基础、时间少也可以开始；
4. **系统解决方案**：不是只解决一个唱歌问题，而是一套课程系统提升多项能力；
5. **Offer / 稀缺权益**：核心诉求就是抓住当下领取 / 报名机会。

这些 Cluster 是样本观察结果，不作为固定 taxonomy；后续随着样本扩充持续调整。

---

## 8. Phase 1 验收目标

Creative Intent V1 的目标不是做出一个“标签很全”的分类器，而是产出一个足够稳定、可解释、能进入线上实验的决策层。

建议首轮 Benchmark 关注：

- Primary Driver Statement 是否与人工判断一致；
- Core Need 的 specific / broad 判断是否合理；
- Post-click Expectation 是否自然；
- Hero Continuation 是否真正接住原广告；
- Evidence 是否足以让业务人员快速判断模型为什么这么选。

进入 Phase 2 前，至少应做到：

- 大多数素材能收敛到唯一 Driver Statement；
- 同类素材输出逻辑稳定；
- 业务人工能够快速判断对错；
- 模型错误能够被具体归因为：Need、Barrier、Persuasion、Evidence 或 Driver 裁决错误，而不是“整体感觉不对”。

---

## 9. 推荐实现方式

首版不建议继续膨胀现有 `analyze_prompt.md`。

推荐增加独立的 Intent Decision Stage：

```text
广告视频多模态信息
        +
现有 analysis.json
        ↓
Intent Decision
        ↓
creative_intent.json
```

建议新增：

```text
assets/categories/singing/intent_prompt.md
```

在 10 条人工 Benchmark 上稳定后，再决定是否长期保留独立 Stage，或合并回主分析流程。
