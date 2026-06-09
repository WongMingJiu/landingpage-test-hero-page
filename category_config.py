"""
多品类配置模块
提供品类感知的路径解析和配置加载功能。
加载优先级：品类目录 → 默认路径
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


def get_prompt_path(stage: str, category_name: str = None) -> str:
    """
    获取 Prompt 文件路径。
    优先级：prompts/categories/{category}/{stage}_prompt.md → prompts/{stage}_prompt.md

    Args:
        stage: "analyze" 或 "generate"
        category_name: 品类名，None 时从环境变量读取
    """
    if category_name is None:
        category_name = get_category_name()

    # 优先品类特定
    category_specific = os.path.join(SCRIPT_DIR, "prompts", "categories", category_name, f"{stage}_prompt.md")
    if os.path.isfile(category_specific):
        print(f"[{stage}] 使用品类特定 Prompt: {category_specific}", file=sys.stderr)
        return category_specific

    # 回退默认
    default = os.path.join(SCRIPT_DIR, "prompts", f"{stage}_prompt.md")
    if os.path.isfile(default):
        print(f"[{stage}] 使用默认 Prompt: {default}", file=sys.stderr)
        return default

    raise FileNotFoundError(
        f"Prompt 文件不存在\n"
        f"  尝试1: {category_specific}\n"
        f"  尝试2: {default}"
    )


def load_category_config(category_name: str = None) -> Dict:
    """
    加载品类配置。
    优先级：assets/categories/{category}/config.json → 内置默认
    """
    if category_name is None:
        category_name = get_category_name()

    config_path = os.path.join(SCRIPT_DIR, "assets", "categories", category_name, "config.json")

    if os.path.isfile(config_path):
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                config = json.load(f)
                print(f"[config] 已加载品类配置: {config_path}", file=sys.stderr)
                return config
        except Exception as e:
            print(f"[config] 警告：加载 {config_path} 失败: {e}，使用内置默认", file=sys.stderr)

    # 内置默认配置
    defaults = {
        "singing": {
            "display_name": "唱歌",
            "description": "中老年唱歌教学课程，强调音乐表达、歌曲演唱、呼吸技巧等。",
            "applicable_inspirations": "A, B, C, D, E, F, G, H, I, J, K",
            "title_pool": ["兴趣岛唱歌训练营首席讲师", "身体唱歌法创始人"],
            "content_list_name": "课程曲目",
            "content_list_description": "具体歌曲名称（如《送别》《鸿雁》等）",
            "decoration_elements": "音符♪、麦克风图标、舞台光效、金色光晕",
        },
        "nutrition": {
            "display_name": "健康营养",
            "description": "中老年健康营养教学课程，强调营养知识、食疗方案、健康管理等。",
            "applicable_inspirations": "A, C, D, E, F, G, I, J",
            "title_pool": ["注册营养师", "健康管理师", "食疗养生专家"],
            "content_list_name": "课程内容",
            "content_list_description": "具体食物/营养知识点等",
            "decoration_elements": "蔬果图标🥦🍎、健康心形❤️、绿叶元素、阳光光晕",
        },
    }

    print(f"[config] 使用内置默认配置: {category_name}", file=sys.stderr)
    return defaults.get(category_name, defaults["singing"])


def get_teacher_ref_paths(category_name: str = None) -> List[str]:
    """
    获取老师面部参考图路径列表。
    优先级：assets/categories/{category}/teacher_face_ref_*.jpg → assets/teacher_face_ref_*.jpg
    """
    if category_name is None:
        category_name = get_category_name()

    # 优先品类目录
    category_pattern = os.path.join(SCRIPT_DIR, "assets", "categories", category_name, "teacher_face_ref_*.jpg")
    category_refs = sorted(glob.glob(category_pattern))
    # 只取不含 _full 的（_full 是全身照）
    category_refs = [p for p in category_refs if "_full" not in os.path.basename(p)]

    if category_refs:
        print(f"[config] 使用品类老师参考图: {len(category_refs)} 张", file=sys.stderr)
        return category_refs

    # 回退默认
    default_pattern = os.path.join(SCRIPT_DIR, "assets", "teacher_face_ref_*.jpg")
    default_refs = sorted(glob.glob(default_pattern))
    default_refs = [p for p in default_refs if "_full" not in os.path.basename(p)]

    if default_refs:
        print(f"[config] 使用默认老师参考图: {len(default_refs)} 张", file=sys.stderr)
        return default_refs

    print("[config] 警告：未找到任何老师面部参考图", file=sys.stderr)
    return []


def get_brand_logo_path(category_name: str = None) -> str:
    """获取品牌 logo 路径。优先品类目录 → 回退全局"""
    if category_name is None:
        category_name = get_category_name()

    category_logo = os.path.join(SCRIPT_DIR, "assets", "categories", category_name, "brand_logo.png")
    if os.path.isfile(category_logo):
        print(f"[config] 使用品类品牌 logo: {category_logo}", file=sys.stderr)
        return category_logo

    default_logo = os.path.join(SCRIPT_DIR, "assets", "brand_logo.png")
    if os.path.isfile(default_logo):
        print(f"[config] 使用默认品牌 logo: {default_logo}", file=sys.stderr)
        return default_logo

    print("[config] 警告：未找到品牌 logo", file=sys.stderr)
    return ""


def get_brand_reference_path(category_name: str = None) -> str:
    """获取品牌参考图路径。优先品类目录 → 回退全局"""
    if category_name is None:
        category_name = get_category_name()

    category_ref = os.path.join(SCRIPT_DIR, "assets", "categories", category_name, "brand_reference.png")
    if os.path.isfile(category_ref):
        print(f"[config] 使用品类品牌参考图: {category_ref}", file=sys.stderr)
        return category_ref

    default_ref = os.path.join(SCRIPT_DIR, "assets", "brand_reference.png")
    if os.path.isfile(default_ref):
        print(f"[config] 使用默认品牌参考图: {default_ref}", file=sys.stderr)
        return default_ref

    print("[config] 警告：未找到品牌参考图", file=sys.stderr)
    return ""
