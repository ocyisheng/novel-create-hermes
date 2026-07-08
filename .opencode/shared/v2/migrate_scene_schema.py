"""
SCENE schema 迁移脚本：旧 SCENE（含 结构规划/张力曲线/场域规划）→ 新 SCENE（单场域格式）。

使用方式：
    python migrate_scene_schema.py <project_path> [--dry-run]

旧 schema 检测标准：content 中存在 "结构规划" 字段。
新 schema 必填字段：子类型, POV角色, 地点, 一句话概要。
"""

import json
import os
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# 确保能找到 graph_schema
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from graph_store import GraphStore
from graph_schema import UnitType


# 旧 → 新 子类型映射
SUBTYPE_MAP = {
    "推进": "推进",
    "高潮": "冲突",
    "过渡": "过渡",
    "引入": "开篇",
    "收束": "收束",
    "铺垫": "展示",
}


def detect_old_schema(content_dict: dict) -> bool:
    """检测是否为旧 schema（含 结构规划）"""
    return "结构规划" in content_dict


def extract_old_subtype(content_dict: dict) -> str:
    """从旧 schema 提取并映射子类型"""
    raw = content_dict.get("子类型", "")
    return SUBTYPE_MAP.get(raw, "")


def extract_old_conflict(content_dict: dict) -> str:
    """从旧 结构规划 中提取核心冲突"""
    structure = content_dict.get("结构规划", {})
    if isinstance(structure, dict):
        dev = structure.get("发展", {})
        if isinstance(dev, dict):
            return dev.get("核心冲突", "")
    return content_dict.get("核心冲突", "")


def extract_old_summary(content_dict: dict) -> str:
    """从旧 schema 提取一句话概要"""
    summary = content_dict.get("一句话概要", "")
    if summary:
        return summary
    # 从结构规划组合
    structure = content_dict.get("结构规划", {})
    if isinstance(structure, dict):
        parts = []
        opening = structure.get("开篇", {})
        if isinstance(opening, dict) and opening.get("方式"):
            parts.append(opening["方式"])
        dev = structure.get("发展", {})
        if isinstance(dev, dict) and dev.get("推进"):
            parts.append(dev["推进"])
        turn = structure.get("转折", {})
        if isinstance(turn, dict) and turn.get("事件"):
            parts.append(turn["事件"])
        result = structure.get("收尾", {})
        if isinstance(result, dict) and result.get("结果"):
            parts.append(result["结果"])
        if parts:
            return "，".join(parts)
    return ""


def extract_old_pov(content_dict: dict) -> str:
    """从旧 schema 推断 POV 角色"""
    field_plan = content_dict.get("场域规划", [])
    if isinstance(field_plan, list) and field_plan:
        first = field_plan[0]
        if isinstance(first, dict):
            pov = first.get("POV角色", "")
            if pov:
                return pov
    # 用出场角色第一个作为兜底
    chars = content_dict.get("出场角色", [])
    if isinstance(chars, list) and chars:
        first = chars[0]
        return first if isinstance(first, str) else ""
    return ""


def extract_old_word_count(content_dict: dict) -> int:
    """从旧 schema 提取字数"""
    wc = content_dict.get("字数", content_dict.get("预计字数", 0))
    if isinstance(wc, (int, float)):
        return int(wc)
    return 0


def extract_old_location(content_dict: dict) -> str:
    """从旧 schema 提取地点"""
    loc = content_dict.get("地点", "")
    if loc:
        return loc
    structure = content_dict.get("结构规划", {})
    if isinstance(structure, dict):
        opening = structure.get("开篇", {})
        if isinstance(opening, dict):
            return opening.get("地点", opening.get("场景", ""))
    return ""


def convert_scene(content_dict: dict) -> Tuple[Optional[dict], List[str]]:
    """
    将旧 schema content 转为新 schema。
    返回 (new_dict, warnings)
    """
    warnings = []
    new_content = {}

    # 子类型
    subtype = extract_old_subtype(content_dict)
    if not subtype:
        warnings.append("无法确定子类型，使用默认值 '展示'")
        subtype = "展示"
    new_content["子类型"] = subtype

    # POV 角色
    pov = extract_old_pov(content_dict)
    if not pov:
        warnings.append("未找到 POV 角色，留空")
    new_content["POV角色"] = pov

    # 地点
    loc = extract_old_location(content_dict)
    if not loc:
        warnings.append("未找到地点，留空")
    new_content["地点"] = loc

    # 时间
    time_str = content_dict.get("时间", "")
    new_content["时间"] = time_str

    # 一句话概要
    summary = extract_old_summary(content_dict)
    if not summary:
        warnings.append("无法生成一句话概要，留空")
    new_content["一句话概要"] = summary

    # 出场角色
    chars = content_dict.get("出场角色", [])
    new_content["出场角色"] = chars if isinstance(chars, list) else [chars] if isinstance(chars, str) else []

    # 核心冲突
    conflict = extract_old_conflict(content_dict)
    if conflict:
        new_content["核心冲突"] = conflict
    elif summary:
        new_content["核心冲突"] = summary

    # 关联情节线
    plots = content_dict.get("关联情节线", [])
    new_content["关联情节线"] = plots if isinstance(plots, list) else []

    # 字数
    wc = extract_old_word_count(content_dict)
    if wc:
        new_content["字数"] = wc

    return new_content, warnings


def migrate_project(project_path: str, dry_run: bool = False) -> dict:
    """迁移项目中的 SCENE 单元"""
    project_root = Path(project_path)
    graph_dir = project_root / "graph"
    if not graph_dir.exists():
        return {"error": f"未找到 graph 目录: {graph_dir}"}

    store = GraphStore(str(project_root))
    store.initialize()

    scenes = store.find_units(type=UnitType.SCENE)
    stats = {
        "total_scenes": len(scenes),
        "old_schema": 0,
        "new_schema": 0,
        "migrated": 0,
        "skipped": 0,
        "errors": 0,
        "warnings": [],
        "details": [],
    }

    for scene in scenes:
        if not scene.content:
            stats["new_schema"] += 1
            continue

        try:
            content_dict = json.loads(scene.content)
        except (json.JSONDecodeError, ValueError):
            # 纯文本内容不是 JSON schema 格式，跳过
            stats["new_schema"] += 1
            continue

        if not isinstance(content_dict, dict):
            stats["new_schema"] += 1
            continue

        if not detect_old_schema(content_dict):
            # 检查是否为 V1 迁移数据（含 索引信息）
            if "索引信息" in content_dict:
                stats["old_schema"] += 1
                new_content, warnings = convert_v1_migration(content_dict)
            else:
                stats["new_schema"] += 1
                continue
        else:
            stats["old_schema"] += 1
            new_content, warnings = convert_scene(content_dict)

        if dry_run:
            stats["details"].append({
                "id": scene.id,
                "name": scene.unit_name,
                "old_fields": list(content_dict.keys()),
                "new_content": new_content,
                "warnings": warnings,
            })
            stats["migrated"] += 1
            if warnings:
                stats["warnings"].extend(f"[{scene.unit_name}] {w}" for w in warnings)
            continue

        # 执行迁移
        try:
            store.update_unit(
                unit_id=scene.id,
                content=json.dumps(new_content, ensure_ascii=False),
                actor="scene_schema_migration",
            )
            stats["migrated"] += 1
            if warnings:
                stats["warnings"].extend(f"[{scene.unit_name}] {w}" for w in warnings)
        except Exception as e:
            stats["errors"] += 1
            stats["warnings"].append(f"[{scene.unit_name}] 迁移失败: {e}")

    if not dry_run and stats["migrated"] > 0:
        store.flush()

    return stats


def convert_v1_migration(content_dict: dict) -> Tuple[Optional[dict], List[str]]:
    """将 V1 迁移数据（含 索引信息）转为新 SCENE schema"""
    warnings = []
    new_content = {
        "子类型": "展示",
        "POV角色": "",
        "地点": "",
        "时间": "",
        "一句话概要": "",
        "出场角色": [],
        "核心冲突": "",
        "关联情节线": [],
    }

    index_info = content_dict.get("索引信息", {})
    if isinstance(index_info, dict):
        new_content["子类型"] = "推进"
        summary_info = content_dict.get("摘要信息", {})
        if isinstance(summary_info, dict):
            desc = summary_info.get("描述", summary_info.get("核心冲突", ""))
            if desc:
                new_content["一句话概要"] = desc
                new_content["核心冲突"] = desc

        content_body = content_dict.get("内容", "")
        if isinstance(content_body, str) and content_body:
            if not new_content["一句话概要"]:
                new_content["一句话概要"] = content_body[:100]

        chars = content_dict.get("出场角色", [])
        if isinstance(chars, list):
            new_content["出场角色"] = chars

    if not new_content["一句话概要"]:
        warnings.append("V1 迁移数据中未找到场景描述")

    return new_content, warnings


def main():
    import argparse

    parser = argparse.ArgumentParser(description="迁移旧 SCENE schema 到新单场域格式")
    parser.add_argument("project_path", help="小说项目根目录")
    parser.add_argument("--dry-run", action="store_true", help="试运行，不实际修改")
    args = parser.parse_args()

    print(f"扫描项目: {args.project_path}")
    stats = migrate_project(args.project_path, dry_run=args.dry_run)

    if "error" in stats:
        print(f"错误: {stats['error']}")
        sys.exit(1)

    print(f"\nSCENE 单元总数: {stats['total_scenes']}")
    print(f"旧 schema: {stats['old_schema']}")
    print(f"新 schema: {stats['new_schema']}")
    print(f"已迁移: {stats['migrated']}")
    print(f"已跳过: {stats['skipped']}")
    print(f"错误: {stats['errors']}")

    if stats["warnings"]:
        print(f"\n警告 ({len(stats['warnings'])}):")
        for w in stats["warnings"][:10]:
            print(f"  - {w}")
        if len(stats["warnings"]) > 10:
            print(f"  ... 还有 {len(stats['warnings']) - 10} 条")

    if args.dry_run and stats["details"]:
        print(f"\n试运行详情 (前 5 条):")
        for d in stats["details"][:5]:
            print(f"  [{d['name']}] 旧字段: {d['old_fields']}")
            print(f"    新 content: {json.dumps(d['new_content'], ensure_ascii=False)[:120]}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
