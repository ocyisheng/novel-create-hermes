/**
 * app.js — novel-web-server 前端主应用
 * 
 * 功能：
 * 1. 加载图谱数据 → vis-network 渲染
 * 2. 类型筛选 + 搜索
 * 3. 点击节点 → 详情面板（含关联关系）
 * 4. 创建/编辑/删除节点
 * 5. 创建/删除关系
 * 6. 物理引擎开关
 */
(function() {
  'use strict';

  // ── 全局状态 ──────────────────────────────────────────────
  let nodeData = {};        // id → node info (服务器原始数据)
  let edgeData = [];        // edge array
  let nodesDataSet = null;  // vis.DataSet
  let edgesDataSet = null;  // vis.DataSet
  let network = null;       // vis.Network
  let currentId = null;     // 当前选中的节点 ID
  let loaded = false;

  // 类型配置
  const TYPE_CONFIG = {};

  // ── 初始化 ────────────────────────────────────────────────
  document.addEventListener('DOMContentLoaded', init);

  async function init() {
    try {
      // 加载项目信息
      const [projInfo, graphResp, scopeResp] = await Promise.all([
        API.projectInfo(),
        API.fullGraph(),
        API.searchScope(),
      ]);

      // 项目名
      document.getElementById('projectName').textContent = projInfo.name || '—';

      // 类型配置
      if (scopeResp && scopeResp.types) {
        scopeResp.types.forEach(t => {
          const opt = document.createElement('option');
          opt.value = t.value;
          opt.textContent = t.label;
          document.getElementById('typeFilter').appendChild(opt);
        });
      }

      // 数据
      nodeData = graphResp.nodes || {};
      edgeData = graphResp.edges || [];

      updateStats();

      // 初始化 vis-network
      const cont = document.getElementById('network');
      if (!cont) return;

      nodesDataSet = new vis.DataSet(
        Object.entries(nodeData).map(([id, n]) => buildVisNode(id, n))
      );

      edgesDataSet = new vis.DataSet(
        edgeData.map(e => buildVisEdge(e))
      );

      const isLarge = Object.keys(nodeData).length > 200;

      const options = {
        layout: { improvedLayout: false },
        physics: isLarge ? {
          solver: 'barnesHut',
          barnesHut: { gravitationalConstant: -3000, centralGravity: 0.3, springLength: 95, springConstant: 0.04, damping: 0.5, overlapAvoid: 0.1 },
          stabilization: { iterations: 50, updateInterval: 25 },
        } : {
          solver: 'forceAtlas2Based',
          forceAtlas2Based: { gravitationalConstant: -60, centralGravity: 0.01, springLength: 150, springConstant: 0.03, damping: 0.5 },
          stabilization: { iterations: 30, updateInterval: 10 },
        },
        interaction: {
          dragNodes: true, dragView: true, zoomView: true,
          hover: true, tooltipDelay: 200, navigationButtons: true, keyboard: true,
        },
        edges: { smooth: isLarge ? false : { type: 'continuous' } },
      };

      network = new vis.Network(cont, { nodes: nodesDataSet, edges: edgesDataSet }, options);

      // 大图自动聚类
      if (isLarge) {
        autoCluster();
      }

      // ── 事件绑定 ──
      network.on('hoverNode', onHoverNode);
      network.on('blurNode', onBlurNode);
      network.on('click', onClick);

      document.getElementById('typeFilter').addEventListener('change', applyFilter);
      document.getElementById('searchBox').addEventListener('input', applyFilter);

      // 搜索清除按钮
      const searchBox = document.getElementById('searchBox');
      const searchClear = document.getElementById('searchClear');
      searchBox.addEventListener('input', function() {
        searchClear.style.display = this.value ? 'block' : 'none';
      });
      searchClear.addEventListener('click', function() {
        searchBox.value = '';
        searchClear.style.display = 'none';
        applyFilter();
      });

      // 鼠标移动 → tooltip 跟随
      cont.addEventListener('mousemove', function(e) {
        const tip = document.getElementById('tooltip');
        if (tip.style.display === 'block') {
          tip.style.left = (e.clientX + 16) + 'px';
          tip.style.top = (e.clientY + 16) + 'px';
        }
      });

      setTimeout(() => { network.fit({ animation: false }); }, 300);

      loaded = true;
    } catch (err) {
      console.error('初始化失败:', err);
      document.getElementById('network').innerHTML =
        '<div style="text-align:center;padding:80px 20px;color:#888"><h2>加载失败</h2><p>' +
        err.message + '</p></div>';
    }
  }

  // ── 节点/边构建 ──────────────────────────────────────────

  function buildVisNode(id, n) {
    const c = n.color || { bg: '#5B9BD5', border: '#2E75B6', text: '#fff' };
    return {
      id,
      label: n.label || id,
      color: { background: c.bg, border: c.border },
      font: { color: c.text || '#fff', size: 14, face: 'sans-serif' },
      shape: 'dot',
      size: n.size || 20,
      borderWidth: n.borderWidth || 2,
      group: n.type || 'other',
      _info: n,
    };
  }

  function buildVisEdge(e) {
    return {
      from: e.from, to: e.to,
      label: e.label || '',
      font: { size: 10, color: e.color || '#888', strokeWidth: 0 },
      color: { color: e.color || '#4a4a6a', opacity: 0.8 },
      width: e.width || 1,
      arrows: { to: { enabled: true, scaleFactor: 1 } },
      smooth: { type: 'continuous' },
      _info: e,
    };
  }

  // ── 自动聚类 ──────────────────────────────────────────────

  function autoCluster() {
    try {
      var threshold = Math.max(30, Math.floor(Object.keys(nodeData).length / 15));
      if (typeof network.clustering === 'object' && network.clustering.clusterOutliers) {
        network.clustering.clusterOutliers({ clusterThreshold: threshold });
      }
    } catch(e) { /* 聚类不可用 */ }
  }

  // ── 筛选 ──────────────────────────────────────────────────

  function applyFilter() {
    if (!nodesDataSet || !network) return;

    const typeVal = document.getElementById('typeFilter').value;
    const query = document.getElementById('searchBox').value.trim().toLowerCase();

    const visible = new Set();
    Object.entries(nodeData).forEach(([id, n]) => {
      let ok = true;
      if (typeVal !== 'all' && n.type !== typeVal) ok = false;
      if (query && !(n.label || '').toLowerCase().includes(query)) ok = false;
      if (ok) visible.add(id);
    });

    nodesDataSet.forEach(node => {
      nodesDataSet.update({ id: node.id, hidden: !visible.has(node.id) });
    });
    edgesDataSet.forEach(edge => {
      edgesDataSet.update({ id: edge.id, hidden: !visible.has(edge.from) || !visible.has(edge.to) });
    });

    network.fit({ animation: true });
  }

  // ── Hover ─────────────────────────────────────────────────

  function onHoverNode(params) {
    const node = nodesDataSet.get(params.node);
    if (!node || !node._info) return;
    const n = node._info;
    const tip = document.getElementById('tooltip');
    tip.innerHTML = '<div class="tt-name">' + (n.label || '') + '</div>' +
      '<div class="tt-type">' + (n.type_label || n.type || '') + '</div>' +
      '<div class="tt-meta">状态: ' + (n.status || '?') + ' · 确信度: ' + (n.confidence || '?') + '</div>';
    tip.style.display = 'block';
  }

  function onBlurNode() {
    document.getElementById('tooltip').style.display = 'none';
  }

  // ── Click → 详情面板 ─────────────────────────────────────

  function onClick(params) {
    if (params.nodes && params.nodes.length > 0) {
      showDetail(params.nodes[0]);
    } else {
      closeDetail();
    }
  }

  async function showDetail(id) {
    currentId = id;
    const n = nodeData[id];
    if (!n) return;

    // 更新标题
    const title = document.getElementById('dpTitle');
    const meta = document.getElementById('dpMeta');
    const body = document.getElementById('dpBody');

    title.textContent = n.label || id;
    meta.innerHTML = (n.type_label || n.type || '') +
      ' · ' + (n.status || '') +
      ' · 确信度: ' + (n.confidence || '?');

    // 渲染内容
    let html = '';

    // Extra 字段
    const extra = n.extra || {};
    const skipKeys = ['subtype_label', 'subtype_color', '_preview', '_display'];
    
    // 遍历 extra 字段
    Object.entries(extra).forEach(([k, v]) => {
      if (skipKeys.includes(k) || k.startsWith('_')) return;
      html += renderField(k, v);
    });

    // 标签
    if (n.tags && n.tags.length > 0) {
      html += '<div class="section"><h3>标签</h3>' +
        n.tags.map(t => '<span class="tag">' + esc(t) + '</span>').join(' ') + '</div>';
    }

    // 关联节点（通过 edges 计算）
    const rels = buildRelations(id);
    if (rels.length > 0) {
      // 按类型分组
      const groups = {};
      rels.forEach(r => {
        if (!groups[r.type]) groups[r.type] = [];
        groups[r.type].push(r);
      });

      const typeOrder = ['character_arc', 'scene', 'plot_thread', 'world_rule', 'note', 'chunk'];
      typeOrder.forEach(t => {
        const items = groups[t];
        if (!items) return;
        const label = TYPE_CONFIG[t] || t;
        html += '<div class="section"><h3>' + label + ' (' + items.length + ')</h3>';
        items.forEach(r => {
          const c = getTypeColor(r.type);
          html += '<div class="rel-item" onclick="APP.focusNode(\'' + r.id + '\')" style="cursor:pointer">' +
            '<span class="rel-dot" style="background:' + c + '"></span>' +
            '<span class="rel-name">' + esc(r.name) + '</span>' +
            '<span class="rel-label">' + esc(r.rel) + '</span></div>';
        });
        html += '</div>';
      });
    }

    // 操作按钮
    html += '<div class="dp-actions">' +
      '<button onclick="APP.editNode(\'' + id + '\')">✏️ 编辑</button>' +
      '<button onclick="APP.deleteNode(\'' + id + '\')" class="btn-danger">🗑️ 删除</button>' +
      '</div>';

    body.innerHTML = html;
    document.getElementById('detailPanel').classList.add('open');
  }

  function closeDetail() {
    document.getElementById('detailPanel').classList.remove('open');
    currentId = null;
  }

  // ── 关联关系构建 ──────────────────────────────────────────

  function buildRelations(nodeId) {
    const results = [];
    edgeData.forEach(e => {
      if (e.from !== nodeId && e.to !== nodeId) return;
      const otherId = e.from === nodeId ? e.to : e.from;
      const other = nodeData[otherId];
      if (!other) return;
      const dir = e.from === nodeId ? '→' : '←';
      results.push({
        id: otherId,
        name: other.label || otherId,
        type: other.type || 'unknown',
        rel: (e.label || '') + ' ' + dir,
      });
    });
    return results;
  }

  function getTypeColor(type) {
    const colors = {
      character_arc: '#5B9BD5', scene: '#A5A5A5', plot_thread: '#FFC000',
      world_rule: '#70AD47', note: '#D6D6D6', chunk: '#CD853F',
      outline: '#4472C4', arc_plan: '#5B9BD5', volume_plan: '#7FCDBB',
      chapter_plan: '#A8D08D', thematic_motif: '#B4A7D6',
    };
    return colors[type] || '#888';
  }

  // ── 字段渲染 ──────────────────────────────────────────────

  function renderField(key, value) {
    const mode = inferMode(key, value);
    if (mode === 'skip') return '';

    if (mode === 'tag') {
      return '<div class="field-item"><span class="fl">' + esc(key) + '</span><span class="fv">' + esc(String(value)) + '</span></div>';
    }
    if (mode === 'textblock') {
      return '<div class="section"><h3>' + esc(key) + '</h3><div class="text-block">' + esc(String(value).slice(0, 2000)) + '</div></div>';
    }
    if (mode === 'tagcloud') {
      const items = Array.isArray(value) ? value : String(value).split(/[,，、\s]+/);
      const tags = items.filter(t => t).map(t => '<span class="tag">' + esc(String(t)) + '</span>').join(' ');
      return '<div class="section"><h3>' + esc(key) + '</h3>' + tags + '</div>';
    }
    if (mode === 'timeline') {
      const items = Array.isArray(value) ? value.slice(0, 20) : [];
      const parts = items.map(item => {
        if (typeof item === 'object' && item !== null) {
          const evt = item['事件'] || item['event'] || String(item);
          return '<div class="tl-item" style="font-size:12px;color:#ccc;padding:2px 0">' + esc(String(evt).slice(0, 100)) + '</div>';
        }
        return '<div class="tl-item">' + esc(String(item).slice(0, 100)) + '</div>';
      }).join('');
      return '<div class="section"><h3>' + esc(key) + '</h3>' + parts + '</div>';
    }
    if (mode === 'group') {
      if (typeof value === 'object' && value !== null) {
        const children = Object.entries(value).map(([k, v]) => renderField(k, v)).join('');
        return '<div class="section"><h3>' + esc(key) + '</h3>' + children + '</div>';
      }
      return renderField(key, value);
    }
    return '';
  }

  function inferMode(key, value) {
    if (value === null || value === undefined || value === '') return 'skip';
    if (typeof value === 'string') return value.length >= 50 ? 'textblock' : 'tag';
    if (typeof value === 'boolean' || typeof value === 'number') return 'tag';
    if (Array.isArray(value)) {
      if (value.length === 0) return 'tagcloud';
      if (typeof value[0] === 'string') return 'tagcloud';
      if (typeof value[0] === 'object' && value[0] !== null) {
        if (value[0]['事件'] || value[0]['event']) return 'timeline';
      }
      return 'tagcloud';
    }
    if (typeof value === 'object') return 'group';
    return 'tag';
  }

  function esc(s) {
    return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  // ── 统计 ──────────────────────────────────────────────────

  function updateStats() {
    const nc = Object.keys(nodeData).length;
    const ec = edgeData.length;
    document.getElementById('statsDisplay').textContent = nc + ' 节点 · ' + ec + ' 关系';
  }

  // ── 物理引擎 ──────────────────────────────────────────────

  window.togglePhysics = function() {
    if (!network) return;
    const btn = document.getElementById('btnPhysics');
    const enabled = btn.textContent.includes('冻结');
    network.setOptions({ physics: { enabled: !enabled } });
    btn.textContent = enabled ? '▶️ 解冻' : '🧊 冻结';
  };

  // ── MODAL: 创建/编辑节点 ──────────────────────────────────

  window.showAddNodeModal = function() {
    showNodeForm(null);
  };

  window.showEditNodeModal = function(id) {
    showNodeForm(id);
  };

  async function showNodeForm(id) {
    const isEdit = !!id;
    let defaults = { unit_type: 'scene', name: '', tags: '', content: '' };

    if (isEdit) {
      try {
        const resp = await API.nodeDetail(id);
        const n = resp.node || {};
        defaults = {
          unit_type: n.type || 'scene',
          name: n.name || '',
          tags: (n.tags || []).join(', '),
          content: typeof n.content === 'string' ? n.content : JSON.stringify(n.content || '', null, 2),
        };
      } catch (err) {
        alert('加载节点数据失败: ' + err.message);
        return;
      }
    }

    const scope = await API.searchScope().catch(() => ({ types: [{ value: 'scene', label: '场景' }] }));
    const typeOptions = (scope.types || []).map(t =>
      `<option value="${t.value}"${t.value === defaults.unit_type ? ' selected' : ''}>${t.label}</option>`
    ).join('');

    const modal = document.getElementById('modalContent');
    modal.innerHTML = `
      <h2>${isEdit ? '编辑节点' : '新建节点'}</h2>
      <form id="nodeForm">
        <label>类型</label>
        <select name="unit_type">${typeOptions}</select>
        <label>名称</label>
        <input name="name" value="${esc(defaults.name)}" required />
        <label>标签（逗号分隔）</label>
        <input name="tags" value="${esc(defaults.tags)}" />
        <label>内容（JSON）</label>
        <textarea name="content">${esc(defaults.content)}</textarea>
        <div class="modal-actions">
          <button type="button" onclick="closeModal()">取消</button>
          <button type="submit" class="btn-primary">${isEdit ? '保存' : '创建'}</button>
        </div>
      </form>
    `;

    document.getElementById('modalOverlay').style.display = 'flex';

    document.getElementById('nodeForm').addEventListener('submit', async function(e) {
      e.preventDefault();
      const fd = new FormData(this);
      const data = {
        unit_type: fd.get('unit_type'),
        name: fd.get('name'),
        tags: (fd.get('tags') || '').split(/[,，、\s]+/).filter(t => t),
      };
      const contentRaw = fd.get('content') || '';
      if (contentRaw) {
        try {
          data.content = JSON.parse(contentRaw);
        } catch {
          data.content = contentRaw;
        }
      }

      try {
        if (isEdit) {
          await API.updateNode(id, data);
        } else {
          await API.createNode(data);
        }
        closeModal();
        await refreshGraph();
      } catch (err) {
        alert('操作失败: ' + err.message);
      }
    });
  };

  // ── MODAL: 创建关系 ──────────────────────────────────────

  window.showAddEdgeModal = function() {
    const modal = document.getElementById('modalContent');
    const nodeOptions = Object.entries(nodeData).map(([id, n]) =>
      `<option value="${id}">${esc(n.label || id)}</option>`
    ).join('');

    const typeOptions = [
      'participates_in', 'causes', 'precedes', 'contradicts', 'implements',
      'belongs_to', 'references', 'implies', 'parallel', 'inspires',
      'refines', 'located_at', 'allied_with', 'contains', 'controls',
      'member_of', 'has_member', 'location_of', 'controlled_by',
    ].map(t => `<option value="${t}">${t}</option>`).join('');

    modal.innerHTML = `
      <h2>新建关联</h2>
      <form id="edgeForm">
        <label>源节点</label>
        <select name="source" required>${nodeOptions}</select>
        <label>目标节点</label>
        <select name="target" required>${nodeOptions}</select>
        <label>关系类型</label>
        <select name="rel_type">${typeOptions}</select>
        <label>标签（可选）</label>
        <input name="label" />
        <label><input type="checkbox" name="bidirectional" value="true" /> 自动建立反向关系</label>
        <div class="modal-actions">
          <button type="button" onclick="closeModal()">取消</button>
          <button type="submit" class="btn-primary">创建</button>
        </div>
      </form>
    `;

    document.getElementById('modalOverlay').style.display = 'flex';

    document.getElementById('edgeForm').addEventListener('submit', async function(e) {
      e.preventDefault();
      const fd = new FormData(this);
      const data = {
        source: fd.get('source'),
        target: fd.get('target'),
        rel_type: fd.get('rel_type'),
        label: fd.get('label') || '',
      };
      if (fd.get('bidirectional')) data.bidirectional = true;

      try {
        await API.createEdge(data);
        closeModal();
        await refreshGraph();
      } catch (err) {
        alert('创建失败: ' + err.message);
      }
    });
  };

  // ── 编辑/删除（从详情面板调用） ──────────────────────────

  window.APP = {
    focusNode(id) {
      if (!network) return;
      network.focus(id, { scale: 1.5, animation: true });
      showDetail(id);
    },

    editNode(id) {
      showNodeForm(id);
    },

    async deleteNode(id) {
      if (!confirm('确认删除此节点？')) return;
      try {
        await API.deleteNode(id);
        await refreshGraph();
        closeDetail();
      } catch (err) {
        alert('删除失败: ' + err.message);
      }
    },
  };

  // ── 刷新图谱 ──────────────────────────────────────────────

  async function refreshGraph() {
    try {
      const graphResp = await API.fullGraph();
      nodeData = graphResp.nodes || {};
      edgeData = graphResp.edges || [];

      // 更新 vis.DataSet
      if (nodesDataSet && edgesDataSet) {
        nodeData = graphResp.nodes || {};
        edgeData = graphResp.edges || [];

        // 清除旧数据
        nodesDataSet.clear();
        edgesDataSet.clear();

        // 添加新数据
        Object.entries(nodeData).forEach(([id, n]) => {
          nodesDataSet.add(buildVisNode(id, n));
        });
        edgeData.forEach(e => {
          edgesDataSet.add(buildVisEdge(e));
        });
      }

      updateStats();
      network.fit({ animation: true });

      // 如果详情面板打开，刷新
      if (currentId && nodeData[currentId]) {
        showDetail(currentId);
      }
    } catch (err) {
      console.error('刷新失败:', err);
    }
  }

  // ── Modal 控制 ────────────────────────────────────────────

  window.closeModal = function() {
    document.getElementById('modalOverlay').style.display = 'none';
  };

  // ── 外部调用 ──────────────────────────────────────────────

  window.closeDetail = closeDetail;
})();