#!/usr/bin/env python3
"""
cascade_impact.py — 级联影响分析器

修改角色/世界观/情节线数据后，分析哪些已写章节需要重新检查或重写。

用法：
    python cascade_impact.py --project-root NOVELS_ROOT/项目名 --changed-entity 角色/刘谌
    python cascade_impact.py --project-root NOVELS_ROOT/项目名 --changed-entity 世界观/力量体系 --detail
    python cascade_impact.py --project-root NOVELS_ROOT/项目名 --changed-file characters/刘谌.yaml
    python cascade_impact.py --project-root NOVELS_ROOT/项目名 --dry-run

算法：
  1. 读取 project_index.yaml 获取实体→文件映射
  2. 扫描所有 outline/分纲/*.yaml 的"出场角色"字段，找出包含该实体的章节
  3. 扫描 outline/情节线/*.yaml 的"涉及角色"字段，找出关联情节线
  4. 扫描 outline/伏笔规划.yaml 的"涉及角色"字段
  5. 对每个命中结果，根据字段关联度计算置信度

输出（stdout + 可选文件）：
    YAML 格式的级联分析报告
"""

import argparse
import sys
from datetime import datetime
from pathlib import Path

try:
    from _utils import load_yaml, save_yaml, extract_chapter_number
except ImportError:
    import importlib.util
    _utils_path = Path(__file__).parent / "_utils.py"
    spec = importlib.util.spec_from_file_location("_utils", _utils_path)
    _utils = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(_utils)
    load_yaml = _utils.load_yaml
    save_yaml = _utils.save_yaml
    extract_chapter_number = _utils.extract_chapter_number


ENTITY_TYPES = {
    "角色": "characters",
    "世界观": "worldbuilding",
    "情节线": "plot_threads",
    "总纲": "synopsis",
}


def parse_entity_spec(spec: str) -> tuple[str, str]:
    """解析实体规格。支持格式：'角色/刘谌' 或 'characters/刘谌' 或 '角色:刘谌'"""
    for sep in ["/", ":", "："]:
        if sep in spec:
            parts = spec.split(sep, 1)
            entity_type = parts[0].strip()
            entity_name = parts[1].strip()
            return entity_type, entity_name
    # 默认：从文件名推断
    return "unknown", spec


def resolve_entity_in_index(
    project_root: Path,
    entity_type: str,
    entity_name: str,
) -> dict | None:
    """在 project_index.yaml 中查找实体。"""
    index_path = project_root / "project_index.yaml"
    index = load_yaml(index_path)
    if not index:
        return None

    # 尝试按类型查找
    type_key = ENTITY_TYPES.get(entity_type, entity_type)
    entity_section = index.get(type_key, {})

    for entity_id, entry in entity_section.items():
        if entry.get("name") == entity_name:
            return {
                "entity_id": entity_id,
                "name": entity_name,
                "type": entity_type,
                "file_path": entry.get("file_path", ""),
                "status": entry.get("status", ""),
            }
        if entity_id == entity_name:
            return {
                "entity_id": entity_id,
                "name": entry.get("name", entity_name),
                "type": entity_type,
                "file_path": entry.get("file_path", ""),
                "status": entry.get("status", ""),
            }

    # 模糊匹配
    for entity_id, entry in entity_section.items():
        name = entry.get("name", "")
        if entity_name in name or name in entity_name:
            return {
                "entity_id": entity_id,
                "name": name,
                "type": entity_type,
                "file_path": entry.get("file_path", ""),
                "status": entry.get("status", ""),
                "note": "模糊匹配",
            }

    return None


def scan_fengang_for_entity(
    project_root: Path,
    entity_name: str,
) -> list[dict]:
    """扫描分纲文件，找出包含该实体的章节。"""
    fengang_dir = project_root / "outline" / "分纲"
    hits = []

    if not fengang_dir.is_dir():
        return hits

    for fengang_file in sorted(fengang_dir.rglob("*.yaml")):
        chapter_num = extract_chapter_number(fengang_file.name)
        if chapter_num == 0:
            continue

        data = load_yaml(fengang_file)
        if not data:
            continue

        full = data.get("完整档案", {})
        summary = data.get("摘要", {})

        # 1. 出场角色（高置信度）
        role_list = full.get("出场角色", [])
        if isinstance(role_list, list):
            for item in role_list:
                if isinstance(item, dict):
                    name = item.get("角色名", "")
                    role_status = item.get("状态", "")
                    role_function = item.get("场景作用", "")
                    if name == entity_name:
                        hits.append({
                            "文件": str(fengang_file.relative_to(project_root)),
                            "章节": chapter_num,
                            "影响": "角色出场章节",
                            "详情": f"状态: {role_status}, 作用: {role_function}" if role_status else "直接出场",
                            "置信度": "高",
                        })
                        break

        # 2. 摘要出场角色（中置信度）
        summary_chars = summary.get("出场角色", [])
        if isinstance(summary_chars, list) and entity_name in summary_chars:
            # 避免重复
            if not any(h["章节"] == chapter_num for h in hits):
                hits.append({
                    "文件": str(fengang_file.relative_to(project_root)),
                    "章节": chapter_num,
                    "影响": "角色出场（摘要层）",
                    "详情": "出场角色列表包含该实体",
                    "置信度": "中",
                })

        # 3. 场域规划中的涉及角色
        scene_plan = full.get("场域规划", [])
        if isinstance(scene_plan, list):
            for scene in scene_plan:
                if isinstance(scene, dict):
                    scene_chars = scene.get("涉及角色", [])
                    if isinstance(scene_chars, list) and entity_name in scene_chars:
                        if not any(h["章节"] == chapter_num for h in hits):
                            hits.append({
                                "文件": str(fengang_file.relative_to(project_root)),
                                "章节": chapter_num,
                                "影响": "场域规划涉及角色",
                                "详情": f"场域 '{scene.get('场域名', '')}' 中出场",
                                "置信度": "高",
                            })

        # 4. 章节类型标记（如果是该角色的关键转折章）
        chapter_type = full.get("基本信息", {}).get("类型", "")
        chapter_title = full.get("基本信息", {}).get("章节名", "")
        summary_text = summary.get("一句话描述", "")

        if entity_name in summary_text or entity_name in chapter_title:
            if not any(h["章节"] == chapter_num for h in hits):
                hits.append({
                    "文件": str(fengang_file.relative_to(project_root)),
                    "章节": chapter_num,
                    "影响": "章节主题关联",
                    "详情": f"章节标题或描述包含角色名: {summary_text[:30]}",
                    "置信度": "中",
                })

    return hits


def scan_plot_threads_for_entity(
    project_root: Path,
    entity_name: str,
) -> list[dict]:
    """扫描情节线文件，找出涉及该实体的情节线。"""
    plot_dir = project_root / "outline" / "情节线"
    hits = []

    if not plot_dir.is_dir():
        return hits

    for plot_file in sorted(plot_dir.glob("*.yaml")):
        if plot_file.name == "主索引.yaml":
            continue

        data = load_yaml(plot_file)
        if not data:
            continue

        full = data.get("完整档案", {})
        summary = data.get("摘要", {})

        # 检查涉及角色
        role_participation = full.get("角色参与", {})
        involved = role_participation.get("涉及角色", [])
        if isinstance(involved, list) and entity_name in involved:
            hits.append({
                "文件": str(plot_file.relative_to(project_root)),
                "影响": "关联情节线，角色动机字段",
                "详情": f"情节线 '{data.get('索引信息', {}).get('名称', plot_file.stem)}' 涉及该角色",
                "置信度": "高",
            })
            continue

        summary_chars = summary.get("关联角色", [])
        if isinstance(summary_chars, list) and entity_name in summary_chars:
            hits.append({
                "文件": str(plot_file.relative_to(project_root)),
                "影响": "关联情节线（摘要层）",
                "详情": f"情节线摘要关联角色包含该实体",
                "置信度": "中",
            })

    return hits


def scan_foreshadowing_for_entity(
    project_root: Path,
    entity_name: str,
) -> list[dict]:
    """扫描伏笔规划文件，找出涉及该实体的伏笔。"""
    plan_path = project_root / "outline" / "伏笔规划.yaml"
    hits = []

    data = load_yaml(plan_path)
    if not data:
        return hits

    for item in data.get("伏笔规划") or []:
        if isinstance(item, dict):
            roles = item.get("涉及角色", [])
            if isinstance(roles, list) and entity_name in roles:
                hits.append({
                    "文件": "outline/伏笔规划.yaml",
                    "影响": "角色关联伏笔",
                    "详情": f"伏笔 '{item.get('名称', '')}' 涉及该角色",
                    "置信度": "低",
                })

    return hits


def scan_worldbuilding_for_entity(
    project_root: Path,
    entity_name: str,
) -> list[dict]:
    """扫描世界观文件，找出涉及该实体的文件（反向引用）。"""
    wb_dir = project_root / "worldbuilding"
    hits = []

    if not wb_dir.is_dir():
        return hits

    for wb_file in sorted(wb_dir.glob("*.yaml")):
        data = load_yaml(wb_file)
        if not data:
            continue

        content = str(data)
        if entity_name in content:
            hits.append({
                "文件": str(wb_file.relative_to(project_root)),
                "影响": "世界观设定文件包含角色引用",
                "详情": "内容中包含角色名",
                "置信度": "低",
            })

    return hits


def analyze_cascade(
    project_root: Path,
    entity_type: str,
    entity_name: str,
    detail: bool = False,
) -> dict:
    """执行级联影响分析。

    Returns:
        {
            "变更实体": {...},
            "直接影响": [...],
            "关联情节线": [...],
            "关联伏笔": [...],
            "分析时间": "...",
        }
    """
    project_root = project_root.resolve()

    # 1. 解析实体
    entity_info = resolve_entity_in_index(project_root, entity_type, entity_name)
    if not entity_info:
        entity_info = {
            "entity_id": entity_name,
            "name": entity_name,
            "type": entity_type,
            "file_path": "",
            "status": "unknown",
            "note": "未在 project_index.yaml 中找到",
        }

    # 2. 扫描分纲（高优先级）
    fengang_hits = scan_fengang_for_entity(project_root, entity_name)

    # 3. 扫描情节线
    plot_hits = scan_plot_threads_for_entity(project_root, entity_name)

    # 4. 扫描伏笔
    foreshadowing_hits = scan_foreshadowing_for_entity(project_root, entity_name)

    # 5. 扫描世界观
    wb_hits = scan_worldbuilding_for_entity(project_root, entity_name)

    # 构建输出
    direct_impacts = []
    for hit in sorted(fengang_hits, key=lambda h: h["置信度"], reverse=True):
        entry = {
            "文件": hit["文件"],
            "影响": hit["影响"],
            "置信度": hit["置信度"],
        }
        if detail:
            entry["详情"] = hit.get("详情", "")
            entry["章节"] = hit["章节"]
        direct_impacts.append(entry)

    result = {
        "变更实体": {
            "类型": entity_type,
            "名称": entity_info["name"],
            "实体ID": entity_info["entity_id"],
            "文件路径": entity_info["file_path"],
            "状态": entity_info["status"],
        },
        "直接影响": direct_impacts,
        "关联情节线": [
            {
                "文件": h["文件"],
                "影响": h["影响"],
                "置信度": h["置信度"],
            }
            for h in plot_hits
        ],
        "关联伏笔": [
            {
                "文件": h["文件"],
                "影响": h["影响"],
                "置信度": h["置信度"],
            }
            for h in foreshadowing_hits
        ],
        "分析时间": datetime.now().isoformat(),
    }

    # 汇总建议
    high_impact = [h for h in direct_impacts if h["置信度"] == "高"]
    if high_impact:
        chapters = sorted(set(
            h.get("章节", 0) for h in fengang_hits if h["置信度"] == "高"
        ))
        result["建议"] = (
            f"发现 {len(high_impact)} 个高置信度影响点，"
            f"涉及章节: {chapters}。建议逐章检查角色行为一致性。"
        )
    else:
        result["建议"] = "未发现高置信度影响点，变更安全性较高。"

    return result


def main():
    parser = argparse.ArgumentParser(
        description="cascade_impact.py — 级联影响分析器",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 分析角色变更的影响
  python cascade_impact.py --project-root NOVELS_ROOT/项目名 --changed-entity 角色/刘谌

  # 包含详细字段
  python cascade_impact.py --project-root NOVELS_ROOT/项目名 --changed-entity 世界观/力量体系 --detail

  # 通过文件路径指定
  python cascade_impact.py --project-root NOVELS_ROOT/项目名 --changed-file characters/刘谌.yaml

  # 仅预览（不写入文件）
  python cascade_impact.py --project-root NOVELS_ROOT/项目名 --changed-entity 角色/刘谌 --dry-run
""",
    )
    parser.add_argument("--project-root", "-p", required=True, help="项目根目录路径")
    parser.add_argument("--changed-entity", type=str, default=None,
                        help="变更的实体规格，如 '角色/刘谌' 或 '世界观/力量体系'")
    parser.add_argument("--changed-file", type=str, default=None,
                        help="变更的文件路径（相对于项目根目录），如 'characters/刘谌.yaml'")
    parser.add_argument("--detail", action="store_true", help="输出详细信息（含章节号和详情）")
    parser.add_argument("--output", "-o", type=str, default=None, help="输出文件路径")
    parser.add_argument("--dry-run", "-n", action="store_true", help="仅打印，不写入文件")

    args = parser.parse_args()

    project_root = Path(args.project_root).resolve()
    if not project_root.is_dir():
        print(f"❌ 项目根目录不存在: {project_root}", file=sys.stderr)
        sys.exit(1)

    # 解析要分析的实体
    entity_spec = args.changed_entity
    if not entity_spec and args.changed_file:
        # 从文件路径推断
        file_path = Path(args.changed_file)
        parts = file_path.parts
        entity_type = parts[0] if parts else "unknown"
        entity_name = file_path.stem
        entity_spec = f"{entity_type}/{entity_name}"

    if not entity_spec:
        print("❌ 请指定 --changed-entity 或 --changed-file", file=sys.stderr)
        sys.exit(1)

    entity_type, entity_name = parse_entity_spec(entity_spec)

    result = analyze_cascade(project_root, entity_type, entity_name, detail=args.detail)

    # 输出
    import yaml
    output_text = yaml.dump(result, allow_unicode=True, default_flow_style=False, sort_keys=False)

    if args.output:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(output_text, encoding="utf-8")
        print(f"✅ 级联分析报告已写入: {out_path}")

    print(output_text)

    # 统计
    direct_count = len(result["直接影响"])
    plot_count = len(result["关联情节线"])
    high_count = sum(1 for h in result["直接影响"] if h["置信度"] == "高")
    print(f"\n📊 摘要: {direct_count} 个直接影响, {plot_count} 个关联情节线, {high_count} 个高优先级")


if __name__ == "__main__":
    main()
