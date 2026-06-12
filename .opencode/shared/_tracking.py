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

    # Track items with plot thread references for back-linking
    items_with_plot_refs = []

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

            # Collect items that reference plot threads
            if f.get("关联实体ID"):
                items_with_plot_refs.append(f)

    if resolve_items:
        for item in data.get("伏笔", []):
            for pattern in resolve_items:
                if pattern in item.get("描述", ""):
                    item["状态"] = "已回收"
                    item["回收章节"] = chapter_num
                    break

    save_yaml(foreshadowing_file, data)

    # Back-link to plot threads
    if items_with_plot_refs:
        plot_result = sync_foreshadowing_to_plots(project_root, items_with_plot_refs)
        if plot_result["updated"] > 0:
            print(f"  情节线伏笔回链: {plot_result['updated']} 条")
            for detail in plot_result["details"]:
                print(f"    {detail}")

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


def update_plot_threads(chapter_path: Path, characters: list[str] | None = None) -> dict:
    """每章写后更新情节线进度。

    主线永远更新（覆盖全书）。支线通过角色匹配判断是否涉及：
    若本章出场角色 ∩ 支线的涉及角色 ≠ ∅ → 该支线在本章活跃 → 更新进度。

    Args:
        chapter_path: 章节文件路径
        characters: 本章出场角色名列表。若为 None，尝试从 fengang 提取

    Returns:
        {"updated": N, "details": ["主线: 0→1", "支线_危机: 0→1"]}
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

    changes = []
    updated_count = 0

    # ── 主线：永远更新 ──
    main_plot = plot_dir / "主线.yaml"
    if main_plot.exists():
        data = load_yaml(main_plot)
        if data:
            old_chapter = data.get("索引信息", {}).get("当前章节位置", 0)
            if chapter_num > old_chapter:
                data.setdefault("索引信息", {})["当前章节位置"] = chapter_num
                data.setdefault("_meta", {})["updated_at"] = now
                save_yaml(main_plot, data)
                updated_count += 1
                main_name = data.get("索引信息", {}).get("名称", "主线")
                changes.append(f"{main_name}: {old_chapter} → {chapter_num}")

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
            old_chapter = data.get("索引信息", {}).get("当前章节位置", 0)
            if chapter_num > old_chapter:
                data.setdefault("索引信息", {})["当前章节位置"] = chapter_num
                data.setdefault("_meta", {})["updated_at"] = now
                save_yaml(subplot_file, data)
                updated_count += 1
                sub_name = data.get("索引信息", {}).get("名称", subplot_file.stem)
                changes.append(f"{sub_name}: {old_chapter} → {chapter_num}")

    return {"updated": updated_count, "details": changes}


def _extract_characters_from_fengang(project_root: Path, chapter_num: int) -> list[str]:
    """从分纲文件中提取本章出场角色名列表。"""
    fengang_dir = project_root / "outline" / "分纲"
    if not fengang_dir.is_dir():
        return []

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


def sync_foreshadowing_to_plots(project_root: Path, foreshadowing_items: list[dict]) -> dict:
    """将伏笔回链到关联的情节线文件。

    对每个有 关联实体ID 字段的伏笔项，更新对应情节线的 完整档案.伏笔清单。

    Args:
        project_root: 项目根目录
        foreshadowing_items: 伏笔项列表，每项需含:
            - 编号: 伏笔编号（如 "F001"）
            - 描述: 伏笔内容
            - 状态: "已埋伏笔" / "已回收" / "待回收"
            - 关联实体ID: [list of plot thread entity IDs]

    Returns:
        {"updated": N, "details": ["主线: +F001", "支线_危机: +F001"]}
    """
    plot_dir = project_root / "outline" / "情节线"
    if not plot_dir.is_dir():
        return {"updated": 0, "details": []}

    # Build lookup: entity_id → file path
    id_to_file = {}
    for f in plot_dir.glob("*.yaml"):
        if f.name == "主索引.yaml":
            continue
        data = load_yaml(f)
        if data:
            eid = data.get("索引信息", {}).get("实体ID", "")
            if eid:
                id_to_file[eid] = f

    changes = []
    updated = 0

    for item in foreshadowing_items:
        plot_ids = item.get("关联实体ID", [])
        if not isinstance(plot_ids, list) or not plot_ids:
            continue

        f_num = item.get("编号", "")
        f_desc = item.get("描述", "")
        f_status = item.get("状态", "已埋伏笔")

        for pid in plot_ids:
            plot_file = id_to_file.get(pid)
            if not plot_file:
                continue

            data = load_yaml(plot_file)
            if not data:
                continue

            # Determine target list: 已埋伏笔 or 待回收伏笔
            full_archive = data.setdefault("完整档案", {})
            foreshadowing = full_archive.setdefault("伏笔清单", {})
            target_key = "待回收伏笔" if f_status == "待回收" else "已埋伏笔"
            target_list = foreshadowing.setdefault(target_key, [])

            # Avoid duplicates
            existing_ids = {entry.get("编号", "") for entry in target_list if isinstance(entry, dict)}
            if f_num and f_num not in existing_ids:
                target_list.append({"编号": f_num, "描述": f_desc})
                data.setdefault("_meta", {})["updated_at"] = datetime.now().isoformat()
                save_yaml(plot_file, data)
                updated += 1
                plot_name = data.get("索引信息", {}).get("名称", plot_file.stem)
                changes.append(f"{plot_name}: +{f_num}")

    return {"updated": updated, "details": changes}
