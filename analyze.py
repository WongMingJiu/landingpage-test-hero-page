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
import shutil
import sys
import time
from typing import List

from category_config import get_prompt_path, get_teacher_ref_paths, get_category_name, load_category_config


SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
FRAMES_DIR = os.environ.get("VIDEO_CLIP_DIR", "").strip() or os.path.join("output", "frames")
TRANSCRIPT_PATH = os.path.join(FRAMES_DIR, "transcript.txt")
_ANALYSE_DIR = os.environ.get("ANALYSE_DIR", "").strip() or "output"
ANALYSIS_PATH = os.path.join(_ANALYSE_DIR, "analysis.json")
PROMPT_PATH = get_prompt_path("analyze")

# 老师面部三视图参考图（用于辅助识别视频中的老师）
TEACHER_REF_PATHS = get_teacher_ref_paths()

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

    # 先注入老师面部三视图参考图（base64），用于辅助识别视频中的老师
    for ref_path in TEACHER_REF_PATHS:
        if not os.path.isfile(ref_path):
            print(f"[analyze] 警告：老师参考图不存在: {ref_path}", file=sys.stderr)
            continue
        with open(ref_path, "rb") as f:
            ref_data = f.read()
        ref_b64 = base64.b64encode(ref_data).decode("ascii")
        user_content.append(
            {
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{ref_b64}"},
            }
        )
        user_content.append(
            {
                "type": "text",
                "text": "以下是老师的面部参考图（三视图），请以此识别视频中的老师：",
            }
        )

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
                "以下是视频前30秒的口播脚本转写文本，请结合上方关键帧综合分析：\n\n"
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


def describe_teacher_from_ref(api_base: str, api_key: str, model: str) -> str:
    """从三视图参考图中提取老师的外貌特征描述。

    Returns: 特征描述文本字符串，如 "男性，约40-50岁，短黑发，佩戴矩形银色金属框眼镜，\n面部轮廓偏方圆，气质沉稳理性。"
    """
    if not TEACHER_REF_PATHS:
        return ""

    try:
        from openai import OpenAI  # type: ignore
    except ImportError as e:
        raise RuntimeError(f"未安装 openai 库: {e}")

    if not api_base.rstrip('/').endswith('/v1'):
        api_base = api_base.rstrip('/') + '/v1'

    client = OpenAI(api_key=api_key, base_url=api_base)

    user_content = []
    for ref_path in TEACHER_REF_PATHS:
        if not os.path.isfile(ref_path):
            continue
        with open(ref_path, "rb") as f:
            ref_data = f.read()
        ref_b64 = base64.b64encode(ref_data).decode("ascii")
        user_content.append({
            "type": "image_url",
            "image_url": {"url": f"data:image/jpeg;base64,{ref_b64}"},
        })
    user_content.append({
        "type": "text",
        "text": (
            "请描述以上图片中人物的外貌特征，重点包括：\n"
            "1. 性别\n"
            "2. 大致年龄段\n"
            "3. 发型、发色\n"
            "4. 是否佩戴眼镜及眼镜款式\n"
            "5. 面部轮廓特征\n"
            "6. 整体气质风格\n\n"
            "请用一段简洁的中文描述，不要做身份识别，只描述外貌特征。"
        ),
    })

    messages = [
        {"role": "system", "content": "你是一位专业的人物外貌描述专家。请客观、准确地描述图片中人物的外貌特征。"},
        {"role": "user", "content": user_content},
    ]

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            print(f"[analyze] 老师特征提取 API (第 {attempt}/{MAX_RETRIES} 次)")
            resp = client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=0.1,
                max_tokens=500,
            )
            content = resp.choices[0].message.content or ""
            content = content.strip()
            if content:
                print(f"[analyze] 老师特征描述: {content}")
                return content
        except Exception as e:
            backoff = 2 ** (attempt - 1)
            print(f"[analyze] 特征提取 API 调用失败：{e}; {backoff}s 后重试", file=sys.stderr)
            time.sleep(backoff)

    return ""


def find_matching_frame(api_base: str, api_key: str, model: str,
                         all_frames: List[dict], teacher_description: str) -> dict:
    """基于老师外貌特征描述，在视频帧中搜索匹配的帧。

    不发送参考图（避免触发模型安全策略），只发送视频帧 + 特征描述文本。
    分批发送，每批 5 帧（纯视频帧，无参考图，不会超 API 限制）。

    Returns: {"frame": "frame_XX", "confidence": int, "reason": str}
    """
    if not teacher_description:
        return {"frame": None, "confidence": 0, "reason": "无老师特征描述，无法扫描"}

    try:
        from openai import OpenAI  # type: ignore
    except ImportError as e:
        raise RuntimeError(f"未安装 openai 库: {e}")

    if not api_base.rstrip('/').endswith('/v1'):
        api_base = api_base.rstrip('/') + '/v1'

    client = OpenAI(api_key=api_key, base_url=api_base)

    batch_size = 5  # 纯视频帧，无参考图，每批可发更多
    best_result = {"frame": None, "confidence": 0, "reason": ""}

    for batch_start in range(0, len(all_frames), batch_size):
        batch = all_frames[batch_start:batch_start + batch_size]
        batch_indices = [f["index"] for f in batch]

        user_content = []
        for fr in batch:
            user_content.append({
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{fr['b64']}"},
            })

        frame_desc = "、".join([f"第{idx}秒" for idx in batch_indices])
        user_content.append({
            "type": "text",
            "text": (
                f"以上 {len(batch)} 张图片是视频的 {frame_desc} 关键帧。\n\n"
                f"我们需要在视频帧中找到一位老师，其外貌特征如下：\n"
                f"{teacher_description}\n\n"
                "请判断每帧中是否出现了符合上述特征描述的人物，并给出匹配度评分。\n\n"
                "评分标准：\n"
                "- 性别不一致 → confidence=0\n"
                "- 年龄段不一致 → confidence ≤ 20\n"
                "- 性别年龄一致但发型/眼镜等关键特征不匹配 → confidence 30-50\n"
                "- 大部分特征匹配 → confidence 60-80\n"
                "- 几乎所有特征匹配 → confidence 80-100\n"
                "- 帧中无人物 → confidence=0\n\n"
                "请严格按以下 JSON 格式回答，不要添加任何其他文字：\n"
                '```json\n'
                '{"frames": [{"frame_index": 帧编号整数, "match": true或false, '
                '"confidence": 0到100的整数, "reason": "理由"}, ...]}'
                '\n```'
            ),
        })

        messages = [
            {"role": "system", "content": (
                "你是一位专业的视觉分析师，擅长根据外貌特征描述在视频帧中识别目标人物。"
                "请根据给定的外貌特征描述，判断每帧中是否出现了符合该描述的人物。"
                "重点关注性别、年龄段、发型、眼镜、面部轮廓等关键特征。"
                "性别不同绝不可能匹配。"
            )},
            {"role": "user", "content": user_content},
        ]

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                print(f"[analyze] 老师帧搜索 API - 帧 {batch_indices} (第 {attempt}/{MAX_RETRIES} 次)")
                resp = client.chat.completions.create(
                    model=model,
                    messages=messages,
                    temperature=0.1,
                    max_tokens=1000,
                )
                content = resp.choices[0].message.content or ""
                result = extract_json(content)
                frame_results = result.get("frames", [])

                for fr_result in frame_results:
                    fr_idx_raw = fr_result.get("frame_index", -1)
                    if fr_idx_raw in batch_indices:
                        actual_idx = fr_idx_raw
                    elif 0 <= fr_idx_raw < len(batch):
                        actual_idx = batch_indices[fr_idx_raw]
                    else:
                        actual_idx = fr_idx_raw

                    conf = fr_result.get("confidence", 0)
                    match_val = fr_result.get("match", False)
                    reason = fr_result.get("reason", "")
                    print(f"[analyze]   帧 {actual_idx}: match={match_val}, confidence={conf}")

                    if match_val and conf > best_result["confidence"]:
                        best_result = {
                            "frame": f"frame_{int(actual_idx):02d}",
                            "confidence": conf,
                            "reason": reason,
                        }
                break
            except Exception as e:
                backoff = 2 ** (attempt - 1)
                print(f"[analyze] 搜索 API 调用失败：{e}; {backoff}s 后重试", file=sys.stderr)
                time.sleep(backoff)

    if best_result["frame"]:
        print(f"[analyze] 搜索完成，最佳匹配帧: {best_result['frame']} "
              f"(confidence={best_result['confidence']})")
    else:
        print("[analyze] 搜索完成，未找到匹配老师的帧", file=sys.stderr)

    return best_result


def _save_recipe_frames(data: dict) -> None:
    """从分析结果中提取食谱帧并保存到 ANALYSE_DIR。

    - 从 data["recipe_frames"]["recipe_frame_indices"] 读取帧编号列表
    - 将对应帧图片复制到 ANALYSE_DIR/recipe_ref_N.jpg（最多3帧）
    - 图片超过 200KB 时进行压缩
    """
    recipe_data = data.get("recipe_frames", {})
    if not recipe_data:
        return

    recipe_indices = recipe_data.get("recipe_frame_indices", [])
    if not recipe_indices:
        print("[analyze] 未检测到食谱参考帧，跳过")
        return

    recipe_desc = recipe_data.get("recipe_description", "")
    print(f"[analyze] 检测到 {len(recipe_indices)} 个食谱帧: {recipe_indices}")
    if recipe_desc:
        print(f"[analyze] 食谱内容: {recipe_desc}")

    saved_count = 0
    for i, frame_idx in enumerate(recipe_indices[:3], 1):  # 最多3帧
        frame_file = os.path.join(FRAMES_DIR, f"frame_{int(frame_idx):02d}.jpg")
        if not os.path.isfile(frame_file):
            print(f"[analyze] 警告：食谱帧 frame_{int(frame_idx):02d}.jpg 不存在，跳过", file=sys.stderr)
            continue

        dest = os.path.join(_ANALYSE_DIR, f"recipe_ref_{i}.jpg")

        # 检查文件大小，超过 200KB 则压缩
        file_size = os.path.getsize(frame_file)
        if file_size > 200 * 1024:
            try:
                from PIL import Image  # type: ignore
                img = Image.open(frame_file)
                # 压缩到 200KB 以下
                quality = 85
                while quality > 20:
                    img.save(dest, "JPEG", quality=quality)
                    if os.path.getsize(dest) <= 200 * 1024:
                        break
                    quality -= 10
                else:
                    # 如果降低质量仍超过，调整尺寸
                    w, h = img.size
                    ratio = (200 * 1024 / os.path.getsize(dest)) ** 0.5
                    img = img.resize((int(w * ratio), int(h * ratio)), Image.LANCZOS)
                    img.save(dest, "JPEG", quality=60)
                print(f"[analyze] 食谱参考帧已压缩保存: {dest} ({os.path.getsize(dest) // 1024}KB)")
            except ImportError:
                # 没有 PIL 则直接复制
                shutil.copy2(frame_file, dest)
                print(f"[analyze] 食谱参考帧已保存(未压缩，缺少Pillow): {dest} ({file_size // 1024}KB)", file=sys.stderr)
        else:
            shutil.copy2(frame_file, dest)
            print(f"[analyze] 食谱参考帧已保存: {dest} ({file_size // 1024}KB)")

        saved_count += 1

    if saved_count > 0:
        print(f"[analyze] 共保存 {saved_count} 张食谱参考图到 {_ANALYSE_DIR}")


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
        # 需要扣除 teacher_ref 图片数量，避免请求体超出网关上限
        try:
            max_api_frames_total = int(os.environ.get("MAX_API_FRAMES", "10"))
        except ValueError:
            max_api_frames_total = 10
        num_teacher_refs = len([p for p in TEACHER_REF_PATHS if os.path.isfile(p)])
        max_api_frames = max(2, max_api_frames_total - num_teacher_refs)  # 至少保留 2 帧
        api_frames = sample_frames_for_api(frames, max_api_frames)
        if len(api_frames) < len(frames):
            picked_idx = [f["index"] for f in api_frames]
            print(f"[analyze] 帧数 {len(frames)} 超过 API 可用配额（MAX_API_FRAMES={max_api_frames_total} - {num_teacher_refs}张老师参考图 = {max_api_frames}），"
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

        # 替换 Prompt 中的品类配置占位符
        cat_cfg = load_category_config()
        system_prompt = system_prompt.replace("{TITLE_POOL_JSON}", json.dumps(cat_cfg.get("title_pool", []), ensure_ascii=False))
        system_prompt = system_prompt.replace("{CONTENT_LIST_NAME}", cat_cfg.get("content_list_name", "课程内容"))

        # 不再注入预设兜底痛点/卖点/利益点：完全依赖视频前30秒的实际信息提取

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

        # ===== 老师帧验证：基于三视图特征描述，确认选中帧确实是老师 =====
        best_tf = data.get("best_teacher_frame", {})
        if best_tf and TEACHER_REF_PATHS:
            selected_frame = best_tf.get("frame", "")
            frame_path = os.path.join(FRAMES_DIR, f"{selected_frame}.jpg")
            if os.path.isfile(frame_path) and len(TEACHER_REF_PATHS) > 0:
                print(f"[analyze] ===== 验证老师帧: {selected_frame} =====")

                # Step 1: 从三视图提取老师外貌特征
                teacher_desc = describe_teacher_from_ref(api_base, api_key, model)
                if not teacher_desc:
                    print("[analyze] 警告：无法提取老师特征描述，跳过验证", file=sys.stderr)
                else:
                    # Step 2: 基于特征描述，在所有帧中搜索匹配的老师帧
                    find_result = find_matching_frame(api_base, api_key, model, frames, teacher_desc)

                    if find_result["frame"] and find_result["confidence"] >= 60:
                        # 找到匹配帧，检查是否与原始选择不同
                        if find_result["frame"] != selected_frame:
                            original_frame = selected_frame
                            data["best_teacher_frame"] = {
                                "frame": find_result["frame"],
                                "reason": (
                                    f"[特征验证纠正] {find_result['reason']} "
                                    f"(原选 {original_frame} 特征不匹配，"
                                    f"新帧 confidence={find_result['confidence']})"
                                ),
                            }
                            # 更新 analysis.json
                            with open(ANALYSIS_PATH, "w", encoding="utf-8") as f:
                                json.dump(data, f, ensure_ascii=False, indent=2)
                            print(f"[analyze] analysis.json 已更新 best_teacher_frame: "
                                  f"{selected_frame} → {find_result['frame']}")
                        else:
                            print(f"[analyze] 老师帧验证通过: {selected_frame} "
                                  f"(confidence={find_result['confidence']})")
                    elif find_result["frame"] and find_result["confidence"] < 60:
                        print(f"[analyze] 老师帧验证：找到的帧置信度较低 "
                              f"({find_result['frame']}, confidence={find_result['confidence']})，保留原选择",
                              file=sys.stderr)
                    else:
                        print(f"[analyze] 警告：基于特征描述未找到匹配老师的帧，保留原选择", file=sys.stderr)
            else:
                print(f"[analyze] 跳过老师帧验证（候选帧或三视图不存在）")

        # ===== 食谱参考帧提取（仅 nutrition 品类）=====
        if get_category_name() == "nutrition":
            _save_recipe_frames(data)

        return 0
    except Exception as e:
        print(f"[analyze] 发生错误：{e}", file=sys.stderr)
        return 9


if __name__ == "__main__":
    sys.exit(main())
