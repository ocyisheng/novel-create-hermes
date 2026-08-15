"""
关系迁移工具（P1/P2 数据迁移骨架）。

用途：对项目 graph/edges.jsonl（及 nodes.jsonl）执行批量关系变换，
支持 dry-run 试运行、JSON 报告输出、快照回滚。

用法:
    python migrate_relations.py --project <项目根路径> [--dry-run] [--report <路径>]
    python migrate_relations.py --project <项目根路径> --rollback <快照路径或ID>

变换管线:
    - metadata_to_payload : metadata → payload 字段迁移
    - allied_with         : allied_with → relates_to 类型迁移
    - temporal_prefix     : xx_ → te_ 时间事件 ID 前缀迁移
    - structure_archive   : STRUCTURE 类型节点归档
    - inverse_dedup_merge : 逆边去重合并（对称对 / 逆类型对 → 单边）
    - plans_normalize     : PLANS/BELONGS_TO/REFERENCES 混用边语义归一
    - references_archive  : REFERENCES 边按 payload.type 分桶归档

变换函数契约:
    每个变换函数接受 edges: List[dict]（edges.jsonl 每行一个 dict），
    返回 (transformed_edges, change_log)。change_log 为变更日志列表，
    每条形如 {"edge_id": str, "transformation": str, "action": str, "detail": str}。
    transform_temporal_prefix 与 archive_structure_type 额外接受 nodes，
    返回 (edges, nodes, change_log)。

安全保证:
    - 执行模式先创建快照（graph/snapshots/migrate_*.json），可用 --rollback 恢复
    - dry-run 模式不写任何文件
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Dict, List, Optional, Set, Tuple


# ── 路径辅助 ──────────────────────────────────────────────────────────────

def _edges_path(project_root: str) -> Path:
    return Path(project_root) / "graph" / "edges.jsonl"


def _nodes_path(project_root: str) -> Path:
    return Path(project_root) / "graph" / "nodes.jsonl"


def _snapshots_dir(project_root: str) -> Path:
    return Path(project_root) / "graph" / "snapshots"


# ── 原子写入 ──────────────────────────────────────────────────────────────

def _atomic_write(path: Path, content: str) -> None:
    """原子写入：唯一 tmp 名 + fsync + rename，失败时清理 tmp。"""
    tmp = path.with_name(f"{path.stem}.{os.getpid()}.{uuid.uuid4().hex[:6]}.tmp")
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        tmp.replace(path)
    except Exception:
        if tmp.exists():
            tmp.unlink(missing_ok=True)
        raise


# ── 加载 / 保存 ───────────────────────────────────────────────────────────

def _load_jsonl(path: Path) -> List[dict]:
    """逐行加载 JSONL。空行跳过；解析失败抛 ValueError（迁移会重写文件，
    静默跳过会导致数据丢失）。utf-8-sig 容忍 Windows 工具写入的首行 BOM。"""
    items: List[dict] = []
    for lineno, line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), start=1):
        line = line.strip()
        if not line:
            continue
        try:
            items.append(json.loads(line))
        except json.JSONDecodeError as e:
            raise ValueError(f"{path} 第 {lineno} 行 JSON 解析失败: {e}") from e
    return items


def _save_jsonl(path: Path, items: List[dict]) -> None:
    """将列表写回 JSONL（原子写入）。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    content = "".join(json.dumps(item, ensure_ascii=False) + "\n" for item in items)
    _atomic_write(path, content)


def load_edges(project_root: str) -> List[dict]:
    """从 {project_root}/graph/edges.jsonl 加载全部边。文件不存在时返回 []。"""
    path = _edges_path(project_root)
    return _load_jsonl(path) if path.exists() else []


def load_nodes(project_root: str) -> List[dict]:
    """从 {project_root}/graph/nodes.jsonl 加载全部节点。文件不存在时返回 []。"""
    path = _nodes_path(project_root)
    return _load_jsonl(path) if path.exists() else []


def save_edges(project_root: str, edges: List[dict]) -> None:
    """将边列表写回 {project_root}/graph/edges.jsonl（原子写入）。"""
    _save_jsonl(_edges_path(project_root), edges)


def save_nodes(project_root: str, nodes: List[dict]) -> None:
    """将节点列表写回 {project_root}/graph/nodes.jsonl（原子写入）。"""
    _save_jsonl(_nodes_path(project_root), nodes)


# ── 快照 / 回滚 ───────────────────────────────────────────────────────────

def create_snapshot(project_root: str) -> str:
    """创建 edges.jsonl + nodes.jsonl 快照，返回快照文件路径。

    快照写入 {project_root}/graph/snapshots/migrate_<时间戳>_<短码>.json，
    包含 edges 与 nodes 完整列表，供 --rollback 恢复。
    """
    edges = load_edges(project_root)
    nodes = load_nodes(project_root)
    snapshots_dir = _snapshots_dir(project_root)
    snapshots_dir.mkdir(parents=True, exist_ok=True)
    snapshot_id = (
        f"migrate_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
        f"_{uuid.uuid4().hex[:6]}"
    )
    snapshot_path = snapshots_dir / f"{snapshot_id}.json"
    data = {
        "snapshot_id": snapshot_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "project_root": str(Path(project_root)),
        "edges": edges,
        "nodes": nodes,
    }
    _atomic_write(snapshot_path, json.dumps(data, ensure_ascii=False, indent=2))
    return str(snapshot_path)


def rollback(project_root: str, snapshot: str) -> dict:
    """从快照恢复 edges.jsonl（及 nodes.jsonl，若快照包含）。

    snapshot 参数可为快照文件路径或快照 ID（自动在 graph/snapshots/ 下查找）。
    """
    snapshot_path = _resolve_snapshot_path(project_root, snapshot)
    if snapshot_path is None:
        return {"status": "error", "error": f"快照不存在: {snapshot}"}
    with open(snapshot_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    edges = data.get("edges", [])
    nodes = data.get("nodes", [])
    save_edges(project_root, edges)
    if nodes:
        save_nodes(project_root, nodes)
    return {
        "status": "ok",
        "mode": "rollback",
        "project": str(Path(project_root)),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "snapshot": str(snapshot_path),
        "edges_restored": len(edges),
        "nodes_restored": len(nodes),
    }


def _resolve_snapshot_path(project_root: str, snapshot: str) -> Optional[Path]:
    """解析快照参数：直接文件路径，或快照 ID（在 graph/snapshots/ 下查找）。"""
    p = Path(snapshot)
    if p.is_file():
        return p
    candidate = _snapshots_dir(project_root) / f"{snapshot}.json"
    return candidate if candidate.is_file() else None


# ── 变换函数（骨架，P1 填充） ─────────────────────────────────────────────

def transform_metadata_to_payload(edges: List[dict]) -> Tuple[List[dict], List[dict]]:
    """metadata → payload 字段迁移。

    将边 dict 中的 metadata 字段合并/重命名为 payload：
    - metadata 为非空 dict 时：
      - payload 不存在 / 为 None / 为空 dict：payload = metadata（复制）
      - payload 为非空 dict：metadata 合并入 payload（payload 键优先）
      - 删除 metadata 字段
    - metadata 为 None / 空 dict / 非 dict：删除 metadata 字段，跳过迁移
    - 无 metadata 字段：原样保留，不产生变更日志

    不修改输入列表；变更的边以浅拷贝返回。

    Returns:
        (transformed_edges, change_log)
        change_log 每条形如 {"edge_id", "transformation", "action", "detail"}，
        action 为 "merged"（已迁移）或 "skipped"（metadata 为空，跳过）。
    """
    transformed: List[dict] = []
    log: List[dict] = []
    for edge in edges:
        if "metadata" not in edge:
            transformed.append(edge)
            continue
        edge_id = edge.get("id", "")
        metadata = edge["metadata"]
        new_edge = dict(edge)
        new_edge.pop("metadata", None)
        if isinstance(metadata, dict) and metadata:
            payload = new_edge.get("payload")
            if isinstance(payload, dict) and payload:
                merged = dict(metadata)
                merged.update(payload)  # payload 键优先
                new_edge["payload"] = merged
                detail = "metadata 合并入 payload（payload 键优先）"
            else:
                new_edge["payload"] = dict(metadata)
                detail = "metadata 复制为 payload（原 payload 为空）"
            log.append({
                "edge_id": edge_id,
                "transformation": "metadata_to_payload",
                "action": "merged",
                "detail": detail,
            })
        else:
            log.append({
                "edge_id": edge_id,
                "transformation": "metadata_to_payload",
                "action": "skipped",
                "detail": "metadata 为空，无需迁移",
            })
        transformed.append(new_edge)
    return transformed, log


def transform_allied_with(edges: List[dict]) -> Tuple[List[dict], List[dict]]:
    """allied_with → relates_to 类型迁移。

    将 relation_type == "allied_with" 的边改写为 "relates_to"：
    - relation_type == "allied_with"：改写为 "relates_to"，其余字段（含 label）原样保留
    - relation_type 存在但 != "allied_with"：跳过，原样保留
    - relation_type 为 None 或缺失：跳过，原样保留
    每条边都产生一条变更日志（action 为 "rewritten" 或 "skipped"）。

    不修改输入列表；变更的边以浅拷贝返回。

    Returns:
        (transformed_edges, change_log)
        change_log 每条形如 {"edge_id", "transformation", "action", "detail"}，
        transformation 为 "allied_with_to_relates_to"。
    """
    transformed: List[dict] = []
    log: List[dict] = []
    for edge in edges:
        edge_id = edge.get("id", "")
        rel_type = edge.get("relation_type")
        if rel_type == "allied_with":
            new_edge = dict(edge)
            new_edge["relation_type"] = "relates_to"
            transformed.append(new_edge)
            log.append({
                "edge_id": edge_id,
                "transformation": "allied_with_to_relates_to",
                "action": "rewritten",
                "detail": "relation_type 由 allied_with 改写为 relates_to",
            })
        elif rel_type is None:
            transformed.append(edge)
            log.append({
                "edge_id": edge_id,
                "transformation": "allied_with_to_relates_to",
                "action": "skipped",
                "detail": "relation_type 缺失或为 None，无需迁移",
            })
        else:
            transformed.append(edge)
            log.append({
                "edge_id": edge_id,
                "transformation": "allied_with_to_relates_to",
                "action": "skipped",
                "detail": f"relation_type 为 {rel_type}，非 allied_with，无需迁移",
            })
    return transformed, log


def transform_temporal_prefix(
    edges: List[dict], nodes: List[dict]
) -> Tuple[List[dict], List[dict], List[dict]]:
    """时间事件 ID 前缀迁移（xx_ → te_）。

    将节点 ID 中遗留的 xx_ 前缀改写为 te_，并同步更新边中
    source_id / target_id 对旧 ID 的引用：
    - 节点 id 以 "xx_" 开头：改写为 "te_" + id[3:]，日志 rewritten
    - 节点 id 以 "te_" 开头：跳过，日志 skipped
    - 其他节点：跳过，日志 skipped
    - 边 source_id / target_id 命中旧 ID 映射：改写为新 ID，日志 rewritten
    - 边未命中任何旧 ID：跳过，日志 skipped

    不修改输入列表；变更的节点/边以浅拷贝返回。

    Returns:
        (transformed_edges, transformed_nodes, change_log)
        change_log 每条形如 {"old_id", "new_id", "transformation",
        "action", "detail"}，transformation 为 "temporal_prefix"。
    """
    # 1. 构建 old_id → new_id 映射，并改写节点
    id_map: Dict[str, str] = {}
    transformed_nodes: List[dict] = []
    log: List[dict] = []
    for node in nodes:
        node_id = node.get("id", "")
        if node_id.startswith("xx_"):
            new_id = "te_" + node_id[3:]
            id_map[node_id] = new_id
            new_node = dict(node)
            new_node["id"] = new_id
            transformed_nodes.append(new_node)
            log.append({
                "old_id": node_id,
                "new_id": new_id,
                "transformation": "temporal_prefix",
                "action": "rewritten",
                "detail": f"节点 ID 由 {node_id} 改写为 {new_id}",
            })
        else:
            transformed_nodes.append(node)
            if node_id.startswith("te_"):
                detail = "节点 ID 已是 te_ 前缀，无需迁移"
            else:
                detail = "非时间事件节点，无需迁移"
            log.append({
                "old_id": node_id,
                "new_id": node_id,
                "transformation": "temporal_prefix",
                "action": "skipped",
                "detail": detail,
            })

    # 2. 改写边中引用旧 ID 的 source_id / target_id
    transformed_edges: List[dict] = []
    for edge in edges:
        edge_id = edge.get("id", "")
        source_id = edge.get("source_id", "")
        target_id = edge.get("target_id", "")
        new_source = id_map.get(source_id, source_id)
        new_target = id_map.get(target_id, target_id)
        if new_source != source_id or new_target != target_id:
            new_edge = dict(edge)
            if new_source != source_id:
                new_edge["source_id"] = new_source
            if new_target != target_id:
                new_edge["target_id"] = new_target
            transformed_edges.append(new_edge)
            if new_source != source_id:
                log.append({
                    "old_id": source_id,
                    "new_id": new_source,
                    "transformation": "temporal_prefix",
                    "action": "rewritten",
                    "detail": f"边 {edge_id} 的 source_id 由 {source_id} 改写为 {new_source}",
                })
            if new_target != target_id:
                log.append({
                    "old_id": target_id,
                    "new_id": new_target,
                    "transformation": "temporal_prefix",
                    "action": "rewritten",
                    "detail": f"边 {edge_id} 的 target_id 由 {target_id} 改写为 {new_target}",
                })
        else:
            transformed_edges.append(edge)
            log.append({
                "old_id": edge_id,
                "new_id": edge_id,
                "transformation": "temporal_prefix",
                "action": "skipped",
                "detail": "边未引用旧 xx_ 前缀 ID，无需迁移",
            })

    return transformed_edges, transformed_nodes, log


def archive_structure_type(
    edges: List[dict], nodes: List[dict]
) -> Tuple[List[dict], List[dict], List[dict]]:
    """STRUCTURE 类型节点归档。

    将 type == "structure" 的节点标记 status = "archived"：
    - 节点 type == "structure" 且 status != "archived"：status 改写为 "archived"，
      日志 archived
    - 节点 type == "structure" 且 status == "archived"：跳过，日志 skipped
      （不重复归档）
    - 节点 type != "structure"（含缺失/None）：跳过，日志 skipped
    - 边 source_id / target_id 引用本次归档的节点：保留边（不删除，
      指向已归档单元的边是允许的），日志 skipped（引用已归档节点）
    - 边未引用任何本次归档的节点：跳过，不产生日志

    不修改输入列表；变更的节点以浅拷贝返回。

    Returns:
        (transformed_edges, transformed_nodes, change_log)
        change_log 每条形如 {"node_id"/"edge_id", "transformation",
        "action", "detail"}，transformation 为 "archive_structure"。
    """
    # 1. 归档 structure 节点，收集本次归档的节点 ID
    archived_ids: Set[str] = set()
    transformed_nodes: List[dict] = []
    log: List[dict] = []
    for node in nodes:
        node_id = node.get("id", "")
        if node.get("type") == "structure":
            if node.get("status") == "archived":
                transformed_nodes.append(node)
                log.append({
                    "node_id": node_id,
                    "transformation": "archive_structure",
                    "action": "skipped",
                    "detail": "节点已是 archived 状态，无需重复归档",
                })
            else:
                new_node = dict(node)
                new_node["status"] = "archived"
                archived_ids.add(node_id)
                transformed_nodes.append(new_node)
                log.append({
                    "node_id": node_id,
                    "transformation": "archive_structure",
                    "action": "archived",
                    "detail": "type 为 structure，status 改写为 archived",
                })
        else:
            transformed_nodes.append(node)
            log.append({
                "node_id": node_id,
                "transformation": "archive_structure",
                "action": "skipped",
                "detail": "type 非 structure，无需归档",
            })

    # 2. 边引用检查：引用本次归档节点的边保留并记录
    transformed_edges: List[dict] = []
    for edge in edges:
        edge_id = edge.get("id", "")
        source_id = edge.get("source_id", "")
        target_id = edge.get("target_id", "")
        refs = []
        if source_id in archived_ids:
            refs.append("source_id")
        if target_id in archived_ids:
            refs.append("target_id")
        if refs:
            transformed_edges.append(edge)
            log.append({
                "edge_id": edge_id,
                "transformation": "archive_structure",
                "action": "skipped",
                "detail": f"边 {edge_id} 的 {'/'.join(refs)} 引用已归档节点，保留边",
            })
        else:
            transformed_edges.append(edge)
    return transformed_edges, transformed_nodes, log


# ── 逆关系类型映射（来源：unit_types/relation_types.yaml 的 inverse 字段） ──

# 对称类型（inverse == 自身）与配对类型（互为逆）的完整映射。
# 未知类型不在表中 → _inverse_type 返回 None，不参与合并（保守）。
_INVERSE_TYPE_MAP: Dict[str, str] = {
    # 对称类型：逆 = 自身
    "causes": "causes",
    "precedes": "precedes",
    "contradicts": "contradicts",
    "implements": "implements",
    "inspires": "inspires",
    "refines": "refines",
    "references": "references",
    "implies": "implies",
    "parallel": "parallel",
    "participates_in": "participates_in",
    "relates_to": "relates_to",
    "involves": "involves",
    "applies_to": "applies_to",
    # 配对类型：互为逆
    "belongs_to": "contains",
    "contains": "belongs_to",
    "plans": "planned_by",
    "planned_by": "plans",
    "located_at": "location_of",
    "location_of": "located_at",
    "possesses": "possessed_by",
    "possessed_by": "possesses",
    "controls": "controlled_by",
    "controlled_by": "controls",
    "member_of": "has_member",
    "has_member": "member_of",
    "has_event": "event_of",
    "event_of": "has_event",
    "caused_by": "causes",
    "caused": "causes",
}


def _inverse_type(rel_type: Optional[str]) -> Optional[str]:
    """返回逆关系类型；未知类型返回 None（不参与合并）。"""
    if rel_type is None:
        return None
    return _INVERSE_TYPE_MAP.get(rel_type)


def _norm_label(label: Optional[str]) -> str:
    """label 归一化：None/空 → ""，去首尾空白。"""
    return (label or "").strip()


def _edge_richness(edge: dict) -> int:
    """边信息丰富度：payload/metadata 键数 + 非空描述性字段数 + 非默认 weight。

    用于逆边合并时选择保留信息更丰富的一条。
    """
    score = 0
    for key in ("payload", "metadata"):
        val = edge.get(key)
        if isinstance(val, dict):
            score += len(val)
    for key in ("description", "label", "source_role", "target_role"):
        if edge.get(key):
            score += 1
    if edge.get("weight") not in (None, 0.5):
        score += 1
    return score


def _forward_sig(edge: dict) -> Optional[Tuple[str, str, str, str]]:
    """边的正向签名：(source, target, type, norm_label)。type 缺失返回 None。"""
    rel_type = edge.get("relation_type")
    if rel_type is None:
        return None
    return (
        edge.get("source_id", ""),
        edge.get("target_id", ""),
        rel_type,
        _norm_label(edge.get("label")),
    )


def _inverse_sig(edge: dict) -> Optional[Tuple[str, str, str, str]]:
    """边的逆向签名：(target, source, inverse_type, norm_label)。

    type 缺失或未知（无逆映射）时返回 None，不参与合并。
    """
    rel_type = edge.get("relation_type")
    inv_type = _inverse_type(rel_type)
    if inv_type is None:
        return None
    return (
        edge.get("target_id", ""),
        edge.get("source_id", ""),
        inv_type,
        _norm_label(edge.get("label")),
    )


def transform_inverse_dedup_merge(edges: List[dict]) -> Tuple[List[dict], List[dict]]:
    """逆边去重合并（P2 T2.1）。

    将互为逆的边对合并为单边：
    - 对称对：(A, B, type, label) 与 (B, A, type, label) —— 同类型双向边
    - 逆类型对：(A, B, type1) 与 (B, A, type2)，其中 type2 = inverse(type1)
    - 仅当 label 匹配（或双方均为空）时合并；label 不同则保留双方并记录 skipped
    - 合并时保留信息更丰富的一条（payload/metadata 键数 + 非空描述字段 +
      非默认 weight），删除其余，并记录 merged 日志
    - 无逆对的边原样保留，不产生日志

    不修改输入列表；未变更的边保持原对象引用。

    Returns:
        (transformed_edges, change_log)
        change_log 每条形如 {"kept_edge_id", "removed_edge_id",
        "transformation": "inverse_dedup_merge", "action": "merged"|"skipped",
        "detail"}。
    """
    if not edges:
        return [], []

    n = len(edges)

    # 1. 并查集：将互为逆的边归入同一组件
    parent = list(range(n))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: int, b: int) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    forward_index: Dict[Tuple[str, str, str, str], List[int]] = {}
    for i, edge in enumerate(edges):
        sig = _forward_sig(edge)
        if sig is not None:
            forward_index.setdefault(sig, []).append(i)

    for i, edge in enumerate(edges):
        inv_sig = _inverse_sig(edge)
        if inv_sig is None:
            continue
        for j in forward_index.get(inv_sig, []):
            union(i, j)

    components: Dict[int, List[int]] = {}
    for i in range(n):
        components.setdefault(find(i), []).append(i)

    # 2. 合并组件：保留信息最丰富的一条，删除其余
    removed: Set[int] = set()
    log: List[dict] = []
    for indices in components.values():
        if len(indices) == 1:
            continue
        kept_idx = max(indices, key=lambda i: (_edge_richness(edges[i]), -i))
        kept = edges[kept_idx]
        kept_id = kept.get("id", "")
        for i in indices:
            if i == kept_idx:
                continue
            removed.add(i)
            removed_edge = edges[i]
            log.append({
                "kept_edge_id": kept_id,
                "removed_edge_id": removed_edge.get("id", ""),
                "transformation": "inverse_dedup_merge",
                "action": "merged",
                "detail": (
                    f"逆边对合并：保留 {kept_id} "
                    f"({kept.get('source_id', '')}→{kept.get('target_id', '')} "
                    f"{kept.get('relation_type', '')})，删除 "
                    f"{removed_edge.get('id', '')} "
                    f"({removed_edge.get('source_id', '')}→"
                    f"{removed_edge.get('target_id', '')} "
                    f"{removed_edge.get('relation_type', '')})"
                ),
            })

    # 3. label 不匹配的逆边对：不合并，记录 skipped（仅当双方都未被合并）
    type_index: Dict[Tuple[str, str, str], List[int]] = {}
    for i, edge in enumerate(edges):
        rel_type = edge.get("relation_type")
        if rel_type is None:
            continue
        key = (edge.get("source_id", ""), edge.get("target_id", ""), rel_type)
        type_index.setdefault(key, []).append(i)

    for i, edge in enumerate(edges):
        rel_type = edge.get("relation_type")
        if rel_type is None:
            continue
        inv_type = _inverse_type(rel_type)
        if inv_type is None:
            continue
        if len(components[find(i)]) > 1:
            continue  # 该边已参与合并，不再记录
        inv_key = (edge.get("target_id", ""), edge.get("source_id", ""), inv_type)
        my_label = _norm_label(edge.get("label"))
        for j in type_index.get(inv_key, []):
            if j <= i:
                continue  # 每对只记录一次（按输入顺序）
            if len(components[find(j)]) > 1:
                continue
            other_label = _norm_label(edges[j].get("label"))
            if other_label != my_label:
                log.append({
                    "kept_edge_id": edge.get("id", ""),
                    "removed_edge_id": "",
                    "transformation": "inverse_dedup_merge",
                    "action": "skipped",
                    "detail": (
                        f"逆边对 label 不同（{my_label or '空'} vs "
                        f"{other_label or '空'}），不合并，保留双方"
                    ),
                })

    transformed = [edges[i] for i in range(n) if i not in removed]
    return transformed, log


# ── PLANS 归一映射（P2 T2.2） ─────────────────────────────────────────────

# 语义归一映射：(source_type, target_type, old_rel_type) → new_rel_type。
# 仅收录确实需要改写的组合（old != new）；已正确的组合不在表中 → 跳过。
# 来源：relation_types.yaml 的 endpoint_types 语义（CONTAINS 为结构归属，
# PLANS 为规划意图）。
_PLANS_NORMALIZE_MAP: Dict[Tuple[str, str, str], str] = {
    # volume_plan CONTAINS chapter_plan（卷包含章，结构归属）
    ("volume_plan", "chapter_plan", "plans"): "contains",
    ("volume_plan", "chapter_plan", "belongs_to"): "contains",
    ("volume_plan", "chapter_plan", "references"): "contains",
    # arc_plan CONTAINS volume_plan（部包含卷）
    ("arc_plan", "volume_plan", "plans"): "contains",
    ("arc_plan", "volume_plan", "belongs_to"): "contains",
    ("arc_plan", "volume_plan", "references"): "contains",
    # chapter_plan PLANS scene（章纲规划场景，规划意图）
    ("chapter_plan", "scene", "belongs_to"): "plans",
    ("chapter_plan", "scene", "references"): "plans",
    # outline CONTAINS arc_plan（总纲包含部）
    ("outline", "arc_plan", "plans"): "contains",
    ("outline", "arc_plan", "belongs_to"): "contains",
    ("outline", "arc_plan", "references"): "contains",
}

# 参与归一的关系类型
_PLANS_NORMALIZE_TYPES: Tuple[str, str, str] = ("plans", "belongs_to", "references")


def transform_plans_normalize(
    edges: List[dict], nodes: List[dict]
) -> Tuple[List[dict], List[dict]]:
    """PLANS/BELONGS_TO/REFERENCES 混用边语义归一（P2 T2.2）。

    按源/目标单元类型将混用边改写为正确的 CONTAINS/PLANS：
    - 仅处理 relation_type ∈ ("plans", "belongs_to", "references") 的边
    - 命中 _PLANS_NORMALIZE_MAP 的 (source_type, target_type, old_rel_type)
      组合：relation_type 改写为映射值，日志 rewritten
    - 未命中映射：原样保留，日志 skipped
    - source/target 类型缺失或为 None（含节点不存在）：原样保留，日志 skipped
    - 其他 relation_type 的边：不处理，不产生日志

    不修改输入列表；变更的边以浅拷贝返回。

    Returns:
        (transformed_edges, change_log)
        change_log 每条形如 {"edge_id", "transformation": "plans_normalize",
        "action": "rewritten"|"skipped", "detail"}。
    """
    node_type_map: Dict[str, Optional[str]] = {}
    for node in nodes:
        node_type_map[node.get("id", "")] = node.get("type")

    transformed: List[dict] = []
    log: List[dict] = []
    for edge in edges:
        edge_id = edge.get("id", "")
        rel_type = edge.get("relation_type")
        if rel_type not in _PLANS_NORMALIZE_TYPES:
            transformed.append(edge)
            continue
        source_type = node_type_map.get(edge.get("source_id", ""))
        target_type = node_type_map.get(edge.get("target_id", ""))
        if source_type is None or target_type is None:
            transformed.append(edge)
            log.append({
                "edge_id": edge_id,
                "transformation": "plans_normalize",
                "action": "skipped",
                "detail": "source/target 类型缺失或为 None，无法归一",
            })
            continue
        new_rel_type = _PLANS_NORMALIZE_MAP.get((source_type, target_type, rel_type))
        if new_rel_type is None:
            transformed.append(edge)
            log.append({
                "edge_id": edge_id,
                "transformation": "plans_normalize",
                "action": "skipped",
                "detail": f"({source_type}→{target_type}) 组合不在归一映射中，保留原类型",
            })
            continue
        new_edge = dict(edge)
        new_edge["relation_type"] = new_rel_type
        transformed.append(new_edge)
        log.append({
            "edge_id": edge_id,
            "transformation": "plans_normalize",
            "action": "rewritten",
            "detail": (
                f"relation_type 由 {rel_type} 改写为 {new_rel_type}"
                f"（{source_type}→{target_type} 语义归一）"
            ),
        })
    return transformed, log


# ── REFERENCES 归档映射（P2 T2.3） ────────────────────────────────────────

# payload.type → 新关系类型映射。仅收录有明确语义的 payload.type；
# 未命中映射的 references 边归档（无明确语义不盲改）。
# 注：当前 schema 中无 DEPENDS_ON/REQUIRES/USES 类型，统一映射为 IMPLIES（弱关联，
# 端点类型不限），避免 Relation.from_dict 因无效 enum 值崩溃。后续 schema 扩展时可细化。
_REFERENCES_ARCHIVE_MAP: Dict[str, str] = {
    "depends_on": "IMPLIES",
    "requires": "IMPLIES",
    "uses": "IMPLIES",
}


def transform_references_archive(edges: List[dict]) -> Tuple[List[dict], List[dict]]:
    """REFERENCES 边归档（P2 T2.3）。

    将 relation_type == "references" 的边按 payload.type 分桶：
    - payload.type 命中 _REFERENCES_ARCHIVE_MAP：relation_type 改写为映射值，
      日志 rewritten
    - payload.type 缺失 / payload 非 dict / 未命中映射：payload.archived = True
      （软删，保留边），日志 archived
    - relation_type != "references"（含缺失/None）：原样保留，日志 skipped
    - 已 archived 的 references 边（payload.archived == True）：跳过（不重复归档），日志 skipped

    不修改输入列表；变更的边以浅拷贝返回。

    Returns:
        (transformed_edges, change_log)
        change_log 每条形如 {"edge_id", "transformation": "references_archive",
        "action": "rewritten"|"archived"|"skipped", "detail"}。
    """
    transformed: List[dict] = []
    log: List[dict] = []
    for edge in edges:
        edge_id = edge.get("id", "")
        rel_type = edge.get("relation_type")
        if rel_type != "references":
            transformed.append(edge)
            log.append({
                "edge_id": edge_id,
                "transformation": "references_archive",
                "action": "skipped",
                "detail": f"relation_type 为 {rel_type}，非 references，无需迁移",
            })
            continue
        payload = edge.get("payload")
        payload_type = payload.get("type") if isinstance(payload, dict) else None
        new_rel_type = _REFERENCES_ARCHIVE_MAP.get(payload_type)
        if new_rel_type is not None:
            new_edge = dict(edge)
            new_edge["relation_type"] = new_rel_type
            transformed.append(new_edge)
            log.append({
                "edge_id": edge_id,
                "transformation": "references_archive",
                "action": "rewritten",
                "detail": f"payload.type 为 {payload_type}，relation_type 改写为 {new_rel_type}",
            })
        elif isinstance(payload, dict) and payload.get("archived") is True:
            transformed.append(edge)
            log.append({
                "edge_id": edge_id,
                "transformation": "references_archive",
                "action": "skipped",
                "detail": "边已归档（payload.archived=True），无需重复归档",
            })
        else:
            new_edge = dict(edge)
            # 确保 payload 存在
            if not isinstance(new_edge.get("payload"), dict):
                new_edge["payload"] = {}
            new_edge["payload"]["archived"] = True
            transformed.append(new_edge)
            log.append({
                "edge_id": edge_id,
                "transformation": "references_archive",
                "action": "archived",
                "detail": "payload 无明确 type 线索，payload.archived 设为 True",
            })
    return transformed, log


# ── 变换管线 ──────────────────────────────────────────────────────────────

# (名称, 变换函数, 是否接收 nodes)
TRANSFORMATIONS: List[Tuple[str, Callable, bool]] = [
    ("metadata_to_payload", transform_metadata_to_payload, False),
    ("allied_with", transform_allied_with, False),
    ("temporal_prefix", transform_temporal_prefix, True),
    ("structure_archive", archive_structure_type, True),
    ("inverse_dedup_merge", transform_inverse_dedup_merge, False),
    ("plans_normalize", transform_plans_normalize, True),
    ("references_archive", transform_references_archive, False),
]


def apply_transformations(
    edges: List[dict], nodes: List[dict]
) -> Tuple[List[dict], List[dict], List[dict], List[dict]]:
    """按注册顺序应用全部变换。

    Returns:
        (edges, nodes, changes, stats)
        - changes: 全部变更日志（跨变换合并）
        - stats: 每步统计 [{name, changed, skipped, errors}]
    """
    changes: List[dict] = []
    stats: List[dict] = []
    for name, fn, takes_nodes in TRANSFORMATIONS:
        if takes_nodes:
            result = fn(edges, nodes)
            if len(result) == 3:
                edges, nodes, log = result
            else:
                edges, log = result
        else:
            edges, log = fn(edges)
        changes.extend(log)
        stats.append({"name": name, "changed": len(log), "skipped": 0, "errors": 0})
    return edges, nodes, changes, stats


# ── 迁移执行 ──────────────────────────────────────────────────────────────

def run_migration(project_root: str, dry_run: bool = False) -> dict:
    """执行关系迁移。

    dry_run=True 时只计算并报告变更，不写任何文件；
    dry_run=False 时先创建快照，再应用变换并写回。
    """
    if not Path(project_root).is_dir():
        return {"status": "error", "error": f"项目路径不存在: {project_root}"}

    edges = load_edges(project_root)
    nodes = load_nodes(project_root)
    edges_loaded = len(edges)
    nodes_loaded = len(nodes)

    snapshot = None
    if not dry_run:
        snapshot = create_snapshot(project_root)

    edges, nodes, changes, stats = apply_transformations(edges, nodes)

    result = {
        "status": "ok",
        "mode": "dry_run" if dry_run else "execute",
        "project": str(Path(project_root)),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "edges_loaded": edges_loaded,
        "nodes_loaded": nodes_loaded,
        "snapshot": snapshot,
        "transformations": stats,
        "changes": changes,
        "summary": {"changed": len(changes), "skipped": 0, "errors": 0},
    }

    if not dry_run:
        save_edges(project_root, edges)
        if nodes or _nodes_path(project_root).exists():
            save_nodes(project_root, nodes)

    return result


# ── 报告输出 ──────────────────────────────────────────────────────────────

def _print_report(result: dict) -> None:
    """将迁移报告打印到 stdout。"""
    if result.get("status") == "error":
        print(f"错误: {result.get('error', '未知错误')}")
        return
    print("关系迁移工具")
    print(f"项目: {result.get('project', '')}")
    print(f"模式: {result.get('mode', '')}")
    if result.get("mode") == "rollback":
        print(f"恢复边: {result.get('edges_restored', 0)} 条, "
              f"恢复节点: {result.get('nodes_restored', 0)} 个")
        print(f"快照: {result.get('snapshot', '')}")
        return
    print(f"边: {result.get('edges_loaded', 0)} 条, "
          f"节点: {result.get('nodes_loaded', 0)} 个")
    if result.get("snapshot"):
        print(f"快照: {result['snapshot']}")
    for t in result.get("transformations", []):
        print(f"  {t['name']}: 变更 {t['changed']}, 跳过 {t['skipped']}, 错误 {t['errors']}")
    s = result.get("summary", {})
    print(f"总计: 变更 {s.get('changed', 0)}, 跳过 {s.get('skipped', 0)}, "
          f"错误 {s.get('errors', 0)}")


def _write_report(result: dict, report_path: str) -> None:
    """将迁移报告写入 JSON 文件。"""
    path = Path(report_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")


# ── CLI ───────────────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="migrate_relations.py",
        description="关系迁移工具：对 graph/edges.jsonl 执行批量变换，"
                    "支持 dry-run / 报告 / 回滚。",
    )
    parser.add_argument("--project", required=True, help="项目根路径（含 graph/ 目录）")
    parser.add_argument("--dry-run", action="store_true",
                        help="试运行：只报告变更，不写任何文件")
    parser.add_argument("--report", help="报告输出路径（JSON）")
    parser.add_argument("--rollback", help="从快照恢复 edges.jsonl（快照路径或 ID）")
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    """CLI 入口。返回进程退出码（0 成功，1 失败）。"""
    args = build_parser().parse_args(argv)

    if args.rollback and args.dry_run:
        print("错误: --rollback 与 --dry-run 不能同时使用")
        return 1

    if args.rollback:
        result = rollback(args.project, args.rollback)
    else:
        result = run_migration(args.project, dry_run=args.dry_run)

    _print_report(result)
    if args.report:
        _write_report(result, args.report)

    return 0 if result.get("status") == "ok" else 1


if __name__ == "__main__":
    sys.exit(main())