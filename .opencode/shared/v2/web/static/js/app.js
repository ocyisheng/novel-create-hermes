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
  let loadedNeighbors = {}; // id → true, 已拉取过邻居的节点
  let initialLimit = 150;   // 首次加载节点数（增大以覆盖多类型并自动带出关系边）
  let initialDepth = 2;     // 首次加载深度（2 级邻居自动带出边）

  // 类型配置
  const TYPE_CONFIG = {};

  // ── 初始化 ────────────────────────────────────────────────
  document.addEventListener('DOMContentLoaded', init);

  async function init() {
    try {
      // 加载项目信息
      const [projInfo, graphResp, scopeResp] = await Promise.all([
        API.projectInfo(),
        API.fullGraph({ limit: initialLimit, depth: initialDepth }),
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

      // 物理引擎：弱力 + 高阻尼，缓慢漂移不弹跳
      const physicsConfig = {
        solver: 'barnesHut',
        barnesHut: { gravitationalConstant: -1500, centralGravity: 0.6, springLength: 120, springConstant: 0.08, damping: 0.9 },
        stabilization: { iterations: 80, updateInterval: 10 },
      };

      const options = {
        layout: { improvedLayout: false },
        physics: physicsConfig,
        interaction: {
          dragNodes: true, dragView: true, zoomView: true,
          hover: true, tooltipDelay: 200, navigationButtons: true, keyboard: true,
        },
        edges: { smooth: isLarge ? false : { type: 'continuous' } },
      };

      network = new vis.Network(cont, { nodes: nodesDataSet, edges: edgesDataSet }, options);

      // 物理常开：用户可通过 🧊 冻结按钮手动暂停

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
        esc(err.message) + '</p></div>';
    }
  }

  // ── 视图切换 ────────────────────────────────────────────

  window.switchView = function(view, focusNodeId) {
    const networkEl = document.getElementById('network');
    const timelineView = document.getElementById('timelineView');
    const structureView = document.getElementById('structureView');
    const graphToolbar = document.getElementById('graphToolbar');
    const timelineToolbar = document.getElementById('timelineToolbar');
    const structureToolbar = document.getElementById('structureToolbar');
    const tabGraph = document.getElementById('tabGraph');
    const tabTimeline = document.getElementById('tabTimeline');
    const tabStructure = document.getElementById('tabStructure');

    if (view === 'timeline') {
      if (networkEl) networkEl.style.display = 'none';
      if (timelineView) timelineView.style.display = 'block';
      if (structureView) structureView.style.display = 'none';
      if (graphToolbar) graphToolbar.style.display = 'none';
      if (timelineToolbar) timelineToolbar.style.display = 'inline-flex';
      if (structureToolbar) structureToolbar.style.display = 'none';
      if (tabGraph) tabGraph.classList.remove('active');
      if (tabTimeline) tabTimeline.classList.add('active');
      if (tabStructure) tabStructure.classList.remove('active');
      // 关闭详情面板
      closeDetail();
      // 加载时间线
      if (typeof TIMELINE !== 'undefined' && TIMELINE.load) {
        TIMELINE.load();
      }
    } else if (view === 'structure') {
      if (networkEl) networkEl.style.display = 'none';
      if (timelineView) timelineView.style.display = 'none';
      if (structureView) structureView.style.display = 'block';
      if (graphToolbar) graphToolbar.style.display = 'none';
      if (timelineToolbar) timelineToolbar.style.display = 'none';
      if (structureToolbar) structureToolbar.style.display = 'inline-flex';
      if (tabGraph) tabGraph.classList.remove('active');
      if (tabTimeline) tabTimeline.classList.remove('active');
      if (tabStructure) tabStructure.classList.add('active');
      // 关闭详情面板
      closeDetail();
      // 加载结构树（每次进入刷新，保证最新）
      loadStructureTree();
    } else {
      if (networkEl) networkEl.style.display = 'block';
      if (timelineView) timelineView.style.display = 'none';
      if (structureView) structureView.style.display = 'none';
      if (graphToolbar) graphToolbar.style.display = 'inline-flex';
      if (timelineToolbar) timelineToolbar.style.display = 'none';
      if (structureToolbar) structureToolbar.style.display = 'none';
      if (tabGraph) tabGraph.classList.add('active');
      if (tabTimeline) tabTimeline.classList.remove('active');
      if (tabStructure) tabStructure.classList.remove('active');
      // 聚焦节点
      if (focusNodeId && nodeData[focusNodeId]) {
        setTimeout(function() {
          if (network) {
            network.fit({ animation: false });
            network.focus(focusNodeId, { scale: 1.5, animation: true });
          }
          showDetail(focusNodeId);
        }, 400);
      }
    }
  };

  window.resetTimelineFilter = function() {
    if (typeof TIMELINE !== 'undefined' && TIMELINE.resetTimelineFilter) {
      TIMELINE.resetTimelineFilter();
    }
  };

  // ── 结构树（总纲 → 卷 → 章） ──────────────────────────────

  const STRUCTURE_META = {
    outline:      { label: '总纲' },
    volume_plan:  { label: '卷' },
    chapter_plan: { label: '章' },
  };

  let structureNodes = [];      // 后端返回的扁平节点（children 存 id，保持树序）
  let structureNodeMap = {};    // id → node（渲染查找用）
  let structureCollapsed = {};  // id → true = 折叠

  async function loadStructureTree() {
    const cont = document.getElementById('structureContent');
    if (!cont) return;
    const statsEl = document.getElementById('stStats');
    try {
      const resp = await API.structureTree();
      structureNodes = resp.nodes || [];
      structureNodeMap = {};
      structureNodes.forEach(n => { structureNodeMap[n.id] = n; });

      const counts = resp.counts || {};
      if (statsEl) {
        statsEl.textContent =
          (counts.outline || 0) + ' 总纲 · ' +
          (counts.volume_plan || 0) + ' 卷 · ' +
          (counts.chapter_plan || 0) + ' 章';
      }

      if (!structureNodes.length) {
        cont.innerHTML = '<div class="tl-empty">暂无结构单元（总纲 / 卷 / 章）</div>';
        return;
      }
      renderStructureTreeIntoDom(cont);
    } catch (err) {
      cont.innerHTML = '<div class="tl-empty">结构树加载失败: ' + esc(err.message) + '</div>';
    }
  }

  /** 根节点 = 未被任何 children 引用的节点（保持后端返回顺序） */
  function structureRoots() {
    const childRefs = new Set();
    structureNodes.forEach(n => (n.children || []).forEach(c => childRefs.add(c)));
    return structureNodes.filter(n => !childRefs.has(n.id));
  }

  function renderStructureTreeIntoDom(cont) {
    cont = cont || document.getElementById('structureContent');
    let html = '<ul class="st-tree">';
    structureRoots().forEach(r => { html += renderStructureNode(r); });
    html += '</ul>';
    cont.innerHTML = html;
  }

  function renderStructureNode(node) {
    const kids = (node.children || []).filter(id => structureNodeMap[id]);
    const collapsed = !!structureCollapsed[node.id];
    const synthetic = !!node.synthetic;
    const meta = STRUCTURE_META[node.type] || { label: node.type };
    const rowCls = 'st-row' + (synthetic ? ' st-synthetic' : '');
    let html = '<li class="st-item">';
    html += '<div class="' + rowCls + '">';
    html += '<span class="st-caret' + (kids.length ? '' : ' st-caret-empty') + '" ' +
      'onclick="event.stopPropagation();toggleStructureNode(\'' + jsStr(node.id) + '\')">' +
      (kids.length ? (collapsed ? '▸' : '▾') : '·') + '</span>';
    html += '<span class="st-dot" style="background:' + getTypeColor(node.type) + '"></span>';
    if (synthetic) {
      html += '<span class="st-name">' + esc(node.name) + '</span>';
    } else {
      html += '<span class="st-name st-link" title="点击在图谱中定位" onclick="jumpToGraphNode(\'' + jsStr(node.id) + '\')">' + esc(node.name) + '</span>';
      html += '<span class="st-type">' + esc(meta.label) + '</span>';
      html += '<span class="st-jump" title="在图谱中定位" onclick="jumpToGraphNode(\'' + jsStr(node.id) + '\')">↗</span>';
    }
    html += '</div>';
    if (kids.length && !collapsed) {
      html += '<ul class="st-children">' + kids.map(id => renderStructureNode(structureNodeMap[id])).join('') + '</ul>';
    }
    html += '</li>';
    return html;
  }

  window.toggleStructureNode = function(id) {
    structureCollapsed[id] = !structureCollapsed[id];
    renderStructureTreeIntoDom();
  };

  window.structureExpandAll = function(expand) {
    structureCollapsed = {};
    if (!expand) {
      structureNodes.forEach(n => {
        if ((n.children || []).length) structureCollapsed[n.id] = true;
      });
    }
    renderStructureTreeIntoDom();
  };

  window.jumpToGraphNode = async function(id) {
    // 未加载过的节点先增量拉取（合并进图数据），保证图视图能聚焦高亮
    if (!nodeData[id] && !loadedNeighbors[id]) {
      try { await loadNeighborsIncremental(id); } catch (e) { /* 忽略，切视图兜底 */ }
    }
    switchView('graph', id);
  };

  // ── 节点/边构建 ──────────────────────────────────────────

  function buildVisNode(id, n) {
    const c = n.color || { bg: '#5B9BD5', border: '#2E75B6', text: '#fff' };
    const isLarge = Object.keys(nodeData).length > 200;
    const baseSize = isLarge ? 8 : 12;
    return {
      id,
      label: n.label || id,
      color: { background: c.bg, border: c.border },
      font: { color: c.text || '#fff', size: isLarge ? 11 : 13, face: 'sans-serif' },
      shape: 'dot',
      size: baseSize,
      borderWidth: isLarge ? 1 : 1.5,
      group: n.type || 'other',
      _info: n,
    };
  }

  function buildVisEdge(e) {
    const isLarge = Object.keys(nodeData).length > 200;
    return {
      from: e.from, to: e.to,
      label: e.label || '',
      font: { size: isLarge ? 7 : 9, color: e.color || '#888', strokeWidth: 0 },
      color: { color: e.color || '#4a4a6a', opacity: 0.8 },
      width: isLarge ? 0.5 : 0.8,
      arrows: { to: { enabled: true, scaleFactor: isLarge ? 0.4 : 0.6 } },
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

    // 计算可见节点集合（类型 + 搜索）
    const visible = new Set();
    Object.entries(nodeData).forEach(([id, n]) => {
      let ok = true;
      if (typeVal !== 'all' && n.type !== typeVal) ok = false;
      if (query && !(n.label || '').toLowerCase().includes(query)) ok = false;
      if (ok) visible.add(id);
    });

    // 重建只含可见节点的图 → 触发独立的物理布局。
    // 原实现只是隐藏节点、保留全图布局位置，导致所有类型过滤都显示同样的聚团；
    // 重建后每个类型/搜索视图展示自己的真实连接结构（回到"全部"时恢复全图总览）。
    const newNodes = new vis.DataSet(
      Array.from(visible).map(id => buildVisNode(id, nodeData[id]))
    );
    const newEdges = new vis.DataSet(
      edgeData.filter(e => visible.has(e.from) && visible.has(e.to)).map(e => buildVisEdge(e))
    );

    nodesDataSet = newNodes;
    edgesDataSet = newEdges;
    network.setData({ nodes: newNodes, edges: newEdges });

    // 重新启用物理布局并适配视角
    network.setOptions({ physics: { enabled: true } });
    network.fit({ animation: false });
    setTimeout(() => network.fit({ animation: false }), 400);
  }

  // ── Hover ─────────────────────────────────────────────────

  function onHoverNode(params) {
    const node = nodesDataSet.get(params.node);
    if (!node || !node._info) return;
    const n = node._info;
    const tip = document.getElementById('tooltip');
    tip.innerHTML = '<div class="tt-name">' + esc(n.label || '') + '</div>' +
      '<div class="tt-type">' + esc(n.type_label || n.type || '') + '</div>' +
      '<div class="tt-meta">状态: ' + esc(n.status || '?') + ' · 确信度: ' + esc(n.confidence || '?') + '</div>';
    tip.style.display = 'block';
  }

  function onBlurNode() {
    document.getElementById('tooltip').style.display = 'none';
  }

  // ── Click → 详情面板 ─────────────────────────────────────

  function onClick(params) {
    if (params.nodes && params.nodes.length > 0) {
      const id = params.nodes[0];
      showDetail(id);
      // 增量加载：未拉取过邻居时按需加载
      if (!loadedNeighbors[id]) {
        loadNeighborsIncremental(id);
      }
    } else {
      closeDetail();
    }
  }

  /**
   * 增量加载节点邻居：调用 /api/graph/neighbors/{id}，
   * 用 vis.DataSet.update() 追加新节点/边，避免全量重载。
   */
  async function loadNeighborsIncremental(id) {
    loadedNeighbors[id] = true;
    try {
      const resp = await API.neighbors(id, 2);
      if (!resp || !resp.nodes) return;

      const newNodes = [];
      const newEdges = [];

      // 收集新节点
      Object.entries(resp.nodes).forEach(([nid, n]) => {
        if (!nodeData[nid]) {
          nodeData[nid] = n;
          newNodes.push(buildVisNode(nid, n));
        }
      });

      // 收集新边（去重）
      (resp.edges || []).forEach(e => {
        const exists = edgeData.some(
          existing => existing.from === e.from && existing.to === e.to && existing.relation_type === e.relation_type
        );
        if (!exists) {
          edgeData.push(e);
          newEdges.push(buildVisEdge(e));
        }
      });

      // 增量更新 DataSet（仅追加，不替换已有数据）
      if (newNodes.length > 0 && nodesDataSet) {
        nodesDataSet.update(newNodes);
      }
      if (newEdges.length > 0 && edgesDataSet) {
        edgesDataSet.update(newEdges);
      }

      if (newNodes.length > 0 || newEdges.length > 0) {
        updateStats();
      }
    } catch (err) {
      console.error('增量加载邻居失败:', err);
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
    const status = n.status || 'sprout';
    const statusLabels = { sprout:'萌芽', growing:'生长中', mature:'成熟', frozen:'冻结', archived:'已归档' };
    meta.innerHTML = esc(n.type_label || n.type || '') +
      ' · <span class="status-badge status-' + esc(status) + '" onclick="APP.editStatus(\'' + jsStr(id) + '\', this)">' + esc(statusLabels[status] || status) + '</span>' +
      ' · 确信度 ' + renderConfidence(n.confidence);

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
          html += '<div class="rel-item">' +
            '<span class="rel-dot" style="background:' + c + '"></span>' +
            '<span class="rel-name" onclick="APP.focusNode(\'' + jsStr(r.id) + '\')" style="cursor:pointer">' + esc(r.name) + '</span>' +
            '<span class="rel-label">' + esc(r.rel) + '</span>' +
            '<span style="margin-left:auto;font-size:11px;display:flex;gap:2px">' +
            '<span onclick="APP.editEdge(\'' + jsStr(r.edgeId) + '\')" style="cursor:pointer;color:var(--accent);padding:0 4px" title="编辑关系">✎</span>' +
            '<span onclick="APP.deleteEdge(\'' + jsStr(r.edgeId) + '\')" style="cursor:pointer;color:var(--danger);padding:0 4px" title="删除关系">✕</span>' +
            '</span></div>';
        });
        html += '</div>';
      });
    }

    // ── 时间线（角色/场景专用） ────────────────────────────
    var showTimeline = n.type && (n.type === 'character_arc' || n.type === 'scene');
    if (showTimeline) {
      var tlLabel = n.type === 'character_arc' ? '角色时间线' : '关联场景';
      html += '<div class="section"><h3>' + tlLabel + '</h3><div id="entityTimeline" class="entity-timeline"><div class="tl-mini-loading">加载中...</div></div></div>';
    }

    // 操作按钮
    html += '<div class="dp-actions">' +
      '<button onclick="APP.editNode(\'' + jsStr(id) + '\')">✏️ 编辑</button>' +
      '<button onclick="APP.deleteNode(\'' + jsStr(id) + '\')" class="btn-danger">🗑️ 删除</button>' +
      '</div>';

    body.innerHTML = html;
    document.getElementById('detailPanel').classList.add('open');

    // 异步加载角色时间线
    if (showTimeline && typeof TIMELINE !== 'undefined' && TIMELINE.renderEntityTimeline) {
      TIMELINE.renderEntityTimeline(id, n.label || id, document.getElementById('entityTimeline'));
    }
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
        edgeId: e.id,
        id: otherId,
        name: other.label || otherId,
        type: other.type || 'unknown',
        rel: (e.label || '') + ' ' + dir,
        label: e.label || '',
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
      const tags = items.filter(t => t).map(t => {
        if (typeof t === 'object') {
          // 对象数组：取第一个字符串字段的值作为标签
          const vals = Object.values(t).filter(v => typeof v === 'string');
          return '<span class="tag">' + esc(vals[0] || JSON.stringify(t).slice(0, 40)) + '</span>';
        }
        return '<span class="tag">' + esc(String(t)) + '</span>';
      }).join(' ');
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

  // 用于内联 onclick="APP.fn('...')" 中的 JS 字符串字面量。
  // 不能只用 esc()——单引号在 HTML 属性内会被解码回原字符，导致 JS 注入。
  // 反斜杠须最先转义，防止 \x27 二次注入。
  function jsStr(s) {
    return String(s)
      .replace(/\\/g, '\\\\')
      .replace(/'/g, "\\'")
      .replace(/"/g, '\\x22')
      .replace(/&/g, '\\x26')
      .replace(/</g, '\\x3c')
      .replace(/>/g, '\\x3e');
  }

  // ── 结构化字段渲染（编辑用） ──────────────────────────────

  function renderEditField(key, value) {
    var name = '_extra_' + key;
    var label = '<div style="font-size:12px;color:var(--text-dim);margin-top:8px;margin-bottom:2px">' + esc(key) + '</div>';

    if (value === null || value === undefined) {
      return label + '<input class="inline-edit" name="' + name + '" value="" />';
    }
    if (typeof value === 'boolean') {
      var checked = value ? ' checked' : '';
      return '<label style="display:flex;align-items:center;gap:6px;margin-top:8px;font-size:13px;cursor:pointer">' +
        '<input type="checkbox" name="' + name + '" value="true"' + checked + ' /> ' + esc(key) + '</label>';
    }
    if (typeof value === 'number') {
      return label + '<input class="inline-edit" type="number" name="' + name + '" value="' + esc(String(value)) + '" />';
    }
    if (typeof value === 'string') {
      if (value.length >= 80) {
        return label + '<textarea class="inline-edit" name="' + name + '" style="min-height:60px">' + esc(value) + '</textarea>';
      }
      return label + '<input class="inline-edit" name="' + name + '" value="' + esc(value) + '" />';
    }
    if (Array.isArray(value)) {
      if (value.length === 0 || typeof value[0] === 'string') {
        return label + '<input class="inline-edit" name="' + name + '" value="' + esc(value.join(', ')) + '" placeholder="逗号分隔" />';
      }
      // 对象数组 → JSON textarea
      return label + '<textarea class="inline-edit" name="' + name + '" style="min-height:60px">' + esc(JSON.stringify(value, null, 2)) + '</textarea>';
    }
    if (typeof value === 'object') {
      return label + '<textarea class="inline-edit" name="' + name + '" style="min-height:60px">' + esc(JSON.stringify(value, null, 2)) + '</textarea>';
    }
    return label + '<input class="inline-edit" name="' + name + '" value="' + esc(String(value)) + '" />';
  }

  // ── 结构化字段重建 JSON ──────────────────────────────────

  function buildContentFromStructured(fd, extraData, skipKeys) {
    var obj = {};
    var keys = Object.keys(extraData);
    var hasAny = false;
    keys.forEach(function(k) {
      if (skipKeys.includes(k) || k.startsWith('_')) return;
      var v = fd.get('_extra_' + k);
      if (v === null) return; // 字段不在表单中
      hasAny = true;
      var orig = extraData[k];
      if (typeof orig === 'number') {
        obj[k] = parseFloat(v) || 0;
      } else if (typeof orig === 'boolean') {
        obj[k] = v === 'true' || v === 'on';
      } else if (Array.isArray(orig)) {
        if (orig.length === 0 || typeof orig[0] === 'string') {
          obj[k] = v.split(/[,，、\s]+/).filter(function(t) { return t; });
        } else {
          try { obj[k] = JSON.parse(v); } catch { obj[k] = v; }
        }
      } else {
        // string, or object stored as JSON
        if (orig && typeof orig === 'object') {
          try { obj[k] = JSON.parse(v); } catch { obj[k] = v; }
        } else {
          obj[k] = v;
        }
      }
    });
    return hasAny ? obj : null;
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
    let defaults = { unit_type: 'scene', name: '', tags: '', content: '', status: '' };
    let extraData = {};
    const skipKeys = ['subtype_label', 'subtype_color', '_preview', '_display'];

    if (isEdit) {
      try {
        const resp = await API.nodeDetail(id);
        const n = resp.node || {};
        defaults = {
          unit_type: n.type || 'scene',
          name: n.name || '',
          tags: (n.tags || []).join(', '),
          content: typeof n.content === 'string' ? n.content : JSON.stringify(n.content || '', null, 2),
          status: n.status || 'sprout',
        };
        extraData = n.extra || {};
      } catch (err) {
        showToast('加载节点数据失败: ' + err.message, 'error');
        return;
      }
    }

    const scope = await API.searchScope().catch(() => ({ types: [{ value: 'scene', label: '场景' }] }));
    const typeOptions = (scope.types || []).map(t =>
      `<option value="${esc(t.value)}"${t.value === defaults.unit_type ? ' selected' : ''}>${esc(t.label)}</option>`
    ).join('');

    var statusOpts = Object.entries(STATUS_LABELS).map(function(e) {
      return '<option value="' + e[0] + '"' + (e[0] === defaults.status ? ' selected' : '') + '>' + e[1] + '</option>';
    }).join('');

    // 构建结构化字段
    var extraFieldsHtml = '';
    var extraJsonContent = defaults.content;
    Object.entries(extraData).forEach(function(e) {
      var k = e[0], v = e[1];
      if (skipKeys.includes(k) || k.startsWith('_')) return;
      extraFieldsHtml += renderEditField(k, v);
    });
    var showStructured = isEdit && extraFieldsHtml.length > 0;

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
        <label>状态</label>
        <select name="status">${statusOpts}</select>
        ${showStructured ? '<div class="section" style="margin-top:12px"><h3>内容字段</h3>' + extraFieldsHtml + '</div>' : ''}
        ${isEdit ? '' : '<div id="schemaFieldsArea" style="margin-top:12px;display:none"><h3 style="font-size:14px;margin-bottom:8px">内容字段</h3><div id="schemaFields"></div></div>'}
        <div style="margin-top:8px">
          <label style="cursor:pointer;display:inline-flex;align-items:center;gap:4px;color:var(--text-dim);font-size:12px">
            <input type="checkbox" id="toggleRawJson" ${showStructured || isEdit ? '' : 'checked'} onchange="document.getElementById('rawJsonArea').style.display=this.checked?'block':'none'" />
            编辑原始 JSON
          </label>
        </div>
        <div id="rawJsonArea" style="display:${showStructured ? 'none' : 'block'}">
          <textarea name="content" style="min-height:120px">${esc(extraJsonContent)}</textarea>
        </div>
        <div class="modal-actions">
          <button type="button" onclick="closeModal()">取消</button>
          <button type="submit" class="btn-primary">${isEdit ? '保存' : '创建'}</button>
        </div>
      </form>
    `;

    document.getElementById('modalOverlay').style.display = 'flex';

    // 新建模式：类型下拉切换 → 加载模板字段
    if (!isEdit) {
      var typeSelect = document.querySelector('#nodeForm select[name="unit_type"]');
      var schemaFieldsDiv = document.getElementById('schemaFields');
      var schemaFieldsArea = document.getElementById('schemaFieldsArea');
      var currentSchemaFields = null;

      function loadSchema(unitType) {
        schemaFieldsDiv.innerHTML = '<div style="color:#888;font-size:12px">加载中...</div>';
        schemaFieldsArea.style.display = 'block';
        _fetchSchema(unitType).then(function(fields) {
          if (Object.keys(fields).length === 0) {
            schemaFieldsDiv.innerHTML = '<div style="color:#888;font-size:12px">该类型无预定义字段</div>';
            currentSchemaFields = null;
            return;
          }
          currentSchemaFields = fields;
          var html = '';
          Object.entries(fields).forEach(function(entry) {
            html += renderSchemaField(entry[0], entry[1]);
          });
          schemaFieldsDiv.innerHTML = html;
        });
      }

      // 默认加载当前选中类型的 schema
      loadSchema(typeSelect.value);

      typeSelect.addEventListener('change', function() {
        loadSchema(this.value);
      });
    }

    document.getElementById('nodeForm').addEventListener('submit', async function(e) {
      e.preventDefault();
      const submitBtn = this.querySelector('.btn-primary');
      setLoading(submitBtn, true);
      const fd = new FormData(this);
      const data = {
        unit_type: fd.get('unit_type'),
        name: fd.get('name'),
        tags: (fd.get('tags') || '').split(/[,，、\s]+/).filter(t => t),
      };
      var statusVal = fd.get('status');
      if (statusVal) data.status = statusVal;

      // 结构化模式 → 从 _extra_* 字段或 _schema_* 字段重建 content
      var toggle = document.getElementById('toggleRawJson');
      if (!isEdit && currentSchemaFields && toggle && !toggle.checked) {
        // 新建 + schema 模板模式（且未勾选"原始 JSON"）
        var built = buildContentFromSchema(fd, currentSchemaFields);
        if (built && Object.keys(built).length > 0) data.content = built;
      } else {
        var useStructured = toggle && !toggle.checked && showStructured;
        if (useStructured) {
          var built = buildContentFromStructured(fd, extraData, skipKeys);
          if (built && Object.keys(built).length > 0) data.content = built;
        } else {
          const contentRaw = fd.get('content') || '';
          if (contentRaw) {
            try {
              data.content = JSON.parse(contentRaw);
            } catch {
              data.content = contentRaw;
            }
          }
        }
      }

      try {
        closeModal();
        if (isEdit) {
          await API.updateNode(id, data);
          showToast('节点已更新', 'success');
          // 增量更新：只更新变化的节点（边可能靠推理变化，但也用 update 避免闪烁）
          await incrementalRefresh();
        } else {
          const resp = await API.createNode(data);
          showToast('节点已创建', 'success');
          // 新建后有推理，需全量刷新
          await refreshGraph();
        }
      } catch (err) {
        showToast('操作失败: ' + err.message, 'error');
        setLoading(submitBtn, false);
      }
    });
  };

  // ── MODAL: 创建关系 ──────────────────────────────────────

  window.showAddEdgeModal = function() {
    const modal = document.getElementById('modalContent');
    const nodeOptions = Object.entries(nodeData).map(([id, n]) =>
      `<option value="${esc(id)}">${esc(n.label || id)}</option>`
    ).join('');

    // 与 graph_schema.py RelationType 枚举一致（26 种）
    const typeOptions = [
      'causes', 'precedes', 'contradicts', 'implements', 'inspires',
      'refines', 'belongs_to', 'references', 'implies', 'parallel',
      'plans', 'planned_by', 'participates_in', 'located_at', 'relates_to',
      'possesses', 'possessed_by', 'contains', 'controls', 'member_of',
      'has_member', 'location_of', 'controlled_by', 'has_event', 'event_of',
      'involves',
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
      const submitBtn = this.querySelector('.btn-primary');
      setLoading(submitBtn, true);
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
        showToast('关联已创建', 'success');
        closeModal();
        await refreshGraph();
      } catch (err) {
        showToast('创建失败: ' + err.message, 'error');
        setLoading(submitBtn, false);
      }
    });
  };

  // ── MODAL: 编辑关系 ──────────────────────────────────────

  function showEdgeEditModal(edgeId) {
    var edge = null;
    for (var i = 0; i < edgeData.length; i++) {
      if (edgeData[i].id === edgeId) { edge = edgeData[i]; break; }
    }
    if (!edge) { showToast('未找到关系数据', 'error'); return; }

    var src = nodeData[edge.from];
    var tgt = nodeData[edge.to];
    var srcName = src ? (src.label || edge.from) : edge.from;
    var tgtName = tgt ? (tgt.label || edge.to) : edge.to;

    var modal = document.getElementById('modalContent');
    modal.innerHTML = `
      <h2>编辑关系</h2>
      <form id="edgeEditForm">
        <label>源节点</label>
        <input value="${esc(srcName)}" disabled style="opacity:0.6" />
        <label>目标节点</label>
        <input value="${esc(tgtName)}" disabled style="opacity:0.6" />
        <label>关系类型</label>
        <input value="${esc(edge.type || '')}" disabled style="opacity:0.6" />
        <label>标签</label>
        <input name="label" value="${esc(edge.label || '')}" />
        <div class="modal-actions">
          <button type="button" onclick="closeModal()">取消</button>
          <button type="submit" class="btn-primary">保存</button>
        </div>
      </form>
    `;

    document.getElementById('modalOverlay').style.display = 'flex';

    document.getElementById('edgeEditForm').addEventListener('submit', async function(e) {
      e.preventDefault();
      var submitBtn = this.querySelector('.btn-primary');
      setLoading(submitBtn, true);
      var fd = new FormData(this);
      var label = fd.get('label') || '';
      try {
        await API.updateEdge(edgeId, { label: label });
        showToast('关系已更新', 'success');
        closeModal();
        // 只更新 label，用增量刷新
        if (currentId && nodeData[currentId]) {
          // 只更新 edgeData 中这条边的 label
          for (var i = 0; i < edgeData.length; i++) {
            if (edgeData[i].id === edgeId) {
              edgeData[i].label = label;
              if (edgesDataSet) edgesDataSet.update({ id: edgeId, label: label });
              break;
            }
          }
          showDetail(currentId);
        } else {
          await incrementalRefresh();
        }
      } catch (err) {
        showToast('更新失败: ' + err.message, 'error');
        setLoading(submitBtn, false);
      }
    });
  }

  // ── 编辑/删除（从详情面板调用） ──────────────────────────

  // ── 状态标签映射 ────────────────────────────────────────────

  const STATUS_LABELS = { sprout:'萌芽', growing:'生长中', mature:'成熟', frozen:'冻结', archived:'已归档' };
  const STATUS_LIST = ['sprout', 'growing', 'mature', 'frozen', 'archived'];

  // ── Schema 缓存（新建节点模板用） ──────────────────────────

  var _schemaCache = {};

  function _fetchSchema(unitType) {
    if (_schemaCache[unitType]) return Promise.resolve(_schemaCache[unitType]);
    return API.schemaFields(unitType).then(function(resp) {
      _schemaCache[unitType] = resp.fields || {};
      return _schemaCache[unitType];
    }).catch(function() { return {}; });
  }

  /** 根据 schema 字段定义渲染表单控件 */
  function renderSchemaField(key, schema) {
    var name = '_schema_' + key;
    var required = schema.required ? ' <span style="color:var(--danger)">*</span>' : '';
    var label = '<div style="font-size:12px;color:var(--text-dim);margin-top:8px;margin-bottom:2px">' + esc(key) + required + '</div>';
    var desc = schema.description ? '<div style="font-size:11px;color:#888;margin-bottom:4px">' + esc(schema.description) + '</div>' : '';

    // 有选项 → select 下拉
    if (schema.options && schema.options.length > 0) {
      var opts = schema.options.map(function(o) { return '<option value="' + esc(o) + '">' + esc(o) + '</option>'; }).join('');
      return desc + label + '<select class="inline-edit" name="' + name + '">' + opts + '</select>';
    }

    // 对象类型（有子字段）
    if (schema.type === 'object' || schema.type === ['object']) {
      if (schema.fields) {
        var children = '';
        Object.entries(schema.fields).forEach(function(e) {
          var subSchema = {
            type: Array.isArray(e[1]) ? e[1][0] || 'string' : e[1],
            required: false,
          };
          children += renderSchemaField(e[0], subSchema);
        });
        return desc + '<div class="section" style="margin:4px 0"><h4 style="font-size:13px">' + esc(key) + '</h4>' + children + '</div>';
      }
      // 无子字段 → 动态键值编辑器
      var kvHtml = '<div class="schema-kv-editor" data-key="' + key + '" style="margin-top:4px">';
      kvHtml += '<div style="font-size:12px;color:var(--text-dim);margin-bottom:4px">' + esc(key) + required + '</div>';
      kvHtml += '<div class="kv-entries" id="kvEntries_' + key + '">';
      kvHtml += renderKvRow(key, 0);
      kvHtml += '</div>';
      kvHtml += '<button type="button" onclick="window.addKvItem(\'' + jsStr(key) + '\')" style="font-size:12px;margin-top:4px;cursor:pointer;color:var(--accent);background:none;border:1px dashed var(--border);border-radius:4px;padding:2px 8px">＋ 添加字段</button>';
      kvHtml += '</div>';
      return desc + kvHtml;
    }

    // 数组类型 + 有 item_fields → 交互式列表
    if ((schema.type === 'array' || (Array.isArray(schema.type) && schema.type.indexOf('array') >= 0)) && schema.item_fields) {
      var html = '<div class="schema-array-field" data-key="' + key + '" style="margin-top:8px">';
      html += '<div style="font-size:12px;color:var(--text-dim);margin-bottom:4px">' + esc(key) + required + '</div>';
      html += '<div class="array-items" id="arrayItems_' + key + '">';
      // 初始一行空模板
      html += renderArrayItemRow(key, schema.item_fields, 0);
      html += '</div>';
      html += '<button type="button" onclick="window.addArrayItem(\'' + jsStr(key) + '\')" style="font-size:12px;margin-top:4px;cursor:pointer;color:var(--accent);background:none;border:1px dashed var(--border);border-radius:4px;padding:4px 10px">＋ 添加条目</button>';
      html += '</div>';
      return html;
    }

    // 数组类型（无 item_fields）→ 简单文本列表（add/remove text inputs）
    if (schema.type === 'array' || (Array.isArray(schema.type) && schema.type.indexOf('array') >= 0)) {
      var arrHtml = '<div class="schema-plain-array" data-key="' + key + '" style="margin-top:4px">';
      arrHtml += '<div style="font-size:12px;color:var(--text-dim);margin-bottom:4px">' + esc(key) + required + '</div>';
      arrHtml += '<div class="plain-array-items" id="plainArrayItems_' + key + '">';
      arrHtml += renderPlainArrayRow(key, 0);
      arrHtml += '</div>';
      arrHtml += '<button type="button" onclick="window.addPlainArrayItem(\'' + jsStr(key) + '\')" style="font-size:12px;margin-top:4px;cursor:pointer;color:var(--accent);background:none;border:1px dashed var(--border);border-radius:4px;padding:2px 8px">＋ 添加</button>';
      arrHtml += '</div>';
      return desc + arrHtml;
    }

    // 布尔
    if (schema.type === 'boolean') {
      return desc + '<label style="display:flex;align-items:center;gap:6px;margin-top:8px;font-size:13px;cursor:pointer">' +
        '<input type="checkbox" name="' + name + '" value="true" /> ' + esc(key) + '</label>';
    }

    // 数字
    if (schema.type === 'int' || schema.type === 'float') {
      return desc + label + '<input class="inline-edit" type="number" name="' + name + '" step="' + (schema.type === 'float' ? 'any' : '1') + '" />';
    }

    // 默认 text input（长文本 → textarea）
    var isMulti = schema.description && schema.description.length > 40;
    return desc + (isMulti
      ? label + '<textarea class="inline-edit" name="' + name + '" style="min-height:60px"></textarea>'
      : label + '<input class="inline-edit" name="' + name + '" />');
  }

  /** 渲染数组 item_fields 的一行 */
  function renderArrayItemRow(key, itemFields, index) {
    var fieldsHtml = '';
    Object.keys(itemFields).forEach(function(fk) {
      var ft = itemFields[fk];
      var fname = '_schema_' + key + '_' + index + '_' + fk;
      var fLabel = '<span style="font-size:11px;color:#999;margin-right:4px">' + esc(fk) + '</span>';
      if (ft === 'boolean') {
        fieldsHtml += '<label style="display:inline-flex;align-items:center;gap:3px;margin-right:8px;font-size:12px;cursor:pointer">' +
          '<input type="checkbox" name="' + fname + '" value="true" /> ' + esc(fk) + '</label>';
      } else if (ft === 'int' || ft === 'float') {
        fieldsHtml += fLabel + '<input class="inline-edit" type="number" name="' + fname + '" step="' + (ft === 'float' ? 'any' : '1') + '" style="width:80px;margin-right:8px" />';
      } else if (ft === 'object' || ft === 'array') {
        fieldsHtml += fLabel + '<input class="inline-edit" name="' + fname + '" placeholder="JSON" style="width:120px;margin-right:8px;font-size:11px" />';
      } else {
        fieldsHtml += fLabel + '<input class="inline-edit" name="' + fname + '" style="width:120px;margin-right:8px" />';
      }
    });
    var rowId = 'arrayRow_' + key + '_' + index;
    return '<div id="' + rowId + '" style="display:flex;align-items:center;gap:2px;padding:4px 0;border-bottom:1px solid var(--border)">' +
      fieldsHtml +
      '<span onclick="window.removeArrayItem(\'' + jsStr(key) + '\',' + index + ')" style="cursor:pointer;color:var(--danger);font-size:14px;padding:2px 6px" title="删除">&times;</span>' +
      '</div>';
  }

  /** 渲染简单数组的一行（无 item_fields） */
  function renderPlainArrayRow(key, index) {
    var fname = '_schema_' + key + '_' + index;
    var rowId = 'plainArrayRow_' + key + '_' + index;
    return '<div id="' + rowId + '" style="display:flex;align-items:center;gap:4px;padding:3px 0">' +
      '<input class="inline-edit" name="' + fname + '" style="flex:1;min-width:80px" />' +
      '<span onclick="window.removePlainArrayItem(\'' + jsStr(key) + '\',' + index + ')" style="cursor:pointer;color:var(--danger);font-size:14px;padding:0 4px" title="删除">&times;</span>' +
      '</div>';
  }

  /** 渲染键值对的一行（object 无 fields） */
  function renderKvRow(key, index) {
    var kName = '_schema_' + key + '_kvk_' + index;
    var vName = '_schema_' + key + '_kvv_' + index;
    var rowId = 'kvRow_' + key + '_' + index;
    return '<div id="' + rowId + '" style="display:flex;align-items:center;gap:4px;padding:3px 0">' +
      '<input class="inline-edit" name="' + kName + '" placeholder="key" style="width:100px;font-size:12px" />' +
      '<input class="inline-edit" name="' + vName + '" placeholder="value" style="flex:1;min-width:80px;font-size:12px" />' +
      '<span onclick="window.removeKvItem(\'' + jsStr(key) + '\',' + index + ')" style="cursor:pointer;color:var(--danger);font-size:14px;padding:0 4px" title="删除">&times;</span>' +
      '</div>';
  }

  /** 从 _schema_* 表单字段构建 content JSON */
  function buildContentFromSchema(fd, schemaFields) {
    var obj = {};
    Object.keys(schemaFields).forEach(function(key) {
      var s = schemaFields[key];

      // 数组 + item_fields → 从 _schema_{key}_{idx}_{field} 逐行读取
      if ((s.type === 'array' || (Array.isArray(s.type) && s.type.indexOf('array') >= 0)) && s.item_fields) {
        var items = [];
        var idx = 0;
        while (true) {
          var row = {};
          var hasAny = false;
          Object.keys(s.item_fields).forEach(function(fk) {
            var fv = fd.get('_schema_' + key + '_' + idx + '_' + fk);
            if (fv === null) return;
            hasAny = true;
            var ft = s.item_fields[fk];
            if (ft === 'boolean') { row[fk] = fv === 'true' || fv === 'on'; }
            else if (ft === 'int') { row[fk] = parseInt(fv, 10) || 0; }
            else if (ft === 'float') { row[fk] = parseFloat(fv) || 0; }
            else if (ft === 'object' || ft === 'array') {
              if (fv.trim()) { try { row[fk] = JSON.parse(fv); } catch { row[fk] = fv; } }
            } else {
              row[fk] = fv;
            }
          });
          if (!hasAny) break;
          items.push(row);
          idx++;
        }
        if (items.length > 0) obj[key] = items;
        return;
      }

      // 数组（无 item_fields）→ 从 _schema_{key}_{idx} 读取
      if ((s.type === 'array' || (Array.isArray(s.type) && s.type.indexOf('array') >= 0)) && !s.item_fields) {
        var items = [];
        var idx = 0;
        while (true) {
          var fv = fd.get('_schema_' + key + '_' + idx);
          if (fv === null) break;
          if (fv.trim()) items.push(fv.trim());
          idx++;
        }
        if (items.length > 0) obj[key] = items;
        return;
      }

      // 对象（无 fields）→ 从 _schema_{key}_kvk_{idx} / _kvv_{idx} 读取
      if ((s.type === 'object' || (Array.isArray(s.type) && s.type.indexOf('object') >= 0)) && !s.fields) {
        var kvObj = {};
        var idx = 0;
        while (true) {
          var k = fd.get('_schema_' + key + '_kvk_' + idx);
          var v = fd.get('_schema_' + key + '_kvv_' + idx);
          if (k === null || v === null) break;
          if (k.trim()) kvObj[k.trim()] = v.trim();
          idx++;
        }
        if (Object.keys(kvObj).length > 0) obj[key] = kvObj;
        return;
      }

      var v = fd.get('_schema_' + key);
      if (v === null) return;
      // 有选项 → 字符串值
      if (s.options && s.options.length > 0) { obj[key] = v; return; }
      if (s.type === 'boolean') { obj[key] = v === 'true' || v === 'on'; return; }
      if (s.type === 'int') { obj[key] = parseInt(v, 10) || 0; return; }
      if (s.type === 'float') { obj[key] = parseFloat(v) || 0; return; }
      // string → 直接存
      obj[key] = v;
    });
    return Object.keys(obj).length > 0 ? obj : null;
  }

  // ── 确信度渲染 ──────────────────────────────────────────────

  function renderConfidence(val) {
    val = parseFloat(val) || 0;
    const pct = Math.round(val * 100);
    let color = '#ef5350';
    if (pct >= 70) color = '#66bb6a';
    else if (pct >= 40) color = '#ffa726';
    const barW = Math.max(4, Math.min(60, pct * 0.6));
    return '<span style="display:inline-flex;align-items:center;gap:4px;font-size:12px">' +
      '<span style="display:inline-block;width:' + barW + 'px;height:8px;border-radius:4px;background:' + color + ';transition:width 0.3s"></span>' +
      pct + '%</span>';
  }

  window.APP = {
    focusNode(id) {
      if (!network) return;
      network.focus(id, { scale: 1.5, animation: true });
      showDetail(id);
    },

    editNode(id) {
      showNodeForm(id);
    },

    async editStatus(id, badgeEl) {
      const n = nodeData[id];
      if (!n) return;
      const current = n.status || 'sprout';

      // 移除已有下拉
      var oldSel = document.querySelector('.status-select');
      if (oldSel) oldSel.remove();

      var sel = document.createElement('select');
      sel.className = 'status-select';
      sel.style.top = (badgeEl.getBoundingClientRect().bottom + 4) + 'px';
      sel.style.left = badgeEl.getBoundingClientRect().left + 'px';
      STATUS_LIST.forEach(function(s) {
        var opt = document.createElement('option');
        opt.value = s;
        opt.textContent = STATUS_LABELS[s] || s;
        if (s === current) opt.selected = true;
        sel.appendChild(opt);
      });

      document.body.appendChild(sel);
      sel.focus();

      sel.addEventListener('change', async function() {
        var newStatus = sel.value;
        if (newStatus === current) { sel.remove(); return; }
        sel.remove();
        try {
          await API.updateNode(id, { status: newStatus });
          nodeData[id].status = newStatus;
          showToast('状态已更新为 ' + (STATUS_LABELS[newStatus] || newStatus), 'success');
          showDetail(id); // 刷新详情
        } catch (err) {
          showToast('状态更新失败: ' + err.message, 'error');
        }
      });

      sel.addEventListener('blur', function() { setTimeout(function() { if (sel.parentNode) sel.remove(); }, 200); });
    },

    async deleteNode(id) {
      if (!confirm('确认删除此节点？')) return;
      showToast('删除中...', 'info');
      try {
        await API.deleteNode(id);
        await refreshGraph();
        closeDetail();
        showToast('节点已删除', 'success');
      } catch (err) {
        showToast('删除失败: ' + err.message, 'error');
      }
    },

    editEdge(edgeId) {
      showEdgeEditModal(edgeId);
    },

    async deleteEdge(edgeId) {
      if (!confirm('确认删除此关系？')) return;
      try {
        await API.deleteEdge(edgeId);
        showToast('关系已删除', 'success');
        await refreshGraph();
        if (currentId && nodeData[currentId]) showDetail(currentId);
      } catch (err) {
        showToast('删除失败: ' + err.message, 'error');
      }
    },
  };

  // ── 交互式数组字段操作 ─────────────────────────────────────

  var _arrayCounters = {};

  window.addArrayItem = function(key) {
    var container = document.getElementById('arrayItems_' + key);
    if (!container) return;
    if (!_arrayCounters[key]) _arrayCounters[key] = 0;
    _arrayCounters[key]++;
    var idx = _arrayCounters[key];
    // 从第一个子元素获取 item_fields（存储为 data-* 或从 schemaCache 获取）
    var schema = _schemaCache ? getCachedSchema(key) : null;
    if (!schema || !schema.item_fields) return;
    var row = renderArrayItemRow(key, schema.item_fields, idx);
    // 替换末尾的临时标记（removeArrayItem 用 data-key+idx 而不是 id 来避免重复 id）
    var tempId = 'arrayRow_' + key + '_' + idx;
    container.insertAdjacentHTML('beforeend', row);
    // 让新行的删除按钮使用当前索引
    var newRow = document.getElementById(tempId);
    if (newRow) {
      var delBtn = newRow.querySelector('[onclick*="removeArrayItem"]');
      if (delBtn) delBtn.setAttribute('onclick', 'window.removeArrayItem(\'' + jsStr(key) + '\',' + idx + ')');
    }
  };

  window.removeArrayItem = function(key, index) {
    var row = document.getElementById('arrayRow_' + key + '_' + index);
    if (row) row.remove();
  };

  function getCachedSchema(key) {
    // 从 _schemaCache 中查找包含该 key 的 schema 定义
    for (var typeKey in _schemaCache) {
      var fields = _schemaCache[typeKey];
      if (fields[key] && fields[key].item_fields) return fields[key];
    }
    return null;
  }

  // ── 简单数组（无 item_fields）操作 ──────────────────────────

  var _plainArrayCounters = {};

  window.addPlainArrayItem = function(key) {
    var container = document.getElementById('plainArrayItems_' + key);
    if (!container) return;
    if (!_plainArrayCounters[key]) _plainArrayCounters[key] = 0;
    _plainArrayCounters[key]++;
    var idx = _plainArrayCounters[key];
    var row = renderPlainArrayRow(key, idx);
    container.insertAdjacentHTML('beforeend', row);
  };

  window.removePlainArrayItem = function(key, index) {
    var row = document.getElementById('plainArrayRow_' + key + '_' + index);
    if (row) row.remove();
  };

  // ── 键值编辑器（object 无 fields）操作 ──────────────────────

  var _kvCounters = {};

  window.addKvItem = function(key) {
    var container = document.getElementById('kvEntries_' + key);
    if (!container) return;
    if (!_kvCounters[key]) _kvCounters[key] = 0;
    _kvCounters[key]++;
    var idx = _kvCounters[key];
    var row = renderKvRow(key, idx);
    container.insertAdjacentHTML('beforeend', row);
  };

  window.removeKvItem = function(key, index) {
    var row = document.getElementById('kvRow_' + key + '_' + index);
    if (row) row.remove();
  };

  async function refreshGraph() {
    try {
      const graphResp = await API.fullGraph({ limit: initialLimit, depth: initialDepth });
      const newNodeData = graphResp.nodes || {};
      const newEdgeData = graphResp.edges || [];

      // 合并：保留已加载的邻居节点，追加新数据
      Object.assign(nodeData, newNodeData);
      edgeData = newEdgeData;

      if (nodesDataSet && edgesDataSet) {
        // 构建全套数据后批量 update
        const nodeUpdates = Object.entries(nodeData).map(([nid, n]) => buildVisNode(nid, n));
        const edgeUpdates = edgeData.map(e => buildVisEdge(e));
        nodesDataSet.update(nodeUpdates);
        edgesDataSet.update(edgeUpdates);
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

  // ── 增量刷新：仅更新已加载节点的属性，不重载全图 ─────────

  function incrementalRefresh() {
    if (!nodesDataSet || !edgesDataSet) return refreshGraph();

    // 更新已有节点的属性（状态、标签等变化）
    const nodeUpdates = Object.entries(nodeData).map(([nid, n]) => buildVisNode(nid, n));
    nodesDataSet.update(nodeUpdates);

    if (currentId && nodeData[currentId]) {
      showDetail(currentId);
    }
  }

  // ── Modal 控制 ────────────────────────────────────────────

  window.closeModal = function() {
    document.getElementById('modalOverlay').style.display = 'none';
  };

  // ── Toast 通知 ──────────────────────────────────────────────

  window.showToast = function(message, type) {
    type = type || 'info';
    const container = document.getElementById('toastContainer');
    if (!container) return;
    const el = document.createElement('div');
    el.className = 'toast toast-' + type;
    el.textContent = message;
    container.appendChild(el);
    setTimeout(function() { if (el.parentNode) el.parentNode.removeChild(el); }, 3000);
  };

  // ── 按钮 loading 状态 ──────────────────────────────────────

  function setLoading(btn, loading) {
    if (!btn) return;
    if (loading) {
      btn.classList.add('btn-loading');
      btn._origText = btn.textContent;
    } else {
      btn.classList.remove('btn-loading');
      if (btn._origText) btn.textContent = btn._origText;
    }
  }

  // ── 外部调用 ──────────────────────────────────────────────

  window.closeDetail = closeDetail;
})();