#!/usr/bin/env python3
"""
validate_entity_consistency.py — 角色档案与分纲出场角色一致性校验

检查分纲中列出的出场角色 vs 角色档案的状态是否一致。
例如：角色档案已标记为 deceased/inactive，但后续分纲仍安排其出场。

用法:
    python validate_entity_consistency.py --project-root NOVELS_ROOT/项目名

输出:
    YAML 格式报告，列出所有不一致项
"""

import sys
import argparse
from pathlib import Path

try:
    import yaml
except ImportError:
    print("错误: 需要 PyYAML，请运行 novel-env-setup 安装依赖")
    sys.exit(1)


from _utils import load_yaml, extract_chapter_number


def extract_characters_from_outline(outline: dict) -> list[str]:
    """从分纲 YAML 中提取出场角色名列表"""
    characters = []
    raw = outline.get("出场角色", [])
    for item in raw:
        if isinstance(item, str):
            characters.append(item)
        elif isinstance(item, dict):
            name = item.get("角色名", "")
            if name:
                characters.append(name)
    return characters


def find_character_file(project_root: Path, char_name: str) -> Path | None:
    """在 characters/ 目录中查找角色档案文件"""
    chars_dir = project_root / "characters"
    if not chars_dir.is_dir():
        return None

    # Direct match: {角色名}.yaml
    direct = chars_dir / f"{char_name}.yaml"
    if direct.is_file():
        return direct

    # Try alias lookup via project_index.yaml
    index_path = project_root / "project_index.yaml"
    if index_path.is_file():
        index = load_yaml(index_path)
        for section_key in ("characters",):
            section = index.get(section_key, {})
            for entity_id, entry in section.items():
                entry_name = entry.get("name", "")
                if entry_name == char_name:
                    candidate = chars_dir / f"{entity_id}.yaml"
                    if candidate.is_file():
                        return candidate

    return None


def check_character_status(
    character_path: Path, char_name: str, outline_chapter: int
) -> dict | None:
    """检查单个角色档案状态与分纲章节是否矛盾"""
    data = load_yaml(character_path)
    if not data:
        return None

    index_info = data.get("索引信息", {})
    status = index_info.get("状态", "active")
    current_chapter = index_info.get("当前章节位置", 0)

    issues = []

    if status in ("deceased", "inactive", "已故", "已退场", "死亡"):
        issues.append(
            f"角色 '{char_name}' 档案状态为 '{status}'（当前章节位置: {current_chapter}），"
            f"但在第 {outline_chapter} 章分纲中仍被列为出场角色"
        )

    return {"角色": char_name, "档案路径": str(character_path), "状态": status, "当前章节": current_chapter, "分纲章节": outline_chapter, "问题": issues} if issues else None


def main():
    parser = argparse.ArgumentParser(
        description="角色档案与分纲出场角色一致性校验",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python validate_entity_consistency.py --project-root novels/穿越三国成刘谌
        """,
    )
    parser.add_argument("--project-root", required=True, help="项目根目录")
    args = parser.parse_args()

    project_root = Path(args.project_root).resolve()
    if not project_root.is_dir():
        print(f"错误: 项目根目录不存在: {project_root}", file=sys.stderr)
        sys.exit(1)

    # Scan all chapter outlines
    outlines_dir = project_root / "outline" / "分纲"
    if not outlines_dir.is_dir():
        print("分纲目录不存在", file=sys.stderr)
        sys.exit(1)

    outline_files = sorted(outlines_dir.rglob("第*章.yaml"))
    all_results = []
    total_warnings = 0

    for outline_path in outline_files:
        if ".summary" in outline_path.parts:
            continue

        chapter_num = extract_chapter_number(outline_path)
        outline = load_yaml(outline_path)
        characters = extract_characters_from_outline(outline)

        for char_name in characters:
            char_file = find_character_file(project_root, char_name)
            if char_file is None:
                result = {
                    "角色": char_name,
                    "分纲章节": chapter_num,
                    "分纲文件": str(outline_path.relative_to(project_root)),
                    "状态": "未找到角色档案",
                    "问题": [f"角色 '{char_name}' 在分纲第 {chapter_num} 章有出场，但 characters/ 下未找到对应档案文件"],
                }
                all_results.append(result)
                total_warnings += 1
                continue

            result = check_character_status(char_file, char_name, chapter_num)
            if result:
                result["分纲文件"] = str(outline_path.relative_to(project_root))
                all_results.append(result)
                total_warnings += 1

    # Output report
    report = {
        "status": "pass" if total_warnings == 0 else "warning",
        "project": str(project_root),
        "扫描分纲数": len(outline_files),
        "问题数": total_warnings,
        "不一致项": all_results,
    }

    yaml.safe_dump(report, sys.stdout, default_flow_style=False, sort_keys=False, allow_unicode=True)
    sys.exit(0 if total_warnings == 0 else 1)


if __name__ == "__main__":
    main()
