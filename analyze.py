#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
多模态分析脚本
- 读取 output/frames/ 下的关键帧图片，转为 base64
- 读取 output/transcript.txt
- 使用 prompts/analyze_prompt.md 作为 system prompt
- 调用 OpenAI 兼容多模态 API，结果保存至 output/analysis.json

环境变量：
  API_BASE_URL  - API 基础地址（OpenAI 兼容）
  API_KEY       - API Key
  MODEL_NAME    - 模型名称
"""

import base64
import glob
import json
import os
import re
import sys
import time
from typing import List


SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
FRAMES_DIR = os.environ.get("VIDEO_CLIP_DIR", "").strip() or os.path.join("output", "frames")
TRANSCRIPT_PATH = os.path.join(FRAMES_DIR, "transcript.txt")
_ANALYSE_DIR = os.environ.get("ANALYSE_DIR", "").strip() or "output"
ANALYSIS_PATH = os.path.join(_ANALYSE_DIR, "analysis.json")
PROMPT_PATH = os.path.join("prompts", "analyze_prompt.md")
FALLBACK_POINTS_PATH = os.path.join(SCRIPT_DIR, "assets", "fallback_points.md")

MAX_RETRIES = 3

# JPEG 魔术字节
JPEG_MAGIC = b'\xff\xd8'


def _parse_frame_index(path: str) -> int:
    """从 frame_XX.jpg 文件名中解析帧编号。"""
    name = os.path.basename(path)
    m = re.match(r"^frame_(\d+)\.jpg$", name)
    return int(m.group(1)) if m else -1


def load_frames() -> List[dict]:
    """动态扫描 output/frames/ 下的关键帧，返回 [{index, name, b64}, ...]。

    不硬编码帧数量；按文件名编号排序加载所有 frame_XX.jpg 文件。
    """
    if not os.path.isdir(FRAMES_DIR):
        raise FileNotFoundError(f"帧目录不存在: {FRAMES_DIR}")
    frame_files = sorted(glob.glob(os.path.join(FRAMES_DIR, "frame_*.jpg")))
    frames: List[dict] = []
    total_size = 0
    for path in frame_files:
        idx = _parse_frame_index(path)
        if idx < 0:
            continue
        with open(path, "rb") as f:
            data = f.read()
        name = os.path.basename(path)
        # JPEG 魔术字节检查
        if not data.startswith(JPEG_MAGIC):
            print(f"[analyze] 警告：{name} 可能不是有效的 JPEG 文件", file=sys.stderr)
        # 单张大小检查
        size_mb = len(data) / (1024 * 1024)
        if size_mb > 5:
            print(f"[analyze] 警告：{name} 大小为 {size_mb:.1f}MB，超过 5MB，可能影响 API 调用", file=sys.stderr)
        total_size += len(data)
        frames.append({
            "index": idx,
            "name": name,
            "b64": base64.b64encode(data).decode("ascii"),
        })
    # 总大小检查（针对 15 帧规模上调阈值至 60MB）
    total_mb = total_size / (1024 * 1024)
    if total_mb > 60:
        print(f"[analyze] 警告：所有帧图片总计 {total_mb:.1f}MB，超过 60MB，可能影响 API 调用", file=sys.stderr)
    if not frames:
        raise FileNotFoundError("未找到任何有效的关键帧图片")
    return frames


def sample_frames_for_api(frames: List[dict], max_frames: int) -> List[dict]:
    """当帧数超过 max_frames 时均匀采样，确保首尾帧被保留。"""
    n = len(frames)
    if max_frames <= 0 or n <= max_frames:
        return frames
    # 均匀采样（包含首尾）
    picked: List[int] = []
    for k in range(max_frames):
        # 在 [0, n-1] 上等距取点
        idx = round(k * (n - 1) / (max_frames - 1)) if max_frames > 1 else 0
        if idx not in picked:
            picked.append(idx)
    # 兜底：若因取整重复导致不足，按顺序补齐
    i = 0
    while len(picked) < max_frames and i < n:
        if i not in picked:
            picked.append(i)
        i += 1
    picked.sort()
    return [frames[i] for i in picked]


def read_text(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def extract_json(text: str) -> dict:
    """从模型返回中尽量稳健地解析 JSON。"""
    text = text.strip()
    if not text:
        raise ValueError("输入文本为空，无法解析 JSON")
    # 优先匹配 ```json ... ``` 代码块
    m = re.search(r"```json\s*(.*?)\s*```", text, re.DOTALL | re.IGNORECASE)
    if m:
        return json.loads(m.group(1))
    # 其次匹配通用 ``` ... ``` 代码块
    m = re.search(r"```\s*(.*?)\s*```", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass
    # 再尝试截取首个 { 到最后一个 }
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        return json.loads(text[start : end + 1])
    # 最后直接解析
    return json.loads(text)


def call_api(api_base: str, api_key: str, model: str, frames: List[dict], transcript: str, system_prompt: str) -> str:
    try:
        from openai import OpenAI  # type: ignore
    except ImportError as e:
        raise RuntimeError(f"未安装 openai 库: {e}")

    # API Base URL 规范化
    if not api_base.rstrip('/').endswith('/v1'):
        api_base = api_base.rstrip('/') + '/v1'

    client = OpenAI(api_key=api_key, base_url=api_base)

    user_content = []
    for fr in frames:
        user_content.append(
            {
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{fr['b64']}"},
            }
        )

    # 帧图片标注时间戳（按帧编号即对应秒数：frame_XX.jpg → 第 XX 秒）
    num_frames = len(frames)
    seconds_list = [fr["index"] for fr in frames]
    if num_frames >= 3 and seconds_list == list(range(seconds_list[0], seconds_list[0] + num_frames)):
        # 连续序列时使用省略式描述
        ts_desc = (
            f"以上 {num_frames} 张图片按顺序分别是视频"
            f"第 {seconds_list[0]} 秒、第 {seconds_list[0]+1} 秒、第 {seconds_list[0]+2} 秒..."
            f"第 {seconds_list[-1]} 秒的关键帧截图。"
        )
    else:
        ts_parts = [f"第 {s} 秒" for s in seconds_list]
        ts_desc = f"以上 {num_frames} 张图片按顺序分别是视频{'、'.join(ts_parts)}的关键帧截图。"
    user_content.append({
        "type": "text",
        "text": ts_desc,
    })

    user_content.append(
        {
            "type": "text",
            "text": (
                "以下是视频前15秒的口播脚本转写文本，请结合上方关键帧综合分析：\n\n"
                f"{transcript.strip()}"
            ),
        }
    )

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content},
    ]

    last_err: Exception | None = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            print(f"[analyze] 调用多模态 API (第 {attempt}/{MAX_RETRIES} 次)，模型: {model}")
            resp = client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=0.3,
                max_tokens=16384,
            )
            content = resp.choices[0].message.content or ""
            if not content.strip():
                raise RuntimeError("API 返回内容为空")
            return content
        except Exception as e:
            last_err = e
            backoff = 2 ** (attempt - 1)
            print(f"[analyze] 调用失败：{e}; {backoff}s 后重试", file=sys.stderr)
            time.sleep(backoff)
    raise RuntimeError(f"API 调用多次失败: {last_err}")


def main() -> int:
    api_base = os.environ.get("API_BASE_URL", "").strip()
    api_key = os.environ.get("API_KEY", "").strip()
    model = os.environ.get("MODEL_NAME", "").strip()
    missing = [k for k, v in (("API_BASE_URL", api_base), ("API_KEY", api_key), ("MODEL_NAME", model)) if not v]
    if missing:
        print(f"[analyze] 错误：缺少环境变量: {', '.join(missing)}", file=sys.stderr)
        return 1

    try:
        print("[analyze] 加载关键帧...")
        frames = load_frames()
        print(f"[analyze] 共加载 {len(frames)} 张帧（编号: {[f['index'] for f in frames]}）")

        # 控制实际发送给 API 的最大帧数（防止 token 过多 / API 图片数量限制）
        try:
            max_api_frames = int(os.environ.get("MAX_API_FRAMES", "10"))
        except ValueError:
            max_api_frames = 10
        api_frames = sample_frames_for_api(frames, max_api_frames)
        if len(api_frames) < len(frames):
            picked_idx = [f["index"] for f in api_frames]
            print(f"[analyze] 帧数 {len(frames)} 超过 MAX_API_FRAMES={max_api_frames}，"
                  f"均匀采样发送给 API: {picked_idx}")
        else:
            print(f"[analyze] 全部 {len(api_frames)} 张帧发送给 API")

        if not os.path.isfile(TRANSCRIPT_PATH):
            print(f"[analyze] 错误：转写文件不存在: {TRANSCRIPT_PATH}", file=sys.stderr)
            return 2
        transcript = read_text(TRANSCRIPT_PATH)
        print(f"[analyze] 转写文本长度: {len(transcript)} 字符")

        if not os.path.isfile(PROMPT_PATH):
            print(f"[analyze] 错误：Prompt 文件不存在: {PROMPT_PATH}", file=sys.stderr)
            return 3
        system_prompt = read_text(PROMPT_PATH)

        # 读取保底痛点/卖点/利益点信息并替换占位符
        fallback_points_text = ""
        if os.path.isfile(FALLBACK_POINTS_PATH):
            with open(FALLBACK_POINTS_PATH, "r", encoding="utf-8") as f:
                fallback_points_text = f.read().strip()

        if fallback_points_text:
            system_prompt = system_prompt.replace("{fallback_points}", fallback_points_text)
        else:
            # 如果没有保底文件，移除整个保底参考段落
            system_prompt = re.sub(
                r"## 保底参考信息（可选采纳）.*?(?=\n## |\Z)", "", system_prompt, flags=re.DOTALL
            )

        raw = call_api(api_base, api_key, model, api_frames, transcript, system_prompt)
        print("[analyze] 解析模型返回 JSON...")
        try:
            data = extract_json(raw)
        except Exception as e:
            # 保存原始返回方便排查
            raw_path = os.path.join(_ANALYSE_DIR, "analysis_raw.txt")
            os.makedirs(_ANALYSE_DIR, exist_ok=True)
            with open(raw_path, "w", encoding="utf-8") as f:
                f.write(raw)
            print(f"[analyze] JSON 解析失败：{e}，原始返回已保存至 {raw_path}", file=sys.stderr)
            print(f"[analyze] 原始返回已保存到: {raw_path}", file=sys.stderr)
            print(f"[analyze] 提示：你可以手动编辑该文件修正 JSON 格式，然后运行:", file=sys.stderr)
            print(f"[analyze]   python3 generate.py", file=sys.stderr)
            return 4

        os.makedirs(os.path.dirname(ANALYSIS_PATH), exist_ok=True)
        with open(ANALYSIS_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"[analyze] 分析结果已保存: {ANALYSIS_PATH}")
        return 0
    except Exception as e:
        print(f"[analyze] 发生错误：{e}", file=sys.stderr)
        return 9


if __name__ == "__main__":
    sys.exit(main())
