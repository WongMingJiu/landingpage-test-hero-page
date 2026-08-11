#!/bin/bash
# =============================================================================
# 批量验证：遍历 ${VALIDATION_BASE:-~/Desktop/验证视频}/{健康营养,唱歌}/*.mp4
# 默认输出到每个视频同级目录的同名文件夹；设置 OUTPUT_BASE 可集中输出。
# 不跑生图，不 sync。
#
# 输出结构：
#   ~/Desktop/验证视频/{品类}/{视频名}/
#     ├── video_clip_result/   关键帧 / 音频 / 视频片段 / 转写文本
#     ├── analyse_result/      analysis.json + 设计方案 MD/HTML
#     └── design_refer/pageN/  每个变体的 prompt.md + 参考图
# =============================================================================

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# ---------- 加载基础配置（API Key 等）----------
CONFIG_FILE="$SCRIPT_DIR/config.env"
if [ ! -f "$CONFIG_FILE" ]; then
  echo "[batch] 错误：未找到 $CONFIG_FILE" >&2
  exit 1
fi
set -a
# shellcheck disable=SC1090
. "$CONFIG_FILE"
set +a

# ---------- 依赖检查 ----------
command -v ffmpeg >/dev/null 2>&1 || { echo "[batch] 错误：未找到 ffmpeg" >&2; exit 1; }
PYTHON_BIN="${PYTHON_BIN:-python3}"
command -v "$PYTHON_BIN" >/dev/null 2>&1 || { echo "[batch] 错误：未找到 Python: $PYTHON_BIN" >&2; exit 1; }

VALIDATION_BASE="${VALIDATION_BASE:-$HOME/Desktop/验证视频}"
OUTPUT_BASE="${OUTPUT_BASE:-}"
[ -d "$VALIDATION_BASE" ] || { echo "[batch] 错误：未找到 $VALIDATION_BASE" >&2; exit 1; }

# ---------- 单视频处理函数 ----------
process_video() {
  local video="$1"
  local category_zh="$2"
  local category_en="$3"

  local video_basename video_name
  video_basename="$(basename "$video")"
  video_name="${video_basename%.*}"

  local cat_dir output_dir
  cat_dir="$(dirname "$video")"
  if [ -n "$OUTPUT_BASE" ]; then
    output_dir="$OUTPUT_BASE/$video_name"
  else
    output_dir="$cat_dir/$video_name"
  fi

  local video_clip_dir="$output_dir/video_clip_result"
  local analyse_dir="$output_dir/analyse_result"
  local design_refer_dir="$output_dir/design_refer"

  mkdir -p "$video_clip_dir" "$analyse_dir" "$design_refer_dir"

  # 关键环境变量
  export SOURCE_VIDEO="$video"
  export VIDEO_NAME="$video_name"
  export OUTPUT_DIR="$output_dir"
  export VIDEO_CLIP_DIR="$video_clip_dir"
  export ANALYSE_DIR="$analyse_dir"
  export DESIGN_REFER_DIR="$design_refer_dir"
  export CATEGORY_NAME="$category_en"
  export CATEGORY_FOLDER_NAME="$category_zh"

  local audio_path="$video_clip_dir/audio.wav"
  local video_clip="$video_clip_dir/video_clip.mp4"

  # ---- 1) 截帧（30 张，每秒一帧，已存在则跳过）----
  if [ ! -s "$video_clip_dir/frame_29.jpg" ]; then
    echo "  [1/5] 截取关键帧..."
    local i idx
    for i in $(seq 0 29); do
      idx=$(printf "%02d" "$i")
      local out="$video_clip_dir/frame_${idx}.jpg"
      [ -s "$out" ] && continue
      ffmpeg -hide_banner -loglevel error -y -ss "$i" -i "$video" \
        -frames:v 1 -q:v 2 "$out" 2>/dev/null || true
    done
  else
    echo "  [1/5] 关键帧已存在，跳过"
  fi
  # 至少要有 1 张
  if ! ls "$video_clip_dir"/frame_*.jpg >/dev/null 2>&1; then
    echo "  [ERROR] 截帧失败" >&2
    return 2
  fi

  # ---- 2) 音频 + 视频片段 ----
  if [ ! -s "$audio_path" ]; then
    echo "  [2/5] 提取前 30 秒音频..."
    ffmpeg -hide_banner -loglevel error -y -i "$video" -t 30 \
      -vn -ac 1 -ar 16000 -acodec pcm_s16le "$audio_path" || {
      echo "  [ERROR] 音频提取失败" >&2
      return 3
    }
  else
    echo "  [2/5] 音频已存在，跳过"
  fi
  if [ ! -s "$video_clip" ]; then
    ffmpeg -hide_banner -loglevel error -y -i "$video" -t 30 \
      -c:v libx264 -c:a aac -movflags +faststart "$video_clip" 2>/dev/null || true
  fi

  # ---- 3) Whisper 转写 ----
  if [ ! -s "$video_clip_dir/transcript.txt" ]; then
    echo "  [3/5] Whisper 转写..."
    "$PYTHON_BIN" transcribe.py || { echo "  [ERROR] 转写失败" >&2; return 4; }
  else
    echo "  [3/5] 转写已存在，跳过"
  fi

  # ---- 4) 多模态分析 ----
  if [ ! -s "$analyse_dir/analysis.json" ]; then
    echo "  [4/5] 多模态分析..."
    "$PYTHON_BIN" analyze.py || { echo "  [ERROR] 分析失败" >&2; return 5; }
  else
    echo "  [4/5] analysis.json 已存在，跳过"
  fi

  # ---- 5) 生成落地页设计方案（不跑生图）----
  if [ ! -s "$analyse_dir/landing_page_design.md" ]; then
    echo "  [5/5] 生成落地页设计..."
    "$PYTHON_BIN" generate.py || { echo "  [ERROR] 生成失败" >&2; return 6; }
  else
    echo "  [5/5] 设计方案已存在，跳过"
  fi

  return 0
}

# ---------- 主循环 ----------
TOTAL=0
SUCCESS=0
FAILED=0
FAILED_LIST=()

# 品类映射：中文目录名 -> 英文 CATEGORY_NAME
process_category() {
  local category_zh="$1"
  local category_en="$2"
  local cat_dir="$VALIDATION_BASE/$category_zh"

  if [ ! -d "$cat_dir" ]; then
    echo "[batch] 跳过：$cat_dir 不存在"
    return
  fi

  echo ""
  echo "================================================================"
  echo "[batch] 开始处理品类：$category_zh ($category_en)"
  echo "================================================================"

  local video
  shopt -s nullglob
  for video in "$cat_dir"/*.mp4 "$cat_dir"/*.MP4 "$cat_dir"/*.mov "$cat_dir"/*.MOV; do
    [ -f "$video" ] || continue
    TOTAL=$((TOTAL+1))
    local vname
    vname="$(basename "$video")"
    echo ""
    echo "----------------------------------------------------------------"
    echo "[$TOTAL] $vname"
    echo "----------------------------------------------------------------"
    if process_video "$video" "$category_zh" "$category_en"; then
      SUCCESS=$((SUCCESS+1))
      echo "[OK] $vname"
    else
      FAILED=$((FAILED+1))
      FAILED_LIST+=("$category_zh/$vname")
      echo "[FAIL] $vname" >&2
    fi
  done
  shopt -u nullglob
}

process_category "健康营养" "nutrition"
process_category "唱歌" "singing"

# ---------- 汇总 ----------
echo ""
echo "================================================================"
echo "[batch] 全部完成"
echo "  总计: $TOTAL"
echo "  成功: $SUCCESS"
echo "  失败: $FAILED"
if [ ${#FAILED_LIST[@]} -gt 0 ]; then
  echo "  失败列表："
  for v in "${FAILED_LIST[@]}"; do
    echo "    - $v"
  done
fi
echo "================================================================"
