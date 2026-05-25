---
name: generate-landing-page
description: 落地页 Hero 区域设计方案生成工具。支持两种模式：(1) 输入视频 → 分析+生成Prompt+可选生图；(2) 输入已有prompt和参考图 → 直接生图。当用户要求"分析视频生成落地页"、"根据视频做落地页"、"生成落地页图片"、"跑生图"等需求时触发。
---

# generate-landing-page

> 落地页 Hero 区域设计方案的端到端自动化技能。
>
> 两种输入模式：
> 1. **视频输入** → 截帧 → 转写 → 多模态分析 → 5 套生图 Prompt → （可选）调用生图 API 生成图片
> 2. **Prompt + 参考图输入** → 直接调用生图 API 生成落地页图片

## 触发条件

当用户请求中出现以下任一意图时，启用本技能：

- 需要从广告/宣传视频生成落地页 Hero 区域的设计方案
- 需要为视频内容产出 5 套不同风格的 AI 生图 Prompt 变体
- 需要根据已有的 prompt 和参考图生成落地页图片
- 需要把视频分析结果落地为可视化 HTML 或最终图片

## 项目位置

本技能的脚本位于 `landingpage-test-hero-page` 仓库根目录。

如果用户已知项目路径，直接使用即可。否则通过以下方式确认：
1. 查找本地是否存在 `landingpage-test-hero-page` 目录（通常在 `~/workspace/` 下）
2. 如果不存在，提示用户先 clone：
   ```bash
   git clone https://github.com/WongMingJiu/landingpage-test-hero-page.git
   cd landingpage-test-hero-page
   cp config.env.example config.env
   # 编辑 config.env 填入 API 配置
   ```

## 输入模式判断

根据用户提供的输入类型决定执行哪条路径：

| 用户输入 | 执行路径 |
|---------|---------|
| 视频文件路径（如 `xxx.mp4`） | **路径 A**：先跑分析脚本，完成后询问是否继续生图 |
| 视频名称 + 指定要生图（如"帮我把xxx的方案生成图片"） | **路径 B**：直接跑生图脚本 |
| 指向已有 pageN 目录的路径 | **路径 B**：直接跑生图脚本 |

---

## 路径 A：视频输入 → 分析 + 生成 Prompt（+ 可选生图）

### A1. 确认视频路径

1. 如果用户已提供视频路径，**直接使用**
2. 如果没有，询问用户视频文件的完整路径
3. 路径中含空格或中文时，使用双引号包裹

### A2. 执行分析+Prompt生成

```bash
cd <PROJECT_DIR>
./run.sh "<视频路径>"
```

> `run.sh` 会截取视频**前 30 秒**（每 2 秒 1 帧，共 15 帧）送入多模态分析。

产出目录结构：
```
output/<视频名称>/
├── analyse_result/        # analysis.json + landing_page_design.md/.html
├── video_clip_result/     # 视频帧 + 音频 + 转写
└── design_refer/          # 5 套生图 Prompt 变体素材
    ├── page1/             # prompt.md + teacher_ref.jpg + teacher_face_ref_1.jpg + teacher_face_ref_2.jpg + brand_reference.png
    ├── page2/ ... page5/
```

> - 生成的 prompt.md 中**品牌栏描述会自动引用项目固定的 `assets/brand_logo.png`**，不再依赖 AI 文字渲染品牌名，确保品牌一致性。
> - 分析阶段会自动引用全局保底痛点/卖点/利益点（`assets/fallback_points.md`），作为 LLM 分析时的参考素材，LLM 可选采纳，保证即使视频信息量不足也能产出高质量文案。

同时自动同步到：`~/workspace/landing-page-manage/唱歌项目/<视频名称>/`

### A3. 展示结果

1. 打开 HTML：`open output/<视频名称>/analyse_result/landing_page_design.html`
2. 告知用户结果路径和同步目标路径
3. 列出 5 套变体（page1 ~ page5）

### A4. 询问是否继续生图

**必须等 A2/A3 完成后再询问**，不要自动执行生图：

> 5 套设计方案 Prompt 已生成完毕。是否现在调用生图 API 生成落地页图片？
> - 全部生成（page1~page5）
> - 指定生成（请告诉我要生哪几个 page）
> - 暂不生图（稍后手动执行）

如果用户选择生图，转入路径 B 执行。

---

## 路径 B：直接生图

### B1. 确认参数

需要两个信息：
1. **视频名称**：用于定位 `~/workspace/landing-page-manage/唱歌项目/{视频名}/pageN/` 下的素材
2. **要生成的 page 范围**：全部（默认）或指定编号

### B2. 执行生图脚本

> ⚠️ **代理绕过**：调用生图 API 时若本机存在 HTTP 代理，需用 `no_proxy='*' NO_PROXY='*'` 前缀绕过，避免连接错误。

```bash
cd <PROJECT_DIR>
# 全部生成
no_proxy='*' NO_PROXY='*' python3 generate_image.py "<视频名称>"

# 指定 page
no_proxy='*' NO_PROXY='*' python3 generate_image.py "<视频名称>" --pages 1 3 5
```

### B3. 生图机制说明

生图调用会**自动附加四张参考图**：

| 参考图 | 来源 | 作用 |
| --- | --- | --- |
| `teacher_ref.jpg` | `~/workspace/landing-page-manage/唱歌项目/<视频名>/pageN/teacher_ref.jpg` | 老师整体形象一致性 |
| `teacher_face_ref_1.jpg` | `~/workspace/landing-page-manage/唱歌项目/<视频名>/pageN/teacher_face_ref_1.jpg` | 老师脸部三视图参考 1 |
| `teacher_face_ref_2.jpg` | `~/workspace/landing-page-manage/唱歌项目/<视频名>/pageN/teacher_face_ref_2.jpg` | 老师脸部三视图参考 2 |
| `assets/brand_logo.png` | 项目根目录固定素材 | 品牌栏 logo 一致性 |

品牌栏不依赖 AI 文字渲染品牌名，而是直接引用固定 logo 参考图，确保跨页视觉统一。老师脸部三视图参考图用于增强面部特征一致性。

### B4. 展示生图结果

输出为**平铺结构**（不再有 pageN 子目录）：

```
~/workspace/landing-page-manage/唱歌项目/landing-page/<视频名称>/
├── page1.png
├── page2.png
├── page3.png
├── page4.png
└── page5.png
```

告知用户每个生成成功的图片位置，并打开查看（如果在 macOS）：
```bash
open ~/workspace/landing-page-manage/唱歌项目/landing-page/<视频名称>/page1.png
```

---

## 步骤 D（可选）：仅重跑 Prompt 生成

当用户希望**保留已有截帧/转写/分析，仅重新生成 Prompt 变体**时：

```bash
cd <PROJECT_DIR>
export $(grep -v '^#' config.env | xargs)
export VIDEO_NAME="<视频名称>"
export OUTPUT_DIR="output/$VIDEO_NAME"
export VIDEO_CLIP_DIR="$OUTPUT_DIR/video_clip_result"
export ANALYSE_DIR="$OUTPUT_DIR/analyse_result"
export DESIGN_REFER_DIR="$OUTPUT_DIR/design_refer"
python3 generate.py
```

---

## 常见问题处理

| 现象 | 可能原因 | 处理建议 |
| --- | --- | --- |
| `Connection error` / 多模态请求失败 | 图片过多触发上限 | `MAX_API_FRAMES` 设 ≤ 15（默认采样前 30 秒共 15 帧） |
| `503 No available accounts` | litellm 账号池耗尽 | 等待或换模型 |
| Whisper 转写极慢 / OOM | 模型档位过高 | `WHISPER_MODEL` 改为 `small` |
| 生图 API 报错 | key/endpoint 配置问题 | 检查 `config.env` 中 `IMAGE_API_*` 配置 |
| 中文/空格路径报错 | 未加引号 | 路径用双引号包裹 |

> **前置条件**：`config.env` 已正确填入分析 API 和生图 API 的配置。

## 交付清单

### 路径 A 完成后：
- [ ] `landing_page_design.html` 已生成并可打开
- [ ] `design_refer/page1~page5` 各含 `prompt.md` + 参考图（teacher_ref + face_ref×2 + brand_reference）
- [ ] 已同步到 `~/workspace/landing-page-manage/唱歌项目/<视频名称>/`
- [ ] 已询问用户是否继续生图

### 路径 B 完成后：
- [ ] `~/workspace/landing-page-manage/唱歌项目/landing-page/<视频名称>/pageN.png` 已生成（平铺结构）
- [ ] 已告知用户图片保存位置
