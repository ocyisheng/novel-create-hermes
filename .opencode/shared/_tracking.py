"""追踪数据维护

负责章节写后更新伏笔、时间线、角色统计和 config 进度。
所有函数独立可测，被 auto_update.py 的 CLI 编排层调用。
"""

import re
import sys
from datetime import datetime
from pathlib import Path

from _utils import find_project_root, load_yaml, save_yaml, extract_chapter_number


def update_foreshadowing(
    chapter_path: Path,
    foreshadowing_data: dict | None = None,
    resolve_items: list[str] | None = None,
) -> dict:
    """更新伏笔.yaml"""
    project_root = find_project_root(chapter_path)
    foreshadowing_file = project_root / "outline" / "追踪" / "伏笔.yaml"
    data = load_yaml(foreshadowing_file)

    chapter_num = extract_chapter_number(chapter_path)

    if not data:
        data = {"伏笔": [], "版本": "1.0"}

    for item in data.get("伏笔", []):
        if "状态" not in item:
            item["状态"] = "待回收"

    if foreshadowing_data:
        existing_descriptions = {
            item.get("描述", "") for item in data.get("伏笔", [])
        }
        for f in foreshadowing_data:
            desc = f.get("描述", "")
            if desc in existing_descriptions:
                print(f"  跳过重复伏笔: '{desc}'")
                continue
            f["出现章节"] = chapter_num
            data["伏笔"].append(f)
            existing_descriptions.add(desc)

    if resolve_items:
        for item in data.get("伏笔", []):
            for pattern in resolve_items:
                if pattern in item.get("描述", ""):
                    item["状态"] = "已回收"
                    item["回收章节"] = chapter_num
                    break

    save_yaml(foreshadowing_file, data)
    return data


def update_timeline(
    chapter_path: Path,
    events: list[dict] | None = None,
) -> dict:
    """更新时间线.yaml"""
    project_root = find_project_root(chapter_path)
    timeline_file = project_root / "outline" / "追踪" / "时间线.yaml"
    data = load_yaml(timeline_file)

    chapter_num = extract_chapter_number(chapter_path)

    if not data:
        data = {"事件": [], "版本": "1.0"}

    if events:
        for event in events:
            event["章节"] = chapter_num
            data["事件"].append(event)

    save_yaml(timeline_file, data)
    return data


def update_character_stats(chapter_path: Path, characters: list[str] | None = None) -> dict:
    """更新角色出场统计"""
    project_root = find_project_root(chapter_path)
    stats_file = project_root / "characters" / "角色统计.yaml"
    data = load_yaml(stats_file)

    chapter_num = extract_chapter_number(chapter_path)

    if not data:
        data = {"角色": {}, "版本": "1.0"}

    if characters:
        for char_name in characters:
            if char_name not in data["角色"]:
                data["角色"][char_name] = {
                    "总出场章节": 0,
                    "出场章节列表": [],
                    "首次出场": chapter_num,
                    "最近出场": chapter_num,
                }
            stats = data["角色"][char_name]
            stats["总出场章节"] += 1
            if chapter_num not in stats["出场章节列表"]:
                stats["出场章节列表"].append(chapter_num)
            stats["最近出场"] = chapter_num

    save_yaml(stats_file, data)
    return data


def update_config_progress(chapter_path: Path) -> dict:
    """更新 config.yaml 的创作进度字段。

    自动维护：
      - 创作进度.当前章节 → max(当前, 本次章节号)（不倒退）
      - 创作进度.已完成章节数 → chapters/ 下 .txt 文件数
      - 创作进度.已完成字数 → 累计字数（统计 chapters/ 下所有 .txt）
      - 最后编辑 → 当前时间戳
    """
    project_root = find_project_root(chapter_path)
    config_path = project_root / "config.yaml"
    config = load_yaml(config_path)

    if not config:
        return {}

    chapter_num = extract_chapter_number(chapter_path)

    chapters_dir = project_root / "chapters"
    total_words = 0
    chapter_count = 0
    if chapters_dir.is_dir():
        for f in sorted(chapters_dir.iterdir()):
            if f.suffix.lower() == ".txt":
                chapter_count += 1
                try:
                    text = f.read_text(encoding="utf-8")
                    total_words += len(text.replace("\n", "").replace(" ", ""))
                except Exception:
                    pass

    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    progress = config.setdefault("创作进度", {})
    old_chapter = progress.get("当前章节", 0)
    progress["当前章节"] = max(old_chapter, chapter_num)
    progress["已完成章节数"] = chapter_count
    progress["已完成字数"] = total_words

    config["最后编辑"] = now

    save_yaml(config_path, config)
    return config
