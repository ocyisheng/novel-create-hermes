"""追踪数据维护

负责章节写后更新伏笔、时间线、角色统计、情节线进度和 config 进度。
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
    """更新伏笔.yaml。

    若 foreshadowing_data 中的项包含 关联实体ID 字段，自动回链到对应情节线文件。
    """
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
            f["章节"] = chapter_num
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
        # 尝试从分纲获取本章故事时间，作为无时间事件的回退
        chapter_time = _extract_chapter_time(project_root, chapter_num)
        for event in events:
            event["章节"] = chapter_num
            if "时间" not in event and chapter_time:
                event["时间"] = chapter_time
            data["事件"].append(event)

    save_yaml(timeline_file, data)
    return data


def update_character_stats(
    chapter_path: Path,
    characters: list[str] | None = None,
    char_states: dict[str, str] | None = None,
) -> dict:
    """更新角色出场统计（扁平列表格式，只追加）

    Args:
        chapter_path: 章节文件路径
        characters: 出场角色名列表
        char_states: 角色状态字典，如 {"张小凡": "重伤", "李四": "死亡"}
    """
    project_root = find_project_root(chapter_path)
    stats_file = project_root / "outline" / "追踪" / "角色统计.yaml"
    data = load_yaml(stats_file)

    chapter_num = extract_chapter_number(chapter_path)

    if not data:
        data = {"出场": []}

    if characters:
        for char_name in characters:
            record = {
                "角色": char_name,
                "章节": chapter_num,
            }
            # 添加状态字段（如果有）
            if char_states and char_name in char_states:
                record["状态"] = char_states[char_name]
            data["出场"].append(record)

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


def update_plot_threads(chapter_path: Path, characters: list[str] | None = None) -> dict:
    """每章写后更新情节线进度。

    主线永远更新（覆盖全书）。支线通过角色匹配判断是否涉及：
    若本章出场角色 ∩ 支线的涉及角色 ≠ ∅ → 该支线在本章活跃 → 更新进度。

    进度写入 outline/追踪/情节线进度.yaml（扁平列表，只追加），
    不再修改情节线文件本身。

    Args:
        chapter_path: 章节文件路径
        characters: 本章出场角色名列表。若为 None，尝试从 fengang 提取

    Returns:
        {"updated": N, "details": ["主线: +1", "支线_危机: +1"]}
    """
    project_root = find_project_root(chapter_path)
    chapter_num = extract_chapter_number(chapter_path)
    now = datetime.now().isoformat()

    plot_dir = project_root / "outline" / "情节线"
    if not plot_dir.is_dir():
        return {"updated": 0, "details": []}

    # Resolve characters if not provided
    if characters is None:
        characters = _extract_characters_from_fengang(project_root, chapter_num)

    # 加载进度文件
    progress_file = project_root / "outline" / "追踪" / "情节线进度.yaml"
    progress_data = load_yaml(progress_file)
    if not progress_data:
        progress_data = {"进度": []}

    # 收集已有的 (情节线, 章节) 组合，避免重复
    existing = {
        (p.get("情节线"), p.get("章节"))
        for p in progress_data.get("进度", [])
        if isinstance(p, dict)
    }

    changes = []
    updated_count = 0

    # ── 主线：永远更新 ──
    main_plot = plot_dir / "主线.yaml"
    if main_plot.exists():
        data = load_yaml(main_plot)
        if data:
            entity_id = data.get("索引信息", {}).get("实体ID", "main_plot")
            if (entity_id, chapter_num) not in existing:
                progress_data["进度"].append({
                    "情节线": entity_id,
                    "章节": chapter_num,
                    "时间": now,
                })
                updated_count += 1
                main_name = data.get("索引信息", {}).get("名称", "主线")
                changes.append(f"{main_name}: +{chapter_num}")

    # ── 支线：角色匹配 ──
    char_set = set(characters) if characters else set()
    for subplot_file in sorted(plot_dir.glob("支线_*.yaml")):
        data = load_yaml(subplot_file)
        if not data:
            continue

        # 提取该支线的涉及角色
        involved_chars = set()
        role_participation = data.get("完整档案", {}).get("角色参与", {})
        char_list = role_participation.get("涉及角色", [])
        if isinstance(char_list, list):
            involved_chars.update(char_list)

        # 也检查 摘要.关联角色
        summary_chars = data.get("摘要", {}).get("关联角色", [])
        if isinstance(summary_chars, list):
            involved_chars.update(summary_chars)

        # 角色交集非空 → 支线在本章活跃
        if char_set and involved_chars and (char_set & involved_chars):
            entity_id = data.get("索引信息", {}).get("实体ID", subplot_file.stem)
            if (entity_id, chapter_num) not in existing:
                progress_data["进度"].append({
                    "情节线": entity_id,
                    "章节": chapter_num,
                    "时间": now,
                })
                updated_count += 1
                sub_name = data.get("索引信息", {}).get("名称", subplot_file.stem)
                changes.append(f"{sub_name}: +{chapter_num}")

    # 保存进度文件
    if updated_count > 0:
        save_yaml(progress_file, progress_data)

    return {"updated": updated_count, "details": changes}


def _extract_characters_from_fengang(project_root: Path, chapter_num: int) -> list[str]:
    """从分纲文件中提取本章出场角色名列表。"""
    fengang_dir = project_root / "outline" / "分纲"
    if not fengang_dir.is_dir():
        return []


def _extract_chapter_time(project_root: Path, chapter_num: int) -> str:
    """从分纲文件中提取本章的故事时间。"""
    fengang_dir = project_root / "outline" / "分纲"
    if not fengang_dir.is_dir():
        return ""
    target_filename = f"第{chapter_num}章.yaml"
    for f in sorted(fengang_dir.rglob(target_filename)):
        data = load_yaml(f)
        if not data:
            continue
        # 模板格式: 摘要.故事时间
        st = data.get("摘要", {}).get("故事时间", "")
        if st:
            return st
        # 兼容旧格式：直接在顶层
        st = data.get("故事时间", "")
        if st:
            return st
    return ""

    target_filename = f"第{chapter_num}章.yaml"
    for f in sorted(fengang_dir.rglob(target_filename)):
        data = load_yaml(f)
        if not data:
            continue
        for field in ["出场角色", "角色", "characters"]:
            chars = data.get(field, [])
            if isinstance(chars, list) and chars:
                return chars
        summary = data.get("摘要", {})
        chars = summary.get("出场角色", [])
        if isinstance(chars, list) and chars:
            return chars

    return []


def update_chapter_summary(
    project_root: Path,
    chapter_path: Path,
    actual_summary: str,
) -> bool:
    """更新章节摘要.yaml（扁平列表，只追加）。

    从章节元数据提取摘要，追加到追踪/章节摘要.yaml。
    """
    if not actual_summary or not actual_summary.strip():
        return False

    chapter_num = extract_chapter_number(chapter_path)
    if not chapter_num:
        return False

    tracking_dir = project_root / "outline" / "追踪"
    if not tracking_dir.is_dir():
        tracking_dir.mkdir(parents=True, exist_ok=True)

    summary_file = tracking_dir / "章节摘要.yaml"
    data = load_yaml(summary_file)

    if not data:
        data = {"摘要": []}

    # 避免重复：如果已有本章摘要则跳过
    existing_chapters = {item.get("章节") for item in data.get("摘要", [])}
    if chapter_num in existing_chapters:
        print(f"  跳过重复: 第{chapter_num}章摘要已存在")
        return False

    data["摘要"].append({
        "章节": chapter_num,
        "摘要": actual_summary.strip(),
    })

    save_yaml(summary_file, data)
    print(f"  -> 章节摘要已追加到 {summary_file.relative_to(project_root)}")
    return True
