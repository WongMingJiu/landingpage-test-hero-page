#!/bin/bash
# =============================================================================
# 视频分析 → 落地页 Hero 设计方案 生成脚本
#
# 用法:
#   ./run.sh <视频文件路径>
#
# 示例:
#   ./run.sh ./sample.mp4
#
# 依赖:
#   - ffmpeg (需在 PATH 中)
#   - python3 + requirements.txt 中的依赖
#   - 同级目录的 config.env (API 配置)
#
# 输出 (output/{视频名称}/ 目录):
#   - video_clip_result/   关键帧 / 音频 / 视频片段 / 转写文本
#   - analyse_result/      analysis.json + 设计方案 MD/HTML
#   - design_refer/pageN/  每个变体的 prompt.txt + 参考图
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# ---------- 参数检查 ----------
if [ $# -lt 1 ]; then
  echo "[run] 用法: $0 <视频文件路径>" >&2
  exit 1
fi

VIDEO="$1"
if [ ! -f "$VIDEO" ]; then
  echo "[run] 错误：视频文件不存在: $VIDEO" >&2
  exit 1
fi

# 将视频路径导出为环境变量，供 Python 脚本使用
export SOURCE_VIDEO="$VIDEO"

# 提取视频文件名（不含路径与扩展名），作为本次输出根目录名
VIDEO_BASENAME="$(basename "$VIDEO")"
VIDEO_NAME="${VIDEO_BASENAME%.*}"
if [ -z "$VIDEO_NAME" ]; then
  echo "[run] 错误：无法从视频路径推断文件名: $VIDEO" >&2
  exit 1
fi

# ---------- 加载配置 ----------
CONFIG_FILE="$SCRIPT_DIR/config.env"
if [ -f "$CONFIG_FILE" ]; then
  echo "[run] 加载配置: $CONFIG_FILE"
  set -a
  # shellcheck disable=SC1090
  . "$CONFIG_FILE"
  set +a
else
  echo "[run] 错误：未找到 $CONFIG_FILE" >&2
  echo "[run] 请确保 config.env 存在并填入正确的 API 配置" >&2
  exit 1
fi

# ---------- 依赖检查 ----------
command -v ffmpeg >/dev/null 2>&1 || {
  echo "[run] 错误：未找到 ffmpeg，请先安装（macOS: brew install ffmpeg）" >&2
  exit 1
}
command -v python3 >/dev/null 2>&1 || {
  echo "[run] 错误：未找到 python3" >&2
  exit 1
}

# ---------- 准备输出目录 ----------
OUTPUT_DIR="$SCRIPT_DIR/output/$VIDEO_NAME"
VIDEO_CLIP_DIR="$OUTPUT_DIR/video_clip_result"
ANALYSE_DIR="$OUTPUT_DIR/analyse_result"
DESIGN_REFER_DIR="$OUTPUT_DIR/design_refer"

mkdir -p "$VIDEO_CLIP_DIR" "$ANALYSE_DIR" "$DESIGN_REFER_DIR"
echo "[run] 输出目录: $OUTPUT_DIR"

# 导出供 Python 脚本使用
export OUTPUT_DIR
export VIDEO_CLIP_DIR
export ANALYSE_DIR
export DESIGN_REFER_DIR
export VIDEO_NAME

AUDIO_PATH="$VIDEO_CLIP_DIR/audio.wav"
VIDEO_CLIP="$VIDEO_CLIP_DIR/video_clip.mp4"

# ---------- 视频时长检查 ----------
DURATION=$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$VIDEO" 2>/dev/null | cut -d'.' -f1)
if [ -n "$DURATION" ] && [ "$DURATION" -lt 30 ]; then
  echo "[run] 警告：视频时长仅 ${DURATION}s（少于30s），将截取可用帧" >&2
fi

# ---------- 截帧重试函数 ----------
extract_frame() {
  local T=$1 OUT=$2
  ffmpeg -hide_banner -loglevel error -y -ss "$T" -i "$VIDEO" -frames:v 1 -q:v 2 "$OUT" 2>/dev/null && return 0
  sleep 1
  ffmpeg -hide_banner -loglevel error -y -ss "$T" -i "$VIDEO" -frames:v 1 -q:v 2 "$OUT" 2>/dev/null && return 0
  return 1
}

# ---------- 1) 截取 30 张关键帧（每1秒一帧：0~29 秒）----------
echo "[run] [1/5] 截取关键帧..."
TIMES=(0 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 19 20 21 22 23 24 25 26 27 28 29)
FRAME_COUNT=0
for i in "${!TIMES[@]}"; do
  IDX=$(printf "%02d" "$i")
  T="${TIMES[$i]}"
  OUT_FRAME="$VIDEO_CLIP_DIR/frame_${IDX}.jpg"
  echo "[run]   - frame_${IDX}.jpg (t=${T}s)"
  if extract_frame "$T" "$OUT_FRAME" && [ -s "$OUT_FRAME" ]; then
    FRAME_COUNT=$((FRAME_COUNT + 1))
  else
    echo "[run] 警告：截帧失败: frame_${IDX}.jpg (t=${T}s)，跳过" >&2
    rm -f "$OUT_FRAME"
  fi
done
if [ "$FRAME_COUNT" -eq 0 ]; then
  echo "[run] 错误：未能截取任何关键帧" >&2
  exit 2
fi
echo "[run] 成功截取 ${FRAME_COUNT} 张关键帧"

# ---------- 2) 提取前 30 秒音频与视频片段 ----------
echo "[run] [2/5] 提取前 30 秒音频..."
ffmpeg -hide_banner -loglevel error -y \
  -i "$VIDEO" -t 30 \
  -vn -ac 1 -ar 16000 -acodec pcm_s16le \
  "$AUDIO_PATH"
if [ ! -s "$AUDIO_PATH" ]; then
  echo "[run] 错误：音频提取失败" >&2
  exit 3
fi

echo "[run]      截取前 30 秒视频片段..."
ffmpeg -hide_banner -loglevel error -y -i "$VIDEO" -t 30 -c:v libx264 -c:a aac -movflags +faststart "$VIDEO_CLIP"
if [ ! -s "$VIDEO_CLIP" ]; then
  echo "[run] 警告：视频片段截取失败（不影响后续流程）" >&2
fi

# ---------- 3) Whisper 本地转写 ----------
echo "[run] [3/5] Whisper 转写..."
python3 transcribe.py
[ -s "$VIDEO_CLIP_DIR/transcript.txt" ] || {
  echo "[run] 错误：转写文件为空或不存在" >&2
  exit 4
}

# ---------- 4) 多模态分析 ----------
echo "[run] [4/5] 多模态分析..."
python3 analyze.py
[ -s "$ANALYSE_DIR/analysis.json" ] || {
  echo "[run] 错误：分析结果文件为空或不存在" >&2
  exit 5
}

# ---------- 5) 生成落地页设计 ----------
echo "[run] [5/5] 生成落地页设计方案..."
python3 generate.py
[ -s "$ANALYSE_DIR/landing_page_design.md" ] || {
  echo "[run] 错误：设计方案 Markdown 未生成" >&2
  exit 6
}
[ -s "$ANALYSE_DIR/landing_page_design.html" ] || {
  echo "[run] 错误：设计方案 HTML 未生成" >&2
  exit 7
}

# ---------- 6) 同步 design_refer 到落地页管理仓库 ----------
SYNC_TARGET_BASE="$HOME/workspace/landing-page-manage/${CATEGORY_FOLDER_NAME:-唱歌}"
SYNC_TARGET="$SYNC_TARGET_BASE/$VIDEO_NAME"
echo ""
echo "[run] [6/6] 同步 design_refer 到: $SYNC_TARGET"
mkdir -p "$SYNC_TARGET_BASE"
if [ -d "$DESIGN_REFER_DIR" ] && [ -n "$(ls -A "$DESIGN_REFER_DIR" 2>/dev/null || true)" ]; then
  # 使用 cp -f 逐文件覆盖，避免 macOS 扩展属性导致 rm/cp -R 失败
  for page_dir in "$DESIGN_REFER_DIR"/page*/; do
    [ -d "$page_dir" ] || continue
    page_name="$(basename "$page_dir")"
    mkdir -p "$SYNC_TARGET/$page_name"
    for src_file in "$page_dir"*; do
      [ -f "$src_file" ] || continue
      file_name="$(basename "$src_file")"
      cp -f "$src_file" "$SYNC_TARGET/$page_name/$file_name" 2>/dev/null || true
    done
  done
  echo "[run] 同步完成"
else
  echo "[run] 警告：design_refer 为空，跳过同步" >&2
fi

echo ""
echo "[run] ========== 全部完成 =========="
echo "[run] 视频名称:   $VIDEO_NAME"
echo "[run] 视频/帧/音频/转写:  $VIDEO_CLIP_DIR"
echo "[run] 分析与设计方案:     $ANALYSE_DIR"
echo "[run] 生图变体素材:       $DESIGN_REFER_DIR"
echo "[run] 同步目标:           $SYNC_TARGET"
