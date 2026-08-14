/**
 * api.js — novel-web-server 前端 API 客户端
 * 封装所有 fetch 调用，统一错误处理。
 */
(function() {
  'use strict';

  window.API = {
    /** 获取项目信息 */
    projectInfo() { return _get('/api/project'); },

    /** 图谱数据（支持分页: limit/offset/depth） */
    fullGraph(params = {}) {
      const q = new URLSearchParams(params).toString();
      return _get(`/api/graph${q ? '?' + q : ''}`);
    },

    /** 单节点详情 */
    nodeDetail(id) { return _get(`/api/nodes/${encodeURIComponent(id)}`); },

    /** 节点列表 */
    listNodes(params = {}) {
      const q = new URLSearchParams(params).toString();
      return _get(`/api/nodes${q ? '?' + q : ''}`);
    },

    /** 创建节点 */
    createNode(data) { return _post('/api/nodes', data); },

    /** 更新节点 */
    updateNode(id, data) { return _put(`/api/nodes/${encodeURIComponent(id)}`, data); },

    /** 删除节点 */
    deleteNode(id, purge = false) {
      return _del(`/api/nodes/${encodeURIComponent(id)}?purge=${purge}`);
    },

    /** 关系列表 */
    listEdges(params = {}) {
      const q = new URLSearchParams(params).toString();
      return _get(`/api/edges${q ? '?' + q : ''}`);
    },

    /** 创建关系 */
    createEdge(data) { return _post('/api/edges', data); },

    /** 更新关系 */
    updateEdge(id, data) { return _put(`/api/edges/${encodeURIComponent(id)}`, data); },

    /** 删除关系 */
    deleteEdge(id) { return _del(`/api/edges/${encodeURIComponent(id)}`); },

    /** 邻居（Ego Network） */
    neighbors(id, depth = 1) {
      return _get(`/api/graph/neighbors/${encodeURIComponent(id)}?depth=${depth}`);
    },

    /** 实体时间线 */
    timeline(id) {
      return _get(`/api/graph/timeline/${encodeURIComponent(id)}`);
    },

    /** 全局时间线（所有场景按故事时间排序） */
    globalTimeline() {
      return _get('/api/graph/timeline');
    },

    /** 结构树（总纲 → 卷 → 章） */
    structureTree() {
      return _get('/api/graph/structure-tree');
    },

    /** 搜索 */
    search(q, scope = '', limit = 50) {
      const params = new URLSearchParams();
      if (q) params.set('q', q);
      if (scope) params.set('scope', scope);
      if (limit) params.set('limit', limit);
      return _get(`/api/search?${params.toString()}`);
    },

    /** 统计 */
    stats() { return _get('/api/stats'); },

    /** 搜索范围（可用类型列表） */
    searchScope() { return _get('/api/project/search-scope'); },

    /** 获取类型的内容字段 schema */
    schemaFields(unitType) { return _get(`/api/project/schema-fields?unit_type=${encodeURIComponent(unitType)}`); },
  };

  // ── 内部方法 ──────────────────────────────────────────────

  function _errMsg(e) {
    // Pydantic 422 错误 detail 可能是数组 [ { loc, msg, type } ]
    if (Array.isArray(e.detail)) {
      return e.detail.map(d => d.msg || d.message).join('; ') || `HTTP 422 (请求参数错误)`;
    }
    if (e.detail && typeof e.detail === 'object') {
      return e.detail.message || e.detail.msg || `HTTP ${e.status || 400}`;
    }
    return e.detail || `HTTP ${e.status || 400}`;
  }

  function _get(url) {
    return fetch(url).then(r => {
      if (!r.ok) return r.json().then(e => { throw new Error(_errMsg(e)); });
      return r.json();
    });
  }

  function _post(url, data) {
    return fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    }).then(r => {
      if (!r.ok) return r.json().then(e => { throw new Error(_errMsg(e)); });
      return r.json();
    });
  }

  function _put(url, data) {
    return fetch(url, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    }).then(r => {
      if (!r.ok) return r.json().then(e => { throw new Error(_errMsg(e)); });
      return r.json();
    });
  }

  function _del(url) {
    return fetch(url, { method: 'DELETE' }).then(r => {
      if (!r.ok) return r.json().then(e => { throw new Error(_errMsg(e)); });
      return r.json();
    });
  }
})();