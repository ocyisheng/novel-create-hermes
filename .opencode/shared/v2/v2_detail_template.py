"""
Detail page HTML template for entity detail pages (Level 2).
"""
import json

DETAIL_HTML = r"""<!DOCTYPE html>
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
    padding: 16px 32px; background: rgba(26,26,46,0.95);
    border-bottom: 1px solid #2a2a4a;
    display: flex; align-items: center; gap: 12px; flex-wrap: wrap;
    position: sticky; top: 0; z-index: 100;
  }}
  .header h1 {{ font-size: 20px; font-weight: 600; color: #fff; }}
  .badge {{ font-size: 12px; padding: 2px 10px; border-radius: 10px; background: rgba(255,255,255,0.1); color: #aaa; }}
  .badge.type {{ background: {type_bg}22; color: {type_bg}; }}
  .back {{ margin-left: auto; }}
  .back a {{ color: #5B9BD5; text-decoration: none; font-size: 13px; }}
  .back a:hover {{ text-decoration: underline; }}

  .container {{ max-width: 1100px; margin: 0 auto; padding: 24px 32px; }}

  .section {{
    background: rgba(255,255,255,0.03); border: 1px solid #2a2a4a;
    border-radius: 8px; padding: 20px; margin-bottom: 20px;
  }}
  .section h2 {{ font-size: 15px; color: #aaa; margin-bottom: 12px; padding-bottom: 6px; border-bottom: 1px solid #2a2a4a; }}

  .field-grid {{
    display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
    gap: 10px;
  }}
  .field-item {{
    background: rgba(255,255,255,0.04); border-radius: 6px; padding: 10px 14px;
  }}
  .field-item .label {{ font-size: 11px; color: #888; margin-bottom: 2px; }}
  .field-item .value {{ font-size: 14px; color: #e0e0e0; }}

  .tag {{
    display: inline-block; font-size: 12px; padding: 2px 10px; border-radius: 10px;
    background: rgba(255,255,255,0.06); color: #bbb; margin: 2px;
  }}

  .event-list {{ }}
  .event-item {{
    padding: 8px 12px; border-left: 2px solid #3a3a5a; margin-bottom: 6px;
    font-size: 13px; color: #ccc; line-height: 1.5;
  }}
  .event-item:hover {{ border-left-color: #5B9BD5; }}

  .rel-section {{ margin-top: 16px; }}
  .rel-section h3 {{ font-size: 13px; color: #888; margin-bottom: 8px; }}
  .rel-group {{
    display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 12px;
  }}
  .rel-tag {{
    font-size: 12px; padding: 4px 12px; border-radius: 14px;
    background: rgba(91,155,213,0.1); color: #8BB9E0; cursor: pointer;
    border: 1px solid rgba(91,155,213,0.2);
  }}
  .rel-tag:hover {{ background: rgba(91,155,213,0.2); }}
  .rel-tag .rtype {{ color: #666; font-size: 10px; }}

  #ego-network {{
    width: 100%; height: 500px; border-radius: 8px;
    background: rgba(0,0,0,0.2);
  }}

  .desc-text {{
    font-size: 13px; color: #ccc; line-height: 1.8;
    white-space: pre-wrap;
  }}

  .empty {{ text-align: center; padding: 60px; color: #555; }}
</style>
</head>
<body>
<div class="header">
  <h1>{entity_name}</h1>
  <span class="badge type">{type_label}</span>
  <span class="badge">{status}</span>
  <span class="badge">确信度: {confidence}</span>
  <div class="back"><a href="{graph_file}">← 返回关系图</a></div>
</div>

<div class="container">

  <!-- 结构化字段 -->
  {fields_html}

  <!-- 核心特质 -->
  {traits_html}

  <!-- 关键事件 -->
  {events_html}

  <!-- 描述 -->
  {desc_html}

  <!-- 人物关系 -->
  {relations_html}

  <!-- 标签 -->
  <div class="section">
    <h2>标签</h2>
    {tags_html}
  </div>

  <!-- 关系网络 -->
  <div class="section">
    <h2>关系网络（1-hop）</h2>
    <div id="ego-network"></div>
  </div>
</div>

<script src="https://unpkg.com/vis-network/standalone/umd/vis-network.min.js"></script>
<script>
(function() {{
  const nodeData = {ego_nodes};
  const edgeData = {ego_edges};
  const centerId = "{center_id}";

  const nodes = new vis.DataSet(
    Object.entries(nodeData).map(([id, n]) => ({{
      id,
      label: n.label || id,
      color: {{ background: n.bg || '#5B9BD5', border: n.border || '#2E75B6' }},
      font: {{ color: '#fff', size: id === centerId ? 20 : 14 }},
      shape: id === centerId ? 'star' : 'dot',
      size: id === centerId ? 35 : 20,
      borderWidth: id === centerId ? 4 : 2,
    }}))
  );

  const edges = new vis.DataSet(
    edgeData.map(e => ({{
      from: e.from, to: e.to,
      label: e.label || '',
      font: {{ size: 10, color: '#888', strokeWidth: 0 }},
      color: {{ color: e.color || '#4a4a6a', opacity: 0.7 }},
      width: e.width || 1,
      arrows: {{ to: {{ enabled: true, scaleFactor: 1 }} }},
      smooth: {{ type: 'continuous' }},
    }}))
  );

  const container = document.getElementById('ego-network');
  const network = new vis.Network(container, {{ nodes, edges }}, {{
    physics: {{
      solver: 'forceAtlas2Based',
      forceAtlas2Based: {{ gravitationalConstant: -60, centralGravity: 0.01, springLength: 150, damping: 0.4 }},
      stabilization: {{ iterations: 100 }},
    }},
    interaction: {{ dragNodes: true, zoomView: true, dragView: true }},
    edges: {{ smooth: {{ type: 'continuous' }} }},
  }});

  network.on('click', function(params) {{
    if (params.nodes && params.nodes.length > 0 && params.nodes[0] !== centerId) {{
      window.open(params.nodes[0] + '.html', '_blank');
    }}
  }});
}})();
</script>
</body>
</html>
"""

def render_detail_html(
    entity_name: str, type_label: str, status: str, confidence: float,
    type_bg: str, extra: dict, tags: list,
    ego_nodes: dict, ego_edges: list, center_id: str,
    graph_file: str = "关系图.html",
) -> str:
    """Render a detail page for an entity."""
    fields_html = ""
    if extra.get("姓名"):
        items = []
        for label, key in [("身份", "身份"), ("修为", "修为"), ("功法", "功法"),
                           ("阵营", "阵营")]:
            val = extra.get(key, "")
            if val:
                items.append(f'<div class="field-item"><div class="label">{label}</div><div class="value">{val}</div></div>')
        if items:
            fields_html = f'<div class="section"><h2>基本信息</h2><div class="field-grid">{"".join(items)}</div></div>'

    traits_html = ""
    if extra.get("核心特质") and isinstance(extra["核心特质"], list):
        tags_html = "".join(f'<span class="tag">{t}</span>' for t in extra["核心特质"])
        traits_html = f'<div class="section"><h2>核心特质</h2>{tags_html}</div>'

    events_html = ""
    if extra.get("关键事件") and isinstance(extra["关键事件"], list):
        items = "".join(f'<div class="event-item">{e[:120]}</div>' for e in extra["关键事件"][:20])
        more = f'<div style="color:#555;font-size:12px;margin-top:6px">...共 {len(extra["关键事件"])} 条</div>' if len(extra["关键事件"]) > 20 else ""
        events_html = f'<div class="section"><h2>关键事件</h2>{items}{more}</div>'

    desc_html = ""
    if extra.get("描述"):
        desc_html = f'<div class="section"><h2>描述</h2><div class="desc-text">{extra["描述"][:500]}</div></div>'

    relations_html = ""
    if extra.get("人物关系"):
        rels = extra["人物关系"]
        parts = []
        for rel_type, targets in rels.items():
            if isinstance(targets, list):
                names = "".join(f'<span class="rel-tag">{t.get("目标", "")} <span class="rtype">({rel_type})</span></span>'
                                for t in targets if isinstance(t, dict))
                if names:
                    parts.append(f'<div class="rel-section"><h3>{rel_type}</h3><div class="rel-group">{names}</div></div>')
        if parts:
            relations_html = f'<div class="section"><h2>人物关系</h2>{"".join(parts)}</div>'

    tags_html = "".join(f'<span class="tag">{t}</span>' for t in (tags or []))

    # Serialize ego network
    def ser_color(c):
        if isinstance(c, dict):
            return c.get("bg", "#5B9BD5")
        return "#5B9BD5"

    ego_nodes_ser = {}
    for nid, n in ego_nodes.items():
        ego_nodes_ser[nid] = {
            "label": n.get("label", nid),
            "bg": ser_color(n.get("color", {})),
        }

    return DETAIL_HTML.format(
        title=f"{entity_name} — 详情",
        entity_name=entity_name,
        type_label=type_label,
        status=status,
        confidence=confidence,
        type_bg=type_bg,
        fields_html=fields_html,
        traits_html=traits_html,
        events_html=events_html,
        desc_html=desc_html,
        relations_html=relations_html,
        tags_html=tags_html,
        ego_nodes=json.dumps(ego_nodes_ser, ensure_ascii=False),
        ego_edges=json.dumps(ego_edges, ensure_ascii=False),
        center_id=center_id,
        graph_file=graph_file,
    )
