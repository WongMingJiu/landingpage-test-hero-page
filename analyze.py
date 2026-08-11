#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
多模态分析脚本
- 读取 output/frames/ 下的关键帧图片，转为 base64
- 读取 output/transcript.txt
- 使用 assets/categories/{category}/analyze_prompt.md 作为 system prompt
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


def _compress_jpeg_for_api(data: bytes, max_size_kb: int = 100, max_long_edge: int = 1280) -> bytes:
    """将 JPEG 压缩到 ≤ max_size_kb，优先限制最长边，再调低 quality。
    缺少 Pillow 时原样返回。
    """
    try:
        from PIL import Image  # type: ignore
        import io
    except ImportError:
        return data

    if len(data) <= max_size_kb * 1024:
        return data

    try:
        img = Image.open(io.BytesIO(data))
        if img.mode != "RGB":
            img = img.convert("RGB")
        # 1) 先缩放最长边
        w, h = img.size
        long_edge = max(w, h)
        if long_edge > max_long_edge:
            ratio = max_long_edge / long_edge
            img = img.resize((int(w * ratio), int(h * ratio)), Image.LANCZOS)
        # 2) 递减 quality 直到达标
        for quality in (85, 75, 65, 55, 45, 35):
            buf = io.BytesIO()
            img.save(buf, "JPEG", quality=quality, optimize=True)
            out = buf.getvalue()
            if len(out) <= max_size_kb * 1024:
                return out
        return out  # 返回最后一次压缩结果
    except Exception as e:
        print(f"[analyze] 警告：帧压缩失败 {e}，原样发送", file=sys.stderr)
        return data


def load_frames() -> List[dict]:
    """动态扫描 output/frames/ 下的关键帧，返回 [{index, name, b64}, ...]。

    不硬编码帧数量；按文件名编号排序加载所有 frame_XX.jpg 文件。
    """
    if not os.path.isdir(FRAMES_DIR):
        raise FileNotFoundError(f"帧目录不存在: {FRAMES_DIR}")
    frame_files = sorted(glob.glob(os.path.join(FRAMES_DIR, "frame_*.jpg")))
    # 压缩阈值：默认 100KB，避免请求体超过 API 网关上限
    try:
        compress_kb = int(os.environ.get("FRAME_COMPRESS_KB", "100"))
    except ValueError:
        compress_kb = 100
    frames: List[dict] = []
    total_size = 0
    compressed_count = 0
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
        # 压缩到不超过 compress_kb（只在内存处理，不动原文件）
        original_size = len(data)
        data = _compress_jpeg_for_api(data, max_size_kb=compress_kb)
        if len(data) < original_size:
            compressed_count += 1
        total_size += len(data)
        frames.append({
            "index": idx,
            "name": name,
            "b64": base64.b64encode(data).decode("ascii"),
        })
    if compressed_count:
        avg_kb = total_size // max(1, len(frames)) // 1024
        print(f"[analyze] 帧图已压缩：{compressed_count}/{len(frames)} 张被压、平均 {avg_kb}KB、总 {total_size // 1024}KB")
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

    # 帧图片标注帧编号（frame_XX）与时间戳（帧编号即对应秒数）
    num_frames = len(frames)
    frame_ids = [f"frame_{fr['index']:02d}" for fr in frames]
    pairs = "、".join([f"{fid}（第 {fr['index']} 秒）" for fid, fr in zip(frame_ids, frames)])
    ts_desc = (
        f"以上 {num_frames} 张图片按顺序分别是：{pairs}。\n"
        f"请注意：best_teacher_frame.frame 必须从 {', '.join(frame_ids)} 中选择。"
    )
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
            print(f"[analyze][debug] resp type={type(resp).__name__}, repr (前 500 字符): {repr(resp)[:500]}", file=sys.stderr)
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
    """以老师三视图为锚点，多模态比对每帧人脸是否为同一人。

    每批同时附带「全部三视图参考图」+「5 张视频帧」，要求 LLM 以三视图为唯一身份锚点
    做脸部硬比对（脸型、眉眼、鼻嘴、发型、年龄段）。teacher_description 仅作为文本辅助。
    若三视图缺失则降级为纯文本比对（保持向后兼容）。

    Returns: {"frame": "frame_XX", "confidence": int, "reason": str}
    """
    try:
        from openai import OpenAI  # type: ignore
    except ImportError as e:
        raise RuntimeError(f"未安装 openai 库: {e}")

    if not api_base.rstrip('/').endswith('/v1'):
        api_base = api_base.rstrip('/') + '/v1'

    client = OpenAI(api_key=api_key, base_url=api_base)

    # 预读三视图为 base64
    ref_b64_list: List[str] = []
    for ref_path in TEACHER_REF_PATHS:
        if not os.path.isfile(ref_path):
            continue
        try:
            with open(ref_path, "rb") as rf:
                ref_b64_list.append(base64.b64encode(rf.read()).decode("ascii"))
        except Exception as e:
            print(f"[analyze] 读取三视图失败 {ref_path}: {e}", file=sys.stderr)

    use_multimodal = len(ref_b64_list) > 0
    if not use_multimodal and not teacher_description:
        return {"frame": None, "confidence": 0, "reason": "无三视图也无特征描述，无法扫描"}

    # 三视图占位多，每批帧数稍降
    batch_size = 4 if use_multimodal else 5
    best_result = {"frame": None, "confidence": 0, "reason": ""}

    for batch_start in range(0, len(all_frames), batch_size):
        batch = all_frames[batch_start:batch_start + batch_size]
        batch_indices = [f["index"] for f in batch]

        user_content = []

        # 1) 先附带三视图（若可用）
        if use_multimodal:
            for ref_b64 in ref_b64_list:
                user_content.append({
                    "type": "image_url",
                    "image_url": {"url": f"data:image/jpeg;base64,{ref_b64}"},
                })

        # 2) 再附带本批视频帧
        for fr in batch:
            user_content.append({
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{fr['b64']}"},
            })

        frame_desc = "、".join([f"第{idx}秒" for idx in batch_indices])

        if use_multimodal:
            prompt_text = (
                f"前 {len(ref_b64_list)} 张图片是同一位老师的人脸参考图（三视图，正面/侧面/不同角度），"
                f"是判断身份的**唯一锚点**。\n"
                f"后 {len(batch)} 张图片是视频的 {frame_desc} 关键帧。\n\n"
                "任务：仅判断每帧中是否出现「与参考图为同一人」的人脸，做客观脸部相似度比对，"
                "不做任何身份/姓名识别。比对维度（按重要性排序）：\n"
                "1) 脸型轮廓（圆/方/瓜子/长脸）\n"
                "2) 五官比例（眉形、眼形/单双眼皮、鼻型、嘴型）\n"
                "3) 发型 / 发色（长短、扎发方式、发色深浅）\n"
                "4) 年龄段（青年/中年/中老年）\n\n"
                "评分标准（必须严格执行）：\n"
                "- 性别不同 → confidence=0, match=false\n"
                "- 年龄段相差 ≥ 1 档 → confidence ≤ 20, match=false\n"
                "- 仅大类相同（同为中年女性/中年男性）但脸型/五官明显不同 → confidence 30-55, match=false\n"
                "- 脸型 + 五官多数维度一致，仅 1 个维度模糊 → confidence 65-80, match=true\n"
                "- 脸型 + 五官 + 发型 + 年龄段全部高度一致（明显是同一人）→ confidence 85-100, match=true\n"
                "- 帧中无清晰人脸（背影、遮挡、空镜）→ confidence=0, match=false\n"
                "- 帧中出现多人时，只要任一人与参考图同一人即可 match=true\n\n"
                "重要提醒：\n"
                "- **「同为中年女性短发」绝不等于同一人**，必须看脸型、五官细节；如不能确认是同一人，宁可 match=false\n"
                "- 若帧带有「剧情演绎」「演员演绎」「学员」等水印/字幕，confidence 强制下调一档（85→70，70→50）\n"
                f"- 辅助参考特征描述（仅供参考，不能替代脸部比对）：{teacher_description or '（无）'}\n\n"
                "请严格按以下 JSON 格式回答，不要添加任何其他文字：\n"
                '```json\n'
                '{"frames": [{"frame_index": 帧编号整数, "match": true或false, '
                '"confidence": 0到100的整数, "reason": "理由（指出与参考图脸部比对的具体异同）"}, ...]}'
                '\n```'
            )
            system_text = (
                "你是一位专业的人脸相似度比对分析师。"
                "请仅基于客观脸部特征（脸型、五官、发型、年龄段）判断视频帧中的人脸是否与参考图为同一人，"
                "不做身份识别或姓名推断。性别或年龄段不同绝不可能为同一人。"
                "宁可放过，不可错认。"
            )
        else:
            prompt_text = (
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
            )
            system_text = (
                "你是一位专业的视觉分析师，擅长根据外貌特征描述在视频帧中识别目标人物。"
                "请根据给定的外貌特征描述，判断每帧中是否出现了符合该描述的人物。"
                "重点关注性别、年龄段、发型、眼镜、面部轮廓等关键特征。"
                "性别不同绝不可能匹配。"
            )

        user_content.append({"type": "text", "text": prompt_text})

        messages = [
            {"role": "system", "content": system_text},
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


def _save_reference_frames(data: dict, rft: dict) -> None:
    """通用参考帧提取：根据品类配置 reference_frame_types 中的一项 rft，
    从 analysis 结果中提取参考帧并保存到 ANALYSE_DIR。

    rft 字段：
      - name              展示名（仅日志）
      - outer_key         analysis.json 顶层字段名（如 "recipe_frames"）
      - frame_indices_key 帧索引数组的 key（如 "recipe_frame_indices"）
      - description_key   描述字段 key（可选，仅日志）
      - output_prefix     输出文件前缀（如 "recipe_ref"）
      - max_count         最多保存几张（默认 3）
      - max_size_kb       超过此大小则压缩（默认 200）
    """
    name = rft.get("name", "reference")
    outer_key = rft.get("outer_key")
    frame_indices_key = rft.get("frame_indices_key")
    description_key = rft.get("description_key", "")
    output_prefix = rft.get("output_prefix", f"{name}_ref")
    max_count = int(rft.get("max_count", 3) or 3)
    max_size_kb = int(rft.get("max_size_kb", 200) or 200)
    max_size_bytes = max_size_kb * 1024

    if not outer_key or not frame_indices_key:
        print(f"[analyze] 警告：reference_frame_types[{name}] 配置缺 outer_key 或 frame_indices_key，跳过", file=sys.stderr)
        return

    section = data.get(outer_key, {})
    if not section:
        return

    indices = section.get(frame_indices_key, [])
    if not indices:
        print(f"[analyze] 未检测到 {name} 参考帧，跳过")
        return

    if description_key:
        desc = section.get(description_key, "")
        if desc:
            print(f"[analyze] {name} 描述: {desc}")

    print(f"[analyze] 检测到 {len(indices)} 个 {name} 帧: {indices}")

    saved_count = 0
    for i, frame_idx in enumerate(indices[:max_count], 1):
        frame_file = os.path.join(FRAMES_DIR, f"frame_{int(frame_idx):02d}.jpg")
        if not os.path.isfile(frame_file):
            print(f"[analyze] 警告：{name} 帧 frame_{int(frame_idx):02d}.jpg 不存在，跳过", file=sys.stderr)
            continue

        dest = os.path.join(_ANALYSE_DIR, f"{output_prefix}_{i}.jpg")
        file_size = os.path.getsize(frame_file)

        if file_size > max_size_bytes:
            try:
                from PIL import Image  # type: ignore
                img = Image.open(frame_file)
                quality = 85
                while quality > 20:
                    img.save(dest, "JPEG", quality=quality)
                    if os.path.getsize(dest) <= max_size_bytes:
                        break
                    quality -= 10
                else:
                    w, h = img.size
                    ratio = (max_size_bytes / os.path.getsize(dest)) ** 0.5
                    img = img.resize((int(w * ratio), int(h * ratio)), Image.LANCZOS)
                    img.save(dest, "JPEG", quality=60)
                print(f"[analyze] {name} 参考帧已压缩保存: {dest} ({os.path.getsize(dest) // 1024}KB)")
            except ImportError:
                shutil.copy2(frame_file, dest)
                print(f"[analyze] {name} 参考帧已保存(未压缩，缺少Pillow): {dest} ({file_size // 1024}KB)", file=sys.stderr)
        else:
            shutil.copy2(frame_file, dest)
            print(f"[analyze] {name} 参考帧已保存: {dest} ({file_size // 1024}KB)")

        saved_count += 1

    if saved_count > 0:
        print(f"[analyze] 共保存 {saved_count} 张 {name} 参考图到 {_ANALYSE_DIR}")


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

        # 采样策略：按步长（默认 3）取帧 → 只保留前 N 张
        # 总图数 = 参考图 N参 + 帧 N帧 ≤ MAX_API_TOTAL（默认 10），避免 API 网关超限
        try:
            sample_step = int(os.environ.get("FRAME_SAMPLE_STEP", "3"))
        except ValueError:
            sample_step = 3
        sample_step = max(1, sample_step)
        try:
            max_total = int(os.environ.get("MAX_API_TOTAL", "10"))
        except ValueError:
            max_total = 10
        num_teacher_refs = len([p for p in TEACHER_REF_PATHS if os.path.isfile(p)])
        # 默认让帧数 = MAX_API_TOTAL - num_teacher_refs；也允许 FRAME_SAMPLE_KEEP 显式覆盖
        default_keep = max(2, max_total - num_teacher_refs)
        try:
            sample_keep = int(os.environ.get("FRAME_SAMPLE_KEEP", str(default_keep)))
        except ValueError:
            sample_keep = default_keep
        sample_keep = max(1, sample_keep)
        sampled = [f for i, f in enumerate(frames) if i % sample_step == 0]
        api_frames = sampled[:sample_keep]
        if len(api_frames) < len(frames):
            picked_idx = [f["index"] for f in api_frames]
            print(f"[analyze] 按步长 {sample_step} 采样后取前 {sample_keep} 张（+{num_teacher_refs}参考图 = {len(api_frames)+num_teacher_refs}张总图）：{len(frames)} 帧 → {len(api_frames)} 帧发送给 API: {picked_idx}")
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

        # 老师帧选择完全交给 LLM（依赖 prompt 第 10 节的「身份匹配 + 剔除多人 + 选最早」三步规则），
        # 不再做基于三视图特征比对的二次校验，避免反向误覆盖。

        # ===== 通用参考帧提取（由品类配置 reference_frame_types 驱动）=====
        ref_frame_types = cat_cfg.get("reference_frame_types", []) or []
        for rft in ref_frame_types:
            _save_reference_frames(data, rft)

        return 0
    except Exception as e:
        print(f"[analyze] 发生错误：{e}", file=sys.stderr)
        return 9


if __name__ == "__main__":
    sys.exit(main())
