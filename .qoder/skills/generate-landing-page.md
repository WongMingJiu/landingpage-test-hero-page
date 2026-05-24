---
name: generate-landing-page
description: 从广告视频自动生成落地页 Hero 区域设计方案（5套生图Prompt变体）。当用户要求"分析视频并生成落地页设计方案"、"根据广告视频做落地页"、"生成 Hero 区域 Prompt 变体"或类似需求时触发。
---

# generate-landing-page

> 视频广告 → 落地页 Hero 区域设计方案的自动化技能。
>
> 输入一个广告视频文件，自动完成：截帧 → 转写 → 多模态分析 → 5 套生图 Prompt 变体 → 结构化输出 → 同步到下游项目。

## 触发条件

当用户请求中出现以下任一意图时，启用本技能：

- 需要从广告/宣传视频生成落地页 Hero 区域的设计方案
- 需要为视频内容产出 5 套不同风格的 AI 生图 Prompt 变体
- 需要把视频分析结果（痛点 / 卖点 / 老师形象等）落地为可视化 HTML
- 需要把生成的素材同步到 `landing-page-manage/唱歌项目/` 下

## 项目位置

```
/Users/huangmingyao/workspace/landingpage-test-hero-page
```

## 执行流程

### 步骤 A：确认视频路径

1. 如果用户在请求中已经提供了视频路径（如 `/path/to/xxx.mp4`），**直接使用**，不要再询问。
2. 如果没有提供，向用户询问：
   > 请提供需要分析的广告视频文件的完整路径（支持 mp4/mov 等格式，路径可以包含中文与空格）。
3. 路径中含有空格或中文时，必须使用双引号包裹。

### 步骤 B：执行完整流程

切换到项目根目录，使用 `run.sh` 一键完成全部流程（截帧 → 转写 → 分析 → 生成）：

```bash
cd /Users/huangmingyao/workspace/landingpage-test-hero-page
./run.sh "<视频路径>"
```

> 注意：`run.sh` 会自动从 `config.env` 加载 API 配置，并按视频文件名（去后缀）创建 `output/<视频名称>/` 子目录。

执行过程中产出的标准目录结构：

```
output/<视频名称>/
├── analyse_result/        # 分析结果（含 landing_page_design.md / .html）
├── video_clip_result/     # 视频帧（前 15 秒，1 秒/帧）与抽取的音频
└── design_refer/          # 5 套生图 Prompt 变体素材
    ├── page1/             # prompt.txt + teacher_ref.jpg + brand_reference.png
    ├── page2/
    ├── ...
    └── page5/
```

### 步骤 C：展示结果

1. 打开生成的 HTML 可视化结果：

   ```bash
   open output/<视频名称>/analyse_result/landing_page_design.html
   ```

2. 主动告知用户以下两个关键路径：

   - **本地结果目录**：
     `/Users/huangmingyao/workspace/landingpage-test-hero-page/output/<视频名称>/`
   - **同步目标位置**（下游 landing-page-manage 项目）：
     `~/workspace/landing-page-manage/唱歌项目/<视频名称>/`

3. 简要列出 5 套变体（page1 ~ page5）所在的 `design_refer/pageN/` 路径，便于用户直接拷贝使用。

### 步骤 D（可选）：仅重跑生成阶段

当用户希望**保留已有的截帧/转写/分析结果，仅重新生成 Prompt 变体**时（例如调整了 `prompts/generate_prompt.md` 之后），不要重跑 `run.sh`，改用：

```bash
cd /Users/huangmingyao/workspace/landingpage-test-hero-page
export $(grep -v '^#' config.env | xargs)
export VIDEO_NAME="<视频名称>"
export OUTPUT_DIR="output/$VIDEO_NAME"
export VIDEO_CLIP_DIR="$OUTPUT_DIR/video_clip_result"
export ANALYSE_DIR="$OUTPUT_DIR/analyse_result"
export DESIGN_REFER_DIR="$OUTPUT_DIR/design_refer"
python3 generate.py
```

这一步只调用文本生成 API，不会重新调用多模态分析，可显著节省 token 与时间。

## 常见问题处理

| 现象 | 可能原因 | 处理建议 |
| --- | --- | --- |
| `Connection error` / 多模态请求失败 | 上传图片过多触发上下文/网络上限 | 检查 `config.env` 中 `MAX_API_FRAMES` 配置（建议 ≤ 5），降低关键帧数量后重试 |
| `503 No available accounts` | litellm 账号池暂时耗尽 | 等待几分钟重试；或在 `config.env` 中切换到其他可用模型组 |
| Whisper 转写极慢 / OOM | 模型档位过高 | 将 `WHISPER_MODEL` 调整为 `base` 或 `small` |
| 中文/空格路径报错 | 未加引号 | 视频路径用双引号包裹，并使用 `${VAR%.*}` 安全去后缀 |
| 同步目标目录不存在 | 下游项目未初始化 | 确认 `~/workspace/landing-page-manage/唱歌项目/` 父目录存在，脚本会自动创建子目录 |

> **前置条件**：执行前请确认 `config.env` 已基于 `config.env.example` 正确填入 API Key、Base URL 与多模态模型名称等三要素配置。

## 交付清单（执行结束时反馈给用户）

- [ ] `output/<视频名称>/analyse_result/landing_page_design.html` 已生成并可在浏览器中打开
- [ ] `output/<视频名称>/design_refer/page1` ~ `page5` 各自包含 `prompt.txt` + `teacher_ref.jpg` + `brand_reference.png`
- [ ] `~/workspace/landing-page-manage/唱歌项目/<视频名称>/` 下已同步 5 套变体目录
