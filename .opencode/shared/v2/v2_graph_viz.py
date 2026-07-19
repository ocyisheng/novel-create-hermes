"""
v2_graph_viz.py — V2 叙事单元网络可视化

直接从 V2 GraphStore 读取数据，生成 vis-network 交互式 HTML。
不依赖旧 YAML 格式。

用法:
    python .opencode/shared/cli.py viz --project-root novels/项目名 [选项]

CLI 入口已移至 cli.py。本模块为纯函数库，由 cli.py 和 novel_tool.py 调用。
"""

import sys
import os
import json
import webbrowser
from pathlib import Path
from typing import Optional
from collections import defaultdict
from datetime import datetime, timezone
from v2_detail_template import render_detail_html
from graph_schema import get_unit_chapter, get_unit_chapter_label

V2_DIR = os.path.join(os.path.dirname(__file__), "v2")
if V2_DIR not in sys.path:
    sys.path.insert(0, V2_DIR)

from graph_schema import UnitType, RelationType, UnitStatus
from graph_store import GraphStore
from render_utils import render_content, summarize_content


# ── V2 类型 → 可视化映射 ──────────────────────────────────────────

UNIT_TYPE_LABELS = {
    UnitType.CHARACTER_ARC: "角色",
    UnitType.SCENE: "场景",
    UnitType.PLOT_THREAD: "情节线",
    UnitType.WORLD_RULE: "世界观",
    UnitType.THEMATIC_MOTIF: "主题意象",
    UnitType.NOTE: "笔记",
    UnitType.CHUNK: "正文",
    UnitType.OUTLINE: "总纲",
    UnitType.ARC_PLAN: "部篇大纲",
    UnitType.VOLUME_PLAN: "卷大纲",
    UnitType.CHAPTER_PLAN: "章纲",
}

UNIT_TYPE_COLORS = {
    UnitType.CHARACTER_ARC:  {"bg": "#5B9BD5", "border": "#2E75B6", "text": "#fff"},
    UnitType.SCENE:          {"bg": "#A5A5A5", "border": "#7A7A7A", "text": "#fff"},
    UnitType.PLOT_THREAD:    {"bg": "#FFC000", "border": "#BF8F00", "text": "#000"},
    UnitType.WORLD_RULE:     {"bg": "#70AD47", "border": "#4E6B31", "text": "#fff"},
    UnitType.THEMATIC_MOTIF: {"bg": "#B4A7D6", "border": "#8E7CC3", "text": "#fff"},
    UnitType.NOTE:           {"bg": "#D6D6D6", "border": "#A0A0A0", "text": "#000"},
    UnitType.CHUNK:          {"bg": "#CD853F", "border": "#8B6914", "text": "#fff"},
    UnitType.OUTLINE:        {"bg": "#4472C4", "border": "#2E5090", "text": "#fff"},
    UnitType.ARC_PLAN:       {"bg": "#5B9BD5", "border": "#3A72B0", "text": "#fff"},
    UnitType.VOLUME_PLAN:    {"bg": "#7FCDBB", "border": "#4EA08A", "text": "#000"},
    UnitType.CHAPTER_PLAN:   {"bg": "#A8D08D", "border": "#70AD47", "text": "#000"},
}

UNIT_TYPE_SIZES = {
    UnitType.CHARACTER_ARC: 28,
    UnitType.SCENE:         18,
    UnitType.PLOT_THREAD:   22,
    UnitType.WORLD_RULE:    24,
    UnitType.THEMATIC_MOTIF: 20,
    UnitType.NOTE:          14,
    UnitType.CHUNK:         16,
    UnitType.OUTLINE:       30,
    UnitType.ARC_PLAN:      26,
    UnitType.VOLUME_PLAN:   24,
    UnitType.CHAPTER_PLAN:  20,
}

RELATION_LABELS = {
    RelationType.PARTICIPATES_IN: "参与",
    RelationType.CAUSES:          "导致",
    RelationType.PRECEDES:        "先于",
    RelationType.CONTRADICTS:     "矛盾",
    RelationType.IMPLEMENTS:      "实现",
    RelationType.BELONGS_TO:      "属于",
    RelationType.REFERENCES:      "引用",
    RelationType.IMPLIES:         "隐含",
    RelationType.PARALLEL:        "并列",
    RelationType.INSPIRES:        "启发",
    RelationType.REFINES:         "细化",
    RelationType.LOCATED_AT:      "位于",
    RelationType.ALLIED_WITH:     "同盟",
    RelationType.CONTAINS:        "包含",
    RelationType.CONTROLS:        "统治",
    RelationType.MEMBER_OF:       "成员",
    RelationType.HAS_MEMBER:      "拥有成员",
    RelationType.LOCATION_OF:     "所在",
    RelationType.CONTROLLED_BY:   "受制",
}

RELATION_COLORS = {
    RelationType.PARTICIPATES_IN: "#5B9BD5",
    RelationType.CAUSES:          "#FF4444",
    RelationType.PRECEDES:        "#FFC000",
    RelationType.CONTRADICTS:     "#FF6600",
    RelationType.IMPLEMENTS:      "#70AD47",
    RelationType.BELONGS_TO:      "#ED7D31",
    RelationType.REFERENCES:      "#8888AA",
    RelationType.IMPLIES:         "#8888AA",
    RelationType.PARALLEL:        "#B4A7D6",
    RelationType.INSPIRES:        "#B4A7D6",
    RelationType.REFINES:         "#70AD47",
    RelationType.LOCATED_AT:      "#00B0F0",
    RelationType.ALLIED_WITH:     "#92D050",
    RelationType.CONTAINS:        "#ED7D31",
    RelationType.CONTROLS:        "#FF6600",
    RelationType.MEMBER_OF:       "#5B9BD5",
    RelationType.HAS_MEMBER:      "#5B9BD5",
    RelationType.LOCATION_OF:     "#00B0F0",
    RelationType.CONTROLLED_BY:   "#FF6600",
}


# ── 数据加载 ───────────────────────────────────────────────────────

class V2GraphLoader:
    """从 V2 GraphStore 加载网络数据"""

    def __init__(self, project_root: str):
        self.store = GraphStore(project_root)
        self.store.initialize()

    def list_units(self) -> list[dict]:
        """列出所有叙事单元（用于 --list-units）"""
        rows = []
        for u in self.store._units.values():
            if u.status == UnitStatus.ARCHIVED:
                continue
            rows.append({
                "id": u.id,
                "name": u.unit_name,
                "type": UNIT_TYPE_LABELS.get(u.type, u.type.value),
                "status": u.status.value,
            })
        rows.sort(key=lambda r: (r["type"], r["name"]))
        return rows

    def find_unit_id(self, name_or_id: str) -> str | None:
        """按名称或 ID 查找叙事单元"""
        # 先按 ID
        u = self.store.get_unit(name_or_id)
        if u:
            return u.id
        # 再按名称
        u = self.store.get_unit_by_name(name_or_id)
        if u:
            return u.id
        return None

    def build_full_graph(self) -> dict:
        """构建全项目图谱"""
        nodes = {}
        edges = []

        for u in self.store._units.values():
            if u.status == UnitStatus.ARCHIVED:
                continue
            nodes[u.id] = self._unit_to_node(u)

        for rel in self.store._relations.values():
            if rel.source_id in nodes and rel.target_id in nodes:
                edges.append(self._rel_to_edge(rel))

        return {"nodes": nodes, "edges": edges}

    def build_character_network(self, character_id: str, depth: int = 2) -> dict:
        """构建角色的 Ego Network（1-hop + 可选 2-hop）"""
        center = self.store.get_unit(character_id)
        if not center:
            return {"nodes": {}, "edges": []}

        nodes = {center.id: self._unit_to_node(center, is_center=True)}
        edges = []
        visited = {center.id}

        # 1-hop
        neighbors_1 = self.store.get_neighbors(character_id, max_depth=1).get(1, set())
        for nid in neighbors_1:
            u = self.store.get_unit(nid)
            if u and u.status != UnitStatus.ARCHIVED:
                nodes[nid] = self._unit_to_node(u, hop=1)
                visited.add(nid)

        # 当前中心的所有关系
        for rel in self.store.get_relations(character_id):
            other = rel.target_id if rel.source_id == character_id else rel.source_id
            if other in visited:
                edges.append(self._rel_to_edge(rel))

        # 1-hop 之间的关系
        for nid in neighbors_1:
            for rel in self.store.get_relations(nid):
                if (rel.source_id in visited and rel.target_id in visited
                        and rel.source_id != center.id and rel.target_id != center.id):
                    # 检查这条边是否已经添加
                    key = frozenset([rel.source_id, rel.target_id, rel.relation_type.value])
                    if not any(
                        frozenset([e["from"], e["to"], e.get("_type","")]) == key
                        for e in edges
                    ):
                        edges.append(self._rel_to_edge(rel))

        # 2-hop（如果 depth >= 2）
        if depth >= 2:
            for nid in list(neighbors_1):
                neighbors_2 = self.store.get_neighbors(nid, max_depth=1).get(1, set())
                for nid2 in neighbors_2:
                    if nid2 not in visited:
                        u2 = self.store.get_unit(nid2)
                        if u2 and u2.status != UnitStatus.ARCHIVED:
                            nodes[nid2] = self._unit_to_node(u2, hop=2)
                            visited.add(nid2)

            # 2-hop 的关系
            for nid in list(neighbors_1):
                for rel in self.store.get_relations(nid):
                    if rel.source_id in visited and rel.target_id in visited:
                        key = frozenset([rel.source_id, rel.target_id, rel.relation_type.value])
                        if not any(
                            frozenset([e["from"], e["to"], e.get("_type","")]) == key
                            for e in edges
                        ):
                            edges.append(self._rel_to_edge(rel))

        return {"nodes": nodes, "edges": edges, "center_id": center.id}

    def build_timeline(self, unit_id: str) -> dict | None:
        """构建角色的时间线（按章节排序的场景 + 关联笔记）"""
        center = self.store.get_unit(unit_id)
        if not center:
            return None

        events = []

        # 收集角色参与的场景
        for rel in self.store.get_relations(unit_id, direction="incoming"):
            source = self.store.get_unit(rel.source_id)
            if source and source.type == UnitType.SCENE and source.status != UnitStatus.ARCHIVED:
                events.append({
                    "sort_key": get_unit_chapter(source),
                    "time_label": get_unit_chapter_label(source),
                    "event": source.unit_name,
                    "source_type": "chapter",
                    "node_id": source.id,
                })

            if source and source.type == UnitType.CHUNK and source.status != UnitStatus.ARCHIVED:
                events.append({
                    "sort_key": get_unit_chapter(source),
                    "time_label": get_unit_chapter_label(source),
                    "event": f"正文: {source.unit_name}",
                    "source_type": "chunk",
                    "node_id": source.id,
                })

        # 关联的情节线
        for rel in self.store.get_relations(unit_id, direction="outgoing"):
            target = self.store.get_unit(rel.target_id)
            if target and target.type == UnitType.PLOT_THREAD and target.status != UnitStatus.ARCHIVED:
                events.append({
                    "sort_key": -1,
                    "time_label": "情节线",
                    "event": f"参与情节线: {target.unit_name}",
                    "source_type": "plot",
                    "node_id": target.id,
                })

        # 关联的世界观
        for rel in self.store.get_relations(unit_id, direction="outgoing"):
            target = self.store.get_unit(rel.target_id)
            if target and target.type == UnitType.WORLD_RULE:
                rel_label = RELATION_LABELS.get(rel.relation_type, rel.relation_type.value)
                events.append({
                    "sort_key": -2,
                    "time_label": "世界观",
                    "event": f"{rel_label}: {target.unit_name}",
                    "source_type": "world",
                    "node_id": target.id,
                })

        # 关联的纪年事件 WORLD_RULE（子类型=纪年事件，content 中有"时间"+"事件"字段）
        seen_ce_ids = set()
        for rel in self.store.get_relations(unit_id):
            other_id = rel.target_id if rel.source_id == unit_id else rel.source_id
            if other_id in seen_ce_ids:
                continue
            seen_ce_ids.add(other_id)
            other = self.store.get_unit(other_id)
            if (other and other.type == UnitType.WORLD_RULE
                    and other.status != UnitStatus.ARCHIVED):
                try:
                    import json as _json
                    c = _json.loads(other.content)
                    content_dict = c if isinstance(c, dict) else {}
                    subtype_raw = content_dict.get("子类型", content_dict.get("实体子类型", ""))
                    if subtype_raw not in ("纪年事件", "chronicle_event"):
                        continue
                    event_time = content_dict.get("时间", "") or ""
                    event_name = content_dict.get("事件", "") or ""
                    if event_time and event_name:
                        import re as _re
                        years = _re.findall(r"(\d+)", event_time)
                        sort_key = int(years[0]) if years else 0
                        events.append({
                            "sort_key": max(sort_key, 0),
                            "time_label": event_time,
                            "event": event_name,
                            "source_type": "world",
                            "node_id": other.id,
                        })
                except (json.JSONDecodeError, AttributeError, KeyError):
                    pass

        events.sort(key=lambda e: (e["sort_key"], e["event"]))

        return {
            "entity": {
                "id": center.id,
                "name": center.unit_name,
                "type": UNIT_TYPE_LABELS.get(center.type, center.type.value),
            },
            "events": events,
        }

    def _unit_to_node(self, u, is_center: bool = False, hop: int = 0) -> dict:
        """叙事单元 → vis-network 节点"""
        colors = UNIT_TYPE_COLORS.get(u.type, {"bg": "#D6D6D6", "border": "#A0A0A0", "text": "#000"})
        size = UNIT_TYPE_SIZES.get(u.type, 18)
        if is_center:
            size = 40
        elif hop == 1:
            size = int(size * 1.2)
        elif hop == 2:
            size = int(size * 0.85)

        border_width = 3
        border_dashes = False
        if is_center:
            border_width = 5
        elif hop >= 1:
            border_width = 2

        extra = {}
        pre_rendered_html = ""
        try:
            if u.content and u.content.startswith("{"):
                extra = json.loads(u.content)
                if isinstance(extra, dict):
                    rendered = render_content(extra)
                    pre_rendered_html = "".join(r["html"] for r in rendered if r["html"])
            elif u.content:
                extra["_preview"] = u.content[:100]
        except json.JSONDecodeError:
            extra["_preview"] = (u.content or "")[:100]

        # 从 subtype 注册表注入展示信息
        from schemas import get_subtype_info
        _st = get_subtype_info(u.type)
        if _st and isinstance(extra, dict):
            _raw = extra.get(_st.field, "")
            if not _raw:
                for _af in _st.alt_fields:
                    _raw = extra.get(_af, "")
                    if _raw:
                        break
            extra["subtype_label"] = _st.value_labels.get(_raw, _raw)
            extra["subtype_color"] = _st.value_colors.get(_raw, {})

        return {
            "id": u.id,
            "label": u.unit_name,
            "type": u.type.value,
            "type_label": UNIT_TYPE_LABELS.get(u.type, u.type.value),
            "color": colors,
            "size": size,
            "borderWidth": border_width,
            "borderDashes": border_dashes,
            "status": u.status.value,
            "confidence": u.confidence,
            "tags": u.tags,
            "chapter": get_unit_chapter(u),
            "chapter_label": get_unit_chapter_label(u),
            "extra": extra,
            "pre_rendered_html": pre_rendered_html,
            "is_center": is_center,
            "hop": hop,
        }

    def _rel_to_edge(self, rel) -> dict:
        """Relation → vis-network 边"""
        label = RELATION_LABELS.get(rel.relation_type, rel.relation_type.value)
        color = RELATION_COLORS.get(rel.relation_type, "#4a4a6a")
        width = 1.5 if rel.weight >= 0.7 else 1.0

        return {
            "from": rel.source_id,
            "to": rel.target_id,
            "label": label,
            "color": color,
            "width": width,
            "relation_type": rel.relation_type.value,
            "_type": rel.relation_type.value,
            "description": rel.description or label,
        }


# ── HTML 生成 ──────────────────────────────────────────────────────

HTML_GRAPH_TEMPLATE = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title} — V2 关系图谱</title>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; background: #1a1a2e; color: #e0e0e0; overflow: hidden; height: 100vh; }}

  #toolbar {{
    position: fixed; top: 0; left: 0; right: 0; z-index: 100;
    padding: 10px 20px;
    background: rgba(26,26,46,0.95);
    border-bottom: 1px solid #2a2a4a;
    display: flex; align-items: center; gap: 12px; flex-wrap: wrap;
  }}
  #toolbar h1 {{ font-size: 16px; font-weight: 600; color: #e0e0e0; margin-right: 16px; }}
  #toolbar label {{ font-size: 13px; color: #aaa; display: flex; align-items: center; gap: 4px; }}
  #toolbar select, #toolbar input {{
    padding: 4px 8px; border-radius: 4px; border: 1px solid #3a3a5a;
    background: #16213e; color: #e0e0e0; font-size: 13px; outline: none;
  }}
  #toolbar .stats {{ font-size: 12px; color: #888; margin-left: auto; }}

  #network {{ position: fixed; top: 50px; left: 0; right: 0; bottom: 0; }}

  #legend {{
    position: fixed; bottom: 20px; right: 20px; z-index: 100;
    background: rgba(26,26,46,0.9); border: 1px solid #2a2a4a;
    border-radius: 8px; padding: 12px 16px; font-size: 12px;
    display: flex; flex-direction: column; gap: 4px;
  }}
  #legend .item {{ display: flex; align-items: center; gap: 8px; }}
  #legend .dot {{ width: 14px; height: 14px; border-radius: 50%; flex-shrink: 0; }}

  #tooltip {{
    position: fixed; z-index: 200; pointer-events: none;
    background: rgba(30,30,50,0.95); border: 1px solid #4a4a7a;
    border-radius: 8px; padding: 12px 16px; font-size: 13px;
    max-width: 320px; line-height: 1.6; display: none;
    box-shadow: 0 4px 16px rgba(0,0,0,0.4);
  }}
  #tooltip .tt-name {{ font-size: 15px; font-weight: 600; color: #fff; }}

  #detail-panel {{
    position: fixed; top: 50px; right: -420px; bottom: 0; width: 400px;
    z-index: 150; background: rgba(22,22,40,0.98); border-left: 1px solid #2a2a4a;
    padding: 20px; overflow-y: auto; transition: right 0.3s ease;
    font-size: 13px; line-height: 1.6;
  }}
  #detail-panel.open {{ right: 0; }}
  #detail-panel .dp-close {{ float: right; cursor: pointer; color: #666; font-size: 20px; }}
  #detail-panel .dp-close:hover {{ color: #e0e0e0; }}
  #detail-panel .dp-name {{ font-size: 17px; font-weight: 600; color: #fff; margin-bottom: 2px; }}
  #detail-panel .dp-meta {{ color: #888; font-size: 12px; margin-bottom: 16px; }}
  #detail-panel .dp-section {{ margin-bottom: 14px; }}
  #detail-panel .dp-section h3 {{ font-size: 13px; color: #aaa; margin-bottom: 6px; padding-bottom: 3px; border-bottom: 1px solid #2a2a4a; }}
  #detail-panel .dp-tag {{
    font-size: 11px; padding: 1px 8px; border-radius: 8px; display: inline-block;
    background: rgba(255,255,255,0.06); color: #bbb; margin: 2px;
  }}
</style>
</head>
<body>

<div id="toolbar">
  <h1>{title}</h1>
  <label>筛选: <select id="typeFilter">
    <option value="all">全部</option>
    {filter_options}
  </select></label>
  <label>搜索: <input id="searchBox" type="text" placeholder="名称..." style="width:160px"></label>
  <span class="stats">{node_count} 个节点 · {edge_count} 条关系</span>
</div>

<div id="network"></div>
<div id="tooltip"></div>
<div id="legend">{legend_html}</div>
<div id="detail-panel">
  <span class="dp-close" onclick="closeDetail()">&times;</span>
  <div class="dp-name" id="dp-name"></div>
  <div class="dp-meta" id="dp-meta"></div>
  <div id="dp-body"></div>
</div>

<script src="https://unpkg.com/vis-network/standalone/umd/vis-network.min.js"></script>
<script>
(function() {{
  const nodeData = {node_data};
  const edgeData = {edge_data};
  const typeLabels = {type_labels};
  const UNIT_TYPE_COLORS = {type_colors};

  // 构建节点
  const nodeMap = {{}};
  const nodes = new vis.DataSet(
    Object.entries(nodeData).map(([id, n]) => {{
      const c = n.color || {{ bg: '#D6D6D6', border: '#A0A0A0' }};
      const node = {{
        id,
        label: n.label || id,
        color: {{ background: c.bg, border: c.border }},
        font: {{ color: c.text || '#fff', size: n.is_center ? 18 : 14, face: 'sans-serif' }},
        shape: n.is_center ? 'star' : 'dot',
        size: n.size || 20,
        borderWidth: n.borderWidth || 2,
        borderDashes: n.borderDashes || false,
        group: n.type || 'other',
        _info: n,
      }};
      nodeMap[id] = node;
      return node;
    }})
  );

  // 构建边
  const edges = new vis.DataSet(
    edgeData
      .filter(e => nodeMap[e.from] && nodeMap[e.to])
      .map(e => ({{
        from: e.from,
        to: e.to,
        label: e.label || '',
        font: {{ size: 10, color: e.color || '#888', strokeWidth: 0 }},
        color: {{ color: e.color || '#4a4a6a', opacity: 0.8 }},
        width: e.width || 1,
        arrows: {{ to: {{ enabled: true, scaleFactor: 1 }} }},
        smooth: {{ type: 'continuous' }},
        _info: e,
      }}))
  );

  // 配置
  const options = {{
    layout: {{ improvedLayout: false, hierarchical: false }},
    physics: {{
      solver: 'forceAtlas2Based',
      forceAtlas2Based: {{
        gravitationalConstant: -60,
        centralGravity: 0.01,
        springLength: 150,
        springConstant: 0.03,
        damping: 0.5,
      }},
      stabilization: {{ iterations: 30, updateInterval: 10 }},
    }},
    interaction: {{
      dragNodes: true, dragView: true, zoomView: true,
      hover: true, tooltipDelay: 200, navigationButtons: true, keyboard: true,
    }},
    edges: {{ smooth: {{ type: 'continuous' }} }},
  }};

  const container = document.getElementById('network');
  const network = new vis.Network(container, {{ nodes, edges }}, options);

  // Tooltip
  const tooltip = document.getElementById('tooltip');
  network.on('hoverNode', function(params) {{
    const node = nodes.get(params.node);
    if (!node || !node._info) return;
    const n = node._info;
    const tl = typeLabels[n.type] || n.type;
    tooltip.innerHTML = '<div class="tt-name">' + n.label + '</div>' +
      '<div>类型: ' + tl + '</div>' +
      '<div>状态: ' + n.status + ' 确信度: ' + (n.confidence || '?') + '</div>';
    tooltip.style.display = 'block';
  }});
  network.on('blurNode', function() {{ tooltip.style.display = 'none'; }});
  container.addEventListener('mousemove', function(e) {{
    if (tooltip.style.display === 'block') {{
      tooltip.style.left = (e.clientX + 16) + 'px';
      tooltip.style.top = (e.clientY + 16) + 'px';
    }}
  }});

  // 筛选
  const typeFilter = document.getElementById('typeFilter');
  const searchBox = document.getElementById('searchBox');
  function applyFilter() {{
    const typeVal = typeFilter.value;
    const query = searchBox.value.trim().toLowerCase();
    const visible = new Set();
    Object.entries(nodeData).forEach(([id, n]) => {{
      let ok = true;
      if (typeVal !== 'all') {{
        if (typeVal.includes('.')) {{
          const parts = typeVal.split('.');
          if (n.type !== parts[0]) {{ ok = false; }}
          else {{
            const st = n.extra?.subtype_label || n.tags?.[0] || '';
            if (st !== parts[1]) ok = false;
          }}
        }} else if (n.type !== typeVal) {{
          ok = false;
        }}
      }}
      if (query && !n.label.toLowerCase().includes(query)) ok = false;
      if (ok) visible.add(id);
    }});
    nodes.forEach(node => {{
      nodes.update({{ id: node.id, hidden: !visible.has(node.id) }});
    }});
    edges.forEach(edge => {{
      edges.update({{ id: edge.id, hidden: !visible.has(edge.from) || !visible.has(edge.to) }});
    }});
    network.fit({{ animation: true }});
  }}
  typeFilter.addEventListener('change', applyFilter);
  searchBox.addEventListener('input', applyFilter);

  // 点击详情面板（使用 render_utils 预渲染的 HTML）
  function openDetail(nodeId) {{
    const info = nodeData[nodeId];
    if (!info) return;
    const tl = typeLabels[info.type] || info.type;
    document.getElementById('dp-name').textContent = info.label;

    // 二级标签：subtype 注册表驱动
    let subtypeHtml = '';
    const ex = info.extra || {{}};
    if (ex.subtype_label) {{
      const c = ex.subtype_color || {{}};
      const bg = c.bg || 'rgba(100,100,100,0.2)';
      const text = c.text || '#666';
      subtypeHtml = ' <span class="dp-tag" style="background:' + bg + ';color:' + text + '">' + ex.subtype_label + '</span>';
    }}
    document.getElementById('dp-meta').innerHTML = tl + ' · ' + info.status + subtypeHtml + ' · 确信度: ' + (info.confidence || '?');

    const body = document.getElementById('dp-body');
    body.innerHTML = '';

    let html = '';

    // ── 使用 Python render_utils 预渲染的 HTML ──
    if (info.pre_rendered_html) {{
      html += info.pre_rendered_html;
    }}

    // ── 标签（公共） ──
    html += '<div class="dp-section"><h3>标签</h3>';
    if (info.tags) info.tags.forEach(function(t) {{ html += '<span class="dp-tag">' + t + '</span>'; }});
    html += '</div>';

    // ── 关联节点（公共，出入双向） ──
    const groups = {{}};
    edgeData.forEach(function(e) {{
      if (e.from !== nodeId && e.to !== nodeId) return;
      const otherId = (e.from === nodeId) ? e.to : e.from;
      const other = nodeData[otherId];
      if (!other) return;
      const label = (e.from === nodeId)
        ? other.label + ' (' + (e.label || '→') + ')'
        : other.label + ' (' + (e.label || '←') + ')';
      if (!groups[other.type]) groups[other.type] = [];
      groups[other.type].push(label);
    }});
    Object.keys(groups).forEach(function(t) {{ groups[t] = [...new Set(groups[t])]; }});
    ['character_arc','scene','plot_thread','world_rule','note'].forEach(function(t) {{
      const items = groups[t];
      if (!items) return;
      const tl2 = typeLabels[t] || t;
      html += '<div class="dp-section"><h3>' + tl2 + ' (' + items.length + ')</h3>';
      items.forEach(function(item) {{
        const col = (UNIT_TYPE_COLORS[t] || {{}}).bg || '#888';
        html += '<div style="padding:2px 0;font-size:12px;color:#ccc"><span style="display:inline-block;width:8px;height:8px;border-radius:4px;background:' + col + ';margin-right:6px"></span>' + item + '</div>';
      }});
    }});

    body.innerHTML = html;
    document.getElementById('detail-panel').classList.add('open');
  }}

  network.on('click', function(params) {{
    if (params.nodes && params.nodes.length > 0) {{
      openDetail(params.nodes[0]);
    }}
  }});

  setTimeout(function() {{ network.fit({{ animation: false }}); }}, 300);
}})();

function closeDetail() {{
  document.getElementById('detail-panel').classList.remove('open');
}}
</script>
</body>
</html>
"""

TIMELINE_HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title} — 时间线</title>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Noto Sans SC", sans-serif;
    background: #1a1a2e; color: #e0e0e0; min-height: 100vh;
  }}
  .header {{
    padding: 20px 32px; background: rgba(26,26,46,0.95);
    border-bottom: 1px solid #2a2a4a;
    display: flex; align-items: center; gap: 12px; flex-wrap: wrap;
    position: sticky; top: 0; z-index: 100;
  }}
  .header h1 {{ font-size: 18px; font-weight: 600; }}
  .badge {{ font-size: 12px; padding: 2px 10px; border-radius: 10px; background: rgba(255,255,255,0.1); color: #aaa; }}
  .badge.count {{ background: rgba(91,155,213,0.2); color: #8BB9E0; }}
  .empty {{ text-align: center; padding: 80px 20px; color: #666; }}
  .tl-wrap {{ max-width: 900px; margin: 0 auto; padding: 40px 20px 60px; }}
  .tl {{ position: relative; padding-left: 40px; }}
  .tl::before {{
    content: ''; position: absolute; left: 16px; top: 0; bottom: 0;
    width: 2px; background: linear-gradient(180deg, #2a2a4a, #5B9BD5, #2a2a4a);
  }}
  .tl-item {{ position: relative; margin-bottom: 20px; padding-left: 20px; }}
  .tl-item::before {{
    content: ''; position: absolute; left: -24px; top: 6px;
    width: 14px; height: 14px; border-radius: 50%;
    z-index: 2; transition: transform 0.2s;
  }}
  .tl-item:hover::before {{ transform: scale(1.4); }}
  .tl-item.type-chapter::before {{ background: #5B9BD5; border: 2px solid #2E75B6; box-shadow: 0 0 6px rgba(91,155,213,0.5); }}
  .tl-item.type-plot::before {{ background: #FFC000; border: 2px solid #BF8F00; box-shadow: 0 0 6px rgba(255,192,0,0.4); }}
  .tl-item.type-world::before {{ background: #70AD47; border: 2px solid #4E6B31; box-shadow: 0 0 6px rgba(112,173,71,0.4); }}
  .tl-item.type-chunk::before {{ background: #CD853F; border: 2px solid #8B6914; box-shadow: 0 0 6px rgba(205,133,63,0.4); }}
  .tl-item.type-note::before {{ background: #B4A7D6; border: 2px solid #8E7CC3; box-shadow: 0 0 6px rgba(180,167,214,0.4); }}
  .tl-item .tl-time {{ font-size: 12px; color: #888; margin-bottom: 4px; font-weight: 500; }}
  .tl-item .tl-card {{
    background: rgba(255,255,255,0.04); border: 1px solid #2a2a4a;
    border-radius: 8px; padding: 12px 16px;
    transition: border-color 0.2s;
  }}
  .tl-item .tl-card:hover {{ border-color: #4a4a7a; }}
  .tl-card .tl-event {{ font-size: 14px; color: #e0e0e0; line-height: 1.6; }}
</style>
</head>
<body>
<div class="header">
  <h1>{entity_name}</h1>
  <span class="badge">{entity_type}</span>
  <span class="badge count">{event_count} 个关联</span>
</div>
<div class="tl-wrap">
  {timeline_html}
</div>
</body>
</html>
"""


# ── HTML 生成器 ────────────────────────────────────────────────────

class V2HTMLGenerator:
    """从 V2GraphLoader 数据生成 HTML"""

    def __init__(self, project_name: str):
        self.project_name = project_name

    def generate_graph(self, graph_data: dict, output_path: str):
        """生成交互式关系图 HTML"""
        nodes = graph_data.get("nodes", {})
        edges = graph_data.get("edges", [])

        # 类型统计（用于筛选下拉和图例）
        type_counts = defaultdict(int)
        type_set = set()
        for n in nodes.values():
            type_counts[n["type"]] += 1
            type_set.add(n["type"])

        type_order = ["character_arc", "scene", "plot_thread", "world_rule", "thematic_motif", "note", "chunk"]
        filter_opts = []
        legend_items = []

        # Collect world_rule subtypes for nested filter
        world_subtypes = {}
        for n in nodes.values():
            if n["type"] == "world_rule":
                sub_label = n.get("extra", {}).get("subtype_label", "")
                if sub_label:
                    world_subtypes[sub_label] = world_subtypes.get(sub_label, 0) + 1

        for t in type_order:
            if t in type_set:
                c = UNIT_TYPE_COLORS.get(UnitType(t), {} if t in type_set else None)
                if not c:
                    c = {"bg": "#D6D6D6", "border": "#A0A0A0", "text": "#000"}
                label = UNIT_TYPE_LABELS.get(UnitType(t), t)
                count = type_counts[t]
                filter_opts.append(f'<option value="{t}">{label} ({count})</option>')
                # Add world_rule sub-type options
                if t == "world_rule" and world_subtypes:
                    for st in sorted(world_subtypes.keys()):
                        sc = world_subtypes[st]
                        filter_opts.append(f'<option value="world_rule.{st}">  ↳ {st} ({sc})</option>')
                legend_items.append(
                    f'<div class="item"><span class="dot" style="background:{c["bg"]}"></span>'
                    f'<span>{label}</span></div>'
                )

        # 序列化为 JSON（node_data 要包含颜色信息供 JS 侧使用）
        node_data = {}
        for nid, n in nodes.items():
            node_data[nid] = n

        type_labels_json = {}
        type_colors_json = {}
        for t in type_order:
            if t in type_set:
                type_labels_json[t] = UNIT_TYPE_LABELS.get(UnitType(t), t)
                c = UNIT_TYPE_COLORS.get(UnitType(t), {})
                if c:
                    type_colors_json[t] = {"bg": c["bg"]}

        html = HTML_GRAPH_TEMPLATE.format(
            title=f"{self.project_name} — V2 关系图谱",
            node_count=len(nodes),
            edge_count=len(edges),
            node_data=json.dumps(node_data, ensure_ascii=False),
            edge_data=json.dumps(edges, ensure_ascii=False),
            type_labels=json.dumps(type_labels_json, ensure_ascii=False),
            type_colors=json.dumps(type_colors_json, ensure_ascii=False),
            filter_options="\n    ".join(filter_opts),
            legend_html="\n  ".join(legend_items),
        )

        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(html, encoding="utf-8")
        return output_path

    def generate_timeline(self, timeline_data: dict, output_path: str):
        """生成时间线 HTML"""
        ent = timeline_data["entity"]
        events = timeline_data["events"]

        if not events:
            timeline_body = f'<div class="empty"><p>"{ent["name"]}" 暂无时间线数据。</p></div>'
        else:
            parts = []
            for item in events:
                css_class = f"type-{item['source_type']}"
                time_html = f'<div class="tl-time">{item["time_label"]}</div>'
                parts.append(
                    f'<div class="tl-item {css_class}">'
                    f'{time_html}'
                    f'<div class="tl-card"><div class="tl-event">{item["event"]}</div></div>'
                    f'</div>'
                )
            timeline_body = '<div class="tl">' + "\n".join(parts) + "</div>"

        html = TIMELINE_HTML_TEMPLATE.format(
            title=f"{self.project_name} — {ent['name']} 时间线",
            entity_name=ent["name"],
            entity_type=ent["type"],
            event_count=len(events),
            timeline_html=timeline_body,
        )

        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(html, encoding="utf-8")
        return output_path

    def generate_detail_pages(self, graph_data: dict, detail_dir: str, graph_file: str = "关系图.html",
                               only_ids: Optional[set] = None):
        """为每个节点生成详情页。

        Args:
            only_ids: 如果提供，只生成这些 ID 对应的详情页（增量模式）。
                      为 None 时生成全部节点（全量模式）。
        """
        nodes = graph_data.get("nodes", {})
        edges = graph_data.get("edges", [])
        detail_path = Path(detail_dir)
        detail_path.mkdir(parents=True, exist_ok=True)

        # Build edge index
        edge_index = {}
        for e in edges:
            for nid in [e["from"], e["to"]]:
                if nid not in edge_index:
                    edge_index[nid] = []
                edge_index[nid].append(e)

        type_colors = {
            "character_arc": "#5B9BD5", "scene": "#A5A5A5",
            "plot_thread": "#FFC000", "world_rule": "#70AD47",
            "note": "#D6D6D6", "chunk": "#CD853F",
        }
        type_labels = {
            "character_arc": "角色", "scene": "场景",
            "plot_thread": "情节线", "world_rule": "世界观",
            "note": "笔记", "chunk": "正文",
        }

        count = 0
        for nid, n in nodes.items():
            if only_ids is not None and nid not in only_ids:
                continue
            # Build ego network (1-hop)
            ego_nodes = {nid: n}
            ego_edges = []
            for e in edge_index.get(nid, []):
                other = e["to"] if e["from"] == nid else e["from"]
                if other not in ego_nodes and other in nodes:
                    ego_nodes[other] = nodes[other]
                ego_edges.append(e)

            extra = n.get("extra", {})
            html = render_detail_html(
                entity_name=n.get("label", nid),
                type_label=type_labels.get(n["type"], n["type"]),
                status=n.get("status", ""),
                confidence=n.get("confidence", 0.5),
                type_bg=type_colors.get(n["type"], "#888"),
                extra=extra,
                tags=n.get("tags", []),
                ego_nodes=ego_nodes,
                ego_edges=ego_edges,
                center_id=nid,
                graph_file=f"../{graph_file}",
            )
            (detail_path / f"{nid}.html").write_text(html, encoding="utf-8")
            count += 1

        if only_ids is not None:
            skipped = len(nodes) - count
            print(f"   详情页: {count} 个 (增量, 跳过 {skipped} 个未变更) → {detail_dir}")
        else:
            print(f"   详情页: {count} 个 → {detail_dir}")
        return count


# ── 增量生成引擎 ────────────────────────────────────────────────────

class VizIncrementalEngine:
    """基于 unit.version 的增量生成引擎。

    不依赖 events.olog（有5000条上限），而是对比每个叙事单元当前的
    unit.version 与上次生成时记录的值，只重新生成有变化的页面。
    """

    STATE_FILE = ".viz_state.json"

    def __init__(self, store, viz_dir: str):
        self.store = store
        self.viz_dir = Path(viz_dir)
        self.state_path = self.viz_dir / self.STATE_FILE
        self.state = self._load_state()

    def _load_state(self) -> dict:
        if self.state_path.exists():
            try:
                return json.loads(self.state_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                pass
        return {"node_versions": {}, "edge_count": 0}

    def _save_state(self, node_versions: dict, edge_count: int):
        state = {
            "node_versions": node_versions,
            "edge_count": edge_count,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }
        self.viz_dir.mkdir(parents=True, exist_ok=True)
        self.state_path.write_text(
            json.dumps(state, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def get_changed_unit_ids(self) -> set:
        """返回 version 有变化的叙事单元 ID"""
        old_versions = self.state.get("node_versions", {})
        changed = set()
        for uid, unit in self.store._units.items():
            if unit.version > old_versions.get(uid, 0):
                changed.add(uid)
        return changed

    def get_archived_unit_ids(self) -> set:
        """返回已被归档且上次生成时存在的单元 ID"""
        old_ids = set(self.state.get("node_versions", {}).keys())
        current_ids = set(
            uid for uid, u in self.store._units.items()
            if u.status == UnitStatus.ARCHIVED
        )
        return old_ids & current_ids

    def should_rebuild_graph(self, changed_ids: set) -> bool:
        """判断主关系图是否需要重建。

        关系图包含所有节点和边。只要：
        1. 有节点变更，或者
        2. 关系总数变了
        都需要重建。
        """
        if changed_ids:
            return True
        if len(self.store._relations) != self.state.get("edge_count", 0):
            return True
        return False

    def build_node_versions(self) -> dict:
        """构建当前所有活跃单元的 version 快照"""
        return {
            uid: unit.version
            for uid, unit in self.store._units.items()
            if unit.status != UnitStatus.ARCHIVED
        }


# ── 核心可视化函数（无 argparse 依赖）────────────────────────────

def generate_viz(
    project_root: str,
    output: str = "",
    character: str = "",
    timeline: str = "",
    list_units: bool = False,
    open_browser: bool = False,
    incremental: bool = False,
    force: bool = False,
):
    """V2 可视化生成函数。

    供 novel_tool.py 等程序化调用，不依赖 argparse。
    也作为 CLI main() 的后端。
    """
    proj = Path(project_root).resolve()
    if not proj.is_dir():
        print(f"错误: 项目目录不存在: {proj}")
        sys.exit(1)

    # 读项目名
    project_name = proj.name
    config_path = proj / "config.yaml"
    if config_path.exists():
        try:
            import yaml
            cfg = yaml.safe_load(config_path.read_text(encoding="utf-8"))
            if cfg and "项目名称" in cfg:
                project_name = cfg["项目名称"]
        except Exception:
            pass

    # 加载 V2 数据
    loader = V2GraphLoader(str(proj))

    # 列出单元
    if list_units:
        rows = loader.list_units()
        if not rows:
            print("(无叙事单元)")
            return
        print(f"{'名称':<16} {'ID':<20} {'类型':<8} {'状态':<8}")
        print("-" * 56)
        for r in rows:
            print(f"{r['name']:<16} {r['id']:<20} {r['type']:<8} {r['status']:<8}")
        return

    # 确定输出路径（默认放到项目下的 graph/viz/ 目录）
    viz_dir = proj / "graph" / "viz"
    if output:
        output_path = str(Path(output).resolve())
        viz_dir = Path(output_path).parent
    else:
        viz_dir.mkdir(parents=True, exist_ok=True)
        if timeline:
            output_path = str(viz_dir / f"{timeline}_时间线.html")
        elif character:
            output_path = str(viz_dir / f"{character}_关系图.html")
        else:
            output_path = str(viz_dir / "全项目关系图.html")

    gen = V2HTMLGenerator(project_name)

    # 时间线模式
    if timeline:
        unit_id = loader.find_unit_id(timeline)
        if not unit_id:
            print(f"错误: 未找到角色/单元: {timeline}")
            sys.exit(1)
        data = loader.build_timeline(unit_id)
        if not data:
            print(f"错误: 无法生成时间线")
            sys.exit(1)
        gen.generate_timeline(data, output_path)
        print(f"✅ 时间线已生成: {output_path}")
        print(f"   实体: {data['entity']['name']}")
        print(f"   事件: {len(data['events'])} 个")
        if open_browser:
            webbrowser.open(output_path)
        return

    # 角色 Ego Network 模式
    if character:
        unit_id = loader.find_unit_id(character)
        if not unit_id:
            print(f"错误: 未找到角色: {character}")
            sys.exit(1)
        data = loader.build_character_network(unit_id)
        center_name = data.get("center_id", "")
        u = loader.store.get_unit(center_name) if center_name else None
        cname = u.unit_name if u else character
        graph_filename = os.path.basename(output_path)
        gen.generate_graph(data, output_path)

        # 生成该角色的详情页
        detail_dir = viz_dir / "detail"
        gen.generate_detail_pages(data, str(detail_dir), graph_file=graph_filename)

        print(f"✅ 角色关系图已生成: {output_path}")
        print(f"   角色: {cname}")
        print(f"   节点: {len(data['nodes'])} 个, 关系: {len(data['edges'])} 条")
        if open_browser:
            webbrowser.open(output_path)
        return

    # 默认：全项目图谱
    use_incremental = incremental and not force
    detail_dir = viz_dir / "detail"

    if use_incremental:
        engine = VizIncrementalEngine(loader.store, str(viz_dir))
        changed_ids = engine.get_changed_unit_ids()
        archived_ids = engine.get_archived_unit_ids()
        graph_needs_rebuild = engine.should_rebuild_graph(changed_ids)

        if not graph_needs_rebuild and not changed_ids and not archived_ids:
            print(f"ℹ️  V2 关系图无变更, 跳过生成 (使用 --force 强制全量)")
            if open_browser:
                webbrowser.open(output_path)
            return

        # 清理已归档节点的详情页
        for aid in archived_ids:
            archived_page = detail_dir / f"{aid}.html"
            if archived_page.exists():
                archived_page.unlink()
                print(f"   🗑 删除已归档节点详情页: {aid}")

        # 关系图有变更 → 重建主图
        if graph_needs_rebuild:
            data = loader.build_full_graph()
            graph_filename = os.path.basename(output_path)
            gen.generate_graph(data, output_path)
            print(f"✅ V2 关系图已生成 ({'变更触发' if changed_ids else '关系变更触发'}): {output_path}")
            graph_filename_for_detail = graph_filename
        else:
            data = None
            graph_filename_for_detail = os.path.basename(output_path)
            print(f"ℹ️  V2 关系图无变更, 跳过")

        # 详情页：只生成有变化的节点
        if changed_ids:
            if data is None:
                data = loader.build_full_graph()
            regen_ids = changed_ids | archived_ids
            gen.generate_detail_pages(
                data, str(detail_dir),
                graph_file=graph_filename_for_detail,
                only_ids=regen_ids,
            )
        elif archived_ids:
            print(f"   详情页: 仅清理, 无变更节点需重新生成")
        else:
            print(f"   详情页: 关系变更不影响详情页, 跳过")

        # 保存增量状态
        engine._save_state(
            node_versions=engine.build_node_versions(),
            edge_count=len(loader.store._relations),
        )

        print(f"   V2 graph: {loader.store.stats()['total_units']} 叙事单元, {loader.store.stats()['total_relations']} 关系")

    else:
        data = loader.build_full_graph()
        graph_filename = os.path.basename(output_path)
        gen.generate_graph(data, output_path)

        # 生成详情页
        gen.generate_detail_pages(data, str(detail_dir), graph_file=graph_filename)

        print(f"✅ V2 关系图已生成: {output_path}")
        print(f"   节点: {len(data['nodes'])} 个, 关系: {len(data['edges'])} 条")

        stats = loader.store.stats()
        print(f"   V2 graph: {stats['total_units']} 叙事单元, {stats['total_relations']} 关系")

    if open_browser:
        webbrowser.open(output_path)



