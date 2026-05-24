# landingpage-test-hero-page

> 一键将「广告视频前 15 秒」转换为一份可直接落地的「落地页 Hero 区域设计方案」。

## 项目简介

本工具针对一段广告视频，自动完成以下流程：

1. **截帧**：使用 ffmpeg 截取前 15 秒内 5 张关键帧（0s / 3s / 6s / 9s / 12s）
2. **音频提取 + 本地 ASR**：用 ffmpeg 抽取前 15 秒音频，再用本地 Whisper 模型转写口播
3. **多模态分析**：将 5 张帧 + 口播文字打包给多模态大模型，提取结构化营销信息（色调、老师、痛点、卖点、利益、辅助说明等）
4. **生成落地页设计方案**：基于结构化分析数据，调用 LLM 生成 Hero 区域的设计思路、页面结构、文案、生图 Prompt
5. **可视化**：同时输出一份美观的 HTML，可直接打开/分享给团队成员

## 目录结构

```
landingpage-test-hero-page/
├── run.sh                       # 主入口脚本
├── transcribe.py                # 本地 Whisper ASR
├── analyze.py                   # 多模态分析
├── generate.py                  # 生成落地页设计 (md + html)
├── prompts/
│   ├── analyze_prompt.md
│   └── generate_prompt.md
├── config.env                   # API 配置
├── requirements.txt
└── README.md
```

## 环境准备

### 1. 安装 ffmpeg

```bash
# macOS
brew install ffmpeg

# Ubuntu/Debian
sudo apt-get install ffmpeg

# Windows (Chocolatey)
choco install ffmpeg
```

### 2. 安装 Python 依赖

建议 Python 3.10+。

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

> openai-whisper 首次运行会自动下载模型权重（默认 `small`，约 460MB），需要联网。

## 配置说明

复制并编辑 `config.env`，填入你的 API 信息：

| 字段 | 说明 |
| --- | --- |
| `API_BASE_URL` | OpenAI 兼容 API 的 base url，例如 `https://api.openai.com/v1` |
| `API_KEY` | API Key |
| `MODEL_NAME` | 使用的多模态模型名称（必须支持图像输入） |
| `GENERATE_API_BASE_URL` | （可选）生成阶段使用的独立 base url，留空则复用上面的 `API_BASE_URL` |
| `GENERATE_API_KEY` | （可选）生成阶段使用的独立 Key，留空则复用 |
| `GENERATE_MODEL_NAME` | （可选）生成阶段使用的纯文本模型；留空则复用 `MODEL_NAME` |
| `WHISPER_MODEL` | 本地 Whisper 模型：`tiny` / `base` / `small` / `medium` / `large`，默认 `small` |

## 使用方法

```bash
chmod +x run.sh
./run.sh /path/to/your_video.mp4
```

执行流程示意：

```
[1/4] 截取关键帧
[2/4] 提取前 15 秒音频
[3/4] Whisper 转写
[4/4] 多模态分析
[5/5] 生成落地页设计方案
```

## 输出文件说明

所有产物位于 `output/` 目录：

| 文件 | 说明 |
| --- | --- |
| `frames/frame_00.jpg ~ frame_04.jpg` | 5 张关键帧 |
| `audio.wav` | 前 15 秒音频（16kHz 单声道 PCM） |
| `transcript.txt` | 口播转写文本 |
| `analysis.json` | 结构化分析结果（颜色、老师、痛点、卖点、利益、辅助说明等） |
| `landing_page_design.md` | 落地页 Hero 设计方案（Markdown） |
| `landing_page_design.html` | 设计方案的可视化页面（独立 HTML，含内联 CSS，可直接双击打开） |
| `analysis_raw.txt` | （仅当 JSON 解析失败时生成）模型原始返回 |

## 常见问题

**Q1：运行 `./run.sh` 报 `ffmpeg: command not found`？**
请先安装 ffmpeg，并确认在 PATH 中：`which ffmpeg`。

**Q2：Whisper 第一次运行很慢？**
首次需下载模型权重；后续会缓存到本地 `~/.cache/whisper/`。可通过 `WHISPER_MODEL=tiny` 改用更小的模型加快速度。

**Q3：调用多模态 API 报错 "model does not support images"？**
说明你配置的 `MODEL_NAME` 不是多模态模型。请在 `config.env` 中改成支持图像输入的模型。

**Q4：`analyze.py` 报 JSON 解析失败？**
脚本已尽量兼容 ```` ```json ```` 包裹的返回；如仍失败，可查看 `output/analysis_raw.txt` 中模型的原始返回，确认是否被截断或包含额外文字。

**Q5：HTML 渲染样式简陋？**
若未安装 `markdown` 库，会回退到内置极简渲染。建议确保 `pip install markdown` 已安装。

**Q6：想跳过部分阶段？**
可单独执行：
```bash
python3 transcribe.py   # 只跑转写
python3 analyze.py      # 只跑分析（需先有 frames + transcript）
python3 generate.py     # 只跑生成（需先有 analysis.json）
```

**Q7：HTTPS 调用失败、网络不稳定？**
`analyze.py` 与 `generate.py` 均带 3 次指数退避重试。若依然失败，请检查代理 / `API_BASE_URL` 是否正确。

**Q8：API 调用超时或连接失败？**

1. 检查 API 地址是否可访问：
   ```bash
   curl -I https://llm.gw.dachensky.com/v1/models
   ```
2. 如在公司内网，设置代理：
   ```bash
   export HTTPS_PROXY=http://your-proxy:port
   ```
3. 检查 API Key 是否有效
