#!/usr/bin/env python3
"""
cascade_impact.py — 级联影响分析器 (Graph-based)

修改角色/世界观/情节线数据后，分析哪些已写章节需要重新检查或重写。

**两种模式**：
1. `--from-graph`（推荐）：基于 outline/追踪/graph/ 的实体注册表和关系边
   - 实体解析 → 01_nodes.yaml
   - 实体关系 → 10_edges_domain.yaml + 11_edges_cross.yaml
   - 章节引用 → 扫描分纲 + graph 出入边
2. 传统模式（无 `--from-graph`）：保持原版 project_index.yaml + 文件扫描

用法：
    python cascade_impact.py --project-root NOVELS_ROOT/项目名 --changed-entity 角色/刘谌 --from-graph
    python cascade_impact.py --project-root NOVELS_ROOT/项目名 --changed-entity 世界观/力量体系 --detail --from-graph
    python cascade_impact.py --project-root NOVELS_ROOT/项目名 --changed-file characters/刘谌.yaml
    python cascade_impact.py --project-root NOVELS_ROOT/项目名 --dry-run

输出（stdout + 可选文件）：
    YAML 格式的级联分析报告，包含直接影响、关联实体、关联情节线、关联伏笔、建议。
"""

import argparse
import sys
from datetime import datetime
from pathlib import Path

try:
    import yaml
except ImportError:
    print("错误: 需要 PyYAML，请运行 novel-env-setup 安装依赖", file=sys.stderr)
    sys.exit(1)

try:
    from _utils import load_yaml, save_yaml, extract_chapter_number, load_yaml_safe
except ImportError:
    import importlib.util
    _utils_path = Path(__file__).parent / "_utils.py"
    spec = importlib.util.spec_from_file_location("_utils", _utils_path)
    _utils = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(_utils)
    load_yaml = _utils.load_yaml
    save_yaml = _utils.save_yaml
    extract_chapter_number = _utils.extract_chapter_number
    load_yaml_safe = _utils.load_yaml_safe


ENTITY_TYPES = {
    "角色": "characters",
    "世界观": "worldbuilding",
    "情节线": "plot_threads",
    "总纲": "synopsis",
}

# ── Graph 路径常量 ───────────────────────────────────────────────────────────

GRAPH_RELATIVE_PATH = Path("relation") / "graph"
FILE_NODES = "01_nodes.yaml"
FILE_CHECKSUMS = "20_checksums.yaml"


def _load_edges_sharded(graph_dir: Path, kind: str) -> dict:
    """读取分片后的边数据（兼容旧文件）。"""
    is_domain = kind == "domain"
    index_name = "domain_edges_index.yaml" if is_domain else "cross_edges_index.yaml"
    subdir_name = "domain_edges" if is_domain else "cross_edges"
    legacy_name = "10_edges_domain.yaml" if is_domain else "11_edges_cross.yaml"

    subdir = graph_dir / subdir_name
    index_path = graph_dir / index_name

    if not subdir.is_dir() and (graph_dir / legacy_name).exists():
        return load_yaml_safe(graph_dir / legacy_name) or {}

    if not index_path.exists():
        return {}

    index_data = load_yaml_safe(index_path) or {}
    segments: dict = {}
    for seg_name, seg_info in index_data.get("segments", {}).items():
        if isinstance(seg_info, dict) and "file" in seg_info:
            filepath = subdir / seg_info["file"]
            if filepath.exists():
                data = load_yaml_safe(filepath) or {}
                segments[seg_name] = {
                    "count": data.get("count", 0),
                    "entries": data.get("entries", []),
                }
        else:
            segments[seg_name] = {
                "count": seg_info.get("count", 0) if isinstance(seg_info, dict) else 0,
                "entries": seg_info.get("entries", []) if isinstance(seg_info, dict) else [],
            }

    return {
        "version": index_data.get("version", 1),
        "last_updated": index_data.get("last_updated", ""),
        "segments": segments,
    }


# ── 解析 ─────────────────────────────────────────────────────────────────────

def parse_entity_spec(spec: str) -> tuple[str, str]:
    """解析实体规格。支持格式：'角色/刘谌' 或 'characters/刘谌' 或 '角色:刘谌'"""
    for sep in ["/", ":", "："]:
        if sep in spec:
            parts = spec.split(sep, 1)
            entity_type = parts[0].strip()
            entity_name = parts[1].strip()
            return entity_type, entity_name
    return "unknown", spec


# ── Graph 初始化 ─────────────────────────────────────────────────────────────

def graph_dir_path(project_root: Path) -> Path:
    """返回 graph 目录路径。"""
    return project_root / GRAPH_RELATIVE_PATH


def require_graph(project_root: Path) -> tuple[Path, dict, dict, dict, dict]:
    """加载 graph 所有核心文件，不存在则报错退出。

    Returns:
        (graph_dir, nodes_data, domain_data, cross_data, checksums_data)
    """
    gd = graph_dir_path(project_root)
    if not gd.is_dir():
        print(f"❌ 图谱目录不存在: {gd}", file=sys.stderr)
        print("   请先运行 project_graph.py build", file=sys.stderr)
        sys.exit(1)

    nodes_data = load_yaml_safe(gd / FILE_NODES) or {}
    domain_data = _load_edges_sharded(gd, "domain") or {}
    cross_data = _load_edges_sharded(gd, "cross") or {}
    checksums_data = load_yaml_safe(gd / FILE_CHECKSUMS) or {}

    return gd, nodes_data, domain_data, cross_data, checksums_data


# ── Graph 查询 ───────────────────────────────────────────────────────────────

def resolve_entity_from_graph(
    graph_dir: Path,
    entity_type: str,
    entity_name: str,
) -> dict | None:
    """从 graph 01_nodes.yaml 查询实体。
    
    支持精确匹配 display_name 和模糊匹配实体 ID/名称。
    """
    nodes_file = graph_dir / FILE_NODES
    nodes_data = load_yaml_safe(nodes_file)
    if not nodes_data:
        return None

    nodes = nodes_data.get("nodes", {})

    # 1. 精确匹配 display_name
    for eid, info in nodes.items():
        if info.get("display_name") == entity_name:
            return {
                "entity_id": eid,
                "name": entity_name,
                "type": info.get("type", ""),
                "file_path": info.get("file_path", ""),
                "status": info.get("status", ""),
            }

    # 2. 精确匹配 entity_id
    for eid, info in nodes.items():
        if eid == entity_name or eid.endswith(f"_{entity_name}"):
            return {
                "entity_id": eid,
                "name": info.get("display_name", entity_name),
                "type": info.get("type", ""),
                "file_path": info.get("file_path", ""),
                "status": info.get("status", ""),
            }

    # 3. 模糊匹配
    for eid, info in nodes.items():
        name = info.get("display_name", "")
        if entity_name in name or name in entity_name:
            return {
                "entity_id": eid,
                "name": name,
                "type": info.get("type", ""),
                "file_path": info.get("file_path", ""),
                "status": info.get("status", ""),
                "note": "模糊匹配",
            }

    return None


def query_graph_edges(
    domain_data: dict,
    cross_data: dict,
) -> list[dict]:
    """返回 graph 中所有边（合并域内+跨域）。"""
    all_edges = []
    for seg_data in domain_data.get("segments", {}).values():
        all_edges.extend(seg_data.get("entries", []))
    for seg_data in cross_data.get("segments", {}).values():
        all_edges.extend(seg_data.get("entries", []))
    return all_edges


def get_incoming_edges(
    domain_data: dict,
    cross_data: dict,
    target_entity_id: str,
) -> list[dict]:
    """查询指向该实体的所有入边。"""
    results = []
    for seg_data in domain_data.get("segments", {}).values():
        for edge in seg_data.get("entries", []):
            if edge.get("to") == target_entity_id:
                results.append(edge)
    for seg_data in cross_data.get("segments", {}).values():
        for edge in seg_data.get("entries", []):
            if edge.get("to") == target_entity_id:
                results.append(edge)
    return results


def get_outgoing_edges(
    domain_data: dict,
    cross_data: dict,
    source_entity_id: str,
) -> list[dict]:
    """查询该实体指向其他实体的所有出边。"""
    results = []
    for seg_data in domain_data.get("segments", {}).values():
        for edge in seg_data.get("entries", []):
            if edge.get("from") == source_entity_id:
                results.append(edge)
    for seg_data in cross_data.get("segments", {}).values():
        for edge in seg_data.get("entries", []):
            if edge.get("from") == source_entity_id:
                results.append(edge)
    return results


# ── 传统解析（无 graph 时的 fallback） ──────────────────────────────────────

def resolve_entity_in_index(
    project_root: Path,
    entity_type: str,
    entity_name: str,
) -> dict | None:
    """在 project_index.yaml 中查找实体（传统模式 fallback）。"""
    index_path = project_root / "project_index.yaml"
    index = load_yaml(index_path)
    if not index:
        return None

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


# ── 分纲扫描（两种模式共用） ────────────────────────────────────────────────

def scan_fengang_for_entity(
    project_root: Path,
    entity_name: str,
    changed_files: set[str] | None = None,
) -> list[dict]:
    """扫描分纲文件，找出包含该实体的章节。

    Args:
        project_root: 项目根目录
        entity_name: 实体名称（显示名）
        changed_files: 如果提供，只扫描这些文件（graph 模式下优化）
    """
    fengang_dir = project_root / "outline" / "分纲"
    hits = []

    if not fengang_dir.is_dir():
        return hits

    for fengang_file in sorted(fengang_dir.rglob("*.yaml")):
        if changed_files is not None:
            rel = fengang_file.relative_to(project_root).as_posix()
            if rel not in changed_files:
                continue

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

        # 4. 章节类型标记
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


# ── Graph 版关联实体提取 ─────────────────────────────────────────────────────

def get_related_entities_from_graph(
    entity_id: str,
    graph_dir: Path,
    nodes_data: dict,
    domain_data: dict,
    cross_data: dict,
    project_root: Path | None = None,
    detail: bool = False,
) -> tuple[list[dict], list[dict], list[dict], list[dict], list[dict]]:
    """基于 graph edges 提取所有级联影响。

    Returns:
        (related_entities, plot_thread_hits, worldbuilding_hits,
         foreshadowing_hits, fengang_hits)
    """
    nodes = nodes_data.get("nodes", {})

    # ── 入边（谁引用了我） ──
    incoming = get_incoming_edges(domain_data, cross_data, entity_id)

    # ── 出边（我引用了谁） ──
    outgoing = get_outgoing_edges(domain_data, cross_data, entity_id)

    # ── 关联实体（排除 outline_detail 等文档型实体） ──
    related_entities: list[dict] = []
    seen_targets: set[str] = set()
    skip_types = {"outline_detail"}

    all_related = incoming + outgoing
    for edge in all_related:
        if edge.get("from") == entity_id:
            target_id = edge["to"]
        else:
            target_id = edge["from"]

        if target_id in seen_targets:
            continue

        target_info = nodes.get(target_id, {})
        if not target_info:
            continue
        if target_info.get("type", "") in skip_types:
            continue  # 文档型实体不放入"关联实体"

        seen_targets.add(target_id)

        entry = {
            "实体ID": target_id,
            "名称": target_info.get("display_name", target_id),
            "类型": target_info.get("type", ""),
            "关系": edge.get("relation_type", "引用"),
            "来源文件": edge.get("source", {}).get("file", ""),
            "置信度": edge.get("confidence", "implicit"),
        }
        if detail:
            entry["字段路径"] = edge.get("source", {}).get("field_path", "")
        related_entities.append(entry)

    # ── 情节线关联（从入边中筛选出 plot 类型的来源） ──
    plot_hits: list[dict] = []
    for edge in incoming:
        from_id = edge["from"]
        from_info = nodes.get(from_id, {})
        if from_info.get("type") in ("plot",):
            entry = {
                "文件": edge.get("source", {}).get("file", ""),
                "影响": f"关联情节线，{edge.get('relation_type', '引用')}",
                "详情": f"来自实体 '{from_info.get('display_name', from_id)}'",
                "置信度": "高" if edge.get("confidence") == "explicit" else "中",
            }
            plot_hits.append(entry)

    # ── 世界观关联（从入边中筛选出 worldbuilding 类型的来源） ──
    wb_hits: list[dict] = []
    for edge in incoming:
        from_id = edge["from"]
        from_info = nodes.get(from_id, {})
        if from_info.get("type") in ("worldbuilding", "faction"):
            entry = {
                "文件": edge.get("source", {}).get("file", ""),
                "影响": f"世界观设定文件包含角色引用，{edge.get('relation_type', '引用')}",
                "详情": f"来自 '{from_info.get('display_name', from_id)}'",
                "置信度": "低",
            }
            wb_hits.append(entry)

    # ── 分纲/章节关联（从入边中筛选出 outline_detail 类型的来源） ──
    fengang_hits: list[dict] = []
    for edge in incoming:
        from_id = edge["from"]
        from_info = nodes.get(from_id, {})
        if from_info.get("type") == "outline_detail":
            source_file = edge.get("source", {}).get("file", "")
            chapter_num = extract_chapter_number(source_file)
            entry = {
                "文件": source_file,
                "影响": f"角色出场章节（{edge.get('relation_type', '引用')}）",
                "置信度": "高" if edge.get("confidence") == "explicit" else "中",
            }
            if chapter_num:
                entry["章节"] = chapter_num
            if detail:
                entry["详情"] = f"字段: {edge.get('source', {}).get('field_path', '')}"
                entry["实体ID"] = from_id
            fengang_hits.append(entry)

    # 去重（同一实体可能在同个分纲被多次引用）
    seen_fengang: set[tuple] = set()
    deduped: list[dict] = []
    for h in fengang_hits:
        key = (h.get("文件", ""), h.get("章节", 0))
        if key not in seen_fengang:
            seen_fengang.add(key)
            deduped.append(h)
    fengang_hits = deduped

    # ── 伏笔关联（从入边中筛选出 foreshadowing 类型的来源） ──
    foreshadowing_hits: list[dict] = []
    for edge in incoming:
        from_id = edge["from"]
        from_info = nodes.get(from_id, {})
        if from_info.get("type") == "foreshadowing":
            entry = {
                "文件": edge.get("source", {}).get("file", ""),
                "影响": "角色关联伏笔",
                "详情": f"伏笔 '{from_info.get('display_name', from_id)}' 涉及该角色",
                "置信度": "低",
            }
            foreshadowing_hits.append(entry)

    return related_entities, plot_hits, wb_hits, foreshadowing_hits, fengang_hits


# ── 传统扫描（无 graph 时使用） ─────────────────────────────────────────────

def scan_plot_threads_for_entity(
    project_root: Path,
    entity_name: str,
) -> list[dict]:
    """扫描情节线文件（传统模式）。"""
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
    """扫描伏笔规划文件。"""
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
    """扫描世界观文件（传统模式）。"""
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


# ── 主分析函数 ───────────────────────────────────────────────────────────────

def analyze_cascade(
    project_root: Path,
    entity_type: str,
    entity_name: str,
    detail: bool = False,
    from_graph: bool = False,
) -> dict:
    """执行级联影响分析。

    Returns:
        {
            "变更实体": {...},
            "直接影响": [...],
            "关联实体": [...],        # 仅 graph 模式
            "关联情节线": [...],
            "关联伏笔": [...],
            "建议": "...",
            "分析时间": "...",
        }
    """
    project_root = project_root.resolve()

    if from_graph:
        return _analyze_cascade_via_graph(
            project_root, entity_type, entity_name, detail,
        )
    else:
        return _analyze_cascade_legacy(
            project_root, entity_type, entity_name, detail,
        )


def _analyze_cascade_via_graph(
    project_root: Path,
    entity_type: str,
    entity_name: str,
    detail: bool = False,
) -> dict:
    """Graph 模式：基于图数据分析。"""
    gd, nodes_data, domain_data, cross_data, checksums_data = require_graph(project_root)

    # 1. 从 graph 解析实体
    entity_info = resolve_entity_from_graph(gd, entity_type, entity_name)
    if not entity_info:
        entity_info = {
            "entity_id": entity_name,
            "name": entity_name,
            "type": entity_type,
            "file_path": "",
            "status": "unknown",
            "note": "未在 graph 中找到，请确认实体名是否正确或先运行 project_graph.py build",
        }

    entity_id = entity_info.get("entity_id", entity_name)
    nodes = nodes_data.get("nodes", {})

    # 2. 从 graph 提取所有关联信息（含分纲引用 → 通过 outline_detail 入边，伏笔 → 通过 foreshadowing 入边）
    related_entities, plot_hits, wb_hits, foreshadowing_hits, fengang_hits = get_related_entities_from_graph(
        entity_id, gd, nodes_data, domain_data, cross_data,
        project_root=project_root, detail=detail,
    )

    # 5. 构建输出
    direct_impacts = []
    for hit in sorted(fengang_hits, key=lambda h: h["置信度"], reverse=True):
        entry = {
            "文件": hit["文件"],
            "影响": hit["影响"],
            "置信度": hit["置信度"],
        }
        if detail:
            entry["详情"] = hit.get("详情", "")
            entry["章节"] = hit.get("章节", 0)
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
        "关联实体": sorted(related_entities, key=lambda e: e.get("置信度", ""), reverse=True),
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
        "分析模式": "graph-based",
        "分析时间": datetime.now().isoformat(),
    }

    # 汇总建议
    high_impact = [h for h in direct_impacts if h["置信度"] == "高"]
    high_relations = [r for r in related_entities if r.get("置信度") == "explicit"]
    if high_impact or high_relations:
        chapters = sorted(set(
            h.get("章节", 0) for h in fengang_hits if h["置信度"] == "高"
        ))
        parts = []
        if high_impact:
            parts.append(f"发现 {len(high_impact)} 个高置信度影响点")
        if chapters:
            parts.append(f"涉及章节: {chapters}")
        if high_relations:
            parts.append(f"关联实体: {len(high_relations)} 个")
        result["建议"] = "；".join(parts) + "。建议逐章检查角色行为一致性。"
    else:
        result["建议"] = "未发现高置信度影响点，变更安全性较高。"

    return result


def _analyze_cascade_legacy(
    project_root: Path,
    entity_type: str,
    entity_name: str,
    detail: bool = False,
) -> dict:
    """传统模式：基于文件扫描（原版逻辑）。"""
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

    # 2. 扫描分纲
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
            entry["章节"] = hit.get("章节", 0)
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


# ── CLI ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="cascade_impact.py — 级联影响分析器",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # Graph 模式（推荐，需先 build graph）
  python cascade_impact.py -p NOVELS_ROOT/项目名 --changed-entity 角色/刘谌 --from-graph

  # 包含详细字段
  python cascade_impact.py -p NOVELS_ROOT/项目名 --changed-entity 世界观/力量体系 --detail --from-graph

  # 通过文件路径指定
  python cascade_impact.py -p NOVELS_ROOT/项目名 --changed-file characters/刘谌.yaml

  # 传统模式（无 graph）
  python cascade_impact.py -p NOVELS_ROOT/项目名 --changed-entity 角色/刘谌

  # 仅预览（不写入文件）
  python cascade_impact.py -p NOVELS_ROOT/项目名 --changed-entity 角色/刘谌 --dry-run
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
    parser.add_argument("--from-graph", action="store_true",
                        help="使用 graph 模式（需先运行 project_graph.py build）")

    args = parser.parse_args()

    project_root = Path(args.project_root).resolve()
    if not project_root.is_dir():
        print(f"❌ 项目根目录不存在: {project_root}", file=sys.stderr)
        sys.exit(1)

    # 解析要分析的实体
    entity_spec = args.changed_entity
    if not entity_spec and args.changed_file:
        file_path = Path(args.changed_file)
        parts = file_path.parts
        entity_type = parts[0] if parts else "unknown"
        entity_name = file_path.stem
        entity_spec = f"{entity_type}/{entity_name}"

    if not entity_spec:
        print("❌ 请指定 --changed-entity 或 --changed-file", file=sys.stderr)
        sys.exit(1)

    entity_type, entity_name = parse_entity_spec(entity_spec)

    result = analyze_cascade(
        project_root, entity_type, entity_name,
        detail=args.detail, from_graph=args.from_graph,
    )

    output_text = yaml.dump(result, allow_unicode=True, default_flow_style=False, sort_keys=False)

    if args.output and not args.dry_run:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(output_text, encoding="utf-8")
        print(f"✅ 级联分析报告已写入: {out_path}")
    elif args.output and args.dry_run:
        print(f"🟡 [DRY RUN] 跳过文件写入: {args.output}")

    print(output_text)

    # 统计
    direct_count = len(result["直接影响"])
    plot_count = len(result.get("关联情节线", []))
    entity_count = len(result.get("关联实体", []))
    high_count = sum(1 for h in result["直接影响"] if h["置信度"] == "高")
    prefix = "📊"
    parts = [f"{direct_count} 个直接影响", f"{plot_count} 个关联情节线"]
    if entity_count:
        parts.append(f"{entity_count} 个关联实体")
    parts.append(f"{high_count} 个高优先级")
    print(f"\n{prefix} 摘要: {', '.join(parts)}")


if __name__ == "__main__":
    main()
