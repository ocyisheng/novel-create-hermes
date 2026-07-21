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


def collect_usage_data(project_root: str) -> dict:
    """
    收集项目所有使用数据，输出结构化报告。
    纯只读，不修改任何文件。
    """
    project = _resolve_project(project_root)
    if not project or not os.path.isdir(os.path.join(project, "graph")):
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

    # ── 5. 优化建议摘要 ──
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
