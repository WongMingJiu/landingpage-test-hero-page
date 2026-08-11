#!/bin/bash
# =============================================================================
# 批量生图：遍历 ${VALIDATION_BASE:-~/Desktop/测试结果}/*/design_refer/page*
# 调用 generate_image.py，输出到 {video_dir}/design_refer/pageN.jpg
# 已存在的图自动跳过（断点续跑）
# =============================================================================

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

CONFIG_FILE="$SCRIPT_DIR/config.env"
[ -f "$CONFIG_FILE" ] || { echo "[batch-img] 错误：未找到 $CONFIG_FILE" >&2; exit 1; }
set -a
# shellcheck disable=SC1090
. "$CONFIG_FILE"
set +a

PYTHON_BIN="${PYTHON_BIN:-python3}"
command -v "$PYTHON_BIN" >/dev/null 2>&1 || { echo "[batch-img] 错误：未找到 Python: $PYTHON_BIN" >&2; exit 1; }

VALIDATION_BASE="${VALIDATION_BASE:-$HOME/Desktop/测试结果}"
[ -d "$VALIDATION_BASE" ] || { echo "[batch-img] 错误：未找到 $VALIDATION_BASE" >&2; exit 1; }

TOTAL=0
SUCCESS=0
FAILED=0
SKIPPED=0
FAILED_LIST=()

process_video() {
  local video_dir="$1"
  local category_en="$2"
  local video_name
  video_name="$(basename "$video_dir")"

  local design_dir="$video_dir/design_refer"
  if [ ! -d "$design_dir" ]; then
    echo "  ! 未找到 design_refer，跳过：$video_dir"
    return 0
  fi

  # 找出所有 pageN 子目录
  local page_dirs=()
  while IFS= read -r d; do page_dirs+=("$d"); done < <(find "$design_dir" -maxdepth 1 -type d -name "page*" | sort -V)

  [ ${#page_dirs[@]} -gt 0 ] || { echo "  ! 无 pageN/，跳过"; return 0; }

  # 计算需要生图的 pages（已存在的图跳过）
  local pages_to_run=()
  local pd page_no out_img
  for pd in "${page_dirs[@]}"; do
    page_no="$(basename "$pd" | sed 's/^page//')"
    out_img="$design_dir/page${page_no}.jpg"
    if [ -s "$out_img" ]; then
      SKIPPED=$((SKIPPED+1))
      continue
    fi
    pages_to_run+=("$page_no")
    TOTAL=$((TOTAL+1))
  done

  if [ ${#pages_to_run[@]} -eq 0 ]; then
    echo "  ✓ 全部已生成，跳过"
    return 0
  fi

  echo "  → 待生成 pages: ${pages_to_run[*]}"

  # 设置 generate_image.py 需要的品类环境（影响 brand_logo/teacher_face_ref 路径）
  export CATEGORY_NAME="$category_en"

  # input_root = video_dir, video_name = "design_refer"
  # 这样 generate_image.py 内部 video_dir = video_dir/design_refer，
  # 输出 output_root/design_refer/pageN.jpg = video_dir/design_refer/pageN.jpg
  "$PYTHON_BIN" generate_image.py "design_refer" \
    --input-root "$video_dir" \
    --output-root "$video_dir" \
    --pages ${pages_to_run[@]} 2>&1 | sed 's/^/    /'
  local rc=${PIPESTATUS[0]}

  # 统计成功/失败：检查每张目标图是否存在
  for page_no in "${pages_to_run[@]}"; do
    out_img="$design_dir/page${page_no}.jpg"
    if [ -s "$out_img" ]; then
      SUCCESS=$((SUCCESS+1))
    else
      FAILED=$((FAILED+1))
      FAILED_LIST+=("$video_name/page${page_no}")
    fi
  done

  return 0
}

# 遍历测试结果目录下所有视频
echo ""
echo "================================================================"
echo "[batch-img] 开始批量生图"
echo "  输入目录: $VALIDATION_BASE"
echo "================================================================"

shopt -s nullglob
for video_dir in "$VALIDATION_BASE"/*/; do
  video_dir="${video_dir%/}"
  [ -d "$video_dir" ] || continue
  [ -d "$video_dir/design_refer" ] || continue
  vname="$(basename "$video_dir")"

  # 根据视频名判断品类
  category_en="singing"
  if echo "$vname" | grep -qi "营养\|nutrition\|健康"; then
    category_en="nutrition"
  fi

  echo ""
  echo "----------------------------------------------------------------"
  echo "[$vname] ($category_en)"
  echo "----------------------------------------------------------------"
  process_video "$video_dir" "$category_en"
done
shopt -u nullglob

echo ""
echo "================================================================"
echo "[batch-img] 全部完成"
echo "  待生成: $TOTAL  成功: $SUCCESS  失败: $FAILED  已跳过(已存在): $SKIPPED"
if [ ${#FAILED_LIST[@]} -gt 0 ]; then
  echo "  失败列表："
  for v in "${FAILED_LIST[@]}"; do
    echo "    - $v"
  done
fi
echo "================================================================"
