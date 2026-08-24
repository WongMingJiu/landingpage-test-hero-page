#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V2.1a tagging pipeline.

Two-stage decision-window pipeline (spec §5 / §12):
  stage 1 (0–30s)  -> if semantic_sufficiency==insufficient ->
  stage 2 (30–60s extension) -> if still insufficient -> review.needed

Correction #1 (frame budget): if a single multimodal request cannot hold the
full frame set, the staged multi-request path is used — Opening 0–10s 1 fps is
**never** degraded, all frames are still seen across requests.
Correction #2 (evidence source): MVP has no audio-understanding component, so
``source="audio"`` is rejected by the schema validator (``audio_enabled=False``).
"""
from __future__ import annotations

import base64
import io
import json
import os
import random
import re
import time
import traceback
from typing import Any

from . import frames as frames_mod
from . import schema
from . import taxonomy

JPEG_MAGIC = b"\xff\xd8"
SCHEMA_VERSION = "creative_tagging_v1"

_PROMPT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "prompts")


# --------------------------------------------------------------------------- #
# Reusable helpers (adapted from V1 analyze.py; not imported to keep V2 isolated)
# --------------------------------------------------------------------------- #
def _compress_jpeg(data: bytes, max_size_kb: int = 100, max_long_edge: int = 1280) -> bytes:
    try:
        from PIL import Image  # type: ignore
    except ImportError:
        return data
    if len(data) <= max_size_kb * 1024:
        return data
    try:
        img = Image.open(io.BytesIO(data))
        if img.mode != "RGB":
            img = img.convert("RGB")
        w, h = img.size
        long_edge = max(w, h)
        if long_edge > max_long_edge:
            ratio = max_long_edge / long_edge
            img = img.resize((int(w * ratio), int(h * ratio)), Image.LANCZOS)
        for quality in (85, 75, 65, 55, 45, 35):
            buf = io.BytesIO()
            img.save(buf, "JPEG", quality=quality, optimize=True)
            out = buf.getvalue()
            if len(out) <= max_size_kb * 1024:
                return out
        return out
    except Exception:
        return data


def extract_json(text: str) -> dict:
    text = text.strip()
    if not text:
        raise ValueError("empty model response")
    m = re.search(r"```json\s*(.*?)\s*```", text, re.DOTALL | re.IGNORECASE)
    if m:
        return json.loads(m.group(1))
    m = re.search(r"```\s*(.*?)\s*```", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        return json.loads(text[start: end + 1])
    return json.loads(text)


# --------------------------------------------------------------------------- #
# Frame loading
# --------------------------------------------------------------------------- #
def load_frames(seconds: list[int], frames_dir: str, compress_kb: int = 100,
                 max_edge: int | None = None) -> list[dict]:
    """Load + compress + base64-encode the frames for the given absolute seconds.

    ``max_edge`` (long-edge pixel cap) defaults to env ``V2_FRAME_MAX_EDGE``
    (1280). Lowering it cuts vision tokens and inference time at the cost of
    fine detail — useful when a gateway upstream times out on many frames.
    """
    if max_edge is None:
        max_edge = int(os.environ.get("V2_FRAME_MAX_EDGE", "1280"))
    out: list[dict] = []
    for sec in seconds:
        path = os.path.join(frames_dir, f"frame_{sec:02d}.jpg")
        if not os.path.isfile(path):
            continue
        with open(path, "rb") as f:
            data = f.read()
        if not data.startswith(JPEG_MAGIC):
            print(f"[tagging] warn: {path} may not be JPEG", flush=True)
        data = _compress_jpeg(data, max_size_kb=compress_kb, max_long_edge=max_edge)
        out.append({"sec": sec, "b64": base64.b64encode(data).decode("ascii")})
    if not out:
        raise FileNotFoundError(f"no frames found in {frames_dir} for seconds {seconds}")
    return out


def _vision_user_content(fr_list: list[dict], transcript_segs: list[dict],
                         window_label: str) -> list[dict]:
    """Build the multimodal user message: images + per-second caption + transcript."""
    parts: list[dict] = []
    for fr in fr_list:
        parts.append({"type": "image_url",
                      "image_url": {"url": f"data:image/jpeg;base64,{fr['b64']}"}})
    caps = "、".join(f"frame_{fr['sec']:02d}（第 {fr['sec']} 秒）" for fr in fr_list)
    parts.append({"type": "text",
                  "text": f"以上 {len(fr_list)} 张图片为决策窗口 {window_label} 的帧，按顺序分别是：{caps}。"
                          f"请结合下方带时间戳转写综合分析。注意画面字幕/横幅/标题卡文字。"})
    # timestamped transcript
    if transcript_segs:
        lines = []
        for s in transcript_segs:
            lines.append(f"[{s['start']:.1f}-{s['end']:.1f}s] {s['text']}")
        parts.append({"type": "text",
                      "text": "以下是带时间戳的 Whisper 转写（空缺可能对应演唱段而非无内容）：\n" + "\n".join(lines)})
    else:
        parts.append({"type": "text",
                      "text": "Whisper 转写为空或稀疏（可能为纯演唱/无口播）。这是 transcript_sparse，"
                              "不等于语义不足；不得仅因此扩窗。"})
    return parts

def _is_payload_too_large(exc: Exception) -> bool:
    """Heuristic: did the gateway reject (size/image-count) or time out?
    Either triggers the staged multi-request fallback (correction #1)."""
    if os.environ.get("V2_FORCE_STAGED", "").strip() in ("1", "true", "yes"):
        return True
    s = str(exc).lower()
    markers = ("413", "request entity too large", "too large", "payload",
               "maximum", "image", "context length", "too many", "max_images",
               "timeout", "timed out", "upstream call timeout", "rate limit")
    return any(m in s for m in markers)

# API client (OpenAI-compatible, adapted from V1 call_api)
# --------------------------------------------------------------------------- #
class ApiClient:
    def __init__(self, api_base: str, api_key: str, model: str,
                 temperature: float = 0.0, max_tokens: int = 16384, max_retries: int = 3):
        self.api_base = api_base
        self.api_key = api_key
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.max_retries = max_retries
        self._client = None

    def _ensure(self):
        if self._client is not None:
            return
        try:
            from openai import OpenAI  # type: ignore
        except ImportError as e:
            raise RuntimeError(f"openai library not installed: {e}") from e
        base = self.api_base.rstrip("/")
        if not base.endswith("/v1"):
            base = base + "/v1"
        self._client = OpenAI(api_key=self.api_key, base_url=base)

    def chat(self, system: str, user_content: list[dict]) -> str:
        self._ensure()
        messages = [{"role": "system", "content": system},
                    {"role": "user", "content": user_content}]
        last_err: Exception | None = None
        for attempt in range(1, self.max_retries + 1):
            try:
                resp = self._client.chat.completions.create(
                    model=self.model, messages=messages,
                    temperature=self.temperature, max_tokens=self.max_tokens,
                )
                content = resp.choices[0].message.content or ""
                if not content.strip():
                    raise RuntimeError("API returned empty content")
                return content
            except Exception as e:
                last_err = e
                # exponential backoff with ±50% jitter: fixed delays collide with
                # the gateway's own retry storms during upstream congestion
                backoff = 2 ** (attempt - 1) * (0.5 + random.random())
                print(f"[tagging] API call failed (attempt {attempt}/{self.max_retries}): {e}; "
                      f"retry in {backoff:.1f}s", flush=True)
                time.sleep(backoff)
        raise RuntimeError(f"API call failed after {self.max_retries} attempts: {last_err}")


# --------------------------------------------------------------------------- #
# Staged multi-request fallback (correction #1) + structured evidence layer
# --------------------------------------------------------------------------- #
_EVIDENCE_SYSTEM = """你是 V2.1a 的结构化证据提取器。你只看到决策窗口的一部分帧 + 带时间戳转写。
你的唯一任务是登记**直接观察到的证据**，不做任何最终标签判定。
输出一个 JSON 对象，严格如下结构：
{"observations": [
  {"time": "00:00-00:04",
   "source": "visual|subtitle|transcript",
   "fact": "客观可观察的事实（画面内容/字幕原文/转写原文，不做推断总结）",
   "candidates": {"opening": [], "value": [], "expectation": []},
   "adjacent": "可选：对易混淆相邻候选的区分线索（如：是否存在学员身份/学习事实/改善结果；是否给出可跟做动作）"}
]}
硬要求：
- fact 只写直接观察；禁止臆测、禁止最终分类结论；candidates 只是候选信号（可用 taxonomy 标签名，也可留空），不是决定；
- source 归属：视觉观察记 visual，画面字幕/横幅文字记 subtitle，转写内容记 transcript；不得使用 audio；
- 每个有意义的帧/字幕/转写段至少登记一条 observation；
- 只输出 JSON，无任何解释文字。"""


def _staged_notes_batches(fr_all: list[dict]) -> list[list[dict]]:
    """Split ALL frames into adaptive batches (V2_STAGED_BATCH, default 6).
    Full coverage preserved — Opening 0–10s 1 fps never sacrificed (C1)."""
    bs = max(1, int(os.environ.get("V2_STAGED_BATCH", "6")))
    return [fr_all[i:i + bs] for i in range(0, len(fr_all), bs)]


def _time_start_seconds(t: str) -> float:
    """Best-effort parse of the start second from a free-form time range string.
    Unparseable values sort last (stable ordering is the goal, not semantics)."""
    m = re.search(r"(\d+(?:\.\d+)?)", t or "")
    if not m:
        return 10 ** 6
    v = float(m.group(1))
    # "MM:SS" style: if the match is followed by ':', treat as minutes
    idx = m.end()
    if idx < len(t) and t[idx] == ":":
        m2 = re.search(r"(\d+(?:\.\d+)?)", t[idx + 1:])
        if m2:
            v = v * 60 + float(m2.group(1))
    return v


def _normalize_observations(raw: str, window: str) -> list[dict]:
    """Parse one batch response into normalized observation records.

    Keeps factual observations + candidate signals without classification
    decisions. Invalid JSON degrades to a single unparsed record rather than
    dropping the batch (C1: no evidence silently lost).
    """
    try:
        data = extract_json(raw)
        obs = data.get("observations") if isinstance(data, dict) else None
        if not isinstance(obs, list):
            raise ValueError("missing observations list")
    except Exception:
        text = (raw or "").strip()[:800]
        return [{"time": "", "source": "visual", "fact": text or "(empty batch response)",
                 "candidates": {}, "adjacent": None, "window": window, "unparsed": True}]
    out: list[dict] = []
    for o in obs:
        if not isinstance(o, dict):
            continue
        fact = str(o.get("fact") or "").strip()
        if not fact:
            continue
        src = o.get("source")
        if src not in ("visual", "subtitle", "transcript"):
            src = "visual"
        cand_raw = o.get("candidates") or {}
        if not isinstance(cand_raw, dict):
            cand_raw = {}
        cand = {}
        for k in ("opening", "value", "expectation"):
            v = cand_raw.get(k)
            if isinstance(v, list):
                cand[k] = [str(x).strip() for x in v if str(x).strip()][:6]
        adj = o.get("adjacent")
        out.append({
            "time": str(o.get("time") or "").strip()[:32],
            "source": src,
            "fact": fact[:400],
            "candidates": cand,
            "adjacent": (str(adj).strip()[:300] if adj else None),
            "window": window,
        })
    return out


def _collect_staged_evidence(api: ApiClient, fr_all: list[dict],
                             transcript_segs: list[dict]) -> list[dict]:
    """One structured-evidence call per batch; returns ONE normalized,
    deterministically ordered + deduplicated observation list.

    Deterministic ordering (time, source, fact) removes batch/ordering
    nondeterminism from the final adjudication input.
    """
    batches = _staged_notes_batches(fr_all)
    print(f"[tagging] staged: {len(batches)} batch(es) of ~{len(batches[0]) if batches else 0} "
          f"(total {len(fr_all)} frames, all seen)", flush=True)
    obs_all: list[dict] = []
    for i, b in enumerate(batches):
        window = f"秒{b[0]['sec']}-{b[-1]['sec']}"
        raw = api.chat(_EVIDENCE_SYSTEM, _vision_user_content(b, transcript_segs, window))
        obs_all.extend(_normalize_observations(raw, window))
    # deterministic sort + dedupe
    obs_all.sort(key=lambda o: (_time_start_seconds(o["time"]), o["source"], o["fact"]))
    seen: set[tuple] = set()
    deduped: list[dict] = []
    for o in obs_all:
        key = (o["time"], o["source"], o["fact"])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(o)
    print(f"[tagging] staged evidence: {len(deduped)} observations "
          f"({sum(1 for o in deduped if o.get('unparsed'))} unparsed fallback)", flush=True)
    return deduped


def _render_observations(obs: list[dict]) -> str:
    """Stable single-line-per-observation rendering for the adjudication call."""
    lines = []
    for o in obs:
        cand = o.get("candidates") or {}
        cand_s = "; ".join(f"{k}=" + "、".join(v) for k, v in cand.items() if v)
        line = f"- [{o['window']}] {o['time'] or '?'} | {o['source']} | {o['fact']}"
        if cand_s:
            line += f" | 候选信号: {cand_s}"
        if o.get("adjacent"):
            line += f" | 相邻区分: {o['adjacent']}"
        lines.append(line)
    return "\n".join(lines)

def _build_contact_sheet(fr_all: list[dict], columns: int = 5,
                         tile_width: int = 240, image_height: int = 135,
                         label_height: int = 22) -> dict:
    """Compose every selected frame into one timestamped JPEG contact sheet.

    The final merge re-sees the raw visual sequence as one image, restoring
    cross-batch gestalt without sending 20 separate image parts. Every frame
    remains present (C1); labels use ASCII in-image for font portability and a
    full Chinese second mapping in the adjacent text payload.
    """
    if not fr_all:
        raise ValueError("cannot build contact sheet from empty frame list")
    try:
        from PIL import Image, ImageDraw, ImageFont  # type: ignore
    except ImportError as e:
        raise RuntimeError(f"Pillow required for contact sheet: {e}") from e

    columns = max(1, min(columns, len(fr_all)))
    rows = (len(fr_all) + columns - 1) // columns
    tile_height = image_height + label_height
    sheet = Image.new("RGB", (columns * tile_width, rows * tile_height), (18, 18, 18))
    font = ImageFont.load_default()
    resample = Image.Resampling.LANCZOS
    labels: list[str] = []

    for i, fr in enumerate(fr_all):
        sec = int(fr["sec"])
        labels.append(f"frame_{sec:02d}（第 {sec} 秒）")
        src = Image.open(io.BytesIO(base64.b64decode(fr["b64"]))).convert("RGB")
        src.thumbnail((tile_width, image_height), resample)
        tile = Image.new("RGB", (tile_width, tile_height), (12, 12, 12))
        tile.paste(src, ((tile_width - src.width) // 2, (image_height - src.height) // 2))
        draw = ImageDraw.Draw(tile)
        draw.rectangle((0, image_height, tile_width, tile_height), fill=(0, 0, 0))
        draw.text((6, image_height + 4), f"frame_{sec:02d} | {sec}s", font=font, fill=(255, 255, 255))
        x = (i % columns) * tile_width
        y = (i // columns) * tile_height
        sheet.paste(tile, (x, y))

    buf = io.BytesIO()
    sheet.save(buf, "JPEG", quality=78, optimize=True)
    return {
        "b64": base64.b64encode(buf.getvalue()).decode("ascii"),
        "labels": labels,
        "width": sheet.width,
        "height": sheet.height,
    }




def _merge_user_content(observations: list[dict], transcript_segs: list[dict],
                        contact_sheet: dict | None = None,
                        feedback: list[str] | None = None) -> list[dict]:
    """Constrained final adjudication input: structured evidence inventory +
    transcript + contact sheet. No free-text intermediate notes; the model
    applies taxonomy definitions / decision priorities / boundary rules from
    the system prompt to a deterministically rendered evidence list."""
    parts: list[dict] = []
    if contact_sheet:
        parts.append({
            "type": "image_url",
            "image_url": {"url": f"data:image/jpeg;base64,{contact_sheet['b64']}"},
        })
        parts.append({
            "type": "text",
            "text": (
                "上图是 0-30s 全部已选帧按时间顺序组成的 contact sheet："
                + "、".join(contact_sheet["labels"])
                + "。它仅用于复核整体视觉主轴与跨帧语境；事实认定以下方结构化证据清单与转写为准。"
            ),
        })
    parts.append({"type": "text",
                  "text": "以下是 0-30s 全部帧的结构化证据清单（已按时间排序去重，candidates 仅为候选信号，不是结论）：\n"
                          + _render_observations(observations)})
    if transcript_segs:
        lines = [f"[{s['start']:.1f}-{s['end']:.1f}s] {s['text']}" for s in transcript_segs]
        parts.append({"type": "text", "text": "带时间戳转写：\n" + "\n".join(lines)})
    parts.append({
        "type": "text",
        "text": (
            "现在进行最终裁决：只能基于上方结构化证据清单与转写认定事实，"
            "不得补充清单之外的事实；把系统指令中的 taxonomy 定义、决策优先级与边界规则"
            "逐条应用到证据上，输出 creative_tagging_v1 JSON（0-30s 主窗口）。"
            "裁决原则：1) Opening 以第一有效开头单元与决策优先级判断，"
            "呈现形式不等于说服机制，辅助信任证据不等于开场驱动，后段不得篡位；"
            "2) User Expectation 与 Opening 独立判断，禁止机械映射；"
            "已给出具体动作/跟练时优先掌握简单方法，仅在主要解释原理且无可操作方法时才用理解专业原理；"
            "3) Value Salience 按 Primary consistency check 逐候选检查。"
        ),
    })
    if feedback:
        parts.append({"type": "text",
                      "text": "你上一次输出未通过校验，错误如下：\n- " + "\n- ".join(feedback) +
                              "\n请修正并重新输出完整的 creative_tagging_v1 JSON。"})
    return parts


# --------------------------------------------------------------------------- #
# Replayable structured-evidence artifact (infrastructure; decision logic and
# creative_tagging_v1 schema unchanged)
# --------------------------------------------------------------------------- #
STRUCTURED_EVIDENCE_SCHEMA = "structured_evidence_v1"
STRUCTURED_EVIDENCE_FILENAME = "structured_evidence.json"


def save_structured_evidence(path: str, observations: list[dict],
                             transcript_segs: list[dict],
                             contact_sheet: dict | None,
                             creative_id: str | None = None) -> dict:
    """Persist the normalized evidence produced BEFORE final adjudication so
    adjudication can be replayed without video/multimodal re-extraction."""
    artifact = {
        "schema": STRUCTURED_EVIDENCE_SCHEMA,
        "creative_id": creative_id,
        "window": {"primary_seconds": 30, "used_seconds": 30},
        "observations": observations,
        "transcript": transcript_segs or [],
        "contact_sheet": contact_sheet,
    }
    d = os.path.dirname(os.path.abspath(path))
    if d:
        os.makedirs(d, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(artifact, f, ensure_ascii=False)
    return artifact


def load_structured_evidence(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        artifact = json.load(f)
    if not isinstance(artifact, dict) or artifact.get("schema") != STRUCTURED_EVIDENCE_SCHEMA:
        raise ValueError(f"unsupported evidence artifact schema: "
                         f"{artifact.get('schema') if isinstance(artifact, dict) else type(artifact)!r}")
    if not isinstance(artifact.get("observations"), list) or not artifact["observations"]:
        raise ValueError("evidence artifact contains no observations")
    return artifact


def _adjudicate(api: "ApiClient", system: str, tax: taxonomy.TaxonomyData,
                observations: list[dict], transcript_segs: list[dict],
                contact_sheet: dict | None, audio_enabled: bool,
                max_retries: int) -> dict:
    """Shared constrained final adjudication (used by the staged path and by
    replay); only schema-validation retries, identical semantics."""
    last_errs: list[str] = []
    for attempt in range(1, max_retries + 1):
        user = _merge_user_content(observations, transcript_segs, contact_sheet,
                                   last_errs or None)
        raw = api.chat(system, user)
        try:
            data = extract_json(raw)
        except Exception as e:
            last_errs = [f"JSON 解析失败: {e}"]
            print(f"[tagging] staged merge parse failed (attempt {attempt}): {e}", flush=True)
            continue
        errs = schema.validate(data, tax, audio_enabled=audio_enabled)
        if not errs:
            return data
        last_errs = errs
        print(f"[tagging] staged merge validation failed (attempt {attempt}): {errs}", flush=True)
    raise RuntimeError(
        f"staged merge failed validation after {max_retries} attempts; "
        f"last errs: {last_errs}"
    )


# --------------------------------------------------------------------------- #
# Pipeline
# --------------------------------------------------------------------------- #
class TaggingConfig:
    @classmethod
    def from_env(cls) -> "TaggingConfig":
        c = cls()
        c.api_base = os.environ.get("V2_API_BASE_URL", "").strip() or os.environ.get("API_BASE_URL", "").strip()
        c.api_key = os.environ.get("V2_API_KEY", "").strip() or os.environ.get("API_KEY", "").strip()
        c.model = os.environ.get("V2_MODEL_NAME", "").strip() or os.environ.get("MODEL_NAME", "").strip()
        c.frame_budget = int(os.environ.get("V2_FRAME_BUDGET", "20"))
        c.compress_kb = int(os.environ.get("V2_FRAME_COMPRESS_KB", "100"))
        c.frame_max_edge = int(os.environ.get("V2_FRAME_MAX_EDGE", "1280"))
        c.temperature = float(os.environ.get("V2_TEMPERATURE", "0"))
        c.max_retries = int(os.environ.get("V2_MAX_RETRIES", "3"))   # validation-retry count
        # Default 3: with V2_FORCE_STAGED the single-request fallback no longer
        # relies on a fast failure, and one exhausted batch fails the whole video.
        c.api_retries = int(os.environ.get("V2_API_RETRIES", "3"))   # per-call API-retry count
        c.audio_enabled = os.environ.get("V2_AUDIO_UNDERSTANDING_ENABLED", "").strip() in ("1", "true", "yes")
        c.whisper_model = os.environ.get("WHISPER_MODEL", "small").strip() or "small"
        return c

    def __init__(self):
        self.api_base = ""
        self.api_key = ""
        self.model = ""
        self.frame_budget = 20
        self.compress_kb = 100
        self.frame_max_edge = 1280
        self.temperature = 0.0
        self.max_retries = 3
        self.api_retries = 3
        self.audio_enabled = False
        self.whisper_model = "small"


def _load_prompt(name: str) -> str:
    with open(os.path.join(_PROMPT_DIR, name), "r", encoding="utf-8") as f:
        return f.read()


def build_system_prompt(tax: taxonomy.TaxonomyData) -> str:
    tpl = _load_prompt("creative_tagging.md")
    return (tpl.replace("{{VALUE_TAXONOMY}}", tax.render_value())
            .replace("{{OPENING_TAXONOMY}}", tax.render_opening())
            .replace("{{EXPECTATION_TAXONOMY}}", tax.render_expectation()))


def _call_with_validation(api: ApiClient, system: str, user_content: list[dict],
                           tax: taxonomy.TaxonomyData, audio_enabled: bool,
                           max_retries: int) -> dict:
    """Call model, parse, validate; retry with error feedback on validation failure."""
    last_errs: list[str] = []
    last_raw = ""
    for attempt in range(1, max_retries + 1):
        msg = list(user_content)
        if last_errs:
            msg.append({"type": "text",
                        "text": "你上一次输出未通过校验，错误如下：\n- " + "\n- ".join(last_errs) +
                                "\n请修正并重新输出完整的 creative_tagging_v1 JSON。"})
        raw = api.chat(system, msg)
        last_raw = raw
        try:
            data = extract_json(raw)
        except Exception as e:
            last_errs = [f"JSON 解析失败: {e}"]
            print(f"[tagging] parse failed (attempt {attempt}): {e}", flush=True)
            continue
        errs = schema.validate(data, tax, audio_enabled=audio_enabled)
        if not errs:
            return data
        last_errs = errs
        print(f"[tagging] validation failed (attempt {attempt}): {errs}", flush=True)
    raise RuntimeError(f"model output failed validation after {max_retries} attempts; last raw:\n{last_raw[:2000]}")


class TaggingPipeline:
    def __init__(self, cfg: TaggingConfig, tax: taxonomy.TaxonomyData | None = None):
        self.cfg = cfg
        self.tax = tax or taxonomy.load_taxonomy("singing")
        self.system = build_system_prompt(self.tax)
        self.ext_system = _load_prompt("extension.md")
        from . import provider  # thin adapter: provider swappable via env/config
        self.api = provider.make_provider(cfg)

    # ------------------------------------------------------------------ #
    def _primary_call(self, fr_all: list[dict], transcript_segs: list[dict],
                      evidence_path: str | None = None) -> dict:
        if os.environ.get("V2_FORCE_STAGED", "").strip() in ("1", "true", "yes"):
            print("[tagging] V2_FORCE_STAGED=1 -> staged multi-request (correction #1)", flush=True)
            return self._staged_primary(fr_all, transcript_segs, evidence_path)
        user = _vision_user_content(fr_all, transcript_segs, "0-30s")
        try:
            return _call_with_validation(self.api, self.system, user, self.tax,
                                         self.cfg.audio_enabled, self.cfg.max_retries)
        except Exception as e:
            if _is_payload_too_large(e):
                print("[tagging] single request too large/timed out; switching to staged multi-request (correction #1)", flush=True)
                return self._staged_primary(fr_all, transcript_segs, evidence_path)
            raise

    # ------------------------------------------------------------------ #
    def run(self, video: str, creative_id: str, work_dir: str) -> dict:
        from . import extract as extract_mod
        os.makedirs(work_dir, exist_ok=True)
        media = extract_mod.MediaExtraction(video, work_dir, self.cfg.whisper_model)

        print(f"[tagging] extracting primary 0-30s (duration={media.duration:.1f}s)", flush=True)
        prim = media.extract_primary()
        n_frames = len(prim["frame_seconds"])
        selected = frames_mod.select_primary_frames(n_frames=n_frames, budget=self.cfg.frame_budget)
        needs_staged = len(selected) < n_frames and len(selected) <= frames_mod.OPENING_END
        # load + compress frames for the selected seconds
        fr_all = load_frames(selected, media.frames_dir, self.cfg.compress_kb)
        print(f"[tagging] frames: available={n_frames} selected={len(selected)} staged={needs_staged}",
              flush=True)

        # stage 1
        evidence_path = os.path.join(work_dir, STRUCTURED_EVIDENCE_FILENAME)
        if needs_staged and not fr_all:
            # budget too small to hold opening -> force staged
            fr_all = load_frames(frames_mod.opening_frame_seconds(n_frames) +
                                 frames_mod.tail_frame_seconds(n_frames),
                                 media.frames_dir, self.cfg.compress_kb)
            data = self._staged_primary(fr_all, prim["segments"], evidence_path)
        else:
            data = self._primary_call(fr_all, prim["segments"], evidence_path)

        # ensure creative_id set
        data["creative_id"] = creative_id

        # stage 2: extension
        dw = data.get("decision_window", {})
        if dw.get("semantic_sufficiency") == "insufficient" or dw.get("extended") is True:
            print("[tagging] stage 1 insufficient; extracting 30-60s extension", flush=True)
            ext = media.extract_extension()
            if ext["frame_seconds"]:
                ext_selected = frames_mod.extension_frame_seconds(
                    n_ext_frames=len(ext["frame_seconds"]), step=3, base=30)
                ext_fr = load_frames(ext_selected, media.frames_dir, self.cfg.compress_kb)
            else:
                ext_fr = []
            data = self._extension_call(data, ext_fr, prim["segments"], ext["segments"])
            data["creative_id"] = creative_id

        # write output
        out_path = os.path.join(work_dir, "creative_tags.json")
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"[tagging] wrote {out_path}", flush=True)
        return data

    def _staged_primary(self, fr_all: list[dict], transcript_segs: list[dict],
                        evidence_path: str | None = None) -> dict:
        # Structured evidence extraction once in small reliable batches, then
        # ONE constrained adjudication over the normalized evidence inventory
        # + all-frame contact sheet; only the adjudication is retried on
        # schema errors (e.g. §6.4 cap overflow).
        observations = _collect_staged_evidence(self.api, fr_all, transcript_segs)
        contact_sheet = _build_contact_sheet(fr_all)
        if evidence_path:
            save_structured_evidence(evidence_path, observations, transcript_segs,
                                     contact_sheet)
            print(f"[tagging] structured evidence artifact: {evidence_path}", flush=True)
        return _adjudicate(self.api, self.system, self.tax, observations,
                           transcript_segs, contact_sheet, self.cfg.audio_enabled,
                           self.cfg.max_retries)

    # ------------------------------------------------------------------ #
    def replay(self, evidence: dict, creative_id: str) -> dict:
        """Adjudication-only replay: consume a structured-evidence artifact
        (observations + timestamped transcript + contact sheet) and run the
        SAME constrained final adjudication — no video extraction, no
        multimodal evidence extraction. Output schema unchanged."""
        observations = evidence["observations"]
        transcript_segs = evidence.get("transcript") or []
        contact_sheet = evidence.get("contact_sheet")
        data = _adjudicate(self.api, self.system, self.tax, observations,
                           transcript_segs, contact_sheet, self.cfg.audio_enabled,
                           self.cfg.max_retries)
        data["creative_id"] = creative_id
        return data

    def _extension_call(self, stage1_draft: dict, ext_fr: list[dict],
                        prim_segs: list[dict], ext_segs: list[dict]) -> dict:
        all_segs = (prim_segs or []) + (ext_segs or [])
        user: list[dict] = []
        for fr in ext_fr:
            user.append({"type": "image_url",
                         "image_url": {"url": f"data:image/jpeg;base64,{fr['b64']}"}})
        caps = "、".join(f"frame_{fr['sec']:02d}（第 {fr['sec']} 秒）" for fr in ext_fr)
        user.append({"type": "text",
                     "text": f"以上 {len(ext_fr)} 张为扩窗 30-60s 帧：{caps}。" if ext_fr else
                             "扩窗 30-60s 无可用帧（视频可能短于 60s）。"})
        user.append({"type": "text",
                     "text": "以下是 0-30s 第一阶段草稿 JSON：\n" +
                             json.dumps(stage1_draft, ensure_ascii=False)})
        if all_segs:
            lines = [f"[{s['start']:.1f}-{s['end']:.1f}s] {s['text']}" for s in all_segs]
            user.append({"type": "text", "text": "带时间戳转写（0-60s）：\n" + "\n".join(lines)})
        data = _call_with_validation(self.api, self.ext_system, user, self.tax,
                                      self.cfg.audio_enabled, self.cfg.max_retries)
        # enforce extension consistency
        dw = data.setdefault("decision_window", {})
        dw["primary_seconds"] = 30
        dw["used_seconds"] = 60
        dw["extended"] = True
        if not dw.get("extended_reason"):
            dw["extended_reason"] = "0-30s multimodal semantics insufficient; extended to 0-60s"
        if dw.get("semantic_sufficiency") not in ("insufficient",):
            # 60s call produced a judgment; keep extended=true but reflect that it resolved
            dw["semantic_sufficiency"] = "insufficient"  # extended implies insufficient per schema
        # re-validate
        errs = schema.validate(data, self.tax, audio_enabled=self.cfg.audio_enabled)
        if errs:
            raise RuntimeError(f"extension output invalid: {errs}")
        return data
