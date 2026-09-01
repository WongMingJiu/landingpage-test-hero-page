# T1 Hero Template — Canonical Runtime Prompt

> 模板：T1 问题 / 方法 / 四利益卡承接型（Frozen V1.0）
>
> 品类：唱歌 | 产品：**5 天身体唱歌体验营 Only** | 老师：**宋伶俐**（固定，本阶段不可替换）
>
> Source of Truth：`docs/templates/singing-hero-template-t1-contract-v1.0.md`（本文件为该 Contract 第 9.2 节 Canonical Prompt Template 的独立生产版，内联完整色板、Slot 契约与合规边界，不依赖 docs 中的任何"见上文"）
>
> **代码使用方式（面向工程，非图像模型输入）**：
>
> 1. 读取本文件，提取 `<!-- BEGIN RUNTIME PROMPT -->` 与 `<!-- END RUNTIME PROMPT -->` 标记之间的正文；
> 2. 将正文中全部 12 个 `{{slot_name}}` 占位符替换为 V2.3 输出的 slot values；
> 3. 连同 T1 Canonical Reference Image（作为 `layout_ref`，由调用方传入，仓库不内嵌该图片资产）一起发送给 gpt-image-2；
> 4. 替换前应按下方 Slot 契约校验字数预算，超预算文案先重写，不得交给图片模型自行解决。
>
> 禁止：改写正文语义、增删 Slot、拆分本文件。

---

## Slot 契约（机器可读）

```json
{
  "template_id": "t1",
  "prompt_version": "1.0",
  "schema": "t1_hero_slots_v1",
  "dynamic_slots": [
    {"name": "headline_line_1", "max_chars": 7, "preferred_chars": 6, "lines": 1},
    {"name": "headline_line_2", "max_chars": 7, "preferred_chars": 6, "lines": 1},
    {"name": "subheadline", "max_chars": 16, "lines": 1},
    {"name": "benefit_1_title", "max_chars": 5, "lines": 1},
    {"name": "benefit_1_desc", "max_chars": 11, "lines": 1, "lines_note": "1 行为优先"},
    {"name": "benefit_2_title", "max_chars": 5, "lines": 1},
    {"name": "benefit_2_desc", "max_chars": 11, "lines": 1, "lines_note": "1 行为优先"},
    {"name": "benefit_3_title", "max_chars": 5, "lines": 1},
    {"name": "benefit_3_desc", "max_chars": 11, "lines": 1, "lines_note": "1 行为优先"},
    {"name": "benefit_4_title", "max_chars": 5, "lines": 1},
    {"name": "benefit_4_desc", "max_chars": 11, "lines": 1, "lines_note": "1 行为优先"},
    {"name": "bottom_banner_text", "max_chars": 15, "lines": 1}
  ],
  "fixed_business_text": {
    "teacher": "宋伶俐",
    "teacher_name_bar": "宋伶俐",
    "product": "5天身体唱歌体验营",
    "price_badge": "1元",
    "price_disclaimer": "此价格为5天体验/试学课价格，具体收费以实际课程信息为准"
  }
}
```

字数处理原则（生成侧，V2.3 责任）：超预算时**先重写文案** → 其次轻微压缩字距 → 最后才允许轻微缩字号；不允许通过改变模块、增加行数或重排版来容纳文案。

---

<!-- BEGIN RUNTIME PROMPT -->

请基于我提供的参考图，对这张唱歌课程 Hero 海报进行"固定模板下的局部文案替换式重绘"。

这不是重新设计新海报。
参考图是本次任务的**版式真值与视觉真值**：所有版式、结构、人物、色系均以参考图为第一依据，下述色号仅用于防止整体视觉漂移。

【核心目标】
在最大程度保持参考图的整体设计风格、版式结构、人物位置、模块数量、综合色系和营销氛围不变的前提下，只替换下方【唯一允许变化的 Slot】中明确指定的 12 个动态文字 Slot。

【必须保持不变】
- 竖版比例；
- 顶部兴趣岛 / 兴趣学堂 Logo；
- 两行大标题所在区域；
- 单行副标题区域；
- 左侧 4 个利益卡片的位置、数量、尺寸和圆形音乐图标；
- 右侧宋伶俐老师人物，包括服装、发型、饰品、姿态、位置和大致占比；
- 右侧竖排姓名条"宋伶俐"；
- 底部大型横幅的几何结构；
- 右下"1元"价格徽章；
- 红橙暖色背景、音乐元素与金色高光；
- 底部价格说明区域。

【固定业务文字（一字不改）】
Teacher：宋伶俐
右侧姓名条：宋伶俐
Price Badge：1元
底部价格说明：此价格为5天体验/试学课价格，具体收费以实际课程信息为准

注意：底部价格说明不得回退或改写为"7 天体验/试学课"等历史口径，必须保持上述 5 天版本原文。

【T1 固定色板（辅助锁定值，参考图优先）】
背景：主红橙 #F24A3A / 中间暖橙 #F57A45 / 浅橙高光 #F6A05A / 浅杏橙 #FFD4A6
主标题：浅金白 #FFF0D8 / 高光白 #FFF8EE / 暖金描边 #E8A15A / 暖棕金阴影 #C97C3C
副标题：主橙红 #F45A2A / 暖白 #FFF8F0
利益卡：图标主红 #E53922 / 图标深红 #C92C1B / 卡片浅米 #FFF1E5 / 卡片浅金描边 #F7C98A / 标题深暖红 #C92C1B / 说明暖深棕 #7A3323
底部横幅：主红 #E3361E / 高光红橙 #F25A2D / 白字 #FFF8F0 / 重点黄 #FFD84A
价格徽章：主红 #D92F1A / 亮红 #F25A2D / 数字黄 #FFD84A / 黄色高光 #FFF09A / "元"字暖白 #FFF8F0
装饰：暖白 #FFF8F0 / 浅金 #F9D28B / 暖棕 #A85D2A

颜色以参考图为第一依据，色号用于防止整体视觉漂移。
禁止改成冷色、深色、科技风、极简风或完全不同的视觉设计。

【唯一允许变化的 Slot（共 12 个）】
headline_line_1 = "{{headline_line_1}}"
headline_line_2 = "{{headline_line_2}}"
subheadline = "{{subheadline}}"

benefit_1_title = "{{benefit_1_title}}"
benefit_1_desc = "{{benefit_1_desc}}"
benefit_2_title = "{{benefit_2_title}}"
benefit_2_desc = "{{benefit_2_desc}}"
benefit_3_title = "{{benefit_3_title}}"
benefit_3_desc = "{{benefit_3_desc}}"
benefit_4_title = "{{benefit_4_title}}"
benefit_4_desc = "{{benefit_4_desc}}"

bottom_banner_text = "{{bottom_banner_text}}"

除以上 12 个 Slot 外，不得新增、移动、删除或改写任何其他文案区域。

【排版硬约束】
- headline 必须保持两行，不新增第三行；每行优先 ≤6 汉字，最多 7；
- subheadline ≤16 汉字，单行；
- benefit title ≤5 汉字，单行；
- benefit desc ≤11 汉字，一行为优先；
- bottom banner ≤15 汉字，单行；
- 如果文字长度与区域发生冲突，优先轻微缩小字号或字距；
- 不允许通过改变模块、增加行数或重新排版来容纳文字。

【业务边界】
这是宋伶俐老师的"5 天身体唱歌体验营"。
只能使用 5 天体验营真实可兑现的课程、方法、服务与价值。
禁止加入：28 天正式营、21 天班、正式营价格体系、实物礼盒、麦克风、K 歌音箱、曲谱集、1V9 直播带练、三师服务、永久回放、四周课程体系，或其他任何仅在正式营中成立的内容。
不得虚构课程承诺、老师头衔、医疗健康效果。
不得把课程"可教授的方法"改写成"用户一定获得的固定结果"。

【合规边界（违禁表达，一律禁止）】
- 全国领先 / 全国第一 / 第一 / 唯一 / 首席；
- 最好 / 最佳 / 最强 / 顶级 / 顶尖；
- 万能 / 保证 / 保证效果 / 包教包会 / 包学会 / 100%；
- 速成 / 立竿见影；
- 医疗治疗 / 疾病改善 / 抗衰 / 防病等健康疗效表达；
- 不买后悔 / 错过再无等恐惧诱导；
- 立即点击 / 马上领取等强按钮 CTA 表达，不新增任何 CTA 按钮。

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
最终效果必须明显属于"同一个固定模板，只更换了文案"，而不是参考原图重新设计的新海报。

<!-- END RUNTIME PROMPT -->
