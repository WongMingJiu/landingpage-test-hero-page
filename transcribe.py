#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
本地 Whisper ASR 转写脚本
读取 output/audio.wav，使用 openai-whisper 进行语音识别，
将结果保存至 output/transcript.txt。

环境变量：
  WHISPER_MODEL  - whisper 模型大小，默认为 small
"""

import os
import sys
import time


_VIDEO_CLIP_DIR = os.environ.get("VIDEO_CLIP_DIR", "").strip() or os.path.join("output")
AUDIO_PATH = os.path.join(_VIDEO_CLIP_DIR, "audio.wav")
TRANSCRIPT_PATH = os.path.join(_VIDEO_CLIP_DIR, "transcript.txt")


def main() -> int:
    if not os.path.isfile(AUDIO_PATH):
        print(f"[transcribe] 错误：音频文件不存在: {AUDIO_PATH}", file=sys.stderr)
        return 1

    model_name = os.environ.get("WHISPER_MODEL", "small").strip() or "small"
    print(f"[transcribe] 正在加载 Whisper 模型: {model_name}...")
    print(f"[transcribe] 提示：首次运行将自动下载模型权重（small≈460MB），请耐心等待...")
    t0 = time.time()
    try:
        import whisper  # type: ignore
    except ImportError as e:
        print(f"[transcribe] 错误：未安装 openai-whisper：{e}", file=sys.stderr)
        print("[transcribe] 请执行: pip install -r requirements.txt", file=sys.stderr)
        return 2

    try:
        model = whisper.load_model(model_name)
    except Exception as e:
        print(f"[transcribe] 加载模型失败：{e}", file=sys.stderr)
        return 3
    print(f"[transcribe] 模型加载完成，耗时 {time.time() - t0:.1f}s")

    print(f"[transcribe] 开始转写音频: {AUDIO_PATH}")
    t1 = time.time()
    try:
        result = model.transcribe(AUDIO_PATH, verbose=False)
    except Exception as e:
        print(f"[transcribe] 转写失败：{e}", file=sys.stderr)
        return 4
    print(f"[transcribe] 转写完成，耗时 {time.time() - t1:.1f}s")

    text = (result.get("text") or "").strip()
    if not text:
        print("[transcribe] 错误：转写结果为空，视频可能无音频或口播内容", file=sys.stderr)
        print("[transcribe] 提示：请确认视频包含人声口播", file=sys.stderr)
        sys.exit(5)

    os.makedirs(os.path.dirname(TRANSCRIPT_PATH), exist_ok=True)
    with open(TRANSCRIPT_PATH, "w", encoding="utf-8") as f:
        f.write(text + "\n")

    print(f"[transcribe] 转写文本已保存: {TRANSCRIPT_PATH}")
    print(f"[transcribe] 文本长度: {len(text)} 字符")
    return 0


if __name__ == "__main__":
    sys.exit(main())
