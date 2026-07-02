#!/usr/bin/env python3
"""
project_graph.py — 项目关系图谱管理

为 novel-search-analysis 和 novel-edit 提供实体注册、关系映射、增量检测能力。
管理 outline/追踪/graph/ 下的多文件体系。

用法:
    # 构建完整的项目图谱（首次运行或全量重建）
    python project_graph.py --project-root NOVELS_ROOT/项目名 build

    # 增量更新（编辑后处理链中调用，自动检测变更）
    python project_graph.py --project-root NOVELS_ROOT/项目名 incremental-update
    python project_graph.py --project-root NOVELS_ROOT/项目名 incremental-update --scope characters

    # 检测哪些源文件发生了变化（供 full-diagnose 使用）
    python project_graph.py --project-root NOVELS_ROOT/项目名 detect-changes

    # 查询实体
    python project_graph.py --project-root NOVELS_ROOT/项目名 query-entity --entity-id characters_林昭

    # 查询出边/入边
    python project_graph.py --project-root NOVELS_ROOT/项目名 query-edges-from --entity-id characters_林昭
    python project_graph.py --project-root NOVELS_ROOT/项目名 query-edges-to --entity-id characters_林昭

依赖: Python 3, PyYAML
"""

import argparse
import hashlib
import re
import sys
from datetime import datetime
from pathlib import Path

try:
    import yaml
except ImportError:
    print("错误: 需要 PyYAML，请运行 novel-env-setup 安装依赖", file=sys.stderr)
    sys.exit(1)

from _utils import load_yaml, load_yaml_safe, save_yaml


# ── 常量 ─────────────────────────────────────────────────────────────────────

GRAPH_VERSION = "1.0.0"
GRAPH_DIR_NAME = "graph"
GRAPH_RELATIVE_PATH = Path("relation") / GRAPH_DIR_NAME

FILE_META = "meta.yaml"
FILE_NODES = "nodes.yaml"
FILE_DEVIATIONS = "deviations.yaml"
FILE_CHECKSUMS = "checksums.yaml"

# 旧文件名（迁移兼容）
_LEGACY_NODES = "01_nodes.yaml"
_LEGACY_DEVIATIONS = "02_deviation_state.yaml"
_LEGACY_CHECKSUMS = "20_checksums.yaml"
_LEGACY_EDGES_DOMAIN = "10_edges_domain.yaml"
_LEGACY_EDGES_CROSS = "11_edges_cross.yaml"

# P1-P7 扫描范围配置
# (子目录路径/具体文件, 文件类型, 文件 glob 模式)
SCAN_SCOPE = [
    ("ideation",             "ideation",       "*.yaml"),
    ("worldbuilding",        "worldbuilding",  "*.yaml"),
    ("characters",           "character",      "*.yaml"),
    ("outline/情节线",        "plot",           "*.yaml"),
    ("outline/分卷",          "volume",         "*.yaml"),
    ("outline/分纲",          "outline_detail", "*.yaml"),
    ("outline",               "foreshadowing",  "伏笔规划.yaml"),
]

# 单文件扫描（非目录结构）
SINGLE_FILE_SCANS = [
    ("outline/总纲.yaml",          "synopsis"),
    ("outline/时间线设计.yaml",     "timeline_design"),
    ("outline/角色弧光.yaml",       "character_arc"),
]

# 用于关系分类的字段路径关键词
RELATION_KEYWORDS = {
    "关系网络": "盟友",
    "关系": "关联",
    "身份": "所属势力",
    "所属": "所属",
}

# edge segment 定义（域内：同类型实体之间）
DOMAIN_SEGMENTS = ["characters", "factions", "locations", "worldbuilding"]
# edge segment 定义（跨域：不同类型实体之间）
CROSS_SEGMENTS = [
    "character_to_faction",
    "character_to_location",
    "character_to_plot",
    "faction_to_location",
]

# ── 边文件分片配置 ──────────────────────────────────────────────────────────
DOMAIN_EDGES_DIR = "domain_edges"
CROSS_EDGES_DIR = "cross_edges"
DOMAIN_EDGES_INDEX = "domain_edges_index.yaml"
CROSS_EDGES_INDEX = "cross_edges_index.yaml"
EDGE_SHARD_THRESHOLD = 10  # count <= 此值内联在索引文件中，否则独立文件


# ── 哈希工具 ─────────────────────────────────────────────────────────────────

def compute_file_hash(filepath: Path) -> str:
    """计算文件的 SHA256 哈希。"""
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def compute_yaml_hash(data: dict) -> str:
    """计算字典的 SHA256 哈希。用于 graph 内部文件一致性校验。"""
    raw = yaml.dump(data, sort_keys=True, allow_unicode=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


# ── 路径工具 ─────────────────────────────────────────────────────────────────

def get_graph_dir(project_root: Path) -> Path:
    """返回 graph/ 目录路径。"""
    return project_root / GRAPH_RELATIVE_PATH


def _migrate_legacy_filenames(graph_dir: Path) -> None:
    """将旧版文件名迁移为新版，仅当新文件不存在时。"""
    legacy_map = {
        "01_nodes.yaml": "nodes.yaml",
        "02_deviation_state.yaml": "deviations.yaml",
        "20_checksums.yaml": "checksums.yaml",
    }
    for old, new in legacy_map.items():
        old_path = graph_dir / old
        new_path = graph_dir / new
        if old_path.exists() and not new_path.exists():
            old_path.rename(new_path)
        # 清理旧 bak
        old_bak = graph_dir / f"{old}.bak"
        if old_bak.exists():
            old_bak.unlink()


def find_project_root(start: Path) -> Path | None:
    """向上查找包含 config.yaml 的项目根目录。"""
    if (start / "config.yaml").is_file():
        return start.resolve()
    for parent in start.parents:
        if (parent / "config.yaml").is_file():
            return parent.resolve()
    return None


# ── 实体注册表（01_nodes.yaml）─────────────────────────────────────────────

def _deep_search_string(data, target_key: str, max_depth: int = 5) -> str:
    """深度递归搜索第一个匹配 target_key 的字符串值。
    
    agent 生成的 YAML 结构不可预测，此函数作为最后 fallback。
    """
    if max_depth <= 0:
        return ""

    if isinstance(data, dict):
        if target_key in data:
            val = data[target_key]
            if isinstance(val, str):
                return val
        for v in data.values():
            result = _deep_search_string(v, target_key, max_depth - 1)
            if result:
                return result
    elif isinstance(data, list):
        for item in data:
            result = _deep_search_string(item, target_key, max_depth - 1)
            if result:
                return result
    return ""


def extract_entity_id(data: dict, fallback_stem: str) -> str:
    """从 YAML 数据中提取实体 ID。
    
    降级链：索引信息 → 基本信息 → id → 递归搜索 → 文件名。
    """
    eid = data.get("索引信息", {}).get("实体ID", "")
    if not eid:
        eid = data.get("基本信息", {}).get("实体ID", "")
    if not eid:
        eid = data.get("id", "")
    if not eid:
        eid = _deep_search_string(data, "实体ID")
    if not eid:
        eid = fallback_stem
    return eid


def extract_display_name(data: dict, fallback: str) -> str:
    """从 YAML 数据中提取显示名称。
    
    降级链：索引信息 → 基本信息 → name → 递归搜索 → fallback。
    """
    name = data.get("索引信息", {}).get("名称", "")
    if not name:
        name = data.get("基本信息", {}).get("名称", "")
    if not name:
        name = data.get("name", "")
    if not name:
        name = _deep_search_string(data, "名称")
    if not name:
        name = _deep_search_string(data, "name")
    if not name:
        name = fallback
    return name


def extract_status(data: dict) -> str:
    """从 YAML 数据中提取实体状态。"""
    status = data.get("索引信息", {}).get("状态", "active")
    if not status:
        status = _deep_search_string(data, "状态")
    return status if status else "active"


# YAML 内实体子类型 → 图谱节点类型映射
ENTITY_SUBTYPE_MAP = {
    "faction":       "faction",
    "势力":          "faction",
    "location":      "location",
    "地点":          "location",
    "forbidden_land": "location",  # 绝地 → 地点
}


def _resolve_node_type(file_type: str, data: dict) -> str:
    """根据 YAML 内声明的子类型解析更精确的节点类型。

    如 worldbuilding 目录下的 势力格局.yaml 应标记为 faction 而非 worldbuilding。
    """
    # 从多个可能的位置查找子类型
    subtype = (
        data.get("索引信息", {}).get("实体子类型", "")
        or data.get("_meta", {}).get("entity_type", "")
    )
    if subtype:
        mapped = ENTITY_SUBTYPE_MAP.get(subtype)
        if mapped:
            return mapped
    return file_type


def scan_file_for_nodes(project_root: Path, rel_path_str: str, file_type: str) -> list[dict]:
    """从单个源文件提取节点注册信息。"""
    filepath = project_root / rel_path_str
    if not filepath.is_file():
        return []

    data = load_yaml_safe(filepath)
    if not data:
        return []

    # 伏笔规划：每个伏笔项目是一个独立节点
    if file_type == "foreshadowing":
        return _scan_foreshadowing_nodes(data, rel_path_str)

    stem = filepath.stem
    entity_id = extract_entity_id(data, stem)
    display_name = extract_display_name(data, stem)
    status = extract_status(data)

    # 如果文件有更精确的子类型声明，用子类型替代目录推定的类型
    resolved_type = _resolve_node_type(file_type, data)

    # 如果是情节线/分卷/分纲等无独立实体 ID 的文件，用文件名作为 key
    key = entity_id if entity_id else f"{file_type}_{stem}"

    # 角色提取身份、能力、出身字段
    extra = {}
    if resolved_type == "character":
        ri = data.get("完整档案", {}).get("角色信息", {})
        if ri:
            for f in ("身份", "修为", "功法", "阵营"):
                v = ri.get(f, "")
                if v:
                    extra[f] = v
        # 出身可能在不同位置
        for src in (data.get("完整档案", {}).get("背景", {}),
                    data.get("完整档案", {}).get("基本信息", {}),
                    data):
            if isinstance(src, dict):
                v = src.get("出身", "") or src.get("出生", "") or src.get("来源", "")
                if v and isinstance(v, str):
                    extra["出身"] = v[:100]
                    break
        summary = data.get("摘要", {})
        traits = summary.get("核心特质", [])
        if traits:
            extra["核心特质"] = traits if isinstance(traits, list) else [traits]

    return [{
        "id": key,
        "type": resolved_type,
        "display_name": display_name,
        "file_path": rel_path_str,
        "status": status,
        **extra,
    }]


def _scan_foreshadowing_nodes(data: dict, rel_path_str: str) -> list[dict]:
    """从伏笔规划数据中提取每个伏笔项作为独立节点。"""
    items = data.get("伏笔规划") or []
    nodes = []
    seen: set[str] = set()
    for item in items:
        name = (item.get("名称", "") or "").strip()
        if not name:
            continue
        eid = f"foreshadowing_{name}"
        if eid in seen:
            continue
        seen.add(eid)
        nodes.append({
            "id": eid,
            "type": "foreshadowing",
            "display_name": name,
            "file_path": rel_path_str,
            "status": "active",
        })
    return nodes


def collect_all_nodes(project_root: Path) -> dict:
    """全量扫描 P1-P7 目录，收集所有实体节点。

    Returns:
        {entity_id: node_info, ...}
    """
    nodes: dict[str, dict] = {}

    for subdir, file_type, pattern in SCAN_SCOPE:
        target_dir = project_root / subdir
        if not target_dir.is_dir():
            continue
        for f in sorted(target_dir.rglob(pattern)):
            if ".bak" in f.suffixes or ".summary" in f.parts:
                continue
            rel = f.relative_to(project_root).as_posix()
            entries = scan_file_for_nodes(project_root, rel, file_type)
            for entry in entries:
                if entry["id"] not in nodes:
                    nodes[entry["id"]] = entry

    # 单文件扫描
    for rel_path, file_type in SINGLE_FILE_SCANS:
        f = project_root / rel_path
        if not f.is_file():
            continue
        entries = scan_file_for_nodes(project_root, rel_path, file_type)
        for entry in entries:
            if entry["id"] not in nodes:
                nodes[entry["id"]] = entry

    # 补充 project_index.yaml 中的实体（如果上面漏了）
    index_path = project_root / "project_index.yaml"
    if index_path.is_file():
        index_data = load_yaml_safe(index_path)
        if index_data:
            for section_key in ("characters", "worldbuilding"):
                section = index_data.get(section_key, {})
                for entity_id, entry in section.items():
                    if entity_id not in nodes:
                        raw_path = entry.get("file_path", "")
                        nodes[entity_id] = {
                            "id": entity_id,
                            "type": section_key,
                            "display_name": entry.get("name", entity_id),
                            "file_path": Path(raw_path).as_posix() if raw_path else "",
                            "status": entry.get("status", "active"),
                        }

    return nodes


def build_nodes_file(project_root: Path, nodes: dict) -> dict:
    """构建 01_nodes.yaml 内容。"""
    return {
        "version": 1,
        "last_updated": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        "entries": len(nodes),
        "nodes": nodes,
    }


# ── 关系边提取 ──────────────────────────────────────────────────────────────

def build_name_to_id_index(nodes: dict) -> dict[str, str]:
    """构建 display_name → entity_id 的反向索引。"""
    index = {}
    for eid, info in nodes.items():
        name = info.get("display_name", "")
        if name:
            index[name] = eid
    return index


def guess_relation_type(source_type: str, target_type: str, field_path: str) -> str:
    """根据上下文猜测关系类型。"""
    # 跨域默认关系
    cross_defaults = {
        ("character", "faction"): "所属势力",
        ("character", "location"): "所在地",
        ("character", "plot"): "参与情节",
        ("faction", "location"): "势力范围",
    }
    key = (source_type, target_type)
    if key in cross_defaults:
        return cross_defaults[key]
    reverse_key = (target_type, source_type)
    if reverse_key in cross_defaults:
        return cross_defaults[reverse_key]

    # 域内默认
    if source_type == target_type:
        return "关联"

    return "引用"


def get_type_group(entity_type: str) -> str:
    """将实体类型映射到域内 segment。"""
    if entity_type == "character":
        return "characters"
    elif entity_type in ("faction", "势力"):
        return "factions"
    elif entity_type in ("location", "地点"):
        return "locations"
    elif entity_type == "worldbuilding":
        return "worldbuilding"
    return "other"


# ── 关系类型上下文关键词 ──────────────────────────────────────────────────

RELATION_TYPE_FIELDS = {"关系", "关系类型", "关系描述", "relation", "type", "role"}
IDENTITY_FIELDS = {"身份", "所属", "门派", "势力", "faction", "affiliation"}
LOCATION_FIELDS = {"所在地", "地点", "位置", "location", "area"}


def _extract_relation_type_from_context(
    dict_item: dict, name_to_id: dict, source_entity_id: str,
) -> str | None:
    """从字典上下文中提取关系类型。"""
    # 优先检查名为"关系/关系类型"的字段值
    entity_ref_field = None
    for k, v in dict_item.items():
        if isinstance(v, str) and k in RELATION_TYPE_FIELDS:
            return v
    # 其次看是否有"身份/所属"字段（值本身是实体名时）
    for k, v in dict_item.items():
        if isinstance(v, str) and k in IDENTITY_FIELDS:
            for name, target_id in name_to_id.items():
                if target_id != source_entity_id and name in v:
                    return "所属势力"
    # 最后看"所在地/位置"字段
    for k, v in dict_item.items():
        if isinstance(v, str) and k in LOCATION_FIELDS:
            for name, target_id in name_to_id.items():
                if target_id != source_entity_id and name in v:
                    return "所在地"
    return None


def scan_value_for_references(
    value, field_path: str, source_entity_id: str, source_type: str,
    name_to_id: dict, nodes: dict, domain_edges: list, cross_edges: list,
    source_file: str, parent_dict: dict | None = None,
) -> None:
    """递归扫描 YAML 值中的实体引用。

    parent_dict: 当 item 是 dict 中的元素时，传入整个 dict 供上下文推断。
    """
    if isinstance(value, str):
        for name, target_id in name_to_id.items():
            if target_id == source_entity_id:
                continue
            if name == value or (len(name) > 1 and name in value):
                target_type = nodes.get(target_id, {}).get("type", "unknown")

                # 确定关系类型
                relation_type = guess_relation_type(source_type, target_type, field_path)
                # 角色→势力/地点的边: 仅在结构化字段中标记为所属/所在地，
                # 叙述文本中的提及降级为"引用"
                if relation_type in ("所属势力", "所在地") and field_path:
                    # 精确判断: 在声明性字段(势力/阵营/身份)中才算所属，
                    # 角色出场统计等元数据排除
                    is_structural = (
                        field_path.endswith(".势力")
                        or field_path.endswith(".阵营")
                        or field_path.endswith(".区域")
                        or (field_path.endswith(".身份") and "角色出场统计" not in field_path)
                        or ".所属" in field_path
                        or ".势力所属" in field_path
                        or field_path == "索引信息.势力"
                    )
                    if not is_structural:
                        relation_type = "引用"

                # 如果有 parent_dict，尝试从兄弟字段中提取更精确的关系类型
                if parent_dict is not None:
                    ctx_type = _extract_relation_type_from_context(
                        parent_dict, name_to_id, source_entity_id,
                    )
                    if ctx_type:
                        relation_type = ctx_type
                # parent_dict 可能重写为"所属势力"，再次做结构检查
                if relation_type in ("所属势力", "所在地") and field_path:
                    still_structural = (
                        field_path.endswith(".势力")
                        or field_path.endswith(".阵营")
                        or field_path.endswith(".区域")
                        or (field_path.endswith(".身份") and "角色出场统计" not in field_path)
                        or ".所属" in field_path
                        or ".势力所属" in field_path
                        or field_path == "索引信息.势力"
                    )
                    if not still_structural:
                        relation_type = "引用"
                # fallback: 从 field_path 推断关系类型
                # 如 人物关系.家族后辈.0.角色 → 家族后辈
                if relation_type in ("关联", "引用") and field_path:
                    for part in field_path.split("."):
                        if part in {
                            # 家族关系
                            "先祖", "后人", "后辈", "晚辈", "族叔", "族侄",
                            "家族后辈", "家族老祖", "家族长辈", "族中后辈",
                            "兄弟", "兄弟/堂兄弟", "始祖",
                            # 宗门/职场
                            "同门", "同僚", "宗门同僚", "上司", "下属",
                            "太上长老", "太上长老/老祖", "主上", "直属上级",
                            "座下护法", "护法者", "效忠",
                            # 个人关系
                            "道侣", "弟子", "学生", "师尊", "徒弟", "好友",
                            "宿敌", "对手", "仇敌", "盟友", "最终对手", "伏击对象",
                            # 通用关系章节（精确匹配时才用）
                            "关系网络",
                        }:
                            relation_type = part
                            break

                edge = {
                    "from": source_entity_id,
                    "to": target_id,
                    "relation_type": relation_type,
                    "source": {
                        "file": source_file,
                        "field_path": field_path,
                        "raw_value": value[:120],
                    },
                    "confidence": "explicit" if value.strip() == name else "implicit",
                }
                if source_type == target_type:
                    domain_edges.append(edge)
                else:
                    cross_edges.append(edge)
                break

    elif isinstance(value, dict):
        for k, v in value.items():
            sub_path = f"{field_path}.{k}" if field_path else k
            if k in ("_meta", "_meta_", "创建时间", "更新时间"):
                continue
            # 补充：当 key 本身是实体名时（如 {吕风: 家族后辈}），
            # 从 key 提取引用，用 value 作为关系类型。
            # 只在场路径包含关系型关键词时才启用，避免误抓统计表。
            if isinstance(v, str) and not isinstance(k, int) and len(k) >= 2:
                is_rel_section = any(x in sub_path for x in (
                    '关键关系', '关系网络', '人物关系', '关键关系',
                ))
                if is_rel_section:
                    for kname, ktid in name_to_id.items():
                        if ktid == source_entity_id:
                            continue
                        if kname == k or (len(kname) > 1 and kname in k):
                            target_type = nodes.get(ktid, {}).get("type", "unknown")
                            rel_type = v if len(v) <= 20 else "关联"
                            kedges = domain_edges if source_type == target_type else cross_edges
                            kedges.append({
                                "from": source_entity_id,
                                "to": ktid,
                                "relation_type": rel_type,
                                "source": {
                                    "file": source_file,
                                    "field_path": sub_path,
                                    "raw_value": v[:120],
                                },
                                "confidence": "explicit" if kname == k else "implicit",
                            })
                            break
            # 传递当前 dict 作为 parent_dict，供子字段推断关系类型时参考兄弟字段
            scan_value_for_references(v, sub_path, source_entity_id, source_type,
                                      name_to_id, nodes, domain_edges, cross_edges,
                                      source_file, parent_dict=value)

    elif isinstance(value, list):
        for i, item in enumerate(value):
            sub_path = f"{field_path}.{i}" if field_path else str(i)
            if isinstance(item, dict):
                # dict in list: 先将整个 dict 传给每个字段的扫描，支持兄弟字段推断
                for k, v in item.items():
                    if isinstance(v, str):
                        field_sub_path = f"{sub_path}.{k}"
                        scan_value_for_references(
                            v, field_sub_path, source_entity_id, source_type,
                            name_to_id, nodes, domain_edges, cross_edges,
                            source_file, parent_dict=item,
                        )
            elif isinstance(item, str):
                scan_value_for_references(item, sub_path, source_entity_id, source_type,
                                          name_to_id, nodes, domain_edges, cross_edges,
                                          source_file)


def extract_edges_from_file(
    project_root: Path,
    rel_path_str: str,
    entity_id: str,
    entity_type: str,
    name_to_id: dict,
    nodes: dict,
) -> tuple[list[dict], list[dict]]:
    """从单个源文件提取所有关系边。

    Returns:
        (domain_edges, cross_edges)
    """
    filepath = project_root / rel_path_str
    if not filepath.is_file():
        return [], []

    data = load_yaml_safe(filepath)
    if not data:
        return [], []

    domain_edges: list[dict] = []
    cross_edges: list[dict] = []

    # 伏笔规划：只扫描当前伏笔项的子数据，避免其他项的影响
    if entity_type == "foreshadowing":
        items = data.get("伏笔规划") or []
        for item in items:
            item_name = (item.get("名称", "") or "").strip()
            expected_id = f"foreshadowing_{item_name}"
            if entity_id == expected_id:
                scan_value_for_references(
                    item, "", entity_id, entity_type,
                    name_to_id, nodes, domain_edges, cross_edges,
                    rel_path_str,
                )
                break
        return domain_edges, cross_edges

    scan_value_for_references(
        data, "", entity_id, entity_type,
        name_to_id, nodes, domain_edges, cross_edges,
        rel_path_str,
    )

    return domain_edges, cross_edges


def organize_edges_by_segment(edges: list[dict], type_group_map: dict[str, str]) -> dict:
    """将边列表按 segment 分组。

    Args:
        edges: 边列表
        type_group_map: entity_id → type_group 映射

    Returns:
        {segment_name: [edges]}
    """
    segments: dict[str, list[dict]] = {}
    for edge in edges:
        target_id = edge["to"]
        group = type_group_map.get(target_id, "other")
        if group not in segments:
            segments[group] = []
        segments[group].append(edge)
    return segments


def build_edges_files(
    project_root: Path,
    nodes: dict,
    name_to_id: dict,
) -> tuple[dict, dict]:
    """全量扫描所有实体，提取关系边。

    Returns:
        (domain_file_data, cross_file_data)
    """
    domain_segments: dict[str, list[dict]] = {s: [] for s in DOMAIN_SEGMENTS}
    cross_segments: dict[str, list[dict]] = {s: [] for s in CROSS_SEGMENTS}

    # 构建 entity_id → type_group 映射
    type_group_map: dict[str, str] = {}
    for eid, info in nodes.items():
        type_group_map[eid] = get_type_group(info.get("type", ""))

    for eid, info in nodes.items():
        file_path = info.get("file_path", "")
        entity_type = info.get("type", "")
        if not file_path or not entity_type:
            continue
        if entity_type in ("ideation", "synopsis", "narrative", "volume"):
            continue  # 这些类型暂不提取关系边（只当节点注册）

        d_edges, c_edges = extract_edges_from_file(
            project_root, file_path, eid, entity_type,
            name_to_id, nodes,
        )

        # 域内边按 segment 分组
        for edge in d_edges:
            target_group = type_group_map.get(edge["to"], "other")
            if target_group in domain_segments:
                domain_segments[target_group].append(edge)
            else:
                domain_segments.setdefault("other", []).append(edge)

        # 跨域边按 segment 分组（自动创建新 segment）
        for edge in c_edges:
            target_type = nodes.get(edge["to"], {}).get("type", "unknown")
            from_type = entity_type
            seg_key = f"{from_type}_to_{target_type}"
            if seg_key not in cross_segments:
                cross_segments[seg_key] = []
            cross_segments[seg_key].append(edge)

    domain_file_data = {
        "version": 1,
        "last_updated": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        "segments": {
            seg: {
                "count": len(edges),
                "entries": edges,
            }
            for seg, edges in domain_segments.items()
        },
    }

    cross_file_data = {
        "version": 1,
        "last_updated": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        "segments": {
            seg: {
                "count": len(edges),
                "entries": edges,
            }
            for seg, edges in cross_segments.items()
        },
    }

    return domain_file_data, cross_file_data


# ── 校验和文件（20_checksums.yaml）──────────────────────────────────────────

def build_checksums_file(project_root: Path, nodes: dict) -> dict:
    """扫描所有实体文件，计算 content_hash。"""
    checksums = {}
    for eid, info in nodes.items():
        file_path = info.get("file_path", "")
        if not file_path:
            continue
        full_path = project_root / file_path
        if full_path.is_file():
            checksums[file_path] = compute_file_hash(full_path)

    return {
        "version": 1,
        "last_updated": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        "source_checksums": checksums,
    }


# ── Meta 文件 ────────────────────────────────────────────────────────────────

def build_meta_file(graph_dir: Path, nodes_count: int, file_data_map: dict) -> dict:
    """构建 meta.yaml。"""
    graph_checksums = {}
    for fname, data in file_data_map.items():
        graph_checksums[fname] = compute_yaml_hash(data)

    return {
        "version": GRAPH_VERSION,
        "last_updated": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        "tool_version": GRAPH_VERSION,
        "summary": {
            "entities": nodes_count,
        },
        "graph_files": graph_checksums,
    }


# ── 嵌入式实体发现 ─────────────────────────────────────────────────────────

_EMBEDDED_SKIP = {
    "正道", "散修", "中立", "正派", "反派", "其它", "其他", "未知",
    # 称号/角色/修为等非组织名
    "修士", "法士", "上师", "大上师", "神师", "大修士",
    "鬼修", "魔修", "妖修", "体修", "散修",
    "器灵", "真魔",
    # 非地点
    "决战", "开幕", "结局",
}

# 元数据复合名称分隔符
_HIERARCHY_SEPS = re.compile(r"[·•‧・、，,\s/\\]+")


def _split_entity_refs(value: str) -> list[str]:
    """拆分复合势力名，如 '落云宗·柳家' → ['落云宗', '柳家']。

    所有段都保留，后续会创建父子级之间的"附属"边。
    """
    raw = value.strip().strip("\"'")
    if not raw:
        return []
    parts = _HIERARCHY_SEPS.split(raw)
    result = []
    for p in parts:
        p = p.strip()
        if 2 <= len(p) <= 8:
            result.append(p)
    return result


def _entity_id_by_name(nodes: dict, name: str) -> str | None:
    """通过 display_name 查找 entity_id。"""
    for eid, info in nodes.items():
        if info.get("display_name") == name:
            return eid
    return None


def _scan_for_embedded_refs(
    data, nodes: dict, name_set: set[str],
    hierarchy_edges: list[dict], path: str = "",
):
    """递归扫描 YAML 数据，从势力/地点字段中发现未注册的实体引用和层级关系。"""
    if isinstance(data, dict):
        # 从 {名称: X, 位置: Y} 结构创建地点层级边
        if "名称" in data and "位置" in data and isinstance(data["名称"], str) and isinstance(data["位置"], str):
            loc_name = data["名称"]
            pos_val = data["位置"]
            if loc_name in name_set:
                for loc_token in _split_entity_refs(pos_val.replace('→', ' ')):
                    loc_id = _entity_id_by_name(nodes, loc_name)
                    parent_id = _entity_id_by_name(nodes, loc_token)
                    if loc_id and parent_id and loc_id != parent_id:
                        key = (parent_id, loc_id)
                        if key not in {(e["from"], e["to"]) for e in hierarchy_edges}:
                            hierarchy_edges.append({
                                "from": parent_id,
                                "to": loc_id,
                                "relation_type": "包含",
                                "source": {"file": "", "field_path": path, "raw_value": f"{pos_val} ⊃ {loc_name}"},
                                "confidence": "explicit",
                            })
        for k, v in data.items():
            sub_path = f"{path}.{k}" if path else k
            # 从 势力 和 阵营 字段提取组织名
            if isinstance(v, str) and k in {"势力", "阵营", "faction", "affiliation", "camp"}:
                tokens = _split_entity_refs(v)
                registered: list[str] = []
                for token in tokens:
                    if token and token not in name_set and token not in _EMBEDDED_SKIP:
                        _add_embedded_stub(token, "faction", nodes, name_set)
                    if token in name_set:
                        registered.append(token)
                # 从层级名建立父子附属边: 落云宗·柳家 → 落云宗 → 附属 → 柳家
                # hierarchy_level 越深虚线越疏: 1=[10,5], 2=[8,8], 3=[5,12]
                for i in range(len(registered) - 1):
                    pid = _entity_id_by_name(nodes, registered[i])
                    cid = _entity_id_by_name(nodes, registered[i + 1])
                    if pid and cid and pid != cid:
                        hierarchy_edges.append({
                            "from": pid,
                            "to": cid,
                            "relation_type": "附属",
                            "hierarchy_level": i + 1,
                            "source": {
                                "file": "",
                                "field_path": sub_path,
                                "raw_value": v[:120],
                            },
                            "confidence": "explicit",
                        })
            elif isinstance(v, str) and k in {"所在地", "地点", "位置", "区域", "地区", "location", "area", "region"}:
                # 区域字段也可能用 → 分隔（如 "极西之地·千竹教 → 南荒"）
                for token in _split_entity_refs(v.replace('→', ' ')):
                    if token and token not in name_set and token not in _EMBEDDED_SKIP:
                        _add_embedded_stub(token, "location", nodes, name_set)
                # 从复合名中提取国/州/府: "天南越国" → "越国"
                for part in re.split(r'[·•‧・、，,\s/\\→]+', v):
                    part = part.strip()
                    if not part:
                        continue
                    # 提取以 国/州/府/郡/城 结尾的 2 字地名: "天南越国" → "越国"
                    m = re.match(r'.*?([\u4e00-\u9fff](?:国|州|府|郡|城))$', part)
                    if m:
                        sub = m.group(1)
                        if sub not in name_set and sub not in _EMBEDDED_SKIP and len(sub) <= 6:
                            _add_embedded_stub(sub, "location", nodes, name_set)

            # 在分类/体系章节中, 名称: 字段通常指向组织/族裔名
            elif isinstance(v, str) and k == "名称" and len(v) >= 2 and len(v) <= 8:
                if any(x in sub_path for x in ("功法定位", "族裔划分", "势力格局", "势力分类", "阵营")):
                    if v not in name_set and v not in _EMBEDDED_SKIP:
                        _add_embedded_stub(v, "faction", nodes, name_set)
                # 在重要地点/区域章节中, 名称: 字段指向地点名
                if any(x in sub_path for x in ("重要地点", "特殊区域", "草原地区")):
                    if v not in name_set and v not in _EMBEDDED_SKIP:
                        # 过滤明显非地点的名称
                        if not any(v.startswith(x) for x in ("混沌碑文", "补灵根", "镇封术", "土属性")):
                            _add_embedded_stub(v, "location", nodes, name_set)
            _scan_for_embedded_refs(v, nodes, name_set, hierarchy_edges, sub_path)
    elif isinstance(data, list):
        for idx, item in enumerate(data):
            sp = f"{path}[{idx}]"
            _scan_for_embedded_refs(item, nodes, name_set, hierarchy_edges, sp)


def _add_embedded_stub(name: str, entity_type: str, nodes: dict, name_set: set[str]):
    """创建嵌入式 stub 节点。"""
    safe = re.sub(r"[^\w\u4e00-\u9fff]", "_", name)
    eid = f"embedded_{entity_type}_{safe}"
    if eid in nodes:
        return
    nodes[eid] = {
        "id": eid,
        "type": entity_type,
        "display_name": name,
        "file_path": f"<embedded:{entity_type}:{name}>",
        "status": "active",
    }
    name_set.add(name)


# ── 事件发现 ──────────────────────────────────────────────────────────────

def _register_event(
    time_raw: str, event_desc: str, note: str, idx: int,
    sub_path: str, source_eid: str, source_file: str,
    nodes: dict, name_set: set[str],
    event_edges: list[dict],
    siblings: list | None = None,
) -> str | None:
    """注册单个事件节点、源实体边、实体引用边、相邻事件边。返回 event_id。"""
    if not time_raw or not event_desc:
        return None
    sort_key = 0
    m_eid = re.search(r"(\d+)", time_raw)
    if m_eid:
        sort_key = int(m_eid.group(1))
    elif "上古" in time_raw:
        sort_key = -9999
    safe_desc = re.sub(r"[^\w\u4e00-\u9fff]", "_", event_desc[:30])
    event_id = f"event_{safe_desc}_{idx}"
    if event_id in nodes:
        return None
    nodes[event_id] = {
        "id": event_id,
        "type": "event",
        "display_name": event_desc[:50],
        "file_path": f"<timeline:{source_file}>",
        "status": "active",
        "_event_time": time_raw,
        "_event_sort": sort_key,
        "_event_note": note,
    }
    name_set.add(event_desc[:50])
    # 连接事件到源实体
    if source_eid and source_eid in nodes:
        event_edges.append({
            "from": source_eid, "to": event_id,
            "relation_type": "纪年事件",
            "source": {"file": source_file, "field_path": sub_path, "raw_value": event_desc[:120]},
            "confidence": "explicit",
        })
    # 解析事件描述中的实体引用
    mentioned: set[tuple[str, str]] = set()
    for ename, eid in [(info.get("display_name", ""), eid)
                       for eid, info in nodes.items()
                       if eid != event_id and eid != source_eid]:
        if ename and len(ename) >= 2 and (ename in event_desc or event_desc.startswith(ename)):
            mentioned.add((eid, ename))
    for mid, mname in mentioned:
        event_edges.append({
            "from": event_id, "to": mid,
            "relation_type": "涉及",
            "source": {"file": source_file, "field_path": sub_path, "raw_value": event_desc[:120]},
            "confidence": "implicit",
        })
    # 相邻事件先后关系
    if siblings is not None and idx > 0 and idx - 1 < len(siblings):
        prev = siblings[idx - 1]
        prev_desc = ""
        if isinstance(prev, dict):
            prev_desc = prev.get("事件", "") or prev.get(next(iter(prev), ""), "")
        elif isinstance(prev, str):
            prev_desc = prev
        if prev_desc:
            prev_safe = re.sub(r"[^\w\u4e00-\u9fff]", "_", prev_desc[:30])
            prev_id = f"event_{prev_safe}_{idx - 1}"
            if prev_id in nodes:
                event_edges.append({
                    "from": prev_id, "to": event_id,
                    "relation_type": "后续",
                    "source": {"file": source_file, "field_path": sub_path, "raw_value": ""},
                    "confidence": "explicit",
                })
    return event_id


def _extract_events_from_data(
    data: dict, source_eid: str, source_file: str,
    nodes: dict, name_set: set[str],
    event_edges: list[dict],
    path: str = "",
):
    """递归扫描 YAML，从时间线映射/纪年对照/核心时间锚点中发现事件并注册为节点。"""
    if isinstance(data, dict):
        for k, v in data.items():
            sub_path = f"{path}.{k}" if path else k
            # 时间线映射数组：[{凡人历:时间, 事件:描述, 说明?}]
            if k in ("时间线映射",) and isinstance(v, list):
                for idx, item in enumerate(v):
                    if not isinstance(item, dict):
                        continue
                    time_raw = item.get("凡人历") or item.get("时间") or ""
                    event_desc = item.get("事件") or ""
                    note = item.get("说明") or ""
                    if not time_raw or not event_desc:
                        continue
                    _register_event(time_raw, event_desc, note, idx, sub_path,
                                    source_eid, source_file, nodes, name_set, event_edges)
            # 纪年对照字典：{凡人历元年: "事件", 凡人历997年: "事件(备注)", ...}
            if k in ("纪年对照", "核心纪年") and isinstance(v, dict):
                for idx, (tk, tv) in enumerate(v.items()):
                    if not isinstance(tv, str) or not re.search(r"[年元]", tk):
                        continue
                    note = ""
                    desc = tv
                    if "（" in tv and "）" in tv:
                        parts = tv.split("（", 1)
                        desc = parts[0]
                        note = parts[1].rstrip("）")
                    elif "(" in tv and ")" in tv:
                        parts = tv.split("(", 1)
                        desc = parts[0]
                        note = parts[1].rstrip(")")
                    _register_event(tk, desc, note, idx + 1000, sub_path,
                                    source_eid, source_file, nodes, name_set, event_edges)
            # 核心时间锚点数组：[{时间, 事件, 说明}, ...]
            if k in ("核心时间锚点",) and isinstance(v, list):
                for idx, item in enumerate(v):
                    if isinstance(item, dict):
                        time_raw = item.get("凡人历") or item.get("时间") or ""
                        event_desc = item.get("事件") or ""
                        note = item.get("说明") or ""
                        _register_event(time_raw, event_desc, note, idx, sub_path,
                                        source_eid, source_file, nodes, name_set, event_edges)
                    elif isinstance(item, str):
                        # "事件描述 (时间)" 格式
                        m = re.match(r"(.+?)[（(](.+?)[）)]\s*$", item)
                        if m:
                            _register_event(m.group(2), m.group(1), "", idx, sub_path,
                                            source_eid, source_file, nodes, name_set, event_edges)
            _extract_events_from_data(v, source_eid, source_file, nodes, name_set, event_edges, sub_path)
    elif isinstance(data, list):
        for idx, item in enumerate(data):
            sp = f"{path}[{idx}]"
            _extract_events_from_data(item, source_eid, source_file, nodes, name_set, event_edges, sp)


def discover_embedded_entities(project_root: Path, nodes: dict) -> tuple[dict, list[dict]]:
    """从所有实体源文件中发现嵌入式势力/地点/事件引用，补充 stub 节点。

    角色文件常有 势力: 落云宗·柳家 字段。
    世界观文件常有 时间线映射 数组（纪年事件）。
    此函数扫描所有源文件，自动发现并注册势力/地点/事件为轻量节点，
    并返回层级关系的"附属"边列表以及事件关系边。
    """
    extended = dict(nodes)
    name_set = {info.get("display_name", "") for info in extended.values()}
    hierarchy_edges: list[dict] = []

    for eid, info in list(nodes.items()):
        file_path = info.get("file_path", "")
        if not file_path or file_path.startswith("<embedded:") or file_path.startswith("<timeline:"):
            continue
        src_file = project_root / file_path
        if not src_file.is_file():
            continue
        data = load_yaml_safe(src_file)
        if not data:
            continue
        _scan_for_embedded_refs(data, extended, name_set, hierarchy_edges)
        # 同时提取事件
        _extract_events_from_data(data, eid, file_path, extended, name_set, hierarchy_edges)

    # 地点层级发现: 名称前缀匹配（天南 → 天南南部）
    loc_hierarchy = _discover_location_hierarchy(extended)
    hierarchy_edges.extend(loc_hierarchy)

    return extended, hierarchy_edges


def _discover_location_hierarchy(nodes: dict) -> list[dict]:
    """通过名称前缀匹配发现地点父子层级关系。

    如 天南 → 天南南部、天南东部沿海、天南大陆中部 等。
    """
    locs = [(eid, info.get("display_name", ""))
            for eid, info in nodes.items()
            if info.get("type") == "location"]
    locs.sort(key=lambda x: -len(x[1]))  # 按名称长度降序，避免短名误匹配

    edges: list[dict] = []
    seen: set[tuple[str, str]] = set()

    for child_id, child_name in locs:
        for parent_id, parent_name in locs:
            if child_id == parent_id:
                continue
            if not parent_name or not child_name:
                continue
            # 子节点以父节点名开头且有额外字符，才是真层级
            if child_name.startswith(parent_name) and len(child_name) > len(parent_name):
                # 排除 "天南越国" 这种复合地名（非层级）
                suffix = child_name[len(parent_name):]
                # 方向/区域后缀才算是层级关系
                if any(suffix.startswith(x) for x in ('大陆', '南部', '北部', '东部', '西部', '沿海', '内陆', '深处', '沙漠', '极北', '西北', '以南', '以西')):
                    key = (parent_id, child_id)
                    if key not in seen:
                        seen.add(key)
                        edges.append({
                            "from": parent_id,
                            "to": child_id,
                            "relation_type": "包含",
                            "source": {"file": "", "field_path": "", "raw_value": f"{parent_name} ⊃ {child_name}"},
                            "confidence": "explicit",
                        })
    return edges


# ── 边文件分片读写 ──────────────────────────────────────────────────────────

EDGE_DIR_MAP = {
    "domain": ("domain_edges", "domain_edges_index.yaml", "10_edges_domain.yaml"),
    "cross":  ("cross_edges",  "cross_edges_index.yaml",  "11_edges_cross.yaml"),
}


def _save_edges_files(graph_dir: Path, kind: str, file_data: dict) -> None:
    """将边数据按 segment 分片写入目录 + 索引文件。

    kind: "domain" | "cross"
    """
    subdir_name, index_name, legacy_file = EDGE_DIR_MAP[kind]
    subdir = graph_dir / subdir_name
    subdir.mkdir(parents=True, exist_ok=True)

    segments = file_data.get("segments", {})
    index_segments: dict = {}
    ts = file_data.get("last_updated", datetime.now().strftime("%Y-%m-%dT%H:%M:%S"))

    for seg_name, seg_data in segments.items():
        entries = seg_data.get("entries", [])
        count = len(entries)
        if count <= EDGE_SHARD_THRESHOLD:
            # 小 segment 内联到索引
            index_segments[seg_name] = {"count": count, "entries": entries}
        else:
            # 大 segment 写独立文件
            filename = f"{seg_name}.yaml"
            filepath = subdir / filename
            save_yaml(filepath, {
                "version": 1,
                "last_updated": ts,
                "count": count,
                "entries": entries,
            })
            index_segments[seg_name] = {"count": count, "file": filename}

    # 写入索引文件
    index_data = {
        "version": 1,
        "last_updated": ts,
        "segments": index_segments,
    }
    save_yaml(graph_dir / index_name, index_data)

    # 清理旧文件（迁移兼容）
    old_file = graph_dir / legacy_file
    if old_file.exists():
        old_file.unlink()
    old_bak = old_file.with_suffix(".yaml.bak")
    if old_bak.exists():
        old_bak.unlink()


def _load_edges_file(graph_dir: Path, kind: str) -> dict:
    """读取分片后的边数据，合并返回完整 dict。

    向后兼容：如果旧文件存在且无分片目录，读旧文件。
    """
    subdir_name, index_name, legacy_file = EDGE_DIR_MAP[kind]
    subdir = graph_dir / subdir_name
    index_path = graph_dir / index_name

    # 向后兼容：旧边文件存在且无分片目录
    if not subdir.is_dir() and (graph_dir / legacy_file).exists():
        return load_yaml_safe(graph_dir / legacy_file) or {}

    # 向后兼容：旧名文件存在且新名不存在
    if not index_path.exists():
        legacy_index_map = {
            "domain_edges_index.yaml": "10_edges_domain.yaml",
            "cross_edges_index.yaml": "11_edges_cross.yaml",
        }
        old = graph_dir / legacy_index_map.get(index_name, "")
        if old.exists():
            return load_yaml_safe(old) or {}

    if not index_path.exists():
        return {}

    index_data = load_yaml_safe(index_path) or {}
    segments: dict = {}
    for seg_name, seg_info in index_data.get("segments", {}).items():
        if "file" in seg_info:
            filepath = subdir / seg_info["file"]
            if filepath.exists():
                data = load_yaml_safe(filepath) or {}
                segments[seg_name] = {
                    "count": data.get("count", 0),
                    "entries": data.get("entries", []),
                }
            else:
                segments[seg_name] = {"count": 0, "entries": []}
        else:
            # 内联
            segments[seg_name] = {
                "count": seg_info.get("count", 0),
                "entries": seg_info.get("entries", []),
            }

    return {
        "version": index_data.get("version", 1),
        "last_updated": index_data.get("last_updated", ""),
        "segments": segments,
    }


# ── 全量构建 ─────────────────────────────────────────────────────────────────

def build(project_root: Path) -> None:
    """全量构建项目图谱。"""
    graph_dir = get_graph_dir(project_root)
    graph_dir.mkdir(parents=True, exist_ok=True)
    _migrate_legacy_filenames(graph_dir)

    # Step 1: 收集节点
    nodes = collect_all_nodes(project_root)

    # Step 1.5: 从角色等源文件中发现嵌入式势力/地点引用，补充 stub 节点
    nodes, hierarchy_edges = discover_embedded_entities(project_root, nodes)

    nodes_file_data = build_nodes_file(project_root, nodes)
    save_yaml(graph_dir / FILE_NODES, nodes_file_data)

    # Step 2: 建立名称索引
    name_to_id = build_name_to_id_index(nodes)

    # Step 3: 提取边
    domain_file_data, cross_file_data = build_edges_files(
        project_root, nodes, name_to_id,
    )
    # 合并 hierarchy_edges 到对应 segment（按关系类型分流）
    if hierarchy_edges:
        seg_map = {
            "附属": "faction_hierarchy",
            "包含": "location_hierarchy",
            "纪年事件": "worldbuilding_to_event",
            "后续": "event_to_event",
        }
        seen_h: set[tuple] = set()
        for he in hierarchy_edges:
            rt = he.get("relation_type", "")
            target_type = nodes.get(he["to"], {}).get("type", "unknown")
            # 涉及边按目标类型分流
            if rt == "涉及":
                seg_key = f"event_to_{target_type}"
            else:
                seg_key = seg_map.get(rt, "other_hierarchy")
            if seg_key not in cross_file_data.get("segments", {}):
                cross_file_data.setdefault("segments", {})[seg_key] = {
                    "count": 0, "entries": [],
                }
            seg = cross_file_data["segments"][seg_key]
            dedup_key = (he["from"], he["to"], rt)
            if dedup_key not in seen_h:
                seen_h.add(dedup_key)
                seg["entries"].append(he)
        for seg in cross_file_data.get("segments", {}).values():
            if isinstance(seg, dict) and "entries" in seg:
                seg["count"] = len(seg["entries"])
    # 保存边文件（分片到 domain_edges/ + cross_edges/）
    _save_edges_files(graph_dir, "domain", domain_file_data)
    _save_edges_files(graph_dir, "cross", cross_file_data)

    # Step 4: 计算校验和
    checksums_file_data = build_checksums_file(project_root, nodes)
    save_yaml(graph_dir / FILE_CHECKSUMS, checksums_file_data)

    # Step 5: 初始化偏差状态文件（空）
    deviations_file_data = {
        "version": 1,
        "last_updated": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        "summary": {"total_tracked": 0, "resolved": 0, "pending": 0, "user_retained": 0},
        "items": [],
    }
    save_yaml(graph_dir / FILE_DEVIATIONS, deviations_file_data)

    # Step 6: 生成 meta.yaml
    file_data_map = {
        FILE_NODES: nodes_file_data,
        DOMAIN_EDGES_INDEX: domain_file_data,
        CROSS_EDGES_INDEX: cross_file_data,
        FILE_CHECKSUMS: checksums_file_data,
        FILE_DEVIATIONS: deviations_file_data,
    }
    meta_file_data = build_meta_file(graph_dir, len(nodes), file_data_map)
    save_yaml(graph_dir / FILE_META, meta_file_data)

    print(f"✅ 项目图谱构建完成: {graph_dir}")
    print(f"   实体: {len(nodes)}, 源文件: {len(checksums_file_data.get('source_checksums', {}))}")


# ── 增量更新 ─────────────────────────────────────────────────────────────────

def incremental_update(project_root: Path, scope: str = "all") -> list[str]:
    """增量更新项目图谱，只重新扫描有变动的文件。

    Args:
        project_root: 项目根目录
        scope: 更新范围："all"=全部, "characters", "worldbuilding" 等

    Returns:
        有变动的文件路径列表
    """
    graph_dir = get_graph_dir(project_root)

    # 如果 graph 不存在，回退到全量构建
    if not (graph_dir / FILE_META).is_file():
        build(project_root)
        return []

    # 读取当前校验和
    chk_path = graph_dir / FILE_CHECKSUMS
    if not chk_path.exists():
        chk_path = graph_dir / _LEGACY_CHECKSUMS
    checksums_data = load_yaml_safe(chk_path)
    if not checksums_data:
        build(project_root)
        return []

    old_checksums = checksums_data.get("source_checksums", {})
    nodes_data = load_yaml_safe(graph_dir / FILE_NODES)
    nodes = nodes_data.get("nodes", {}) if nodes_data else {}

    # 确定要检查的文件范围
    if scope == "all":
        check_files = set(old_checksums.keys())
        # 也检查是否有新文件
        for subdir, file_type, pattern in SCAN_SCOPE:
            target_dir = project_root / subdir
            if not target_dir.is_dir():
                continue
            for f in sorted(target_dir.rglob(pattern)):
                if ".bak" in f.suffixes or ".summary" in f.parts:
                    continue
                rel = f.relative_to(project_root).as_posix()
                check_files.add(rel)
    else:
        # 按类型范围扫描
        check_files = set()
        for subdir, file_type, pattern in SCAN_SCOPE:
            if scope != "all" and file_type != scope and subdir != scope:
                continue
            target_dir = project_root / subdir
            if not target_dir.is_dir():
                continue
            for f in sorted(target_dir.rglob(pattern)):
                if ".bak" in f.suffixes or ".summary" in f.parts:
                    continue
                rel = f.relative_to(project_root).as_posix()
                check_files.add(rel)

    # 检测变更
    changed_files: list[str] = []
    for rel_path in sorted(check_files):
        full_path = project_root / rel_path
        if not full_path.is_file():
            if rel_path in old_checksums:
                changed_files.append(rel_path)
            continue

        new_hash = compute_file_hash(full_path)
        old_hash = old_checksums.get(rel_path, "")
        if new_hash != old_hash:
            changed_files.append(rel_path)

    if not changed_files:
        # 没有变更，更新时间戳即可
        meta_path = graph_dir / FILE_META
        meta_data = load_yaml_safe(meta_path)
        if meta_data:
            meta_data["last_updated"] = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
            save_yaml(meta_path, meta_data)
        return []

    # ── 有变更：重新注册受影响的节点 ──
    name_to_id = build_name_to_id_index(nodes)
    domain_data = _load_edges_file(graph_dir, "domain") or {"segments": {}}
    cross_data = _load_edges_file(graph_dir, "cross") or {"segments": {}}

    affected_entity_ids: set[str] = set()

    for rel_path in changed_files:
        # 重新注册节点
        full_path = project_root / rel_path
        if not full_path.is_file():
            # 文件被删除，移除对应节点
            for eid, info in list(nodes.items()):
                if info.get("file_path") == rel_path:
                    del nodes[eid]
                    affected_entity_ids.add(eid)
            continue

        # 推断文件类型
        file_type = "unknown"
        for subdir, ft, _ in SCAN_SCOPE:
            if rel_path.startswith(subdir):
                file_type = ft
                break

        new_nodes = scan_file_for_nodes(project_root, rel_path, file_type)
        for entry in new_nodes:
            # 移除该文件对应的旧节点
            old_eids = [eid for eid, info in nodes.items() if info.get("file_path") == rel_path]
            for oeid in old_eids:
                if oeid != entry["id"]:
                    del nodes[oeid]
                    affected_entity_ids.add(oeid)
            nodes[entry["id"]] = entry
            affected_entity_ids.add(entry["id"])

    # ── 重新提取受影响的边 ──
    # 删除受影响实体的旧边
    for segment in DOMAIN_SEGMENTS:
        seg_data = domain_data.get("segments", {}).get(segment, {})
        seg_data["entries"] = [
            e for e in seg_data.get("entries", [])
            if e.get("from") not in affected_entity_ids
        ]
        seg_data["count"] = len(seg_data["entries"])

    for segment in CROSS_SEGMENTS:
        seg_data = cross_data.get("segments", {}).get(segment, {})
        seg_data["entries"] = [
            e for e in seg_data.get("entries", [])
            if e.get("from") not in affected_entity_ids
        ]
        seg_data["count"] = len(seg_data["entries"])
    # 也处理 uncategorized
    uncat = cross_data.get("segments", {}).get("uncategorized", {})
    uncat["entries"] = [
        e for e in uncat.get("entries", [])
        if e.get("from") not in affected_entity_ids
    ]
    uncat["count"] = len(uncat["entries"])

    # 为新边重新提取
    name_to_id = build_name_to_id_index(nodes)
    type_group_map: dict[str, str] = {}
    for eid, info in nodes.items():
        type_group_map[eid] = get_type_group(info.get("type", ""))

    for eid in affected_entity_ids:
        info = nodes.get(eid, {})
        file_path = info.get("file_path", "")
        entity_type = info.get("type", "")
        if not file_path or not entity_type:
            continue
        if entity_type in ("ideation", "synopsis", "narrative", "volume"):
            continue

        d_edges, c_edges = extract_edges_from_file(
            project_root, file_path, eid, entity_type,
            name_to_id, nodes,
        )

        for edge in d_edges:
            target_group = type_group_map.get(edge["to"], "other")
            if target_group in domain_data.setdefault("segments", {}):
                domain_data["segments"][target_group].setdefault("entries", []).append(edge)
            else:
                domain_data["segments"].setdefault("other", {"entries": []})["entries"].append(edge)

        for edge in c_edges:
            target_type = nodes.get(edge["to"], {}).get("type", "unknown")
            from_type = entity_type
            seg_key = f"{from_type}_to_{target_type}"
            cross_data.setdefault("segments", {}).setdefault(seg_key, {"entries": []})["entries"].append(edge)

    # 更新计数
    for segment in DOMAIN_SEGMENTS:
        seg = domain_data.get("segments", {}).get(segment, {})
        seg["count"] = len(seg.get("entries", []))
    for segment in CROSS_SEGMENTS:
        seg = cross_data.get("segments", {}).get(segment, {})
        seg["count"] = len(seg.get("entries", []))
    uncat = cross_data.get("segments", {}).get("uncategorized", {})
    uncat["count"] = len(uncat.get("entries", []))

    # 写入更新（分片保存边数据）
    domain_data["last_updated"] = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    cross_data["last_updated"] = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    _save_edges_files(graph_dir, "domain", domain_data)
    _save_edges_files(graph_dir, "cross", cross_data)

    # 更新节点文件
    nodes_data["nodes"] = nodes
    nodes_data["entries"] = len(nodes)
    nodes_data["last_updated"] = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    save_yaml(graph_dir / FILE_NODES, nodes_data)

    # 更新校验和
    for rel_path in changed_files:
        full_path = project_root / rel_path
        if full_path.is_file():
            old_checksums[rel_path] = compute_file_hash(full_path)
        elif rel_path in old_checksums:
            del old_checksums[rel_path]

    checksums_data["source_checksums"] = old_checksums
    checksums_data["last_updated"] = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    save_yaml(graph_dir / FILE_CHECKSUMS, checksums_data)

    # 更新 meta.yaml
    file_data_map = {
        FILE_NODES: nodes_data,
        DOMAIN_EDGES_INDEX: domain_data,
        CROSS_EDGES_INDEX: cross_data,
        FILE_CHECKSUMS: checksums_data,
    }
    dev_path = graph_dir / FILE_DEVIATIONS
    if dev_path.is_file():
        file_data_map[FILE_DEVIATIONS] = load_yaml_safe(dev_path) or {}

    meta_data = build_meta_file(graph_dir, len(nodes), file_data_map)
    save_yaml(graph_dir / FILE_META, meta_data)

    print(f"✅ 增量更新完成")
    print(f"   变更文件: {len(changed_files)}")
    print(f"   受影响实体: {len(affected_entity_ids)}")

    return changed_files


# ── 实体变动检测 ─────────────────────────────────────────────────────────────

def detect_changed_entities(project_root: Path) -> list[dict]:
    """检测哪些源文件发生了变动（供 full-diagnose 使用）。

    Returns:
        [{file_path, entity_id, status, old_hash, new_hash}, ...]
    """
    graph_dir = get_graph_dir(project_root)
    chk_path = graph_dir / FILE_CHECKSUMS
    if not chk_path.exists():
        chk_path = graph_dir / _LEGACY_CHECKSUMS
    if not chk_path.exists():
        return []

    checksums_data = load_yaml_safe(chk_path)
    if not checksums_data:
        return []

    old_checksums = checksums_data.get("source_checksums", {})
    nodes_data = load_yaml_safe(graph_dir / FILE_NODES)
    nodes = nodes_data.get("nodes", {}) if nodes_data else {}

    # 反向映射：file_path → entity_id
    path_to_entity: dict[str, str] = {}
    for eid, info in nodes.items():
        fp = info.get("file_path", "")
        if fp:
            path_to_entity[fp] = eid

    changed: list[dict] = []

    for file_path, old_hash in old_checksums.items():
        full_path = project_root / file_path
        entity_id = path_to_entity.get(file_path, "")

        if not full_path.is_file():
            changed.append({
                "file_path": file_path,
                "entity_id": entity_id,
                "status": "deleted",
                "old_hash": old_hash,
                "new_hash": "",
            })
            continue

        new_hash = compute_file_hash(full_path)
        if new_hash != old_hash:
            changed.append({
                "file_path": file_path,
                "entity_id": entity_id,
                "status": "modified",
                "old_hash": old_hash,
                "new_hash": new_hash,
            })

    # 检查新文件（在 nodes 中但不在 checksums 中）
    for file_path, entity_id in path_to_entity.items():
        if file_path not in old_checksums:
            full_path = project_root / file_path
            if full_path.is_file():
                changed.append({
                    "file_path": file_path,
                    "entity_id": entity_id,
                    "status": "new",
                    "old_hash": "",
                    "new_hash": compute_file_hash(full_path),
                })

    return changed


# ── 查询函数 ─────────────────────────────────────────────────────────────────

def load_graph(graph_dir: Path) -> tuple[dict, dict, dict, dict]:
    """加载 graph 的核心数据。

    Returns:
        (nodes, domain_edges, cross_edges, checksums)
    """
    nodes_path = graph_dir / FILE_NODES
    if not nodes_path.exists():
        nodes_path = graph_dir / _LEGACY_NODES  # 向后兼容
    nodes = load_yaml_safe(nodes_path) or {"nodes": {}}
    domain = _load_edges_file(graph_dir, "domain") or {"segments": {}}
    cross = _load_edges_file(graph_dir, "cross") or {"segments": {}}
    chk_path = graph_dir / FILE_CHECKSUMS
    if not chk_path.exists():
        chk_path = graph_dir / _LEGACY_CHECKSUMS
    checksums = load_yaml_safe(chk_path) or {}
    return nodes, domain, cross, checksums


def query_entity(graph_dir: Path, entity_id: str) -> dict | None:
    """查询指定实体。"""
    nodes, _, _, _ = load_graph(graph_dir)
    return nodes.get("nodes", {}).get(entity_id)


def query_edges_from(graph_dir: Path, entity_id: str) -> list[dict]:
    """查询指定实体的所有出边。"""
    _, domain, cross, _ = load_graph(graph_dir)
    results = []

    for seg in domain.get("segments", {}).values():
        for edge in seg.get("entries", []):
            if edge.get("from") == entity_id:
                results.append(edge)

    for seg in cross.get("segments", {}).values():
        for edge in seg.get("entries", []):
            if edge.get("from") == entity_id:
                results.append(edge)

    return results


def query_edges_to(graph_dir: Path, entity_id: str) -> list[dict]:
    """查询指定实体的所有入边。"""
    _, domain, cross, _ = load_graph(graph_dir)
    results = []

    for seg in domain.get("segments", {}).values():
        for edge in seg.get("entries", []):
            if edge.get("to") == entity_id:
                results.append(edge)

    for seg in cross.get("segments", {}).values():
        for edge in seg.get("entries", []):
            if edge.get("to") == entity_id:
                results.append(edge)

    return results


def get_all_entity_ids(graph_dir: Path) -> list[str]:
    """获取所有实体 ID。"""
    nodes, _, _, _ = load_graph(graph_dir)
    return list(nodes.get("nodes", {}).keys())


# ── CLI ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="project_graph.py — 项目关系图谱管理",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用示例:
  python project_graph.py --project-root novels/项目名 build
  python project_graph.py --project-root novels/项目名 incremental-update
  python project_graph.py --project-root novels/项目名 incremental-update --scope characters
  python project_graph.py --project-root novels/项目名 detect-changes
  python project_graph.py --project-root novels/项目名 query-entity --entity-id characters_林昭
  python project_graph.py --project-root novels/项目名 query-edges-from --entity-id characters_林昭
  python project_graph.py --project-root novels/项目名 query-edges-to --entity-id characters_林昭
        """,
    )
    parser.add_argument("--project-root", "-p", required=True, help="项目根目录")
    parser.add_argument("command", choices=[
        "build", "incremental-update", "detect-changes",
        "query-entity", "query-edges-from", "query-edges-to",
    ], help="操作命令")
    parser.add_argument("--scope", default="all", help="增量更新的范围（all/characters/worldbuilding 等）")
    parser.add_argument("--entity-id", help="实体 ID（用于查询操作）")
    args = parser.parse_args()

    project_root = Path(args.project_root).resolve()
    if not project_root.is_dir():
        # 尝试查找项目根
        found = find_project_root(project_root)
        if found:
            project_root = found
        else:
            print(f"错误: 项目根目录不存在: {project_root}", file=sys.stderr)
            sys.exit(1)

    graph_dir = get_graph_dir(project_root)

    if args.command == "build":
        build(project_root)

    elif args.command == "incremental-update":
        incremental_update(project_root, scope=args.scope)

    elif args.command == "detect-changes":
        if not graph_dir.is_dir():
            print("项目图谱尚未构建，请先运行 build", file=sys.stderr)
            sys.exit(1)
        changed = detect_changed_entities(project_root)
        result = {
            "total": len(changed),
            "changed": changed,
        }
        print(yaml.dump(result, allow_unicode=True, default_flow_style=False, sort_keys=False))

    elif args.command == "query-entity":
        if not args.entity_id:
            print("错误: --entity-id 是必填参数", file=sys.stderr)
            sys.exit(1)
        entity = query_entity(graph_dir, args.entity_id)
        if entity:
            print(yaml.dump(entity, allow_unicode=True, default_flow_style=False, sort_keys=False))
        else:
            print(f"未找到实体: {args.entity_id}")

    elif args.command == "query-edges-from":
        if not args.entity_id:
            print("错误: --entity-id 是必填参数", file=sys.stderr)
            sys.exit(1)
        edges = query_edges_from(graph_dir, args.entity_id)
        result = {"count": len(edges), "edges": edges}
        print(yaml.dump(result, allow_unicode=True, default_flow_style=False, sort_keys=False))

    elif args.command == "query-edges-to":
        if not args.entity_id:
            print("错误: --entity-id 是必填参数", file=sys.stderr)
            sys.exit(1)
        edges = query_edges_to(graph_dir, args.entity_id)
        result = {"count": len(edges), "edges": edges}
        print(yaml.dump(result, allow_unicode=True, default_flow_style=False, sort_keys=False))


if __name__ == "__main__":
    main()
