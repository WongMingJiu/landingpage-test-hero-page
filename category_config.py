"""
多品类配置模块
品类自包含架构：所有品类资源均位于 assets/categories/{category}/ 下，包括：
  - config.json
  - analyze_prompt.md / generate_prompt.md
  - teacher_face_ref_*.jpg（含 _full 源图，代码仅读取无 _full 的版本）
  - brand_logo.png / brand_reference.png
  - examples/（可选，由 generate_prompt.md 通过 {EXAMPLES_DIR} 占位符引用）
新增品类只需创建上述目录与文件，无需改动 Python 代码。
"""

import os
import sys
import json
import glob
from typing import List, Dict

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))


def get_category_name() -> str:
    """从环境变量获取品类标识，默认 singing"""
    return os.environ.get("CATEGORY_NAME", "singing").strip()


def get_category_folder() -> str:
    """从环境变量获取品类文件夹名（中文），默认 唱歌"""
    return os.environ.get("CATEGORY_FOLDER_NAME", "唱歌").strip()


def get_category_dir(category_name: str = None) -> str:
    """获取品类资源目录的绝对路径"""
    if category_name is None:
        category_name = get_category_name()
    return os.path.join(SCRIPT_DIR, "assets", "categories", category_name)


def get_examples_dir(category_name: str = None) -> str:
    """获取品类 examples 目录的相对路径（用于 prompt 中的占位符替换）"""
    if category_name is None:
        category_name = get_category_name()
    return f"assets/categories/{category_name}/examples/"


def get_prompt_path(stage: str, category_name: str = None) -> str:
    """
    获取 Prompt 文件路径。仅从品类目录下读取，不再回退到 prompts/。

    Args:
        stage: "analyze" 或 "generate"
        category_name: 品类名，None 时从环境变量读取
    """
    if category_name is None:
        category_name = get_category_name()

    category_path = os.path.join(SCRIPT_DIR, "assets", "categories", category_name, f"{stage}_prompt.md")
    if os.path.isfile(category_path):
        print(f"[{stage}] 使用品类 Prompt: {category_path}", file=sys.stderr)
        return category_path

    raise FileNotFoundError(
        f"品类 Prompt 不存在: {category_path}\n"
        f"请在该品类目录下创建 {stage}_prompt.md"
    )


def load_category_config(category_name: str = None) -> Dict:
    """
    加载品类配置。仅从 assets/categories/{category}/config.json 读取，不再有内置默认值。
    若文件不存在，直接抛出错误，强制要求新品类显式声明配置。
    """
    if category_name is None:
        category_name = get_category_name()

    config_path = os.path.join(SCRIPT_DIR, "assets", "categories", category_name, "config.json")

    if not os.path.isfile(config_path):
        raise FileNotFoundError(
            f"品类配置不存在: {config_path}\n"
            f"请为该品类创建 config.json（参考其他品类的字段结构）"
        )

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)
            print(f"[config] 已加载品类配置: {config_path}", file=sys.stderr)
            return config
    except Exception as e:
        raise RuntimeError(f"加载品类配置失败 {config_path}: {e}")


def get_teacher_ref_paths(category_name: str = None) -> List[str]:
    """
    获取老师面部参考图路径列表（仅取无 _full 后缀的文件，_full 是人工裁剪源）。
    仅从品类目录下读取。
    """
    if category_name is None:
        category_name = get_category_name()

    category_pattern = os.path.join(SCRIPT_DIR, "assets", "categories", category_name, "teacher_face_ref_*.jpg")
    refs = sorted(glob.glob(category_pattern))
    refs = [p for p in refs if "_full" not in os.path.basename(p)]

    if refs:
        print(f"[config] 使用品类老师参考图: {len(refs)} 张", file=sys.stderr)
        return refs

    print(f"[config] 警告：品类 {category_name} 下未找到老师面部参考图", file=sys.stderr)
    return []


def get_brand_logo_path(category_name: str = None) -> str:
    """获取品牌 logo 路径。仅从品类目录读取。"""
    if category_name is None:
        category_name = get_category_name()

    logo = os.path.join(SCRIPT_DIR, "assets", "categories", category_name, "brand_logo.png")
    if os.path.isfile(logo):
        print(f"[config] 使用品类品牌 logo: {logo}", file=sys.stderr)
        return logo

    print(f"[config] 警告：品类 {category_name} 下未找到 brand_logo.png", file=sys.stderr)
    return ""


def get_brand_reference_path(category_name: str = None) -> str:
    """获取品牌参考图路径（可选）。仅从品类目录读取。"""
    if category_name is None:
        category_name = get_category_name()

    ref = os.path.join(SCRIPT_DIR, "assets", "categories", category_name, "brand_reference.png")
    if os.path.isfile(ref):
        print(f"[config] 使用品类品牌参考图: {ref}", file=sys.stderr)
        return ref

    print(f"[config] 提示：品类 {category_name} 下无 brand_reference.png（可选）", file=sys.stderr)
    return ""
