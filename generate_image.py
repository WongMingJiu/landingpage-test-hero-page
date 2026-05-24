#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
落地页生图脚本
读取 ~/workspace/landing-page-manage/唱歌项目/{视频名}/pageN/ 中的 prompt.md 和参考图，
调用 gpt-image-2 API 生成落地页图片，保存到 landing-page/{视频名}/pageN.png

使用方式：
  python3 generate_image.py "视频名称"
  python3 generate_image.py "视频名称" --pages 1 3 5
  python3 generate_image.py "视频名称" --key "sk-xxx" --model "gpt-image-2"
"""

import argparse
import base64
import os
import re
import sys
import time
from pathlib import Path
from typing import List, Optional

import requests


SCRIPT_DIR = Path(__file__).resolve().parent
CONFIG_PATH = SCRIPT_DIR / "config.env"
BRAND_LOGO_PATH = SCRIPT_DIR / "assets" / "brand_logo.png"

# 默认输入/输出根目录
DEFAULT_INPUT_ROOT = Path.home() / "workspace" / "landing-page-manage" / "唱歌项目"
DEFAULT_OUTPUT_ROOT = DEFAULT_INPUT_ROOT / "landing-page"

# 默认参数
DEFAULT_API_BASE_URL = "https://api-slb.packyapi.com/v1/images/edits"
DEFAULT_API_KEY = ""
DEFAULT_MODEL_NAME = "gpt-image-2"
DEFAULT_SIZE = "1024x1792"

MAX_RETRIES = 3
INITIAL_BACKOFF = 2.0  # 秒
REQUEST_TIMEOUT = 600  # 秒（生图可能耗时较长）


# ---------- 配置加载 ----------

def load_config_env(path: Path) -> dict:
    """读取项目根目录的 config.env，返回 dict"""
    cfg = {}
    if not path.exists():
        return cfg
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            k, v = line.split("=", 1)
            cfg[k.strip()] = v.strip()
    return cfg


# ---------- 工具函数 ----------

def list_page_dirs(video_dir: Path) -> List[Path]:
    """扫描视频目录下所有 pageN 子目录，按编号升序"""
    if not video_dir.exists():
        return []
    pages = []
    pattern = re.compile(r"^page(\d+)$")
    for child in video_dir.iterdir():
        if not child.is_dir():
            continue
        m = pattern.match(child.name)
        if m:
            pages.append((int(m.group(1)), child))
    pages.sort(key=lambda x: x[0])
    return [p for _, p in pages]


def page_number(page_dir: Path) -> Optional[int]:
    m = re.match(r"^page(\d+)$", page_dir.name)
    return int(m.group(1)) if m else None


def read_prompt_text(prompt_md: Path) -> str:
    with open(prompt_md, "r", encoding="utf-8") as f:
        return f.read().strip()


def save_image_from_response(resp_json: dict, output_path: Path) -> None:
    """
    OpenAI 兼容 /images/edits 响应可能为：
      {"data":[{"b64_json":"..."}]}  或
      {"data":[{"url":"..."}]}
    """
    if not isinstance(resp_json, dict):
        raise RuntimeError(f"响应非 JSON 对象: {resp_json!r}")

    data_list = resp_json.get("data")
    if not data_list or not isinstance(data_list, list):
        # 部分网关可能直接返回 b64_json/url
        if "b64_json" in resp_json or "url" in resp_json:
            data_list = [resp_json]
        else:
            raise RuntimeError(f"响应缺少 data 字段: {resp_json}")

    item = data_list[0]
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if "b64_json" in item and item["b64_json"]:
        img_bytes = base64.b64decode(item["b64_json"])
        with open(output_path, "wb") as f:
            f.write(img_bytes)
        return

    if "url" in item and item["url"]:
        url = item["url"]
        r = requests.get(url, timeout=REQUEST_TIMEOUT)
        r.raise_for_status()
        with open(output_path, "wb") as f:
            f.write(r.content)
        return

    raise RuntimeError(f"响应中未找到 b64_json 或 url: {item}")


# ---------- API 调用 ----------

def call_image_edit_api(
    api_url: str,
    api_key: str,
    model: str,
    prompt_text: str,
    image_paths: List[Path],
    size: str,
    n: int = 1,
) -> dict:
    """发送 multipart/form-data POST 请求到 /images/edits，支持多张参考图"""
    headers = {"Authorization": f"Bearer {api_key}"}
    data = {
        "model": model,
        "prompt": prompt_text,
        "n": str(n),
        "size": size,
    }

    # 打开所有图片文件
    opened_files = []
    try:
        files_list = []
        for img_path in image_paths:
            f = open(img_path, "rb")
            opened_files.append(f)
            mime = "image/png" if img_path.suffix.lower() == ".png" else "image/jpeg"
            files_list.append(("image[]", (img_path.name, f, mime)))

        resp = requests.post(
            api_url,
            headers=headers,
            data=data,
            files=files_list,
            timeout=REQUEST_TIMEOUT,
        )
    finally:
        for f in opened_files:
            f.close()

    if resp.status_code != 200:
        raise RuntimeError(
            f"API 返回 {resp.status_code}: {resp.text[:500]}"
        )
    try:
        return resp.json()
    except ValueError as e:
        raise RuntimeError(f"响应非 JSON: {resp.text[:500]}") from e


def call_with_retry(
    api_url: str,
    api_key: str,
    model: str,
    prompt_text: str,
    image_paths: List[Path],
    size: str,
    max_retries: int = MAX_RETRIES,
) -> dict:
    last_err: Optional[Exception] = None
    for attempt in range(1, max_retries + 1):
        try:
            return call_image_edit_api(
                api_url=api_url,
                api_key=api_key,
                model=model,
                prompt_text=prompt_text,
                image_paths=image_paths,
                size=size,
                n=1,
            )
        except Exception as e:
            last_err = e
            if attempt < max_retries:
                wait = INITIAL_BACKOFF * (2 ** (attempt - 1))
                print(f"    ! 第 {attempt} 次调用失败：{e}；{wait:.1f}s 后重试...")
                time.sleep(wait)
            else:
                print(f"    ! 第 {attempt} 次调用失败：{e}")
    raise RuntimeError(f"重试 {max_retries} 次后仍失败：{last_err}")


# ---------- 处理单个 page ----------

def process_page(
    page_dir: Path,
    output_path: Path,
    api_url: str,
    api_key: str,
    model: str,
    size: str,
) -> bool:
    """处理单个 page，返回是否成功"""
    page_name = page_dir.name
    print(f"\n[{page_name}] 开始处理")

    # 兼容 prompt.md 和 prompt.txt 两种格式
    prompt_file = page_dir / "prompt.md"
    if not prompt_file.exists():
        prompt_file = page_dir / "prompt.txt"
    teacher_ref = page_dir / "teacher_ref.jpg"

    if not prompt_file.exists():
        print(f"  x 缺少 prompt.md 或 prompt.txt：{page_dir}")
        return False
    if not teacher_ref.exists():
        print(f"  x 缺少 teacher_ref.jpg：{teacher_ref}")
        return False

    prompt_text = read_prompt_text(prompt_file)
    if not prompt_text:
        print(f"  x prompt 文件为空：{prompt_file}")
        return False

    # 构建参考图列表：老师参考图 + 品牌 logo
    image_paths = [teacher_ref]
    if BRAND_LOGO_PATH.exists():
        image_paths.append(BRAND_LOGO_PATH)
        print(f"  - 品牌 logo：{BRAND_LOGO_PATH}")
    else:
        print(f"  ! 品牌 logo 不存在，仅使用老师参考图：{BRAND_LOGO_PATH}")

    print(f"  - prompt 长度：{len(prompt_text)} 字符")
    print(f"  - 参考图：{[str(p) for p in image_paths]}")
    print(f"  - 调用 API（model={model}, size={size}）...")

    try:
        resp_json = call_with_retry(
            api_url=api_url,
            api_key=api_key,
            model=model,
            prompt_text=prompt_text,
            image_paths=image_paths,
            size=size,
        )
    except Exception as e:
        print(f"  x API 调用失败：{e}")
        return False

    try:
        save_image_from_response(resp_json, output_path)
    except Exception as e:
        print(f"  x 保存图片失败：{e}")
        return False

    print(f"  ✓ 已保存：{output_path}")
    return True


# ---------- 入口 ----------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="调用 gpt-image-2 API 生成落地页图片",
    )
    parser.add_argument(
        "video_name",
        help="视频名称（对应 ~/workspace/landing-page-manage/唱歌项目/{视频名}/）",
    )
    parser.add_argument(
        "--pages",
        nargs="+",
        type=int,
        default=None,
        help="指定要生成的 page 编号列表（如 --pages 1 3 5），默认全部",
    )
    parser.add_argument(
        "--key",
        default=None,
        help="覆盖 API Key（默认读取 config.env 中的 IMAGE_API_KEY）",
    )
    parser.add_argument(
        "--model",
        default=None,
        help="覆盖模型名（默认读取 config.env 中的 IMAGE_MODEL_NAME）",
    )
    parser.add_argument(
        "--url",
        default=None,
        help="覆盖 API Endpoint（默认读取 config.env 中的 IMAGE_API_BASE_URL）",
    )
    parser.add_argument(
        "--size",
        default=DEFAULT_SIZE,
        help=f"图片尺寸（默认 {DEFAULT_SIZE}）",
    )
    parser.add_argument(
        "--input-root",
        default=str(DEFAULT_INPUT_ROOT),
        help="素材根目录（默认 ~/workspace/landing-page-manage/唱歌项目）",
    )
    parser.add_argument(
        "--output-root",
        default=str(DEFAULT_OUTPUT_ROOT),
        help="输出根目录（默认 ~/workspace/landing-page-manage/唱歌项目/landing-page）",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    cfg = load_config_env(CONFIG_PATH)

    api_url = (
        args.url
        or cfg.get("IMAGE_API_BASE_URL")
        or DEFAULT_API_BASE_URL
    )
    api_key = (
        args.key
        or cfg.get("IMAGE_API_KEY")
        or DEFAULT_API_KEY
    )
    model = (
        args.model
        or cfg.get("IMAGE_MODEL_NAME")
        or DEFAULT_MODEL_NAME
    )
    size = args.size

    if not api_key:
        print("错误：未配置 API Key（请在 config.env 中设置 IMAGE_API_KEY，或使用 --key）")
        return 2

    input_root = Path(os.path.expanduser(args.input_root))
    output_root = Path(os.path.expanduser(args.output_root))

    video_dir = input_root / args.video_name
    if not video_dir.exists():
        print(f"错误：视频素材目录不存在：{video_dir}")
        return 2

    all_pages = list_page_dirs(video_dir)
    if not all_pages:
        print(f"错误：在 {video_dir} 下未找到 pageN/ 子目录")
        return 2

    # 过滤指定 pages
    if args.pages:
        wanted = set(args.pages)
        pages = [p for p in all_pages if page_number(p) in wanted]
        if not pages:
            print(f"错误：指定的 pages={args.pages} 在素材目录中不存在")
            return 2
    else:
        pages = all_pages

    output_video_dir = output_root / args.video_name

    print(f"视频：{args.video_name}")
    print(f"素材目录：{video_dir}")
    print(f"输出目录：{output_video_dir}")
    print(f"待处理 pages：{[p.name for p in pages]}")
    print(f"API：{api_url}")
    print(f"模型：{model}")
    print(f"尺寸：{size}")

    success = 0
    failed = 0
    for page_dir in pages:
        out_page_path = output_video_dir / f"{page_dir.name}.png"
        try:
            ok = process_page(
                page_dir=page_dir,
                output_path=out_page_path,
                api_url=api_url,
                api_key=api_key,
                model=model,
                size=size,
            )
        except Exception as e:
            print(f"  x 处理 {page_dir.name} 异常：{e}")
            ok = False

        if ok:
            success += 1
        else:
            failed += 1

    print(f"\n完成：成功 {success} 个，失败 {failed} 个")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
