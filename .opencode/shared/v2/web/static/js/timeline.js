/**
 * timeline.js — 时间线视图
 *
 * 功能：
 * 1. 全局时间线：所有 SCENE 按故事时间排序的纵向时间轴
 * 2. 按章节分组，折叠/展开
 * 3. 角色筛选、章节筛选
 * 4. 点击场景 → 在图中聚焦该节点（切换到图谱视图）
 */
(function() {
  'use strict';

  let tlData = null;           // 原始时间线数据
  let tlCharacterMap = {};     // 角色名 → 场景列表（引用）
  let currentChapterFilter = '';
  let currentCharacterFilter = '';

  // ── 主渲染入口 ──────────────────────────────────────────

  /** 加载并渲染全局时间线 */
  function loadTimeline() {
    const content = document.getElementById('timelineContent');
    if (!content) return;

    // 尝试先渲染已缓存数据
    if (tlData) {
      renderTimeline(tlData);
      return;
    }

    content.innerHTML = '<div class="tl-loading">⏳ 加载时间线中...</div>';

    API.globalTimeline()
      .then(function(data) {
        tlData = data;
        // 构建角色表
        tlCharacterMap = data.by_character || {};
        // 填充筛选器
        populateFilters(data);
        renderTimeline(data);
      })
      .catch(function(err) {
        content.innerHTML = '<div class="tl-empty">加载失败: ' + esc(err.message) + '</div>';
      });
  }

  /** 填充角色和章节筛选下拉 */
  function populateFilters(data) {
    // 角色
    const charSelect = document.getElementById('tlCharacterFilter');
    if (charSelect) {
      const names = Object.keys(data.by_character || {}).sort();
      charSelect.innerHTML = '<option value="">全部角色</option>' +
        names.map(function(n) { return '<option value="' + esc(n) + '">' + esc(n) + '</option>'; }).join('');
    }

    // 章节
    const chSelect = document.getElementById('tlChapterFilter');
    if (chSelect && data.chapters) {
      chSelect.innerHTML = '<option value="">全部章节</option>' +
        data.chapters.map(function(ch) {
          return '<option value="' + ch.chapter + '">第 ' + ch.chapter + ' 章（' + ch.scenes.length + ' 场景）</option>';
        }).join('');
    }

    // 统计
    const stats = document.getElementById('tlStats');
    if (stats) {
      stats.textContent = data.total_scenes + ' 场景';
    }
  }

  /** 渲染时间线 */
  function renderTimeline(data) {
    const content = document.getElementById('timelineContent');
    if (!content) return;

    if (!data.chapters || data.chapters.length === 0) {
      content.innerHTML = '<div class="tl-empty">暂无时间线数据</div>';
      return;
    }

    var html = '';

    data.chapters.forEach(function(ch) {
      var chapterNum = ch.chapter;
      var scenes = ch.scenes;

      // 应用筛选
      if (currentChapterFilter && String(chapterNum) !== currentChapterFilter) return;
      if (currentCharacterFilter) {
        scenes = scenes.filter(function(s) {
          return s.characters && s.characters.indexOf(currentCharacterFilter) >= 0;
        });
        if (scenes.length === 0) return;
      }

      html += '<div class="tl-chapter">';
      html += '<div class="tl-chapter-header" onclick="TIMELINE.toggleChapter(this)">';
      html += '<span class="tl-chapter-toggle">▶</span>';
      html += '<span class="tl-chapter-title">第 ' + chapterNum + ' 章</span>';
      html += '<span class="tl-chapter-count">' + scenes.length + ' 场景</span>';
      html += '</div>';
      html += '<div class="tl-chapter-body">';

      scenes.forEach(function(s, idx) {
        var isLast = idx === scenes.length - 1;
        html += renderSceneItem(s, idx, isLast);
      });

      html += '</div>'; // tl-chapter-body
      html += '</div>'; // tl-chapter
    });

    if (!html) {
      html = '<div class="tl-empty">没有匹配的场景</div>';
    }

    content.innerHTML = html;

    // 默认所有章节展开
    var bodies = content.querySelectorAll('.tl-chapter-body');
    for (var i = 0; i < bodies.length; i++) {
      bodies[i].style.display = 'block';
    }
    var toggles = content.querySelectorAll('.tl-chapter-toggle');
    for (var i = 0; i < toggles.length; i++) {
      toggles[i].textContent = '▼';
    }
  }

  /** 渲染单个场景条目 */
  function renderSceneItem(s, idx, isLast) {
    var ordinal = s.ordinal !== undefined && s.ordinal !== null
      ? '<span class="tl-ordinal">#' + Math.round(s.ordinal) + '</span>'
      : '';
    var timeLabel = s.time_label
      ? '<span class="tl-time-label">' + esc(s.time_label) + '</span>'
      : '';
    var location = s.location
      ? '<span class="tl-location">📍 ' + esc(s.location) + '</span>'
      : '';
    var manualBadge = s.is_manual_ordinal
      ? '<span class="tl-badge tl-badge-manual" title="手动序数">📌</span>'
      : '';
    var parallelBadge = s.precision === 'same'
      ? '<span class="tl-badge tl-badge-parallel" title="平行场景">↕</span>'
      : '';

    // 角色标签（最多 5 个，超出显示 +N）
    var charHtml = '';
    if (s.characters && s.characters.length > 0) {
      var shown = s.characters.slice(0, 5);
      var extra = s.characters.length > 5 ? s.characters.length - 5 : 0;
      charHtml = shown.map(function(c) {
        return '<span class="tl-char-tag" onclick="TIMELINE.filterByCharacter(\'' + esc(c) + '\')">' + esc(c) + '</span>';
      }).join('');
      if (extra > 0) {
        charHtml += '<span class="tl-char-tag tl-char-more" title="' + esc(s.characters.slice(5).join(', ')) + '">+' + extra + '</span>';
      }
    }

    return '<div class="tl-scene" data-unit-id="' + esc(s.unit_id || '') + '">' +
      '<div class="tl-scene-line">' +
        '<div class="tl-dot-wrapper">' +
          '<div class="tl-dot' + (s.precision === 'same' ? ' tl-dot-parallel' : '') + '"></div>' +
          (!isLast ? '<div class="tl-line"></div>' : '') +
        '</div>' +
        '<div class="tl-scene-card" onclick="TIMELINE.focusScene(\'' + esc(s.unit_id || '') + '\')">' +
          '<div class="tl-scene-header">' +
            '<span class="tl-scene-name">' + esc(s.unit_name || '') + '</span>' +
            ordinal +
            manualBadge + parallelBadge +
          '</div>' +
          '<div class="tl-scene-meta">' +
            timeLabel +
            location +
          '</div>' +
          '<div class="tl-scene-chars">' + charHtml + '</div>' +
        '</div>' +
      '</div>' +
    '</div>';
  }

  // ── 筛选 ────────────────────────────────────────────────

  function applyFilter() {
    if (!tlData) return;
    currentCharacterFilter = document.getElementById('tlCharacterFilter')?.value || '';
    currentChapterFilter = document.getElementById('tlChapterFilter')?.value || '';
    renderTimeline(tlData);
  }

  function resetTimelineFilter() {
    var cf = document.getElementById('tlCharacterFilter');
    var chf = document.getElementById('tlChapterFilter');
    if (cf) cf.value = '';
    if (chf) chf.value = '';
    currentCharacterFilter = '';
    currentChapterFilter = '';
    if (tlData) renderTimeline(tlData);
  }

  function filterByCharacter(name) {
    var cf = document.getElementById('tlCharacterFilter');
    if (cf) { cf.value = name; }
    currentCharacterFilter = name;
    currentChapterFilter = '';
    var chf = document.getElementById('tlChapterFilter');
    if (chf) chf.value = '';
    if (tlData) renderTimeline(tlData);
  }

  // ── 交互 ────────────────────────────────────────────────

  function toggleChapter(headerEl) {
    var body = headerEl.parentNode.querySelector('.tl-chapter-body');
    if (!body) return;
    var toggle = headerEl.querySelector('.tl-chapter-toggle');
    if (body.style.display === 'none') {
      body.style.display = 'block';
      if (toggle) toggle.textContent = '▼';
    } else {
      body.style.display = 'none';
      if (toggle) toggle.textContent = '▶';
    }
  }

  function focusScene(unitId) {
    if (!unitId) return;
    // 切换到图谱视图并聚焦节点
    if (typeof window.switchView === 'function') {
      switchView('graph', unitId);
    }
  }

  // ── 工具 ────────────────────────────────────────────────

  function esc(s) {
    return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  // ── 在 detail panel 中渲染角色时间线 ─────────────────────

  function renderEntityTimeline(entityId, entityName, container) {
    if (!container) return;
    container.innerHTML = '<div class="tl-mini-loading">加载时间线...</div>';

    API.timeline(entityId)
      .then(function(data) {
        if (!data.events || data.events.length === 0) {
          container.innerHTML = '<div class="tl-empty" style="padding:8px 0;font-size:12px">暂无时间线事件</div>';
          return;
        }
        var html = '<div class="tl-mini">';
        data.events.forEach(function(evt) {
          html += '<div class="tl-mini-item">' +
            '<div class="tl-mini-dot"></div>' +
            '<div class="tl-mini-body">' +
              '<div class="tl-mini-time">' + esc(evt.time_label || '') + '</div>' +
              '<div class="tl-mini-event">' +
                (evt.location ? '📍 ' + esc(evt.location) + ' · ' : '') +
                esc(evt.event || '') +
              '</div>' +
            '</div>' +
          '</div>';
        });
        html += '</div>';
        container.innerHTML = html;
      })
      .catch(function(err) {
        container.innerHTML = '<div class="tl-empty" style="padding:8px 0;font-size:12px;color:var(--danger)">加载失败</div>';
      });
  }

  // ── 暴露全局接口 ────────────────────────────────────────

  window.TIMELINE = {
    load: loadTimeline,
    toggleChapter: toggleChapter,
    focusScene: focusScene,
    filterByCharacter: filterByCharacter,
    applyFilter: applyFilter,
    renderEntityTimeline: renderEntityTimeline,
  };

  // 绑定筛选事件
  document.addEventListener('DOMContentLoaded', function() {
    var cf = document.getElementById('tlCharacterFilter');
    var chf = document.getElementById('tlChapterFilter');
    if (cf) cf.addEventListener('change', applyFilter);
    if (chf) chf.addEventListener('change', applyFilter);
  });

})();
