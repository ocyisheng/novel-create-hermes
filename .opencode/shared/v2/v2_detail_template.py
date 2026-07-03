"""
Detail page HTML template for entity detail pages (Level 2).
Uses render_utils.render_content() for unified field rendering.
"""
import json

from render_utils import render_content

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

  .field-item {{
    display: inline-flex; align-items: baseline; gap: 6px;
    background: rgba(255,255,255,0.04); border-radius: 6px;
    padding: 8px 14px; margin: 4px;
  }}
  .field-item .label {{ font-size: 11px; color: #888; }}
  .field-item .value {{ font-size: 14px; color: #e0e0e0; }}

  .tag {{
    display: inline-block; font-size: 12px; padding: 2px 10px; border-radius: 10px;
    background: rgba(255,255,255,0.06); color: #bbb; margin: 2px;
  }}

  .tagcloud {{ margin: -2px; }}

  .timeline {{ position: relative; padding-left: 16px; }}
  .timeline::before {{
    content: ''; position: absolute; left: 4px; top: 0; bottom: 0;
    width: 2px; background: linear-gradient(#5B9BD5, #70AD47);
  }}
  .tl-item {{ padding: 4px 0 8px 12px; font-size: 12px; color: #ccc; line-height: 1.5; position: relative; }}
  .tl-item::before {{
    content: ''; position: absolute; left: -3px; top: 6px;
    width: 8px; height: 8px; border-radius: 50%; background: #5B9BD5;
  }}
  .tl-time {{ color: #888; }}
  .tl-event {{ color: #ccc; }}

  .rel-item {{ padding: 3px 0; font-size: 12px; }}
  .rel-target {{ color: #8BB9E0; }}
  .rel-type {{ color: #666; font-size: 11px; }}

  .chart-item {{ display: inline-flex; align-items: center; gap: 8px; margin: 4px 12px 4px 0; }}
  .chart-key {{ font-size: 11px; color: #888; }}
  .chart-val {{ font-size: 14px; color: #e0e0e0; font-weight: 600; }}

  .group {{ padding-left: 8px; border-left: 2px solid rgba(255,255,255,0.06); }}

  .desc-text {{
    font-size: 13px; color: #ccc; line-height: 1.8;
    white-space: pre-wrap;
  }}

  #ego-network {{
    width: 100%; height: 500px; border-radius: 8px;
    background: rgba(0,0,0,0.2);
  }}
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

  <!-- 统一渲染字段 -->
  {rendered_html}

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
      stabilization: {{ iterations: 30 }},
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
    """Render a detail page for an entity using unified render_utils."""
    # 使用 render_utils.render_content() 统一渲染
    rendered = render_content(extra)
    rendered_html = "".join(r["html"] for r in rendered if r["html"])

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
        rendered_html=rendered_html,
        tags_html=tags_html,
        ego_nodes=json.dumps(ego_nodes_ser, ensure_ascii=False),
        ego_edges=json.dumps(ego_edges, ensure_ascii=False),
        center_id=center_id,
        graph_file=graph_file,
    )
