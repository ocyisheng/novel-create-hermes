#!/usr/bin/env python3
"""
graph_viz.py — 项目关系图谱可视化

读取 graph 数据（01_nodes.yaml + 10/11_edges_*.yaml），生成交互式 HTML 关系图。

用法:
    python graph_viz.py --project-root NOVELS_ROOT/项目名 --output 关系图.html [--open]
    python graph_viz.py --project-root NOVELS_ROOT/项目名 --timeline <entity_id> --output 时间线.html [--open]

依赖: Python 3, PyYAML
"""

import argparse
import re
import sys
import webbrowser
from pathlib import Path

try:
    import yaml
except ImportError:
    print("错误: 需要 PyYAML，请运行 novel-env-setup 安装依赖", file=sys.stderr)
    sys.exit(1)

from _utils import load_yaml_safe

# 层级关系类型（方向敏感、用于虚线+箭头展示）
FACTION_HIERARCHY_TYPES = ["附属"]
LOCATION_HIERARCHY_TYPES = ["包含"]
CHARACTER_HIERARCHY_TYPES = [
    "先祖", "后人", "始祖", "后辈", "晚辈", "族叔", "族侄",
    "后人与当代老祖", "家族老祖", "祖孙", "族中后辈", "家族后辈",
    "太上长老", "下属", "主上", "座下护法", "护法者",
    "弟子", "学生", "师尊", "兄长·先辈", "太上长老/老祖",
    "族中后辈/家主", "上级", "前辈", "长辈", "老师",
    "庇护者", "被效忠",
]

ALL_HIERARCHY_TYPES = FACTION_HIERARCHY_TYPES + LOCATION_HIERARCHY_TYPES + CHARACTER_HIERARCHY_TYPES

# ── Entity type → color mapping ──
TYPE_COLORS = {
    "character":      {"bg": "#5B9BD5", "border": "#2E75B6", "text": "#fff"},
    "worldbuilding":  {"bg": "#70AD47", "border": "#4E6B31", "text": "#fff"},
    "faction":        {"bg": "#ED7D31", "border": "#C55A11", "text": "#fff"},
    "location":       {"bg": "#00B0F0", "border": "#0070C0", "text": "#fff"},
    "plot":           {"bg": "#FFC000", "border": "#BF8F00", "text": "#000"},
    "outline_detail": {"bg": "#A5A5A5", "border": "#7A7A7A", "text": "#fff"},
    "foreshadowing": {"bg": "#B4A7D6", "border": "#8E7CC3", "text": "#fff"},
    "event":          {"bg": "#F4A460", "border": "#D2691E", "text": "#000"},
    "timeline_design": {"bg": "#CD853F", "border": "#8B6914", "text": "#fff"},
    "character_arc":   {"bg": "#CD5C5C", "border": "#8B3A3A", "text": "#fff"},
    "ideation":       {"bg": "#D6D6D6", "border": "#A0A0A0", "text": "#000"},
    "synopsis":       {"bg": "#D6D6D6", "border": "#A0A0A0", "text": "#000"},
    "narrative":      {"bg": "#D6D6D6", "border": "#A0A0A0", "text": "#000"},
    "volume":         {"bg": "#D6D6D6", "border": "#A0A0A0", "text": "#000"},
}

# 未知类型默认颜色
DEFAULT_COLOR = {"bg": "#D6D6D6", "border": "#A0A0A0", "text": "#000"}


# ── 工具函数 ────────────────────────────────────────────────────────────────

def get_graph_dir(project_root: Path) -> Path:
    """定位 graph 目录。"""
    candidates = [
        project_root / "relation" / "graph",
        project_root / "outline" / "追踪" / "graph",  # 旧路径向后兼容
        project_root / "graph",
    ]
    for c in candidates:
        if c.is_dir():
            return c
    return candidates[0]


def parse_edges(domain_data: dict, cross_data: dict) -> list[dict]:
    """合并所有边数据。"""
    edges: list[dict] = []

    # 域内边
    for seg, seg_data in (domain_data or {}).get("segments", {}).items():
        for entry in seg_data.get("entries", []):
            edges.append(entry)

    # 跨域边
    for seg, seg_data in (cross_data or {}).get("segments", {}).items():
        if seg == "uncategorized":
            continue
        for entry in seg_data.get("entries", []):
            edge = dict(entry)
            edges.append(edge)

    return edges


# ── HTML 生成 ───────────────────────────────────────────────────────────────

HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title} — 关系图谱</title>
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
  #toolbar input:focus, #toolbar select:focus {{ border-color: #5B9BD5; }}
  #toolbar .stats {{ font-size: 12px; color: #888; margin-left: auto; }}
  
  #network {{
    position: fixed; top: 50px; left: 0; right: 0; bottom: 0;
  }}
  
  /* 图例 */
  #legend {{
    position: fixed; bottom: 20px; right: 20px; z-index: 100;
    background: rgba(26,26,46,0.9); border: 1px solid #2a2a4a;
    border-radius: 8px; padding: 12px 16px; font-size: 12px;
    display: flex; flex-direction: column; gap: 4px;
  }}
  #legend .item {{ display: flex; align-items: center; gap: 8px; }}
  #legend .dot {{ width: 14px; height: 14px; border-radius: 50%; flex-shrink: 0; border: none; }}

  /* 自定义 Tooltip */
  #tooltip {{
    position: fixed; z-index: 200; pointer-events: none;
    background: rgba(30,30,50,0.95); border: 1px solid #4a4a7a;
    border-radius: 8px; padding: 12px 16px; font-size: 13px;
    max-width: 320px; line-height: 1.6; display: none;
    box-shadow: 0 4px 16px rgba(0,0,0,0.4);
  }}
  #tooltip .tt-name {{ font-size: 15px; font-weight: 600; color: #fff; }}
  #tooltip .tt-label {{ color: #aaa; }}
  #tooltip .tt-value {{ color: #e0e0e0; }}

  /* ── 点击详情面板 ── */
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
  #detail-panel .dp-row {{ padding: 3px 0; display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }}
  #detail-panel .dp-row .rel {{ color: #888; font-size: 11px; }}
  #detail-panel .dp-tag {{
    font-size: 11px; padding: 1px 8px; border-radius: 8px; display: inline-block;
    background: rgba(255,255,255,0.06); color: #bbb;
  }}
  #detail-panel .dp-btn {{
    display: inline-block; margin-top: 8px; padding: 6px 14px; border-radius: 6px;
    background: rgba(91,155,213,0.15); color: #5B9BD5; font-size: 12px; cursor: pointer;
    border: 1px solid rgba(91,155,213,0.3); text-decoration: none;
  }}
  #detail-panel .dp-btn:hover {{ background: rgba(91,155,213,0.25); }}
</style>
</head>
<body>

<div id="toolbar">
  <h1>{title}</h1>
  <label>筛选: <select id="typeFilter">
    <option value="all">全部</option>
    {filter_options}
  </select></label>
  <label>搜索: <input id="searchBox" type="text" placeholder="实体名称..." style="width:160px"></label>
  <span class="stats">{node_count} 个实体 · {edge_count} 条关系</span>
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
  // ── 数据 ──
  const nodeData = {node_data};
  const edgeData = {edge_data};
  const allHierTypes = {all_hierarchy_types};

  // 构建节点
  // 先扫描层级边，记录每个目标节点的最大层级
  const nodeLevel = {{}};
  edgeData.forEach(function(e) {{
    if (e.hierarchy_level) {{
      var lv = e.hierarchy_level + 1; // 目标节点比边深一级
      var cur = nodeLevel[e.to] || 0;
      if (lv > cur) nodeLevel[e.to] = lv;
    }}
  }});
  const nodeMap = {{}};
  const nodes = new vis.DataSet(
    Object.entries(nodeData).map(([id, n]) => {{
      const c = n.color || {{ bg: '#D6D6D6', border: '#A0A0A0' }};
      var nlv = nodeLevel[id] || 0;
      // 2级加粗+虚线边框，3级再加阴影
      var bw = n.type === 'character' ? 3 : 2;
      if (nlv >= 3) bw = 5;
      else if (nlv === 2) bw = 4;
      // 事件节点按时间排成水平数轴
      var nx = undefined, ny = undefined, nFixed = false, nPhysics = true;
      if (n.type === 'event' && n._event_sort !== undefined) {{
        // 上古(-9999)到5020年映射到 x: -500 ~ 2000
        var sortVal = n._event_sort;
        if (sortVal < 0) sortVal = 0; // 上古事件归零
        nx = (sortVal / 5020) * 2000;
        ny = 0;
        nFixed = true;
        nPhysics = false;
      }}
      const node = {{
        id,
        label: n.type === 'event' ? (n._event_time || '') : (n.display_name || id),
        title: n.type === 'event' ? (n.display_name || '') : '',
        color: {{ background: c.bg, border: c.border }},
        font: {{ color: c.font || (c.bg === '#FFC000' ? '#000' : '#fff'), size: n.type === 'event' ? 11 : 14, face: 'sans-serif' }},
        shape: 'dot',
        size: n.size || 20,
        borderWidth: bw,
        borderDashes: nlv >= 2 ? [6, 4] : false,
        shadow: nlv >= 3 ? {{ enabled: true, color: 'rgba(255,255,255,0.25)', size: 12 }} : false,
        group: n.type || 'other',
        x: nx,
        y: ny,
        fixed: nFixed,
        physics: nPhysics,
        _info: n,
      }};
      nodeMap[id] = node;
      return node;
    }})
  );

  // 构建边（去重）
  const seen = new Set();
  const edges = new vis.DataSet(
    edgeData
      .filter(e => nodeMap[e.from] && nodeMap[e.to])
      .filter(e => {{
        const key = e.from < e.to ? `${{e.from}}|${{e.to}}` : `${{e.to}}|${{e.from}}`;
        if (seen.has(key)) return false;
        seen.add(key);
        return true;
      }})
      .map(e => {{
        var isHier = allHierTypes.indexOf(e.relation_type) >= 0;
        // 层级边颜色按源实体类型: 势力=橙, 地点=青
        var hierColor = '#ED7D31';
        if (isHier && nodeData[e.from]) {{
          var st = nodeData[e.from].type;
          if (st === 'location') hierColor = '#00B0F0';
          else if (st === 'faction') hierColor = '#ED7D31';
          else if (st === 'character') hierColor = '#5B9BD5';
        }}
        var dashPat = false;
        if (isHier) {{
          var lv = e.hierarchy_level || 1;
          dashPat = lv >= 3 ? [3, 20] : lv === 2 ? [5, 16] : [10, 6];
        }}
        return {{
          from: e.from,
          to: e.to,
          label: e.relation_type || '',
          font: {{
            size: isHier ? 11 : 10,
            color: isHier ? hierColor : '#888',
            strokeWidth: 0,
          }},
          color: {{
            color: isHier ? hierColor : (e.confidence === 'explicit' ? '#5B9BD5' : '#4a4a6a'),
            opacity: isHier ? 0.95 : (e.confidence === 'explicit' ? 0.9 : 0.5),
          }},
          width: isHier ? 2.5 : (e.confidence === 'explicit' ? 2 : 1),
          dashes: dashPat,
          arrows: {{
            to: {{ enabled: e.relation_type !== '关联', scaleFactor: isHier ? 1.5 : 1 }},
          }},
          smooth: {{ type: 'continuous' }},
        }};
      }})
  );

  // ── 配置 ──
  // 声明 group 颜色防止 vis-network 用默认组色覆盖独立节点颜色
  const groupColors = {{
    character: {{ color: {{ background: '#5B9BD5', border: '#2E75B6' }} }},
    worldbuilding: {{ color: {{ background: '#70AD47', border: '#4E6B31' }} }},
    faction: {{ color: {{ background: '#ED7D31', border: '#C55A11' }} }},
    location: {{ color: {{ background: '#00B0F0', border: '#0070C0' }} }},
    plot: {{ color: {{ background: '#FFC000', border: '#BF8F00' }} }},
    outline_detail: {{ color: {{ background: '#A5A5A5', border: '#7A7A7A' }} }},
    foreshadowing: {{ color: {{ background: '#B4A7D6', border: '#8E7CC3' }} }},
    event: {{ color: {{ background: '#F4A460', border: '#D2691E' }} }},
    timeline_design: {{ color: {{ background: '#CD853F', border: '#8B6914' }} }},
    character_arc: {{ color: {{ background: '#CD5C5C', border: '#8B3A3A' }} }},
    ideation: {{ color: {{ background: '#D6D6D6', border: '#A0A0A0' }} }},
    synopsis: {{ color: {{ background: '#D6D6D6', border: '#A0A0A0' }} }},
    narrative: {{ color: {{ background: '#D6D6D6', border: '#A0A0A0' }} }},
    volume: {{ color: {{ background: '#D6D6D6', border: '#A0A0A0' }} }},
  }};
  const options = {{
    layout: {{
      improvedLayout: true,
      hierarchical: false,
    }},
    groups: groupColors,
    physics: {{
      solver: 'forceAtlas2Based',
      forceAtlas2Based: {{
        gravitationalConstant: -80,
        centralGravity: 0.005,
        springLength: 180,
        springConstant: 0.02,
        damping: 0.4,
      }},
      stabilization: {{ iterations: 200 }},
    }},
    interaction: {{
      dragNodes: true,
      dragView: true,
      zoomView: true,
      hover: true,
      tooltipDelay: 200,
      navigationButtons: true,
      keyboard: true,
    }},
    edges: {{
      smooth: {{ type: 'continuous' }},
    }},
  }};

  const container = document.getElementById('network');
  const network = new vis.Network(container, {{ nodes, edges }}, options);

  // ── 自定义 Tooltip ──
  const tooltip = document.getElementById('tooltip');
  network.on('hoverNode', function(params) {{
    const node = nodes.get(params.node);
    if (!node || !node._info) return;
    const n = node._info;
    const typeLabel = {{
      character: '角色', worldbuilding: '世界观', faction: '势力',
      location: '地点', plot: '情节线', outline_detail: '分纲',
      foreshadowing: '伏笔', event: '事件',
      timeline_design: '时间线设计', character_arc: '角色弧光',
      ideation: '创意', synopsis: '总纲',
      narrative: '叙事策略', volume: '分卷',
    }}[n.type] || n.type;
    var tooltipHtml =
      '<div class="tt-name">' + (n.display_name || node.label || '') + '</div>' +
      '<div><span class="tt-label">类型：</span><span class="tt-value">' + typeLabel + '</span></div>';
    if (n.type === 'event') {{
      tooltipHtml += '<div><span class="tt-label">时间：</span><span class="tt-value">' + (n._event_time || '') + '</span></div>';
      if (n._event_note) tooltipHtml += '<div><span class="tt-label">备注：</span><span class="tt-value">' + n._event_note + '</span></div>';
    }} else {{
      tooltipHtml += '<div><span class="tt-label">状态：</span><span class="tt-value">' + (n.status || 'active') + '</span></div>' +
        '<div><span class="tt-label">文件：</span><span class="tt-value">' + (n.file_path || '-') + '</span></div>';
    }}
    tooltip.innerHTML = tooltipHtml;
    tooltip.style.display = 'block';
  }});
  network.on('blurNode', function() {{
    tooltip.style.display = 'none';
  }});
  // 跟随鼠标移动
  network.on('beforeDrawing', function(ctx) {{
    // 通过 moveEvent 更新位置
  }});
  container.addEventListener('mousemove', function(e) {{
    if (tooltip.style.display === 'block') {{
      tooltip.style.left = (e.clientX + 16) + 'px';
      tooltip.style.top = (e.clientY + 16) + 'px';
    }}
  }});

  // ── 筛选 ──
  const typeFilter = document.getElementById('typeFilter');
  const searchBox = document.getElementById('searchBox');

  function applyFilter() {{
    const typeVal = typeFilter.value;
    const query = searchBox.value.trim().toLowerCase();

    const visible = new Set();
    Object.entries(nodeData).forEach(([id, n]) => {{
      let ok = true;
      if (typeVal !== 'all' && n.type !== typeVal) ok = false;
      if (query && !(n.display_name || '').toLowerCase().includes(query) && !id.toLowerCase().includes(query)) ok = false;
      if (ok) visible.add(id);
    }});

    nodes.forEach(node => {{
      if (visible.has(node.id)) {{
        nodes.update({{ id: node.id, hidden: false }});
      }} else {{
        nodes.update({{ id: node.id, hidden: true }});
      }}
    }});

    // 隐藏被过滤节点的边
    edges.forEach(edge => {{
      const hide = !visible.has(edge.from) || !visible.has(edge.to);
      edges.update({{ id: edge.id, hidden: hide }});
    }});

    network.fit({{ animation: true }});
  }}

  typeFilter.addEventListener('change', applyFilter);
  searchBox.addEventListener('input', applyFilter);

  // ── 点击详情面板 ──
  // 建立边索引: entity_id → {{out: [...], in: [...]}}
  var edgeIndex = {{}};
  edgeData.forEach(function(e) {{
    if (!edgeIndex[e.from]) edgeIndex[e.from] = {{out: [], in_: []}};
    if (!edgeIndex[e.to]) edgeIndex[e.to] = {{out: [], in_: []}};
    edgeIndex[e.from].out.push(e);
    edgeIndex[e.to].in_.push(e);
  }});

  function openDetail(nodeId) {{
    var info = nodeData[nodeId];
    if (!info) return;
    var displayName = info.display_name || nodeId;
    var typeLabel = ({{
      character: '角色', worldbuilding: '世界观', faction: '势力',
      location: '地点', plot: '情节线', outline_detail: '分纲',
      foreshadowing: '伏笔', ideation: '创意', synopsis: '总纲',
      narrative: '叙事策略', volume: '分卷',
    }}[info.type] || info.type);
    var status = info.status || 'active';

    document.getElementById('dp-name').textContent = displayName;
    document.getElementById('dp-meta').textContent = typeLabel + ' · ' + status + ' · ' + (info.file_path || '');
    var body = document.getElementById('dp-body');
    body.innerHTML = '';

    // 角色身份/能力信息块
    if (info.type === 'character') {{
      var charInfo = '';
      if (info.身份) charInfo += '<span class="dp-tag" style="background:rgba(91,155,213,0.12)">' + info.身份 + '</span> ';
      if (info.修为) charInfo += '<span class="dp-tag" style="background:rgba(237,125,49,0.12)">' + info.修为 + '</span> ';
      if (info.功法) charInfo += '<span class="dp-tag" style="background:rgba(112,173,71,0.12)">' + info.功法 + '</span> ';
      if (info.阵营) charInfo += '<span class="dp-tag" style="background:rgba(180,167,214,0.12)">' + info.阵营 + '</span> ';
      if (info.核心特质) {{
        var traits = typeof info.核心特质 === 'string' ? [info.核心特质] : info.核心特质;
        traits.forEach(function(t) {{ charInfo += '<span class="dp-tag" style="background:rgba(255,255,255,0.06)">' + t + '</span> '; }});
      }}
      if (info.出身) charInfo += '<div style="margin-top:6px;font-size:12px;color:#888">出身: ' + info.出身 + '</div>';
      if (charInfo) body.innerHTML += '<div class="dp-section" style="margin-bottom:12px">' + charInfo + '</div>';
    }}

    var related = edgeIndex[nodeId] || {{out: [], in_: []}};

    // 按对方实体类型分组（角色/势力/事件/地点），替代按关系类型分组
    var typeOrder = ['character', 'faction', 'event', 'location'];
    var typeLabels = {{character:'角色', faction:'势力', event:'事件', location:'地点'}};
    var typeColors = {{character:'rgba(91,155,213,0.12)', faction:'rgba(237,125,49,0.12)', event:'rgba(244,164,96,0.15)', location:'rgba(0,176,240,0.12)'}};
    // 按对方实体类型分组，保留最佳关系类型（含方向翻转）
    var defaultRel = '关联';
    var typeGroups = {{}};
    // 方向敏感关系（入边时翻转）
    var revRel = {{
      '学生': '老师', '弟子': '师尊', '后人': '先祖', '后辈': '前辈',
      '晚辈': '长辈', '下属': '上级', '上司': '下属', '上级': '下属', '座下护法': '主上', '主上': '座下护法', '护法者': '庇护者', '庇护者': '护法者',
      '效忠': '被效忠', '族叔': '族侄', '族侄': '族叔',
      '伏击对象': '伏击者', '始祖': '后人', '先祖': '后人', '师尊': '弟子',
      '后续': '前续', '附属': '上级', '所属势力': '成员', '所在地': '相关角色',
      '纪年事件': '所属纪年',
    }};
    var revWhen = {{'所属势力':'faction','所在地':'location','后续':'event','附属':'faction','纪年事件':'event','先祖':'character','始祖':'character'}};
    var relPriority = {{'关联': 0, '引用': 0, '涉及': 1, '纪年事件': 1, '所属势力': 2, '所在地': 2,
      '成员': 2, '相关角色': 2, '附属': 3, '包含': 3, '后续': 3, '前续': 3,
      '所属纪年': 3, '参与情节': 3, '势力范围': 3}};
    var childLocSet = new Set();
    var bestRel = {{}};
    var allEdges = related.out.concat(related.in_);
    allEdges.forEach(function(e) {{
      var otherId = e.from === nodeId ? e.to : e.from;
      var other = nodeData[otherId];
      if (!other) return;
      var ot = other.type || 'other';
      if (!typeGroups[ot]) typeGroups[ot] = {{}};
      typeGroups[ot][otherId] = other.display_name || otherId;
      // 入边翻转方向敏感关系
      var rt = e.relation_type || defaultRel;
      if (e.to === nodeId && revRel[rt]) {{
        if (!revWhen.hasOwnProperty(rt) || revWhen[rt] === info.type) rt = revRel[rt];
      }}
      var pri = relPriority[rt] !== undefined ? relPriority[rt] : 2;
      if (!bestRel[otherId] || pri > bestRel[otherId].pri) {{
        bestRel[otherId] = {{rel: rt, pri: pri}};
      }}
      if (info.type === 'location' && ot === 'location' && e.relation_type === '包含') {{
        if (e.from === nodeId) childLocSet.add(otherId);
      }}
    }});
    // 按角色/势力/事件/地点顺序渲染（地点分开孙和关联）
    typeOrder.forEach(function(ot) {{
      var items = typeGroups[ot];
      if (!items) return;
      var names = Object.keys(items).map(function(id) {{
        var label = items[id];
        var rel = bestRel[id] ? bestRel[id].rel : '';
        // 角色之间显示具体关系
        if (info.type === 'character' && ot === 'character' && rel && rel !== '关联' && rel !== '引用') {{
          return {{name: label, rel: rel}};
        }}
        return {{name: label, rel: ''}};
      }});
      names.sort(function(a,b) {{ return a.name.localeCompare(b.name); }});
      if (names.length === 0) return;
      if (info.type === 'location' && ot === 'location') {{
        var children = [], relatedLocs = [];
        names.forEach(function(item) {{
          if (childLocSet.has(Object.keys(typeGroups[ot]).find(function(k) {{ return typeGroups[ot][k] === item.name; }}))) {{
            children.push(item);
          }} else {{
            relatedLocs.push(item);
          }}
        }});
        if (children.length > 0) {{
          var h = '<div class="dp-section"><h3>子孙地点 (' + children.length + ')</h3>';
          children.forEach(function(item) {{ h += '<div class="dp-row"><span class="dp-tag" style="background:' + typeColors[ot] + '">' + item.name + '</span></div>'; }});
          h += '</div>'; body.innerHTML += h;
        }}
        if (relatedLocs.length > 0) {{
          var h = '<div class="dp-section"><h3>关联地点 (' + relatedLocs.length + ')</h3>';
          relatedLocs.forEach(function(item) {{ h += '<div class="dp-row"><span class="dp-tag" style="background:' + typeColors[ot] + '">' + item.name + '</span></div>'; }});
          h += '</div>'; body.innerHTML += h;
        }}
      }} else {{
        var label = typeLabels[ot] || ot;
        var html = '<div class="dp-section"><h3>' + label + ' (' + names.length + ')</h3>';
        names.forEach(function(item) {{
          var display = item.rel ? item.name + ' (' + item.rel + ')' : item.name;
          html += '<div class="dp-row"><span class="dp-tag" style="background:' + typeColors[ot] + '">' + display + '</span></div>';
        }});
        html += '</div>'; body.innerHTML += html;
      }}
    }});

    // 时间线按钮
    timelineBtn = '<a class="dp-btn" href="时间线/' + nodeId + '.html" target="_blank">📊 查看时间线</a>';
    body.innerHTML += timelineBtn;

    document.getElementById('detail-panel').classList.add('open');
  }}

  network.on('click', function(params) {{
    if (params.nodes && params.nodes.length > 0) {{
      openDetail(params.nodes[0]);
    }}
  }});

  // ── 初始适配 ──
  setTimeout(function() {{ network.fit({{ animation: false }}); }}, 300);

}})();

function closeDetail() {{
  document.getElementById('detail-panel').classList.remove('open');
}}
</script>
</body>
</html>
"""


def build_color_map(nodes: dict) -> dict:
    """为每个节点分配颜色和尺寸。"""
    # 统计入边/出边数来决定节点大小
    edge_count: dict[str, int] = {}

    result: dict[str, dict] = {}
    for eid, info in nodes.items():
        ntype = info.get("type", "")
        colors = TYPE_COLORS.get(ntype, DEFAULT_COLOR)
        size = 20
        if ntype == "character":
            size = 28
        elif ntype == "worldbuilding":
            size = 24
        elif ntype == "faction":
            size = 24

        result[eid] = {
            "id": eid,
            "display_name": info.get("display_name", eid),
            "type": ntype,
            "file_path": info.get("file_path", ""),
            "status": info.get("status", "active"),
            "color": colors,
            "size": size,
        }
        # 事件节点透传时间字段
        if ntype == "event":
            result[eid]["_event_time"] = info.get("_event_time", "")
            result[eid]["_event_sort"] = info.get("_event_sort", 0)
            result[eid]["_event_note"] = info.get("_event_note", "")
        # 角色透传身份/能力
        if ntype == "character":
            for f in ("身份", "修为", "功法", "阵营", "核心特质", "出身"):
                v = info.get(f, "")
                if v:
                    result[eid][f] = v
    return result


# 图例和筛选只显示 4 种核心类型（其他类型在"全部"视图可见）
CORE_TYPES = ["character", "faction", "location", "event"]
CORE_LABELS = {
    "character": "角色", "faction": "势力",
    "location": "地点", "event": "事件",
}


def build_legend(nodes: dict) -> str:
    """生成图例 HTML（只显示核心类型）。"""
    items = []
    for tid in CORE_TYPES:
        colors = TYPE_COLORS.get(tid, DEFAULT_COLOR)
        items.append(
            f'<div class="item">'
            f'<span class="dot" style="background:{colors["bg"]}"></span>'
            f'<span>{CORE_LABELS[tid]}</span></div>'
        )
    return "\n".join(items)


def build_filter_options(nodes: dict) -> str:
    """生成实体类型筛选下拉选项（只核心类型）。"""
    opts = []
    for tid in CORE_TYPES:
        opts.append(f'<option value="{tid}">{CORE_LABELS[tid]}</option>')
    return "\n".join(opts)


def generate_html(
    project_name: str,
    nodes: dict,
    edges: list[dict],
) -> str:
    """生成完整 HTML。"""
    color_map = build_color_map(nodes)
    node_json = yaml.dump(color_map, default_flow_style=False, allow_unicode=True, sort_keys=False)
    edge_json = yaml.dump(edges, default_flow_style=False, allow_unicode=True, sort_keys=False)

    # 用 JSON 替代 YAML 以保证 JS 可直接 parse
    import json
    node_json_str = json.dumps(color_map, ensure_ascii=False, indent=2)
    edge_json_str = json.dumps(edges, ensure_ascii=False, indent=2)
    hier_types_json = json.dumps(ALL_HIERARCHY_TYPES, ensure_ascii=False)

    return HTML_TEMPLATE.format(
        title=f"{project_name} — 关系图谱",
        node_count=len(nodes),
        edge_count=len(edges),
        node_data=node_json_str,
        edge_data=edge_json_str,
        all_hierarchy_types=hier_types_json,
        filter_options=build_filter_options(nodes),
        legend_html=build_legend(nodes),
    )


# ── 时间线数据收集 ──────────────────────────────────────────────────────────

TYPE_LABELS = {
    "character": "角色", "worldbuilding": "世界观", "faction": "势力",
    "location": "地点", "plot": "情节线", "outline_detail": "分纲",
    "foreshadowing": "伏笔", "ideation": "创意", "synopsis": "总纲",
    "narrative": "叙事策略", "volume": "分卷",
}


# ── 从图谱事件节点读取纪年事件 ──────────────────────────────────────────

def _collect_graph_events(entity_id: str, nodes: dict, cross_data: dict) -> list[dict]:
    """从图谱的事件节点和边数据中收集与该实体相关的纪年事件。

    取代旧的 _extract_world_events（直接从 YAML 解析），
    事件节点在建图时已由 _extract_events_from_data 创建。
    """
    segments = (cross_data or {}).get("segments", {})
    events: list[dict] = []
    seen: set[str] = set()

    # 被事件"涉及"：event_to_character/faction/location
    for seg_name in ("event_to_character", "event_to_faction", "event_to_location"):
        seg = segments.get(seg_name, {})
        for entry in seg.get("entries", []):
            if entry.get("to") != entity_id:
                continue
            eid = entry.get("from")
            en = nodes.get(eid, {})
            if en.get("type") != "event":
                continue
            desc = en.get("display_name", "")
            if desc in seen:
                continue
            seen.add(desc)
            events.append({
                "sort_key": en.get("_event_sort", 0),
                "time_label": en.get("_event_time", ""),
                "event": desc,
                "note": en.get("_event_note", ""),
                "source_type": "world",
                "is_approximate": "约" in (en.get("_event_time", "") or ""),
            })

    # 该实体本身的纪年事件：worldbuilding_to_event（如 凡人历纪年→事件）
    wb_seg = segments.get("worldbuilding_to_event", {})
    for entry in wb_seg.get("entries", []):
        if entry.get("from") != entity_id:
            continue
        eid = entry.get("to")
        en = nodes.get(eid, {})
        if en.get("type") != "event":
            continue
        desc = en.get("display_name", "")
        if desc in seen:
            continue
        seen.add(desc)
        events.append({
            "sort_key": en.get("_event_sort", 0),
            "time_label": en.get("_event_time", ""),
            "event": desc,
            "note": en.get("_event_note", ""),
            "source_type": "world",
            "is_approximate": "约" in (en.get("_event_time", "") or ""),
        })

    events.sort(key=lambda x: x["sort_key"])
    return events


# ── 章节事件提取 ──────────────────────────────────────────────────────────

def _collect_chapter_events(entity_id: str, nodes: dict, cross_data: dict) -> list[dict]:
    """从图谱边数据中提取实体出场的章节事件。"""
    entity_name = nodes.get(entity_id, {}).get("display_name", entity_id)
    segments = (cross_data or {}).get("segments", {})

    # 找出该实体出场的所有章节
    od_to_char = segments.get("outline_detail_to_character", {}).get("entries", [])
    entity_chapters: set[str] = set()
    for e in od_to_char:
        if e["to"] == entity_id:
            entity_chapters.add(e["from"])

    if not entity_chapters:
        if nodes.get(entity_id, {}).get("type") == "plot":
            plot_to_od = segments.get("plot_to_outline_detail", {}).get("entries", [])
            for e in plot_to_od:
                if e["from"] == entity_id:
                    entity_chapters.add(e["to"])

    if not entity_chapters:
        return []

    # plot → chapter
    plot_to_od_entries = segments.get("plot_to_outline_detail", {}).get("entries", [])
    ch_to_plots: dict[str, list[str]] = {}
    for e in plot_to_od_entries:
        ch = e["to"]
        if ch not in ch_to_plots:
            ch_to_plots[ch] = []
        ch_to_plots[ch].append(e["from"])

    # chapter → 共现角色
    ch_to_chars: dict[str, set[str]] = {}
    for e in od_to_char:
        ch = e["from"]
        if ch in entity_chapters:
            if ch not in ch_to_chars:
                ch_to_chars[ch] = set()
            ch_to_chars[ch].add(e["to"])

    # chapter → 世界观引用
    od_to_wb = segments.get("outline_detail_to_worldbuilding", {}).get("entries", [])
    ch_to_wb: dict[str, set[str]] = {}
    for e in od_to_wb:
        ch = e["from"]
        if ch in entity_chapters:
            if ch not in ch_to_wb:
                ch_to_wb[ch] = set()
            ch_to_wb[ch].add(e["to"])

    # 组装章节事件
    chapter_events: list[dict] = []
    for ch_id in entity_chapters:
        ch_node = nodes.get(ch_id, {})
        ch_name = ch_node.get("display_name", ch_id)
        m = re.search(r"(\d+)", ch_name)
        ch_num = int(m.group(1)) if m else 0

        # 摘要 + 关键事件
        char_edges_for_ch = [e for e in od_to_char if e["from"] == ch_id and e["to"] == entity_id]
        summary = ""
        key_events: list[str] = []
        for e in char_edges_for_ch:
            raw = e.get("source", {}).get("raw_value", "")
            field = e.get("source", {}).get("field_path", "")
            if raw:
                if "一句话描述" in field or "摘要" in field:
                    summary = raw
                elif "核心情节点" in field:
                    key_events.append(raw)

        plot_ids = ch_to_plots.get(ch_id, [])
        plot_names = [nodes.get(p, {}).get("display_name", p) for p in plot_ids]

        other_char_ids = ch_to_chars.get(ch_id, set()) - {entity_id}
        other_char_names = [nodes.get(cid, {}).get("display_name", cid) for cid in other_char_ids]

        wb_ids = ch_to_wb.get(ch_id, set())
        wb_names = [nodes.get(wid, {}).get("display_name", wid) for wid in wb_ids]

        chapter_events.append({
            "sort_key": ch_num,
            "time_label": ch_name,
            "event": summary or f"{entity_name} 出场",
            "note": "",
            "source_type": "chapter",
            "is_approximate": False,
            "tags": plot_names + other_char_names + wb_names,
            "key_events": key_events[:5],
        })

    chapter_events.sort(key=lambda x: x["sort_key"])
    return chapter_events


# ── 时间线入口 ────────────────────────────────────────────────────────────

def collect_timeline_data(entity_id: str, nodes: dict, cross_data: dict,
                          project_root: Path | None = None) -> dict | None:
    """收集某实体的完整时间线数据。

    - 章节事件: 从图谱边数据 outline_detail_to_* 提取出场章节
    - 纪年事件: 从图谱事件节点（已由建图时创建）读取
    """
    entity = nodes.get(entity_id)
    if not entity:
        return None

    entity_name: str = entity.get("display_name", entity_id)

    # 1) 章节事件
    chapter_events = _collect_chapter_events(entity_id, nodes, cross_data)

    # 2) 纪年事件（从图谱事件节点读取，取代旧的 YAML 直接解析）
    world_events = _collect_graph_events(entity_id, nodes, cross_data)

    # 3) 合并去重 + 排序
    all_events: list[dict] = []
    all_events.extend(chapter_events)
    all_events.extend(world_events)

    # 去重（同 sort_key 的 chapter/world 事件）
    seen_keys: set[tuple] = set()
    unique: list[dict] = []
    for ev in sorted(all_events, key=lambda x: x["sort_key"]):
        dedup_key = (ev["sort_key"], ev["source_type"], ev["event"][:40])
        if dedup_key not in seen_keys:
            seen_keys.add(dedup_key)
            unique.append(ev)

    return {
        "entity": {
            "id": entity_id,
            "display_name": entity_name,
            "type": entity.get("type", ""),
            "status": entity.get("status", "active"),
        },
        "timeline": unique,
    }


# ── 时间线 HTML 模板（垂直布局）───────────────────────────────────────────

TIMELINE_HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
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
  .header h1 {{ font-size: 18px; font-weight: 600; margin-right: 4px; }}
  .badge {{
    font-size: 12px; padding: 2px 10px; border-radius: 10px;
    background: rgba(255,255,255,0.1); color: #aaa;
  }}
  .badge.count {{ background: rgba(91,155,213,0.2); color: #8BB9E0; }}
  .header .back {{ margin-left: auto; font-size: 13px; }}
  .header .back a {{ color: #5B9BD5; text-decoration: none; }}
  .header .back a:hover {{ text-decoration: underline; }}

  .empty {{ text-align: center; padding: 80px 20px; color: #666; }}

  /* ── 垂直时间线容器 ── */
  .tl-wrap {{
    max-width: 900px; margin: 0 auto; padding: 40px 20px 60px;
  }}

  .tl {{
    position: relative; padding-left: 40px;
  }}

  /* 竖线 */
  .tl::before {{
    content: ''; position: absolute;
    left: 16px; top: 0; bottom: 0;
    width: 2px;
    background: linear-gradient(180deg, #2a2a4a, #5B9BD5, #2a2a4a);
  }}

  .tl-item {{
    position: relative; margin-bottom: 20px;
    padding-left: 20px;
    opacity: 0; transform: translateY(12px);
    animation: fadeIn 0.4s ease forwards;
  }}
  .tl-item:nth-child(1) {{ animation-delay: 0.02s; }}
  .tl-item:nth-child(2) {{ animation-delay: 0.06s; }}
  .tl-item:nth-child(3) {{ animation-delay: 0.10s; }}
  .tl-item:nth-child(4) {{ animation-delay: 0.14s; }}
  .tl-item:nth-child(n+5) {{ animation-delay: 0.18s; }}

  @keyframes fadeIn {{
    to {{ opacity: 1; transform: translateY(0); }}
  }}

  /* 节点 */
  .tl-item::before {{
    content: ''; position: absolute;
    left: -24px; top: 6px;
    width: 14px; height: 14px;
    border-radius: 50%;
    z-index: 2;
    transition: transform 0.2s;
  }}
  .tl-item:hover::before {{
    transform: scale(1.4);
  }}
  .tl-item.type-chapter::before {{
    background: #5B9BD5; border: 2px solid #2E75B6;
    box-shadow: 0 0 6px rgba(91,155,213,0.5);
  }}
  .tl-item.type-world::before {{
    background: #70AD47; border: 2px solid #4E6B31;
    box-shadow: 0 0 6px rgba(112,173,71,0.4);
  }}
  .tl-item.type-era::before {{
    background: #B4A7D6; border: 2px solid #8E7CC3;
    box-shadow: 0 0 6px rgba(180,167,214,0.4);
    width: 18px; height: 18px; left: -26px; top: 4px;
  }}

  /* 时间标签 */
  .tl-item .tl-time {{
    font-size: 12px; color: #888; margin-bottom: 4px;
    font-weight: 500;
  }}
  .tl-item .tl-time .approx {{
    color: #666; font-style: italic;
  }}
  .tl-item .tl-time .era-label {{
    color: #B4A7D6;
  }}

  /* 卡片 */
  .tl-item .tl-card {{
    background: rgba(255,255,255,0.04);
    border: 1px solid #2a2a4a;
    border-radius: 8px;
    padding: 12px 16px;
    transition: border-color 0.2s, background 0.2s;
  }}
  .tl-item .tl-card:hover {{
    border-color: #4a4a7a;
    background: rgba(255,255,255,0.06);
  }}
  .tl-card .tl-event {{
    font-size: 14px; color: #e0e0e0; line-height: 1.6;
  }}
  .tl-card .tl-note {{
    font-size: 12px; color: #777; line-height: 1.5;
    margin-top: 4px; padding-left: 12px;
    border-left: 2px solid #2a2a4a;
  }}
  .tl-card .tl-tags {{
    display: flex; flex-wrap: wrap; gap: 4px; margin-top: 6px;
  }}
  .tl-card .tl-tag {{
    font-size: 10px; padding: 1px 7px; border-radius: 6px;
    background: rgba(255,255,255,0.06); color: #999;
  }}
  .tl-card .tl-tag.plot {{ background: rgba(255,192,0,0.12); color: #FFD700; }}
  .tl-card .tl-tag.char {{ background: rgba(91,155,213,0.12); color: #8BB9E0; }}
  .tl-card .tl-src {{
    font-size: 11px; color: #555; margin-top: 6px;
    border-top: 1px solid #2a2a4a; padding-top: 6px;
  }}
</style>
</head>
<body>

<div class="header">
  <h1>{entity_name}</h1>
  <span class="badge">{entity_type}</span>
  <span class="badge count">{event_count} 个事件</span>
  <span class="back"><a href="javascript:history.back()">← 返回</a></span>
</div>

<div class="tl-wrap">
  {timeline_html}
</div>

</body>
</html>
"""


def generate_timeline_html(
    project_name: str,
    timeline_data: dict,
) -> str:
    """生成实体时间线 HTML。"""
    ent = timeline_data["entity"]
    items = timeline_data["timeline"]

    if not items:
        timeline_body = (
            '<div class="empty">'
            f'<p>"{ent["display_name"]}" 暂无关联的时间线数据。</p>'
            f'<p style="font-size:12px;margin-top:8px">没有章节出场记录，也没有纪年事件。</p>'
            '</div>'
        )
    else:
        parts = []
        for item in items:
            st = item["source_type"]

            # CSS class
            cls = "type-world"
            if item.get("era"):
                cls = "type-era"
            elif st == "chapter":
                cls = "type-chapter"

            # 时间标签
            time_html = ""
            if st == "chapter":
                time_html = f'<div class="tl-time">章节: {item["time_label"]}</div>'
            else:
                approx = "（约）" if item.get("is_approximate") else ""
                era = item.get("era", "")
                if era:
                    time_html = f'<div class="tl-time"><span class="era-label">{era}</span></div>'
                else:
                    time_html = f'<div class="tl-time">{item["time_label"]}<span class="approx">{approx}</span></div>'

            # 备注
            note_html = f'<div class="tl-note">📎 {item["note"]}</div>' if item.get("note") else ""

            # 标签
            tags_html = ""
            for t in item.get("tags", []):
                tags_html += f'<span class="tl-tag">{t}</span>'
            if item.get("key_events"):
                for ev in item["key_events"]:
                    tags_html += f'<span class="tl-tag char">{ev}</span>'

            parts.append(
                f'<div class="tl-item {cls}">'
                f'{time_html}'
                f'<div class="tl-card">'
                f'<div class="tl-event">{item["event"]}</div>'
                f'{note_html}'
                f'<div class="tl-tags">{tags_html}</div>'
                f'</div></div>'
            )

        timeline_body = '<div class="tl">' + "".join(parts) + "</div>"

    return TIMELINE_HTML_TEMPLATE.format(
        title=f"{project_name} — {ent['display_name']} 时间线",
        entity_name=ent["display_name"],
        entity_type=TYPE_LABELS.get(ent["type"], ent["type"]),
        event_count=len(items),
        timeline_html=timeline_body,
    )


# ── 缓存与输出路径 ─────────────────────────────────────────────────────────

HTMLS_DIR_NAME = "htmls"  # 相对 graph_dir 的父级


def get_htmls_dir(graph_dir: Path) -> Path:
    """返回 htmls 输出目录（relation/htmls/）。"""
    return graph_dir.parent / HTMLS_DIR_NAME


def get_source_mtimes(graph_dir: Path, entity_id: str = "",
                      project_root: Path | None = None,
                      nodes: dict | None = None) -> list[float]:
    """收集影响时间线输出的源文件 mtime 列表。

    用于判断缓存是否过期。
    """
    sources: list[Path] = []
    # 图谱数据文件
    legacy_fb = {"nodes.yaml": "01_nodes.yaml",
                 "domain_edges_index.yaml": "10_edges_domain.yaml",
                 "cross_edges_index.yaml": "11_edges_cross.yaml"}
    for name in ["nodes.yaml", "domain_edges_index.yaml", "cross_edges_index.yaml"]:
        p = graph_dir / name
        if p.exists():
            sources.append(p)
        else:
            fb = graph_dir / legacy_fb.get(name, "")
            if fb.exists():
                sources.append(fb)
    # 实体源文件（如果存在）
    if entity_id and nodes and project_root:
        entity = nodes.get(entity_id)
        if entity:
            fp = entity.get("file_path", "")
            if fp:
                src = project_root / fp
                if src.exists():
                    sources.append(src)
    return [s.stat().st_mtime for s in sources] if sources else [0]


def is_html_fresh(html_path: Path, source_mtimes: list[float]) -> bool:
    """判断 HTML 是否仍是最新的（存在且比所有源文件新）。"""
    if not html_path.exists():
        return False
    html_mtime = html_path.stat().st_mtime
    return all(html_mtime >= sm for sm in source_mtimes)


# ── CLI ───────────────────────────────────────────────────────────────────

def get_project_name(project_root: Path, config_path: Path) -> str:
    """读取项目名称。"""
    if config_path.is_file():
        config = load_yaml_safe(config_path)
        if config and "name" in config:
            return config["name"]
    return project_root.name


def _load_edges_sharded(graph_dir: Path, kind: str) -> dict:
    """读取分片后的边数据（兼容旧文件）。"""
    is_domain = kind == "domain"
    index_name = "domain_edges_index.yaml" if is_domain else "cross_edges_index.yaml"
    subdir_name = "domain_edges" if is_domain else "cross_edges"
    legacy_name = "10_edges_domain.yaml" if is_domain else "11_edges_cross.yaml"

    subdir = graph_dir / subdir_name
    index_path = graph_dir / index_name

    # 向后兼容：无分片目录时读旧文件
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


def load_graph_data(graph_dir: Path) -> tuple[dict, dict, dict]:
    """加载图谱数据，返回 (nodes, domain_data, cross_data)。"""
    nodes_path = graph_dir / "nodes.yaml"
    if not nodes_path.exists():
        nodes_path = graph_dir / "01_nodes.yaml"  # 向后兼容
    nodes_data = load_yaml_safe(nodes_path)
    if not nodes_data:
        print(f"错误: 未找到节点数据 ({nodes_path.name})", file=sys.stderr)
        sys.exit(1)
    nodes = nodes_data.get("nodes", {})

    domain_data = _load_edges_sharded(graph_dir, "domain")
    cross_data = _load_edges_sharded(graph_dir, "cross")
    return nodes, domain_data, cross_data


def list_entities(nodes: dict, search: str = "") -> None:
    """列出所有实体及其 ID。"""
    print(f"{'实体名称':<20} {'ID':<24} {'类型':<12} {'状态':<8}")
    print("-" * 68)
    for eid, info in sorted(nodes.items(), key=lambda x: (x[1].get("type", ""), x[1].get("display_name", ""))):
        name = info.get("display_name", eid)
        ntype = TYPE_LABELS.get(info.get("type", ""), info.get("type", ""))
        status = info.get("status", "active")
        if search and search not in eid.lower() and search not in name.lower():
            continue
        print(f"{name:<20} {eid:<24} {ntype:<12} {status:<8}")


def main():
    parser = argparse.ArgumentParser(description="项目关系图谱可视化")
    parser.add_argument("--project-root", "-p", required=True, help="项目根目录")
    parser.add_argument("--output", "-o", default="", help="输出 HTML 路径")
    parser.add_argument("--open", action="store_true", help="生成后自动在浏览器打开")
    parser.add_argument("--timeline", "-t", metavar="ENTITY_ID", default="",
                        help="生成指定实体的时间线视图（按章节排序）")
    parser.add_argument("--list-entities", action="store_true",
                        help="列出所有实体 ID（配合 --search 过滤）")
    parser.add_argument("--search", "-s", default="",
                        help="配合 --list-entities 搜索实体名称")
    args = parser.parse_args()

    project_root = Path(args.project_root).resolve()
    if not project_root.is_dir():
        print(f"错误: 项目目录不存在: {project_root}", file=sys.stderr)
        sys.exit(1)

    graph_dir = get_graph_dir(project_root)
    if not graph_dir.is_dir():
        print(f"错误: graph 目录不存在: {graph_dir}", file=sys.stderr)
        print("请先运行 project_graph.py build 生成图谱数据。", file=sys.stderr)
        sys.exit(1)

    nodes, domain_data, cross_data = load_graph_data(graph_dir)

    # ── 列出实体 ──
    if args.list_entities:
        list_entities(nodes, args.search)
        return

    # ── 时间线模式 ──
    if args.timeline:
        timeline_data = collect_timeline_data(args.timeline, nodes, cross_data, project_root)
        if timeline_data is None:
            # 尝试按 display_name 模糊匹配
            matched = [eid for eid, info in nodes.items()
                       if args.timeline.lower() in info.get("display_name", "").lower()
                       or args.timeline.lower() in eid.lower()]
            if len(matched) == 1:
                timeline_data = collect_timeline_data(matched[0], nodes, cross_data, project_root)
            elif len(matched) > 1:
                print(f"匹配到多个实体，请指定确切的 entity_id:")
                for m in matched:
                    info = nodes[m]
                    print(f"  {m:<24} {info.get('display_name', '')}")
                sys.exit(1)
            else:
                print(f"错误: 未找到实体 '{args.timeline}'", file=sys.stderr)
                print("提示: 使用 --list-entities 查看所有实体 ID", file=sys.stderr)
                sys.exit(1)

        config_path = project_root / "config.yaml"
        project_name = get_project_name(project_root, config_path)

        # 确定输出路径
        entity_id = timeline_data["entity"]["id"]
        if args.output:
            output_path = Path(args.output)
        else:
            htmls_dir = get_htmls_dir(graph_dir)
            htmls_dir.mkdir(parents=True, exist_ok=True)
            output_path = htmls_dir / "时间线" / f"{entity_id}.html"

        # 缓存检查
        entity_name = timeline_data["entity"]["display_name"]
        source_mtimes = get_source_mtimes(graph_dir, entity_id, project_root, nodes)
        if is_html_fresh(output_path, source_mtimes):
            print(f"⏺ 时间线已是最新: {output_path.resolve()}")
            print(f"   实体: {entity_name}，共 {len(timeline_data['timeline'])} 个事件")
            if args.open:
                webbrowser.open(output_path.resolve().as_uri())
            return

        # 生成
        html = generate_timeline_html(project_name, timeline_data)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(html, encoding="utf-8")
        print(f"✅ 时间线已生成: {output_path.resolve()}")
        print(f"   实体: {entity_name}")
        print(f"   事件: {len(timeline_data['timeline'])} 个")
        if args.open:
            webbrowser.open(output_path.resolve().as_uri())
        return

    # ── 关系图谱模式（默认）──
    edges = parse_edges(domain_data, cross_data)
    config_path = project_root / "config.yaml"
    project_name = get_project_name(project_root, config_path)

    # 输出路径
    if args.output:
        output_path = Path(args.output)
    else:
        htmls_dir = get_htmls_dir(graph_dir)
        htmls_dir.mkdir(parents=True, exist_ok=True)
        output_path = htmls_dir / "关系图.html"

    # 缓存检查
    source_mtimes = get_source_mtimes(graph_dir, project_root=project_root)
    if is_html_fresh(output_path, source_mtimes):
        print(f"⏺ 关系图已是最新: {output_path.resolve()}")
        print(f"   {len(nodes)} 个实体, {len(edges)} 条关系（缓存）")
        if args.open:
            webbrowser.open(output_path.resolve().as_uri())
        return

    html = generate_html(project_name, nodes, edges)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")
    print(f"✅ 关系图已生成: {output_path.resolve()}")
    print(f"   {len(nodes)} 个实体, {len(edges)} 条关系")

    if args.open:
        webbrowser.open(output_path.resolve().as_uri())


if __name__ == "__main__":
    main()
