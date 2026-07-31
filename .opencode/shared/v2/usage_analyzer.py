"""
usage_analyzer.py — 使用数据收集与分析引擎。

读取所有现有数据源，输出结构化报告供优化决策。
不修改任何数据，纯只读。

用法:
    python .opencode/shared/cli.py analyze --project-root <路径>
    python .opencode/shared/cli.py analyze --project-root <路径> --mode full
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Any
from collections import Counter, defaultdict

_SHARED_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_V2_DIR = os.path.join(_SHARED_DIR, "v2")
for _d in [_SHARED_DIR, _V2_DIR]:
    if _d not in sys.path:
        sys.path.insert(0, _d)

from graph_store import is_v2_project
from telemetry import project_basename


def _resolve_project(project: str) -> str:
    if not project:
        return ""
    if os.path.isabs(project):
        return project
    env = os.environ.get("NOVELS_ROOT")
    novels_root = env if env and os.path.isdir(env) else os.path.join(os.getcwd(), "novels")
    cand = os.path.join(novels_root, project)
    if os.path.isdir(cand):
        return cand
    return os.path.abspath(project)


def _resolve_engine_root() -> str:
    """解析 .engine/ 目录路径。"""
    current = Path(__file__).resolve().parent  # v2/
    shared = current.parent                      # shared/
    opencode = shared.parent                     # .opencode/
    tool_root = opencode.parent                  # novel-create-hermes/
    return str(tool_root / ".engine")


def _collect_subagent_traces(project: str = "") -> dict:
    """
    读取 .engine/subagents/{month}.ndjson，聚合子 agent 调度数据。
    """
    engine_root = _resolve_engine_root()
    traces_dir = os.path.join(engine_root, "subagents")
    if not os.path.isdir(traces_dir):
        return {"total_traces": 0, "note": "无子 agent 调度数据"}
    
    norm_project = project_basename(project)
    traces = []
    for fname in sorted(os.listdir(traces_dir)):
        if fname.endswith(".ndjson"):
            fpath = os.path.join(traces_dir, fname)
            try:
                with open(fpath, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line:
                            entry = json.loads(line)
                            entry["project"] = project_basename(entry.get("project", ""))
                            if not norm_project or entry.get("project") == norm_project:
                                traces.append(entry)
            except (json.JSONDecodeError, Exception):
                pass
    
    if not traces:
        return {"total_traces": 0, "note": "无子 agent 调度数据"}
    
    # 按 subagent 类型统计
    subagent_counts = Counter(t.get("subagent", "unknown") for t in traces)
    
    # 按结果统计
    result_counts = Counter(t.get("result", "unknown") for t in traces)
    
    # 按 focus_type × subagent 交叉
    focus_subagent = defaultdict(Counter)
    for t in traces:
        focus_subagent[t.get("focus_type", "unknown")][t.get("subagent", "unknown")] += 1
    
    # 按 preheat_level × subagent 交叉
    preheat_subagent = defaultdict(Counter)
    for t in traces:
        preheat_subagent[t.get("preheat_level", "unknown")][t.get("subagent", "unknown")] += 1
    
    # 失败统计
    failures = [t for t in traces if t.get("result") == "failed"]
    failure_by_subagent = Counter(t.get("subagent", "unknown") for t in failures)
    failure_by_focus = Counter(t.get("focus_type", "unknown") for t in failures)
    
    # 按 session 分组（检测同一 session 内连续失败）
    session_failures = defaultdict(list)
    for t in failures:
        sid = t.get("session_id", "")
        if sid:
            session_failures[sid].append(t)
    consecutive_failure_sessions = [
        {"session_id": sid, "failure_count": len(fts)}
        for sid, fts in session_failures.items() if len(fts) >= 2
    ]
    
    return {
        "total_traces": len(traces),
        "success_count": result_counts.get("success", 0),
        "partial_count": result_counts.get("partial", 0),
        "failed_count": result_counts.get("failed", 0),
        "by_subagent": dict(subagent_counts),
        "by_focus_type": {ft: dict(sc) for ft, sc in focus_subagent.items()},
        "by_preheat_level": {pl: dict(sc) for pl, sc in preheat_subagent.items()},
        "failure_by_subagent": dict(failure_by_subagent),
        "failure_by_focus": dict(failure_by_focus),
        "consecutive_failure_sessions": consecutive_failure_sessions[:10],
    }


def _collect_summary_clues(project: str = "") -> dict:
    """
    读取 .engine/summaries/**/*.summary.md，提取优化线索。
    """
    import re
    import yaml
    
    engine_root = _resolve_engine_root()
    summaries_dir = os.path.join(engine_root, "summaries")
    if not os.path.isdir(summaries_dir):
        return {"total_clues": 0, "note": "无会话总结数据"}
    
    clues = []
    total_summaries = 0
    
    for root, dirs, files in os.walk(summaries_dir):
        for fname in files:
            if not fname.endswith(".summary.md"):
                continue
            total_summaries += 1
            fpath = os.path.join(root, fname)
            try:
                content = Path(fpath).read_text(encoding="utf-8")
            except Exception:
                continue
            
            # 解析 front matter 获取 project
            proj_name = ""
            if content.startswith("---"):
                parts = content.split("---", 2)
                if len(parts) >= 3:
                    try:
                        fm = yaml.safe_load(parts[1]) or {}
                    except Exception:
                        try:
                            fm = json.loads(parts[1])
                        except Exception:
                            fm = {}
                    proj_name = fm.get("project", "")
            
            if project and proj_name and proj_name != project:
                continue
            
            # 提取 ### 优化线索 段落
            clue_match = re.search(r'### 优化线索.*?\n((?:- \[.*?\n)*)', content, re.DOTALL)
            if not clue_match:
                continue
            
            for line in clue_match.group(1).strip().split("\n"):
                line = line.strip()
                m = re.match(r'- \[(\w+)\]\[(\w+)\]\s+(.+?)：(.+?)（证据：(.+?)）', line)
                if m:
                    clues.append({
                        "type": m.group(1),
                        "severity": m.group(2),
                        "component": m.group(3).strip(),
                        "description": m.group(4).strip(),
                        "evidence": m.group(5).strip(),
                        "project": proj_name,
                        "source_file": fname,
                    })
    
    if not clues:
        return {"total_clues": 0, "total_summaries": total_summaries, "note": "无优化线索"}
    
    # 按类型 + 组件聚类
    cluster_key = lambda c: f"{c['type']}|{c['component']}"
    clusters = defaultdict(list)
    for c in clues:
        clusters[cluster_key(c)].append(c)
    
    # 严重程度自动升级
    severity_order = {"low": 0, "medium": 1, "high": 2, "critical": 3}
    clustered = []
    for key, items in clusters.items():
        max_sev = max(items, key=lambda c: severity_order.get(c["severity"], 0))
        count = len(items)
        if count >= 3:
            effective_sev = "critical"
        elif count >= 2:
            effective_sev = "high"
        else:
            effective_sev = max_sev["severity"]
        
        clustered.append({
            "type": max_sev["type"],
            "component": max_sev["component"],
            "description": max_sev["description"],
            "occurrence_count": count,
            "original_severity": max_sev["severity"],
            "effective_severity": effective_sev,
            "projects": list(set(c["project"] for c in items if c["project"])),
        })
    
    clustered.sort(key=lambda c: severity_order.get(c["effective_severity"], 0), reverse=True)
    
    return {
        "total_summaries": total_summaries,
        "total_clues": len(clues),
        "by_type": dict(Counter(c["type"] for c in clues)),
        "by_component": dict(Counter(c["component"] for c in clues)),
        "by_project": dict(Counter(c["project"] for c in clues if c["project"])),
        "clusters": clustered,
    }


def collect_usage_data(project_root: str, telemetry_project: str = "") -> dict:
    """
    收集项目所有使用数据，输出结构化报告。
    纯只读，不修改任何文件。
    
    Args:
        project_root: 项目路径（用于读取 graph/ 数据）
        telemetry_project: 遥测数据按项目名过滤（可选，不传则分析所有项目）
    """
    project = _resolve_project(project_root)
    if not project or not is_v2_project(project):
        return {"error": f"项目路径无效或不是 V2 项目: {project_root}"}

    report = {
        "project": os.path.basename(project),
        "collected_at": datetime.now(timezone.utc).isoformat(),
        "sections": {},
    }

    # ── 1. Graph 统计 ──
    from graph_store import GraphStore
    from graph_schema import UnitType, RelationType

    store = GraphStore(project)
    store.initialize()

    # 单元统计
    units = store.list_units()
    type_counts = Counter(u.type.value for u in units)
    status_counts = Counter(u.status.value for u in units)
    version_dist = Counter(u.version for u in units)

    # 关系统计
    relations = list(store._relations.values())
    rel_type_counts = Counter(r.relation_type.value for r in relations)

    # 事件统计
    events = store._events
    event_type_counts = Counter(e.event_type.value for e in events)
    event_by_date = Counter(e.timestamp.strftime("%Y-%m-%d") for e in events)

    # 按类型统计修改次数（version 反映修改频率）
    type_version_sum = defaultdict(list)
    for u in units:
        type_version_sum[u.type.value].append(u.version)

    report["sections"] = {
        "graph_overview": {
            "total_units": len(units),
            "total_relations": len(relations),
            "total_events": len(events),
            "unit_types": dict(type_counts),
            "unit_statuses": dict(status_counts),
            "relation_types": dict(rel_type_counts),
            "event_types": dict(event_type_counts),
        },
        "modification_patterns": {
            "avg_version_by_type": {
                t: round(sum(vs) / len(vs), 1)
                for t, vs in type_version_sum.items()
            },
            "max_version_by_type": {
                t: max(vs) for t, vs in type_version_sum.items()
            },
            "event_timeline": dict(sorted(event_by_date.items())),
        },
    }

    # ── 2. 偏差数据 ──
    from deviation_manager import DeviationManager
    dm = DeviationManager(project)
    dev_stats = dm.stats()
    all_devs = dm.list_all()

    report["sections"]["quality_deviations"] = {
        "stats": dev_stats,
        "pending_count": len([d for d in all_devs if d.status == "pending"]),
        "resolved_count": len([d for d in all_devs if d.status == "resolved"]),
        "retained_count": len([d for d in all_devs if d.status == "retained"]),
        "top_dimensions": [
            {"dimension": dim, "count": cnt}
            for dim, cnt in sorted(dev_stats.get("by_dimension", {}).items(), key=lambda x: -x[1])[:10]
        ],
        "recurring_issues": [
            {"id": d.id, "dimension": d.dimension, "entity": d.entity,
             "severity": d.severity, "summary": d.summary, "detection_count": d.detection_count}
            for d in all_devs if d.detection_count >= 2
        ],
    }

    # ── 3. 会话数据 ──
    from session import SessionManager
    sm = SessionManager(project)
    sm.load_user_state()

    session_info = {}
    if sm.active_session:
        s = sm.active_session
        session_info = {
            "has_active_session": True,
            "cycle_type": s.cycle_type.value,
            "cycle_number": s.cycle_number,
            "phase": s.phase.value,
            "status": s.status.value,
            "duration_minutes": round(s.total_duration_seconds() / 60, 1),
            "total_tokens": s.total_tokens(),
            "action_count": len(s.timeline),
            "action_types": dict(Counter(a.action for a in s.timeline)),
            "new_units_created": len(s.new_unit_ids),
        }
    else:
        session_info = {"has_active_session": False}

    report["sections"]["sessions"] = {
        "active": session_info,
        "user_state": {
            "current_cycle": sm.user_state.current_cycle,
            "cycle_type": sm.user_state.current_cycle_type.value,
            "energy_level": sm.user_state.energy_level.value,
            "avg_session_minutes": sm.user_state.avg_session_minutes,
            "unresolved_intentions": [
                i for i in sm.user_state.expressed_intentions if not i.get("resolved")
            ],
        },
    }

    # ── 4. 事件分析 ──
    # 按操作类型统计
    event_actions = Counter()
    for e in events:
        action = e.payload.get("action", e.event_type.value) if e.payload else e.event_type.value
        event_actions[action] += 1

    # 按 actor 统计
    actor_counts = Counter(e.actor for e in events if e.actor)

    # 按 session 分组
    session_events = defaultdict(list)
    for e in events:
        if e.session_id:
            session_events[e.session_id].append(e)

    report["sections"]["events"] = {
        "total_events": len(events),
        "action_distribution": dict(event_actions.most_common(20)),
        "actor_distribution": dict(actor_counts.most_common(10)),
        "daily_activity": dict(event_by_date.most_common(30)),
        "session_count": len(session_events),
    }

    # ── 5. 写作效率分析 ──
    # 按类型统计平均修改次数
    avg_mods = {}
    for t, vs in type_version_sum.items():
        avg_mods[t] = round(sum(vs) / len(vs), 1)

    # 找出修改最多的单元（可能有问题）
    high_mod_units = sorted(
        [(u.unit_name, u.type.value, u.version) for u in units if u.version >= 3],
        key=lambda x: -x[2]
    )[:20]

    report["sections"]["efficiency"] = {
        "avg_modifications_by_type": avg_mods,
        "most_reworked_units": [
            {"name": name, "type": t, "version": v}
            for name, t, v in high_mod_units
        ],
    }

    # ── 6. 子 agent 调度分析 ──
    subagent_data = _collect_subagent_traces(telemetry_project or os.path.basename(project))
    report["sections"]["subagent_traces"] = subagent_data

    # ── 7. 会话总结线索 ──
    summary_clues = _collect_summary_clues(telemetry_project or os.path.basename(project))
    report["sections"]["summary_clues"] = summary_clues

    # ── 8. 优化建议摘要 ──
    suggestions = []

    # 基于偏差数据的建议
    dev_stats = report["sections"]["quality_deviations"]["stats"]
    by_dim = dev_stats.get("by_dimension", {})
    if by_dim:
        worst_dim = max(by_dim, key=by_dim.get)
        suggestions.append({
            "type": "quality",
            "target": f"dimension:{worst_dim}",
            "signal": f"偏差最多维度: {worst_dim} ({by_dim[worst_dim]} 次)",
            "action": "优化 crafter prompt 中该维度的处理逻辑",
        })

    # 基于修改模式
    avg_mods = report["sections"]["efficiency"]["avg_modifications_by_type"]
    high_mod_types = {t: v for t, v in avg_mods.items() if v >= 2.0}
    if high_mod_types:
        suggestions.append({
            "type": "rework",
            "target": f"types:{','.join(high_mod_types.keys())}",
            "signal": f"高修改率类型: {high_mod_types}",
            "action": "优化这些类型单元的首次生成质量",
        })

    # 基于事件分布
    if events:
        # 检查是否有大量 UPDATE 事件（可能表示反复修改）
        update_count = event_type_counts.get("unit_updated", 0)
        create_count = event_type_counts.get("unit_created", 0)
        if create_count > 0 and update_count / create_count > 3:
            suggestions.append({
                "type": "efficiency",
                "target": "general",
                "signal": f"修改/创建比: {update_count}/{create_count} = {update_count/create_count:.1f}",
                "action": "首次生成质量可能不足，需优化 crafter 的首次输出",
            })

    report["sections"]["suggestions"] = suggestions

    return report


def format_report(report: dict, verbose: bool = False) -> str:
    """将报告格式化为可读文本。"""
    if "error" in report:
        return f"❌ {report['error']}"

    lines = []
    lines.append("=" * 60)
    lines.append(f"📊 使用数据分析报告 — {report['project']}")
    lines.append(f"收集时间: {report['collected_at']}")
    lines.append("=" * 60)

    # Graph 概览
    g = report["sections"].get("graph_overview", {})
    lines.append(f"\n📦 Graph 概览")
    lines.append(f"  叙事单元: {g.get('total_units', 0)}")
    lines.append(f"  关系: {g.get('total_relations', 0)}")
    lines.append(f"  事件: {g.get('total_events', 0)}")
    lines.append(f"  单元类型分布: {g.get('unit_types', {})}")
    lines.append(f"  关系类型分布: {g.get('relation_types', {})}")

    # 质量偏差
    q = report["sections"].get("quality_deviations", {})
    lines.append(f"\n🔍 质量偏差")
    lines.append(f"  总计: {q.get('stats', {}).get('total', 0)}")
    lines.append(f"  待处理: {q.get('pending_count', 0)}")
    lines.append(f"  已解决: {q.get('resolved_count', 0)}")
    lines.append(f"  已保留: {q.get('retained_count', 0)}")
    if q.get("top_dimensions"):
        lines.append(f"  问题维度 Top:")
        for d in q["top_dimensions"][:5]:
            lines.append(f"    - {d['dimension']}: {d['count']} 次")
    if q.get("recurring_issues"):
        lines.append(f"  反复出现的问题:")
        for issue in q["recurring_issues"][:5]:
            lines.append(f"    - [{issue['severity']}] {issue['summary']} (检测 {issue['detection_count']} 次)")

    # 效率
    eff = report["sections"].get("efficiency", {})
    lines.append(f"\n⚡ 效率分析")
    lines.append(f"  平均修改次数(按类型):")
    for t, v in eff.get("avg_modifications_by_type", {}).items():
        lines.append(f"    {t}: {v}")
    if eff.get("most_reworked_units"):
        lines.append(f"  高频修改单元 (≥3次):")
        for u in eff["most_reworked_units"][:5]:
            lines.append(f"    {u['name']} ({u['type']}) — 修改 {u['version']} 次")

    # 事件
    ev = report["sections"].get("events", {})
    lines.append(f"\n📋 事件活动")
    lines.append(f"  总事件数: {ev.get('total_events', 0)}")
    lines.append(f"  操作分布 Top:")
    for action, count in list(ev.get("action_distribution", {}).items())[:10]:
        lines.append(f"    {action}: {count}")
    if ev.get("daily_activity"):
        lines.append(f"  最近活动日期:")
        for date, count in list(ev.get("daily_activity", {}).items())[:10]:
            lines.append(f"    {date}: {count} 次操作")

    # 子 agent 调度
    st = report["sections"].get("subagent_traces", {})
    if st.get("total_traces", 0) > 0:
        lines.append(f"\n🤖 子 Agent 调度")
        lines.append(f"  总调度次数: {st.get('total_traces', 0)}")
        lines.append(f"  成功: {st.get('success_count', 0)} / 部分: {st.get('partial_count', 0)} / 失败: {st.get('failed_count', 0)}")
        if st.get("by_subagent"):
            lines.append(f"  按类型: {st['by_subagent']}")
        if st.get("failure_by_subagent"):
            lines.append(f"  失败按类型: {st['failure_by_subagent']}")
        if st.get("consecutive_failure_sessions"):
            lines.append(f"  连续失败 session:")
            for s in st["consecutive_failure_sessions"][:3]:
                lines.append(f"    {s['session_id']}: {s['failure_count']} 次")

    # 会话总结线索
    sc = report["sections"].get("summary_clues", {})
    if sc.get("total_clues", 0) > 0:
        lines.append(f"\n📝 优化线索（来自 {sc.get('total_summaries', 0)} 份会话总结）")
        lines.append(f"  线索总数: {sc.get('total_clues', 0)}")
        if sc.get("by_type"):
            lines.append(f"  按类型: {sc['by_type']}")
        if sc.get("clusters"):
            lines.append(f"  聚类 (按严重程度):")
            for c in sc["clusters"][:5]:
                lines.append(f"    [{c['effective_severity']}] [{c['type']}] {c['component']}: {c['description'][:60]} (×{c['occurrence_count']})")

    # 优化建议
    suggestions = report["sections"].get("suggestions", [])
    if suggestions:
        lines.append(f"\n💡 优化建议")
        for s in suggestions:
            lines.append(f"  [{s['type']}] {s.get('signal', '')}")
            lines.append(f"    建议: {s['action']}")

    lines.append("\n" + "=" * 60)
    return "\n".join(lines)


def main():
    """CLI 入口。"""
    import argparse
    parser = argparse.ArgumentParser(description="使用数据分析工具")
    parser.add_argument("--project-root", "-p", required=True, help="项目根目录")
    parser.add_argument("--mode", choices=["quick", "full"], default="full",
                        help="分析模式: quick=仅统计, full=含详细分析")
    parser.add_argument("--json", action="store_true", help="输出 JSON 格式")
    parser.add_argument("--output", "-o", default="", help="输出到文件")

    args = parser.parse_args()

    report = collect_usage_data(args.project_root)
    if "error" in report:
        print(f"❌ {report['error']}")
        sys.exit(1)

    if args.json:
        output = json.dumps(report, ensure_ascii=False, indent=2, default=str)
    else:
        output = format_report(report, verbose=(args.mode == "full"))

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(output)
        print(f"✅ 报告已写入: {args.output}")
    else:
        print(output)


if __name__ == "__main__":
    main()
