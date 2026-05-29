#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
落地页设计方案生成脚本
- 读取 ANALYSE_DIR/analysis.json
- 使用 prompts/generate_prompt.md 作为 system prompt
  (将占位符 analysis_json 替换为实际的 JSON 字符串)
- 调用 OpenAI 兼容 API（纯文本）
- 输出 ANALYSE_DIR/landing_page_design.md
- 同时生成 ANALYSE_DIR/landing_page_design.html（含内联 CSS，独立可打开）
- 解析 markdown 中的 5 个变体，将每个变体的 Prompt 文本及参考素材
  保存到 DESIGN_REFER_DIR/pageN/

环境变量：
  API_BASE_URL / API_KEY / MODEL_NAME
  可选覆盖：GENERATE_API_BASE_URL / GENERATE_API_KEY / GENERATE_MODEL_NAME
  路径环境变量（由 run.sh 注入）：
    VIDEO_CLIP_DIR  - 帧/音频/视频片段/转写所在目录
    ANALYSE_DIR     - analysis.json + 设计方案 MD/HTML 输出目录
    DESIGN_REFER_DIR - 各变体素材输出根目录
"""

import base64
import html
import json
import os
import re
import shutil
import sys
import time
from typing import List, Tuple


SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# ---- 路径配置（优先取环境变量，回退到旧布局）----
VIDEO_CLIP_DIR = os.environ.get("VIDEO_CLIP_DIR", "").strip() or os.path.join("output", "frames")
ANALYSE_DIR = os.environ.get("ANALYSE_DIR", "").strip() or "output"
DESIGN_REFER_DIR = os.environ.get("DESIGN_REFER_DIR", "").strip() or os.path.join("output", "design_refer")

ANALYSIS_PATH = os.path.join(ANALYSE_DIR, "analysis.json")
PROMPT_PATH = os.path.join("prompts", "generate_prompt.md")
MD_OUT = os.path.join(ANALYSE_DIR, "landing_page_design.md")
HTML_OUT = os.path.join(ANALYSE_DIR, "landing_page_design.html")
TEACHER_REF_PATH = os.path.join(ANALYSE_DIR, "teacher_ref.jpg")

BRAND_REFERENCE_SRC = os.path.join(SCRIPT_DIR, "assets", "brand_reference.png")
TEACHER_FACE_REF_1 = os.path.join(SCRIPT_DIR, "assets", "teacher_face_ref_1.jpg")
TEACHER_FACE_REF_2 = os.path.join(SCRIPT_DIR, "assets", "teacher_face_ref_2.jpg")

MAX_RETRIES = 3


def read_text(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def describe_teacher_outfit(image_path: str, api_base: str, api_key: str, model: str) -> str:
    """调用多模态模型，对老师参考图进行视觉描述，返回一句话着装描述。

    使用 OpenAI 兼容的多模态消息格式（content 数组中包含 image_url），
    图片使用 base64 内联编码。
    """
    try:
        from openai import OpenAI  # type: ignore
    except ImportError as e:
        raise RuntimeError(f"未安装 openai 库: {e}")

    if not os.path.isfile(image_path):
        raise RuntimeError(f"参考图不存在: {image_path}")

    # API Base URL 规范化（与 call_api 一致）
    if not api_base.rstrip('/').endswith('/v1'):
        api_base = api_base.rstrip('/') + '/v1'

    # 读取并 base64 编码
    with open(image_path, "rb") as f:
        img_b64 = base64.b64encode(f.read()).decode("utf-8")
    ext = os.path.splitext(image_path)[1].lower().lstrip(".") or "jpeg"
    if ext == "jpg":
        ext = "jpeg"
    data_url = f"data:image/{ext};base64,{img_b64}"

    client = OpenAI(api_key=api_key, base_url=api_base)
    system_msg = (
        "请用一句话简洁描述图片中人物的着装，包括：服装颜色、款式、配饰。"
        "只描述着装，不要描述其他内容。"
    )
    messages = [
        {"role": "system", "content": system_msg},
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "请用一句中文描述这位人物的着装。"},
                {"type": "image_url", "image_url": {"url": data_url}},
            ],
        },
    ]

    last_err: Exception | None = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            print(f"[generate] 调用视觉预处理 API (第 {attempt}/{MAX_RETRIES} 次)，模型: {model}")
            resp = client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=0.2,
            )
            content = resp.choices[0].message.content or ""
            content = content.strip()
            if not content:
                raise RuntimeError("视觉预处理返回空内容")
            return content
        except Exception as e:
            last_err = e
            backoff = 2 ** (attempt - 1)
            print(f"[generate] 视觉预处理失败：{e}; {backoff}s 后重试", file=sys.stderr)
            time.sleep(backoff)
    raise RuntimeError(f"视觉预处理多次失败: {last_err}")


def call_api(api_base: str, api_key: str, model: str, system_prompt: str) -> str:
    try:
        from openai import OpenAI  # type: ignore
    except ImportError as e:
        raise RuntimeError(f"未安装 openai 库: {e}")

    # API Base URL 规范化
    if not api_base.rstrip('/').endswith('/v1'):
        api_base = api_base.rstrip('/') + '/v1'

    client = OpenAI(api_key=api_key, base_url=api_base)
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": "请基于上方的输入数据，按照输出要求生成完整的落地页 Hero 区域设计方案。"},
    ]

    last_err: Exception | None = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            print(f"[generate] 调用生成 API (第 {attempt}/{MAX_RETRIES} 次)，模型: {model}")
            resp = client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=0.6,
            )
            content = resp.choices[0].message.content or ""
            if not content.strip():
                raise RuntimeError("API 返回内容为空")
            return content
        except Exception as e:
            last_err = e
            backoff = 2 ** (attempt - 1)
            print(f"[generate] 调用失败：{e}; {backoff}s 后重试", file=sys.stderr)
            time.sleep(backoff)
    raise RuntimeError(f"API 调用多次失败: {last_err}")


# ----------------- HTML 渲染 -----------------

def md_to_html(md_text: str) -> str:
    """优先使用 python-markdown，失败时回退为简易渲染器。"""
    try:
        import markdown  # type: ignore
        return markdown.markdown(
            md_text,
            extensions=["fenced_code", "tables", "toc", "nl2br"],
        )
    except Exception:
        return _fallback_md(md_text)


def _fallback_md(md_text: str) -> str:
    """极简 Markdown 渲染（保底方案）。"""
    lines = md_text.split("\n")
    out: list[str] = []
    in_code = False
    code_buf: list[str] = []
    in_list = False

    def flush_list():
        nonlocal in_list
        if in_list:
            out.append("</ul>")
            in_list = False

    for raw in lines:
        line = raw.rstrip()
        if line.startswith("```"):
            if not in_code:
                flush_list()
                in_code = True
                code_buf = []
            else:
                out.append("<pre><code>" + html.escape("\n".join(code_buf)) + "</code></pre>")
                in_code = False
            continue
        if in_code:
            code_buf.append(line)
            continue

        if not line.strip():
            flush_list()
            out.append("")
            continue

        m = re.match(r"^(#{1,6})\s+(.*)$", line)
        if m:
            flush_list()
            level = len(m.group(1))
            out.append(f"<h{level}>{html.escape(m.group(2))}</h{level}>")
            continue

        if re.match(r"^\s*[-*]\s+", line):
            if not in_list:
                out.append("<ul>")
                in_list = True
            item = re.sub(r"^\s*[-*]\s+", "", line)
            out.append(f"<li>{_inline(html.escape(item))}</li>")
            continue

        flush_list()
        out.append(f"<p>{_inline(html.escape(line))}</p>")

    flush_list()
    return "\n".join(out)


def _inline(s: str) -> str:
    s = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s)
    s = re.sub(r"\*(.+?)\*", r"<em>\1</em>", s)
    s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
    return s


HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0" />
<title>落地页 Hero 设计方案</title>
<style>
  :root {
    --ink: #14161a;
    --ink-soft: #4a4f57;
    --muted: #8a8f99;
    --line: #e7e7ea;
    --bg: #f5f4ef;
    --panel: #ffffff;
    --accent: #ff5a1f;
    --accent-soft: #ffe6dc;
    --code-bg: #0f1115;
    --code-fg: #e8eaed;
  }
  * { box-sizing: border-box; }
  html, body { margin: 0; padding: 0; background: var(--bg); color: var(--ink);
    font-family: -apple-system, BlinkMacSystemFont, "PingFang SC", "Hiragino Sans GB",
                 "Microsoft YaHei", "Helvetica Neue", Arial, sans-serif;
    -webkit-font-smoothing: antialiased;
  }
  .topbar {
    position: sticky; top: 0; z-index: 10;
    backdrop-filter: saturate(180%) blur(12px);
    background: rgba(245,244,239,0.85);
    border-bottom: 1px solid var(--line);
    padding: 14px 28px;
    display: flex; align-items: center; gap: 14px;
  }
  .topbar .dot { width: 10px; height: 10px; border-radius: 50%; background: var(--accent); }
  .topbar h1 { font-size: 15px; margin: 0; letter-spacing: 0.02em; font-weight: 600; }
  .topbar .meta { margin-left: auto; color: var(--muted); font-size: 12px; }

  .wrap { max-width: 980px; margin: 0 auto; padding: 48px 32px 96px; }

  .hero {
    border: 1px solid var(--line);
    background: var(--panel);
    border-radius: 24px;
    padding: 40px 40px 36px;
    margin-bottom: 28px;
    position: relative;
    overflow: hidden;
  }
  .hero::after {
    content: "";
    position: absolute; right: -80px; top: -80px;
    width: 260px; height: 260px; border-radius: 50%;
    background: var(--accent-soft);
    filter: blur(8px);
    z-index: 0;
  }
  .hero .kicker {
    position: relative; z-index: 1;
    display: inline-block;
    font-size: 12px; letter-spacing: 0.18em; text-transform: uppercase;
    color: var(--accent); font-weight: 700;
    padding: 4px 10px; border: 1px solid var(--accent); border-radius: 999px;
  }
  .hero h2 {
    position: relative; z-index: 1;
    font-size: clamp(28px, 4vw, 44px);
    line-height: 1.15; margin: 16px 0 10px; letter-spacing: -0.01em;
  }
  .hero p.lead {
    position: relative; z-index: 1;
    color: var(--ink-soft); font-size: 16px; max-width: 640px; margin: 0;
  }

  .content {
    background: var(--panel);
    border: 1px solid var(--line);
    border-radius: 20px;
    padding: 36px 44px;
    line-height: 1.75;
    font-size: 15.5px;
  }
  .content h1, .content h2, .content h3, .content h4 {
    letter-spacing: -0.01em;
    line-height: 1.3;
    margin: 1.8em 0 0.6em;
  }
  .content h1 { font-size: 26px; }
  .content h2 {
    font-size: 22px;
    padding-bottom: 8px;
    border-bottom: 1px solid var(--line);
  }
  /* 变体卡片标题：每个 ### 变体 X 用顶部强分隔线突出 */
  .content h3 {
    font-size: 20px;
    color: var(--accent);
    margin-top: 48px;
    padding-top: 24px;
    border-top: 2px solid var(--accent);
    font-weight: 700;
    letter-spacing: 0.005em;
  }
  .content h3::before {
    content: "✦";
    display: inline-block;
    color: var(--accent);
    margin-right: 10px;
    font-size: 16px;
    transform: translateY(-1px);
  }
  /* 第一个 h3 不需要顶部分隔（紧跟 h2 时） */
  .content h2 + h3,
  .content h2 + p + h3 {
    margin-top: 24px;
    padding-top: 0;
    border-top: none;
  }
  .content h4 { font-size: 15px; color: var(--ink-soft); }
  .content p { color: var(--ink-soft); margin: 0.6em 0; }
  .content ul, .content ol { padding-left: 1.3em; margin: 0.6em 0; }
  .content li { margin: 0.3em 0; color: var(--ink-soft); }
  .content li::marker { color: var(--accent); }
  .content strong { color: var(--ink); font-weight: 600; }
  .content em { color: var(--ink); font-style: normal;
    background: linear-gradient(180deg, transparent 60%, var(--accent-soft) 60%); }
  .content code {
    font-family: "SF Mono", Menlo, Consolas, monospace;
    background: #f1efe9;
    padding: 1px 6px; border-radius: 4px; font-size: 0.92em;
    color: #b13a06;
  }
  /* 生图 Prompt 代码块：深色高对比，方便复制阅读 */
  .content pre {
    position: relative;
    background: #1e1e1e;
    color: #d4d4d4;
    padding: 20px 22px;
    border-radius: 8px;
    overflow-x: auto;
    line-height: 1.6;
    font-size: 13px;
    margin: 16px 0;
    border: 1px solid #2a2a2a;
    box-shadow: 0 4px 16px rgba(0,0,0,0.08);
  }
  .content pre::before {
    content: "PROMPT · 点击右上选中复制";
    position: absolute;
    top: -10px; left: 16px;
    background: var(--accent);
    color: #fff;
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 0.12em;
    padding: 3px 10px;
    border-radius: 4px;
    font-family: -apple-system, BlinkMacSystemFont, "PingFang SC", sans-serif;
  }
  .content pre code {
    background: none;
    color: inherit;
    padding: 0;
    font-family: "SF Mono", Menlo, Consolas, "Courier New", monospace;
  }
  .content blockquote {
    margin: 1em 0; padding: 12px 18px;
    background: var(--accent-soft); border-left: 3px solid var(--accent);
    border-radius: 0 8px 8px 0; color: var(--ink);
  }
  .content table {
    border-collapse: collapse; width: 100%; margin: 1em 0; font-size: 14px;
  }
  .content th, .content td {
    border: 1px solid var(--line); padding: 8px 12px; text-align: left;
  }
  .content th { background: #faf8f3; font-weight: 600; }
  .content hr { border: none; border-top: 1px solid var(--line); margin: 2em 0; }

  .footer {
    margin-top: 28px;
    color: var(--muted); font-size: 12px; text-align: center;
  }
  .footer code {
    font-family: "SF Mono", Menlo, Consolas, monospace;
    color: var(--ink-soft);
  }

  .reference-section {
    margin-top: 48px;
    padding-top: 32px;
    border-top: 1px solid #e0e0e0;
  }
  .reference-section h2 {
    font-size: 20px;
    margin-bottom: 16px;
    color: #333;
  }
  .reference-section img {
    display: block;
  }
</style>
</head>
<body>
  <header class="topbar">
    <span class="dot"></span>
    <h1>Landing Page · Hero 设计方案</h1>
    <span class="meta">__GENERATED_AT__</span>
  </header>

  <main class="wrap">
    <section class="hero">
      <span class="kicker">Design Brief</span>
      <h2>从广告视频到落地页 Hero<br/>一份可直接落地的视觉与文案方案</h2>
      <p class="lead">基于视频前 15 秒的多模态分析结果，自动生成的设计思路、页面结构、文案与主视觉 Prompt。</p>
    </section>

    <article class="content">
__BODY__
    </article>
__REFERENCES__
    <p class="footer">由 <code>landingpage-test-hero-page</code> 自动生成 · 可直接分享给团队成员</p>
  </main>
</body>
</html>
"""


def build_html(md_text: str, elapsed: int = 0) -> str:
    body = md_to_html(md_text)
    ts = time.strftime("%Y-%m-%d %H:%M")
    if elapsed > 0:
        generated_at = f"生成于 {ts} (耗时 {elapsed}s)"
    else:
        generated_at = f"生成于 {ts}"
    references = build_references_html()
    return (
        HTML_TEMPLATE
        .replace("__BODY__", body)
        .replace("__GENERATED_AT__", generated_at)
        .replace("__REFERENCES__", references)
    )


def _rel_from_html(target_abs: str) -> str:
    """计算从 HTML 输出位置到目标资源的相对路径。"""
    try:
        return os.path.relpath(target_abs, start=os.path.dirname(os.path.abspath(HTML_OUT)))
    except ValueError:
        return target_abs


def build_references_html() -> str:
    """构建素材参考区域 HTML。

    HTML 位于 ANALYSE_DIR；视频与帧位于 VIDEO_CLIP_DIR；
    brand_reference 位于项目根 assets/。
    所有引用使用相对路径。
    """
    sections: list[str] = []

    # 区域 0：品牌标识参考图
    if os.path.isfile(BRAND_REFERENCE_SRC):
        rel = _rel_from_html(BRAND_REFERENCE_SRC)
        sections.append(
            '<section class="reference-section">\n'
            '  <h2>品牌标识参考</h2>\n'
            '  <p>生图时请参照此图的顶部红色品牌栏样式：</p>\n'
            f'  <img src="{html.escape(rel)}" alt="品牌标识参考" '
            'style="max-width: 100%; border-radius: 8px; '
            'box-shadow: 0 2px 8px rgba(0,0,0,0.1);">\n'
            '</section>'
        )

    # 区域 0.5：老师脸部三视图
    face_refs_exist = os.path.isfile(TEACHER_FACE_REF_1) or os.path.isfile(TEACHER_FACE_REF_2)
    if face_refs_exist:
        face_imgs = ""
        if os.path.isfile(TEACHER_FACE_REF_1):
            rel1 = _rel_from_html(TEACHER_FACE_REF_1)
            face_imgs += (
                f'  <img src="{html.escape(rel1)}" alt="老师脸部参考1" '
                'style="max-width: 400px; border-radius: 8px; '
                'box-shadow: 0 2px 8px rgba(0,0,0,0.1); margin-right: 12px;">\n'
            )
        if os.path.isfile(TEACHER_FACE_REF_2):
            rel2 = _rel_from_html(TEACHER_FACE_REF_2)
            face_imgs += (
                f'  <img src="{html.escape(rel2)}" alt="老师脸部参考2" '
                'style="max-width: 400px; border-radius: 8px; '
                'box-shadow: 0 2px 8px rgba(0,0,0,0.1);">\n'
            )
        sections.append(
            '<section class="reference-section">\n'
            '  <h2>老师脸部参考（三视图）</h2>\n'
            '  <p>生图时请参照以下三视图保持老师面部五官一致性：</p>\n'
            '  <div style="display: flex; flex-wrap: wrap; gap: 12px;">\n'
            + face_imgs +
            '  </div>\n'
            '</section>'
        )

    # 区域 A：老师参考图（与 HTML 同目录）
    if os.path.isfile(TEACHER_REF_PATH):
        sections.append(
            '<section class="reference-section">\n'
            '  <h2>老师参考图</h2>\n'
            '  <p>生图时请附上此图作为老师形象参考：</p>\n'
            '  <img src="teacher_ref.jpg" alt="老师参考图" '
            'style="max-width: 400px; border-radius: 8px; '
            'box-shadow: 0 2px 8px rgba(0,0,0,0.1);">\n'
            '</section>'
        )

    # 区域 B：视频片段
    video_clip = os.path.join(VIDEO_CLIP_DIR, "video_clip.mp4")
    if os.path.isfile(video_clip):
        rel_video = _rel_from_html(video_clip)
        sections.append(
            '<section class="reference-section">\n'
            '  <h2>视频前15秒片段</h2>\n'
            '  <video controls style="max-width: 100%; border-radius: 8px;">\n'
            f'    <source src="{html.escape(rel_video)}" type="video/mp4">\n'
            '    您的浏览器不支持视频播放\n'
            '  </video>\n'
            '</section>'
        )

    # 区域 C：关键帧（动态适应 1~N 帧；每秒一帧）
    if os.path.isdir(VIDEO_CLIP_DIR):
        frame_files = sorted(
            f for f in os.listdir(VIDEO_CLIP_DIR)
            if re.match(r"^frame_\d+\.jpg$", f)
        )
        if frame_files:
            n = len(frame_files)
            cols = min(n, 5)
            items: list[str] = []
            for fname in frame_files:
                m = re.match(r"^frame_(\d+)\.jpg$", fname)
                seconds = int(m.group(1)) if m else 0
                rel_frame = _rel_from_html(os.path.join(VIDEO_CLIP_DIR, fname))
                items.append(
                    '    <div style="text-align: center;">\n'
                    f'      <img src="{html.escape(rel_frame)}" alt="{seconds}s" '
                    'style="width: 100%; border-radius: 4px;">\n'
                    f'      <p style="margin-top: 4px; font-size: 12px; color: #666;">{seconds}s</p>\n'
                    '    </div>'
                )
            sections.append(
                '<section class="reference-section">\n'
                f'  <h2>关键帧截图（每秒一帧，共 {n} 帧）</h2>\n'
                f'  <div style="display: grid; grid-template-columns: repeat({cols}, 1fr); gap: 8px;">\n'
                + "\n".join(items) + "\n"
                '  </div>\n'
                '</section>'
            )

    # 附图提示
    sections.append(
        '<section class="reference-section">\n'
        '  <h2>生图附图提示</h2>\n'
        '  <p>生图时请同时附上：</p>\n'
        '  <ol>\n'
        '    <li><code>teacher_ref.jpg</code>（老师形象参考）</li>\n'
        '    <li><code>assets/teacher_face_ref_1.jpg</code>（老师脸部三视图1）</li>\n'
        '    <li><code>assets/teacher_face_ref_2.jpg</code>（老师脸部三视图2）</li>\n'
        '    <li><code>assets/brand_logo.png</code>（品牌 logo 参考）</li>\n'
        '  </ol>\n'
        '</section>'
    )

    if not sections:
        return ""
    return "\n    " + "\n    ".join(sections) + "\n"


# ----------------- 变体提取 / 素材分发 -----------------

# 匹配形如 "## 变体 1" / "### 变体 1：xxx" / "### 变体1: xxx" 的标题（兼容二级和三级）
_VARIANT_HEADING_RE = re.compile(r"^#{2,3}\s*变体\s*(\d+)\s*[:：]?\s*(.*)$")


def extract_variants(md_text: str) -> List[Tuple[int, str, str]]:
    """从 markdown 中提取每个 "### 变体 N" 区块的首个代码块内容。

    返回 [(变体编号, 标题尾巴, prompt 文本), ...]，按出现顺序。
    若 markdown 为空或无任何变体，返回空列表（不抛错）。
    """
    if not md_text:
        return []

    lines = md_text.split("\n")
    # 第一步：定位所有变体标题行
    headings: List[Tuple[int, int, str]] = []  # (line_idx, variant_num, suffix)
    for i, line in enumerate(lines):
        m = _VARIANT_HEADING_RE.match(line.strip())
        if m:
            headings.append((i, int(m.group(1)), m.group(2).strip()))

    results: List[Tuple[int, str, str]] = []
    for k, (start_idx, num, suffix) in enumerate(headings):
        end_idx = headings[k + 1][0] if k + 1 < len(headings) else len(lines)
        block = lines[start_idx:end_idx]

        # 提取 block 中第一个 ``` ... ``` 围栏代码块的内容
        prompt_lines: List[str] = []
        in_fence = False
        captured = False
        for ln in block:
            stripped = ln.lstrip()
            if not in_fence:
                if stripped.startswith("```"):
                    in_fence = True
                    continue
            else:
                if stripped.startswith("```"):
                    captured = True
                    break
                prompt_lines.append(ln)
        if not captured and not prompt_lines:
            # 该变体没有代码块，跳过
            continue
        prompt_text = "\n".join(prompt_lines).strip()
        if not prompt_text:
            continue
        results.append((num, suffix, prompt_text))

    return results


def write_design_refer(variants: List[Tuple[int, str, str]]) -> int:
    """将每个变体的 prompt + 老师参考图 + 品牌参考图写入 DESIGN_REFER_DIR/pageN/。

    返回成功写入的页数。
    """
    if not variants:
        print("[generate] 警告：未在 markdown 中识别到任何 ### 变体 X 区块，跳过 design_refer 生成", file=sys.stderr)
        return 0

    os.makedirs(DESIGN_REFER_DIR, exist_ok=True)

    written = 0
    for idx, (num, suffix, prompt_text) in enumerate(variants, start=1):
        # pageN 用枚举顺序而不是变体声明的编号，确保即便模型跳号也能形成 page1..pageK
        page_dir = os.path.join(DESIGN_REFER_DIR, f"page{idx}")
        os.makedirs(page_dir, exist_ok=True)

        # 1) prompt.md
        prompt_path = os.path.join(page_dir, "prompt.md")
        with open(prompt_path, "w", encoding="utf-8") as f:
            f.write(prompt_text.rstrip() + "\n")

        # 2) teacher_ref.jpg
        if os.path.isfile(TEACHER_REF_PATH):
            try:
                shutil.copy2(TEACHER_REF_PATH, os.path.join(page_dir, "teacher_ref.jpg"))
            except Exception as e:
                print(f"[generate] 警告：复制 teacher_ref.jpg 到 {page_dir} 失败：{e}", file=sys.stderr)
        else:
            print(f"[generate] 警告：teacher_ref.jpg 不存在，page{idx} 缺少老师参考图", file=sys.stderr)

        # 3) brand_reference.png
        if os.path.isfile(BRAND_REFERENCE_SRC):
            try:
                shutil.copy2(BRAND_REFERENCE_SRC, os.path.join(page_dir, "brand_reference.png"))
            except Exception as e:
                print(f"[generate] 警告：复制 brand_reference.png 到 {page_dir} 失败：{e}", file=sys.stderr)
        else:
            print(f"[generate] 警告：brand_reference.png 不存在: {BRAND_REFERENCE_SRC}", file=sys.stderr)

        # 4) teacher_face_ref_1.jpg / teacher_face_ref_2.jpg - 老师脸部三视图
        if os.path.isfile(TEACHER_FACE_REF_1):
            try:
                shutil.copy2(TEACHER_FACE_REF_1, os.path.join(page_dir, "teacher_face_ref_1.jpg"))
            except Exception as e:
                print(f"[generate] 警告：复制 teacher_face_ref_1.jpg 到 {page_dir} 失败：{e}", file=sys.stderr)
        if os.path.isfile(TEACHER_FACE_REF_2):
            try:
                shutil.copy2(TEACHER_FACE_REF_2, os.path.join(page_dir, "teacher_face_ref_2.jpg"))
            except Exception as e:
                print(f"[generate] 警告：复制 teacher_face_ref_2.jpg 到 {page_dir} 失败：{e}", file=sys.stderr)

        suffix_show = f"（{suffix}）" if suffix else ""
        print(f"[generate] page{idx} 写入完成（变体{num}{suffix_show}）: {page_dir}")
        written += 1

    return written


# ----------------- 主流程 -----------------

def main() -> int:
    start_time = time.time()

    api_base = (os.environ.get("GENERATE_API_BASE_URL") or os.environ.get("API_BASE_URL") or "").strip()
    api_key = (os.environ.get("GENERATE_API_KEY") or os.environ.get("API_KEY") or "").strip()
    model = (os.environ.get("GENERATE_MODEL_NAME") or os.environ.get("MODEL_NAME") or "").strip()
    missing = [k for k, v in (("API_BASE_URL", api_base), ("API_KEY", api_key), ("MODEL_NAME", model)) if not v]
    if missing:
        print(f"[generate] 错误：缺少环境变量: {', '.join(missing)}", file=sys.stderr)
        return 1

    if not os.path.isfile(ANALYSIS_PATH):
        print(f"[generate] 错误：分析结果文件不存在: {ANALYSIS_PATH}", file=sys.stderr)
        return 2
    if not os.path.isfile(PROMPT_PATH):
        print(f"[generate] 错误：Prompt 文件不存在: {PROMPT_PATH}", file=sys.stderr)
        return 3

    try:
        with open(ANALYSIS_PATH, "r", encoding="utf-8") as f:
            analysis = json.load(f)
    except Exception as e:
        print(f"[generate] 错误：analysis.json 解析失败：{e}", file=sys.stderr)
        return 4

    analysis_str = json.dumps(analysis, ensure_ascii=False, indent=2)
    prompt_tpl = read_text(PROMPT_PATH)

    # 提取老师参考帧
    best_frame = "frame_00"  # 默认
    if "best_teacher_frame" in analysis:
        bf = analysis["best_teacher_frame"]
        if isinstance(bf, dict) and "frame" in bf:
            best_frame = bf["frame"]
        elif isinstance(bf, str):
            best_frame = bf

    os.makedirs(ANALYSE_DIR, exist_ok=True)
    src_path = os.path.join(VIDEO_CLIP_DIR, f"{best_frame}.jpg")
    if os.path.isfile(src_path):
        shutil.copy2(src_path, TEACHER_REF_PATH)
        print(f"[generate] 老师参考图已保存: {TEACHER_REF_PATH} (来自 {best_frame})")
    else:
        # 回退到 frame_00
        fallback = os.path.join(VIDEO_CLIP_DIR, "frame_00.jpg")
        if os.path.isfile(fallback):
            shutil.copy2(fallback, TEACHER_REF_PATH)
            print(f"[generate] 警告：{best_frame} 不存在，使用 frame_00 作为参考图", file=sys.stderr)
        else:
            print(f"[generate] 警告：无可用的老师参考帧（{src_path} 和 frame_00 均缺失）", file=sys.stderr)

    # 视觉预处理：提取老师着装描述
    teacher_outfit_desc = ""
    if os.path.isfile(TEACHER_REF_PATH):
        try:
            analyse_base = (os.environ.get("ANALYSE_API_BASE_URL") or api_base).strip()
            analyse_key = (os.environ.get("ANALYSE_API_KEY") or api_key).strip()
            analyse_model = (os.environ.get("ANALYSE_MODEL_NAME") or model).strip()
            teacher_outfit_desc = describe_teacher_outfit(TEACHER_REF_PATH, analyse_base, analyse_key, analyse_model)
            print(f"[generate] 老师着装描述: {teacher_outfit_desc}")
        except Exception as e:
            print(f"[generate] 警告：视觉预处理失败，将不注入着装描述：{e}", file=sys.stderr)

    # 组装 system_prompt（在视觉预处理之后，注入着装描述）
    system_prompt = prompt_tpl.replace("analysis_json", analysis_str)
    if teacher_outfit_desc:
        outfit_instruction = (
            "\n\n## 老师着装参考（来自 teacher_ref.jpg 的视觉分析）\n\n"
            f"实际着装：{teacher_outfit_desc}\n\n"
            "请在每套生图 Prompt 的老师形象描述中，明确包含上述着装颜色和款式描述，"
            "确保 gpt-image-2 不会因品牌色偏见而改变老师的着装颜色。"
        )
        system_prompt = system_prompt + outfit_instruction

    try:
        md_text = call_api(api_base, api_key, model, system_prompt)
    except Exception as e:
        print(f"[generate] 调用失败：{e}", file=sys.stderr)
        return 5

    # 添加 YAML frontmatter
    source_video = os.environ.get("SOURCE_VIDEO", "")
    meta = f"""---
title: Landing Page Hero 设计方案
generated_at: {time.strftime("%Y-%m-%d %H:%M:%S")}
model: {model}
source_video: {source_video}
---

"""
    md_full = meta + md_text.strip() + "\n"
    with open(MD_OUT, "w", encoding="utf-8") as f:
        f.write(md_full)
    print(f"[generate] 设计方案 Markdown 已保存: {MD_OUT}")

    try:
        elapsed = int(time.time() - start_time)
        html_text = build_html(md_text, elapsed)
        with open(HTML_OUT, "w", encoding="utf-8") as f:
            f.write(html_text)
        print(f"[generate] 设计方案 HTML 已保存: {HTML_OUT}")
    except Exception as e:
        print(f"[generate] 警告：生成 HTML 失败：{e}", file=sys.stderr)
        return 6

    # 解析变体并写入 design_refer/pageN/
    try:
        variants = extract_variants(md_text)
        n_pages = write_design_refer(variants)
        if n_pages > 0:
            print(f"[generate] 共生成 {n_pages} 个变体素材文件夹于: {DESIGN_REFER_DIR}")
    except Exception as e:
        # 提取失败不应阻塞主流程
        print(f"[generate] 警告：解析变体或写入 design_refer 失败：{e}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())
