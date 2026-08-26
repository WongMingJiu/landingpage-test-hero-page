#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Media extraction for V2.1a (Phase A §4 + §5).

- Frames: ffmpeg @ 1 fps, written as ``frame_{second:02d}.jpg`` where *second*
  is the absolute second in the decision window (0..29 for primary, 30..59 for
  the extension). This matches V1's second-aligned naming so the frame
  selector's second-indices map directly to files.
- Audio: 16 kHz mono wav for a window.
- Transcript: Whisper with **segments preserved** (V1 discards timestamps; V2.1a
  needs them). Sparse-tolerant: an empty/sparse result is legal and MUST NOT
  abort (spec §5.2 ``transcript_sparse != semantic_sparse``). This is the key
  behavioral difference from V1 ``transcribe.py`` which ``exit 5``s on empty.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import time
from typing import Any


def _run(cmd: list[str]) -> None:
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"command failed: {' '.join(cmd)}\nstderr: {proc.stderr.strip()}")


def video_duration_seconds(video: str) -> float:
    """Return duration in seconds via ffprobe, or 0.0 on failure."""
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", video],
            capture_output=True, text=True,
        )
        return float(out.stdout.strip()) if out.stdout.strip() else 0.0
    except Exception:
        return 0.0


def extract_frames(video: str, out_dir: str, start: int, end: int) -> list[int]:
    """Extract 1 fps frames for seconds [start, end) into ``out_dir``.

    Returns the list of absolute seconds actually produced (may be fewer than
    ``end - start`` for short videos).
    """
    os.makedirs(out_dir, exist_ok=True)
    duration = max(0, end - start)
    if duration <= 0:
        return []
    tmp_pattern = os.path.join(out_dir, "_tmp_frame_%04d.jpg")
    # fast-seek to `start`, then sample at 1 fps for `duration` seconds
    _run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-ss", str(start), "-i", video, "-t", str(duration),
        "-vf", "fps=1", "-q:v", "2", tmp_pattern,
    ])
    # rename _tmp_frame_0001.jpg -> frame_{start:02d}.jpg, etc.
    produced: list[int] = []
    for name in sorted(os.listdir(out_dir)):
        m = re.match(r"_tmp_frame_(\d+)\.jpg$", name)
        if not m:
            continue
        idx = int(m.group(1))  # 1-based
        sec = start + (idx - 1)
        os.replace(os.path.join(out_dir, name),
                   os.path.join(out_dir, f"frame_{sec:02d}.jpg"))
        produced.append(sec)
    produced.sort()
    return produced


def extract_audio(video: str, out_path: str, start: int, end: int) -> str:
    """Extract mono 16 kHz wav for [start, end)."""
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    duration = max(0, end - start)
    if duration <= 0:
        return out_path
    _run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-ss", str(start), "-i", video, "-t", str(duration),
        "-vn", "-ac", "1", "-ar", "16000", "-acodec", "pcm_s16le", out_path,
    ])
    return out_path


def transcribe_timestamped(audio_path: str, model_name: str = "small",
                           language: str | None = None) -> list[dict]:
    """Whisper transcription preserving segment timestamps.

    Sparse-tolerant: returns ``[]`` (or a sparse list) when there is little
    speech / mostly singing. Never raises on empty — that is a legal V2.1a
    input (spec §5.2). Raises only on missing library / failed load / failed
    transcribe (real errors, not sparse content).
    """
    if not os.path.isfile(audio_path):
        raise FileNotFoundError(f"audio not found: {audio_path}")
    try:
        import whisper  # type: ignore
    except ImportError as e:
        raise RuntimeError(f"openai-whisper not installed: {e}") from e

    t0 = time.time()
    model = whisper.load_model(model_name)
    kwargs: dict[str, Any] = {"verbose": False}
    if language:
        kwargs["language"] = language
    result = model.transcribe(audio_path, **kwargs)

    segments: list[dict] = []
    for seg in result.get("segments", []) or []:
        text = (seg.get("text") or "").strip()
        if not text:
            continue
        segments.append({
            "start": float(seg.get("start", 0.0)),
            "end": float(seg.get("end", 0.0)),
            "text": text,
        })
    print(f"[extract] whisper {model_name}: {len(segments)} segments in {time.time()-t0:.1f}s", flush=True)
    return segments


def save_transcript_json(segments: list[dict], out_path: str) -> None:
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({"segments": segments}, f, ensure_ascii=False, indent=2)


def load_transcript_json(path: str) -> list[dict]:
    if not os.path.isfile(path):
        return []
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data.get("segments", []) if isinstance(data, dict) else []


class MediaExtraction:
    """Coordinates primary (0–30s) and extension (30–60s) extraction."""

    def __init__(self, video: str, work_dir: str, whisper_model: str = "small"):
        self.video = video
        self.work_dir = work_dir
        self.whisper_model = whisper_model
        self.frames_dir = os.path.join(work_dir, "frames")
        self.duration = video_duration_seconds(video)

    def extract_primary(self) -> dict:
        end = min(30, int(self.duration) if self.duration > 0 else 30)
        if end < 1:
            raise RuntimeError(f"video too short (<1s): {self.video}")
        secs = extract_frames(self.video, self.frames_dir, 0, end)
        audio_path = os.path.join(self.work_dir, "audio_0_30.wav")
        extract_audio(self.video, audio_path, 0, end)
        segs = transcribe_timestamped(audio_path, self.whisper_model)
        save_transcript_json(segs, os.path.join(self.work_dir, "transcript_0_30.json"))
        return {"frame_seconds": secs, "audio": audio_path, "segments": segs}

    def extract_extension(self) -> dict:
        # only extract if the video actually has content past 30s
        start = 30
        end = min(60, int(self.duration) if self.duration > 0 else 60)
        if end <= start:
            return {"frame_seconds": [], "audio": None, "segments": []}
        secs = extract_frames(self.video, self.frames_dir, start, end)
        audio_path = os.path.join(self.work_dir, "audio_30_60.wav")
        extract_audio(self.video, audio_path, start, end)
        segs = transcribe_timestamped(audio_path, self.whisper_model)
        save_transcript_json(segs, os.path.join(self.work_dir, "transcript_30_60.json"))
        return {"frame_seconds": secs, "audio": audio_path, "segments": segs}
