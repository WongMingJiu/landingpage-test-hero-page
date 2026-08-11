# landingpage-test-hero-page

> 一键将「广告视频前 30 秒」转换为「落地页 Hero 区域」的多套 AI 生图设计方案。

## 项目简介

本工具是一套面向**营销设计团队**的 AI 自动化流水线，专门服务于**中老年课程**类广告视频的落地页 Hero 区域设计，支持多品类（唱歌、健康营养等）。

输入一段广告视频，工具会自动完成：

> **视频文件 → 自动截帧 → 本地 Whisper 转写 → 多模态 AI 结构化分析 → 多套不同风格的落地页生图 Prompt**

最终产出多套各具风格的生图素材包（含 Prompt + 老师参考图 + 品牌参考图），可直接喂给 AI 生图工具批量出图。

## 功能特性

- **视频前 30 秒自动截帧**：1 秒/帧，共 30 帧关键帧
- **Whisper 本地语音转写**：完全本地推理，无需上传云端，保护素材隐私
- **多模态 AI 结构化分析**：自动提取痛点 / 卖点 / 老师形象 / 歌曲列表 / 效果标签等结构化营销信息
- **多套不同风格生图 Prompt 自动生成**：温馨怀旧、活力舞台、清新简约、专业课堂、潮流时尚等多变体
- **结构化输出目录**：分析结果 / 视频素材 / 生图素材包 三层清晰分离
- **自动同步到设计管理项目**：运行结束自动复制到 `landing-page-manage` 项目对应目录，下游设计师即取即用

## 环境要求

- macOS / Linux
- Python 3.10+
- ffmpeg
- 支持多模态（图像输入）的 LLM API（OpenAI 兼容格式）

## 安装

```bash
# 1. 克隆仓库
git clone https://github.com/WongMingJiu/landingpage-test-hero-page.git
cd landingpage-test-hero-page

# 2. 安装 ffmpeg（macOS）
brew install ffmpeg
# Ubuntu/Debian: sudo apt-get install ffmpeg

# 3. 安装 Python 依赖
pip install -r requirements.txt

# 4. 复制并编辑配置
cp config.env.example config.env
# 然后编辑 config.env，填入你的 API 配置
```

> openai-whisper 首次运行会自动下载模型权重（默认 `small`，约 460MB），需要联网。

## 配置说明

编辑 `config.env`，填入以下字段：

| 字段 | 必填 | 说明 |
| --- | --- | --- |
| `API_BASE_URL` | ✅ | OpenAI 兼容 API 地址，例如 `https://api.openai.com/v1` |
| `API_KEY` | ✅ | API 密钥 |
| `MODEL_NAME` | ✅ | 多模态模型名称（**必须支持图像输入**） |
| `WHISPER_MODEL` | ❌ | Whisper 模型大小：`tiny` / `base` / `small` / `medium` / `large`，默认 `small` |
| `MAX_API_FRAMES` | ❌ | 发送给多模态 API 的最大帧数，默认 `5`（防止超出模型上下文） |
| `GENERATE_API_BASE_URL` | ❌ | 生成阶段独立的 base url，留空则复用 `API_BASE_URL` |
| `GENERATE_API_KEY` | ❌ | 生成阶段独立的 API Key，留空则复用 |
| `GENERATE_MODEL_NAME` | ❌ | 生成阶段使用的纯文本模型，留空则复用 `MODEL_NAME` |

## 使用方式

### 方式一：终端直接运行

```bash
chmod +x run.sh
./run.sh /path/to/video.mp4
```

执行流程：

```
[1/5] 截取前 30 秒关键帧
[2/5] 提取前 30 秒音频
[3/5] Whisper 本地转写
[4/5] 多模态结构化分析
[5/5] 生成落地页 Hero 生图方案
```

### 方式二：Qoder Skill 触发

在 Qoder 中打开本项目后，skill 自动加载。支持两种输入模式：

**模式 1：输入视频**（分析 + 生成 Prompt + 可选生图）
> "帮我分析这个视频生成落地页设计方案：/path/to/video.mp4"

Skill 会先执行分析流水线生成多套 Prompt 变体，完成后**询问你是否继续调用生图 API 生成图片**。

**模式 2：输入视频名称直接生图**（已有 Prompt 素材时）
> "帮我把 陈家智-xxx 的方案生成图片"
> "跑一下生图，视频名：xxx，只生成 page 1 3 5"

Skill 会直接调用 `generate_image.py` 生成落地页图片。

### 方式三：终端单独跑生图

```bash
# 全部变体
python3 generate_image.py "视频名称"

# 指定 page
python3 generate_image.py "视频名称" --pages 1 3 5
```

生成的图片保存到：`~/workspace/landing-page-manage/{品类名}/landing-page/{视频名称}/pageN.png`

## 输出结构

所有产物位于 `output/{视频名称}/` 下，按用途分为三个子目录：

```
output/{视频名称}/
├── analyse_result/              # 分析结果 + 设计方案
│   ├── analysis.json            # 结构化分析数据（痛点/卖点/老师/歌曲/效果标签…）
│   ├── landing_page_design.md   # 落地页设计方案（Markdown）
│   ├── landing_page_design.html # 设计方案可视化页面（可直接打开/分享）
│   └── teacher_ref.jpg          # 自动选帧得到的老师参考图
│
├── video_clip_result/           # 视频原始素材
│   ├── video_clip.mp4           # 前 30 秒片段
│   ├── frame_00.jpg ~ frame_29.jpg  # 30 张关键帧
│   ├── audio.wav                # 前 30 秒音频（16kHz 单声道）
│   └── transcript.txt           # Whisper 转写文本
│
└── design_refer/                # 多套生图素材包（每个变体独立目录）
    ├── page1/
    │   ├── prompt.md            # 该变体的生图 Prompt
    │   ├── teacher_ref.jpg      # 老师参考图
    │   ├── brand_reference.png  # 品牌参考图
    │   └── teacher_face_ref_*.jpg # 老师脸部三视图
    ├── page2/
    ├── ...
    └── pageN/
```

## 同步说明

每次运行结束后，`design_refer/` 内容会被**自动同步**到设计管理项目：

```
~/workspace/landing-page-manage/{品类名}/{视频名称}/
├── page1/
├── page2/
├── ...
└── pageN/
```

每个 `pageN` 文件夹都是一份**自包含**的生图素材，可直接交付给设计师或喂给 AI 生图工具批量出图。

## 技术架构

```
┌──────────┐   ┌─────────┐   ┌──────────┐   ┌──────────────┐   ┌────────────────┐   ┌──────────────────┐
│ 视频文件 │ → │ ffmpeg  │ → │ Whisper  │ → │ 多模态 AI     │ → │ 结构化 JSON     │ → │ 多套生图 Prompt   │
│  (.mp4)  │   │  截帧   │   │  本地转写│   │ 综合分析      │   │ (痛点/卖点/老师)│   │ 变体（page1~N）   │
└──────────┘   └─────────┘   └──────────┘   └──────────────┘   └────────────────┘   └──────────────────┘
                                                                                              │
                                                                                              ▼
                                                                           ┌──────────────────────────────────┐
                                                                           │ 同步到 landing-page-manage/{品类名} │
                                                                           └──────────────────────────────────┘
```

核心模块：

- [`run.sh`](run.sh) — 主入口流水线脚本
- [`transcribe.py`](transcribe.py) — 本地 Whisper ASR 转写
- [`analyze.py`](analyze.py) — 多模态结构化分析
- [`generate.py`](generate.py) — 多套落地页生图 Prompt 生成 + 同步
- `assets/categories/{category}/analyze_prompt.md` — 分析阶段品类 Prompt 模板
- `assets/categories/{category}/generate_prompt.md` — 生成阶段品类 Prompt 模板

## 常见问题

**Q1：`ffmpeg: command not found`？**
请先安装 ffmpeg，并确认在 PATH 中：`which ffmpeg`。

**Q2：Whisper 第一次运行很慢？**
首次需下载模型权重；后续缓存到 `~/.cache/whisper/`。可通过 `WHISPER_MODEL=tiny` 改用更小模型加速。

**Q3：调用多模态 API 报错 "model does not support images"？**
说明配置的 `MODEL_NAME` 不是多模态模型。请在 `config.env` 中改成支持图像输入的模型。

**Q4：API 调用超时或连接失败？**
1. 检查 API 地址可达性：`curl -I $API_BASE_URL/models`
2. 公司内网请配置代理：`export HTTPS_PROXY=http://your-proxy:port`
3. 检查 API Key 是否有效

**Q5：想跳过部分阶段单独执行？**
```bash
python3 transcribe.py   # 只跑转写
python3 analyze.py      # 只跑分析（需先有 frames + transcript）
python3 generate.py     # 只跑生成（需先有 analysis.json）
```

## License

MIT
