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

    // 预计算可见节点
    const visible = new Set();
    Object.entries(nodeData).forEach(([id, n]) => {
      let ok = true;
      if (typeVal !== 'all' && n.type !== typeVal) ok = false;
      if (query && !(n.label || '').toLowerCase().includes(query)) ok = false;
      if (ok) visible.add(id);
    });

    // 批量更新节点可见性（一次 update 一批，避免逐条 re-render）
    const nodeUpdates = [];
    nodesDataSet.forEach(node => {
      const shouldHide = !visible.has(node.id);
      if (node.hidden !== shouldHide) nodeUpdates.push({ id: node.id, hidden: shouldHide });
    });
    if (nodeUpdates.length) nodesDataSet.update(nodeUpdates);

    // 批量更新边
    const edgeUpdates = [];
    edgesDataSet.forEach(edge => {
      const shouldHide = !visible.has(edge.from) || !visible.has(edge.to);
      if (edge.hidden !== shouldHide) edgeUpdates.push({ id: edge.id, hidden: shouldHide });
    });
    if (edgeUpdates.length) edgesDataSet.update(edgeUpdates);

    network.fit({ animation: false });
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
    const status = n.status || 'sprout';
    const statusLabels = { sprout:'萌芽', growing:'生长中', mature:'成熟', frozen:'冻结', archived:'已归档' };
    meta.innerHTML = (n.type_label || n.type || '') +
      ' · <span class="status-badge status-' + status + '" onclick="APP.editStatus(\'' + id + '\', this)">' + (statusLabels[status] || status) + '</span>' +
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
            '<span class="rel-name" onclick="APP.focusNode(\'' + r.id + '\')" style="cursor:pointer">' + esc(r.name) + '</span>' +
            '<span class="rel-label">' + esc(r.rel) + '</span>' +
            '<span style="margin-left:auto;font-size:11px;display:flex;gap:2px">' +
            '<span onclick="APP.editEdge(\'' + r.edgeId + '\')" style="cursor:pointer;color:var(--accent);padding:0 4px" title="编辑关系">✎</span>' +
            '<span onclick="APP.deleteEdge(\'' + r.edgeId + '\')" style="cursor:pointer;color:var(--danger);padding:0 4px" title="删除关系">✕</span>' +
            '</span></div>';
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
      `<option value="${t.value}"${t.value === defaults.unit_type ? ' selected' : ''}>${t.label}</option>`
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
        <div style="margin-top:8px">
          <label style="cursor:pointer;display:inline-flex;align-items:center;gap:4px;color:var(--text-dim);font-size:12px">
            <input type="checkbox" id="toggleRawJson" ${showStructured ? '' : 'checked'} onchange="document.getElementById('rawJsonArea').style.display=this.checked?'block':'none'" />
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

      // 结构化模式 → 从 _extra_* 字段重建 content
      var toggle = document.getElementById('toggleRawJson');
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

  // ── 刷新图谱 ──────────────────────────────────────────────

  async function refreshGraph() {
    try {
      const graphResp = await API.fullGraph();
      nodeData = graphResp.nodes || {};
      edgeData = graphResp.edges || [];

      // 更新 vis.DataSet（用 update 替代 clear+add，避免闪烁）
      if (nodesDataSet && edgesDataSet) {
        nodeData = graphResp.nodes || {};
        edgeData = graphResp.edges || [];

        // 构建全套数据后批量 update（DataSet 按 id 匹配，新旧一致则保持状态）
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

  // ── 增量刷新（用 update 避免闪烁，语义别名） ─────────────

  function incrementalRefresh() {
    return refreshGraph();
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