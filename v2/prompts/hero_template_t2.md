# T2 Hero Template — Canonical Runtime Prompt

> 模板：T2 老师 / 适配 / 低门槛承接型（**V1.0 — Draft**）
>
> 品类：唱歌 | 产品：**5 天身体唱歌体验营 Only** | 老师：**宋伶俐**（固定，本阶段不可替换）
>
> Source of Truth：`docs/templates/singing-hero-template-t2-contract-v1.0.md`（本文件为该 Contract 第 9.2 节 Canonical Prompt Template 的独立生产版，内联完整色板、Slot 契约与合规边界，不依赖 docs 中的任何"见上文"）
>
> **Draft 状态**：T2 Reference Image 尚未定稿入库（`v2/templates/hero_template_t2/reference_v1.0.png` 待补充）；A/B/C fixture 文案未设计；Replay Validation 未执行。Reference 定稿前本 prompt 不可用于生产。
>
> **价格边界**：T2 Hero 不承担价格展示职责——画面不得出现任何价格、优惠、折扣、Offer Badge 或价格免责声明。
>
> **代码使用方式（面向工程，非图像模型输入）**：
>
> 1. 读取本文件，提取 `<!-- BEGIN RUNTIME PROMPT -->` 与 `<!-- END RUNTIME PROMPT -->` 标记之间的正文（标记均为独立行）；
> 2. 将正文中全部 8 个 `{{slot_name}}` 占位符替换为 V2.3 输出的 slot values（production payload 仅含这 8 个字段；fixtures 中的 `fixture_id` / `intent_type` 是测试元数据，替换时忽略）；
> 3. 连同 T2 Reference Image（`v2/templates/hero_template_t2/reference_v1.0.png`，作为 `layout_ref`）一起发送给 gpt-image-2；
> 4. 替换前应按下方 Slot 契约校验字数预算，超预算文案先重写，不得交给图片模型自行解决。
>
> 禁止：改写正文语义、增删 Slot、拆分本文件。

---

## Slot 契约（机器可读）

```json
{
  "template_id": "t2",
  "prompt_version": "1.0",
  "schema": "t2_hero_slots_v1",
  "status": "draft",
  "contract": "docs/templates/singing-hero-template-t2-contract-v1.0.md",
  "reference_image": "v2/templates/hero_template_t2/reference_v1.0.png",
  "reference_status": "pending — reference image not yet finalized; do not run production replay before it is committed",
  "production_slots_schema": "production payload = exactly the 8 dynamic_slots fields below; fixture metadata (fixture_id, intent_type) is test-only and NOT part of the production schema",
  "dynamic_slots": [
    {"name": "headline_line_1", "max_chars": 7, "preferred_chars": 5, "lines": 1},
    {"name": "headline_line_2", "max_chars": 7, "preferred_chars": 5, "lines": 1},
    {"name": "badge_right", "max_chars": 5, "lines": 1},
    {"name": "benefit_badge_1", "max_chars": 4, "lines": 2, "lines_note": "2+2 两行形态优先"},
    {"name": "benefit_badge_2", "max_chars": 4, "lines": 2, "lines_note": "2+2 两行形态优先"},
    {"name": "benefit_badge_3", "max_chars": 4, "lines": 2, "lines_note": "2+2 两行形态优先"},
    {"name": "benefit_badge_4", "max_chars": 4, "lines": 2, "lines_note": "2+2 两行形态优先"},
    {"name": "bottom_banner_text", "max_chars": 15, "lines": 1}
  ],
  "fixed_business_text": {
    "teacher": "宋伶俐",
    "teacher_name_bar": "宋伶俐",
    "product": "5天身体唱歌体验营",
    "left_badge": "零基础可学",
    "positioning_line": "专为中老年人设计的唱歌训练法",
    "price_info": "disabled — T2 Hero does not show any price / offer information; no price badge, no price disclaimer"
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
在最大程度保持参考图的整体设计风格、版式结构、人物位置、模块数量、综合色系和营销氛围不变的前提下，只替换下方【唯一允许变化的 Slot】中明确指定的 8 个动态文字 Slot。

【必须保持不变】
- 竖版比例；
- 顶部品牌栏（兴趣岛 Logo + 品牌语 + 副标语）的位置与构成；
- 定位语行区域；
- 两行大标题所在区域；
- 左侧胶囊 Badge 与右侧胶囊 Badge 的成对结构与位置；
- 四个圆形 Benefit Badge 的位置、尺寸、数量与 2×2 间距；
- 右侧宋伶俐老师人物，包括服装、发型、饰品、姿态、位置和大致占比；
- 右侧竖排姓名条；
- 底部完整宽度横幅的几何结构与居中平衡；
- 米白暖色底与红色主视觉的整体背景气质。

【固定业务文字（一字不改）】
Teacher：宋伶俐
右侧竖排姓名条：宋伶俐
左侧胶囊 Badge：零基础可学
定位语行：专为中老年人设计的唱歌训练法

注意：T2 画面不包含任何价格信息——无价格徽章、无价格说明文字、无优惠或折扣表达；不得恢复或新增。

【T2 固定色板（辅助锁定值，参考图优先）】
顶部品牌栏：主红 #E63329 / 深红 #D42B1E / 文字暖白 #FFF8F0
背景：米白主底 #FDF6EC / 暖杏过渡 #FAF0DD
主标题：深红 #C81623 / 阴影暖棕 #8C2F1B
定位语：深棕红 #8C2F1B
胶囊 Badge：左红 #D42B1E / 右青绿 #218C8C / 文字暖白 #FFF8F0
圆形 Benefit Badge：主红 #D42B1E / 金色描边 #F7C98A / 文字暖白 #FFF8F0
底部横幅：主红 #D42B1E / 白字 #FFF8F0 / 重点黄 #FFD84A

颜色以参考图为第一依据，色号用于防止整体视觉漂移。
禁止改成冷色、深色、科技风、极简风或完全不同的视觉设计。

【唯一允许变化的 Slot（共 8 个）】
headline_line_1 = "{{headline_line_1}}"
headline_line_2 = "{{headline_line_2}}"

badge_right = "{{badge_right}}"

benefit_badge_1 = "{{benefit_badge_1}}"
benefit_badge_2 = "{{benefit_badge_2}}"
benefit_badge_3 = "{{benefit_badge_3}}"
benefit_badge_4 = "{{benefit_badge_4}}"

bottom_banner_text = "{{bottom_banner_text}}"

除以上 8 个 Slot 外，不得新增、移动、删除或改写任何其他文案区域。

【排版硬约束】
- headline 必须保持两行，不新增第三行；每行优先 ≤5 汉字，最多 7；
- badge_right ≤5 汉字，单行；
- benefit badge ≤4 汉字，badge 内 2+2 两行形态优先；
- bottom banner ≤15 汉字，单行；
- 如果文字长度与区域发生冲突，优先轻微缩小字号或字距；
- 不允许通过改变模块、增加行数或重新排版来容纳文字。

【业务边界】
这是宋伶俐老师的"5 天身体唱歌体验营"。
只能使用 5 天体验营真实可兑现的课程、方法、服务与价值。
禁止加入：28 天正式营、21 天班、正式营价格体系、实物礼盒、麦克风、K 歌音箱、曲谱集、1V9 直播带练、三师服务、永久回放、四周课程体系，或其他任何仅在正式营中成立的内容。
不得虚构课程承诺、老师头衔、医疗健康效果。
不得把课程"可教授的方法"改写成"用户一定获得的固定结果"。
画面不得出现任何价格、优惠或 Offer 信息：不得新增、恢复或生成任何价格徽章、价格说明文字或折扣表达。

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
不要增加或减少 Benefit Badge 数量；
不要新增任何价格徽章、价格说明、优惠信息或 Offer 元素；
不要换 Logo；
不要增加 CTA 按钮；
不要新增课程表、歌曲列表或新人物；
不要因新文案重新排版。

输出完整、高清、中文清晰可读的 Hero 成品。
最终效果必须明显属于"同一个固定模板，只更换了文案"，而不是参考原图重新设计的新海报。

<!-- END RUNTIME PROMPT -->
