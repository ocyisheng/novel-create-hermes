"""
render_utils.py — 统一字段渲染引擎

实现值类型推断标准表 + 字段名特殊规则。
所有消费者（v2_graph_viz / v2_detail_template / projection_engine / query）
共用此模块，不再各自实现渲染逻辑。
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple


# ── 字段名特殊规则（优先级最高，覆盖值类型推断） ──────────────────────

SPECIAL_RENDER_MAP: Dict[str, str] = {
    # 字段名 → 强制渲染方式
    "描述": "textblock",
    "核心特质": "tagcloud",
    "key_events": "timeline",
    "character_arc_detail": "group",
    "等级划分": "timeline",
    "cast": "tagcloud",
    "related_plotlines": "tagcloud",
    "主要成员": "tagcloud",
    "角色参与": "tagcloud",
    "涉及角色": "tagcloud",
    "sub_type_detail": "tag",
    "chapter_number": "tag",
    "word_count": "tag",
    "file_path": "tag",
    "章节类型": "tag",
    "类型": "tag",
    "core_conflict": "textblock",
    "ending_design": "textblock",
}

# 自动注册 subtype 字段到特殊渲染映射
from schemas import get_subtype_field_names
for _f in get_subtype_field_names():
    if _f not in SPECIAL_RENDER_MAP:
        SPECIAL_RENDER_MAP[_f] = "tag"

ENTITY_REF_FIELDS = {
    "cast", "related_plotlines", "主要成员", "角色参与", "涉及角色",
}


# ── 值类型推断 ─────────────────────────────────────────────────────


def _is_string_list(val: Any) -> bool:
    return isinstance(val, list) and len(val) > 0 and all(isinstance(v, str) for v in val)


def _is_event_list(val: Any) -> bool:
    return (isinstance(val, list) and len(val) > 0
            and isinstance(val[0], dict)
            and ("event" in val[0]))


def _is_relation_list(val: Any) -> bool:
    return (isinstance(val, list) and len(val) > 0
            and isinstance(val[0], dict)
            and ("目标" in val[0] or "target" in val[0]))


def infer_render_mode(key: str, value: Any) -> str:
    """
    推断字段的渲染方式。
    
    优先级: 字段名特殊规则 > 值类型推断
    """
    # 1. 字段名特殊规则
    if key in SPECIAL_RENDER_MAP:
        return SPECIAL_RENDER_MAP[key]
    
    # 2. 值类型推断
    if value is None or value == "":
        return "skip"
    if isinstance(value, str):
        return "textblock" if len(value) >= 50 else "tag"
    if isinstance(value, bool):
        return "tag"
    if isinstance(value, (int, float)):
        return "tag"
    if isinstance(value, list):
        if len(value) == 0:
            return "tagcloud"  # 空列表默认标签云
        if _is_event_list(value):
            return "timeline"
        if _is_relation_list(value):
            return "relationlist"
        if _is_string_list(value):
            return "tagcloud"
        return "list"
    if isinstance(value, dict):
        return "group"
    return "tag"


# ── 值摘要（用于 QUERY 协议和投影引擎） ─────────────────────────────


def summarize_value(value: Any, max_items: int = 5) -> str:
    """将字段值转为可读摘要字符串"""
    if value is None:
        return "（无）"
    if isinstance(value, str):
        return value[:120] + ("..." if len(value) > 120 else "")
    if isinstance(value, (int, float, bool)):
        return str(value)
    if isinstance(value, list):
        if len(value) == 0:
            return "（空）"
        parts = []
        for i, item in enumerate(value):
            if i >= max_items:
                parts.append(f"...等{len(value)}项")
                break
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                # 取第一个非空值作为摘要
                for v in item.values():
                    if isinstance(v, str) and v:
                        parts.append(v[:30])
                        break
                else:
                    parts.append(str(item)[:30])
            else:
                parts.append(str(item)[:30])
        return ", ".join(parts)
    if isinstance(value, dict):
        keys = list(value.keys())[:max_items]
        return "{" + ", ".join(f"{k}: {summarize_value(value[k], 1)}" for k in keys) + "}"
    return str(value)[:120]


def summarize_content(content: dict, max_fields: int = 20) -> str:
    """
    将 content dict 渲染为可读的多行摘要。
    用于替代当前 query.py 中的 unit.content[:300] 原始 JSON 截断。
    
    兼容旧数据：如果 `_display` 存在，摘要其字段。
    """
    lines = []
    count = 0
    
    # 检查 _display 旧数据兼容
    display_content = content.get("_display")
    if isinstance(display_content, dict) and len(display_content) > 0:
        source = display_content
    else:
        source = content
    
    for key, value in source.items():
        if count >= max_fields:
            lines.append(f"...共 {len(source)} 个字段，仅显示前 {max_fields} 个")
            break
        if key.startswith("_"):
            continue
        mode = infer_render_mode(key, value)
        if mode == "skip":
            continue
        summary = summarize_value(value)
        lines.append(f"  {key}: {summary}")
        count += 1
    return "\n".join(lines)


# ── 渲染分发 ────────────────────────────────────────────────────────


def render_field(key: str, value: Any, mode: Optional[str] = None) -> dict:
    """
    渲染单个字段为结构化结果。
    
    返回: {
        "key": 字段名,
        "mode": 渲染方式,
        "html": 渲染后的 HTML 片段（用于可视化）,
        "text": 纯文本摘要（用于 QUERY）,
    }
    """
    if mode is None:
        mode = infer_render_mode(key, value)
    
    if mode == "skip":
        return {"key": key, "mode": mode, "html": "", "text": ""}
    
    text = summarize_value(value)
    html = _render_to_html(key, value, mode)
    
    return {"key": key, "mode": mode, "html": html, "text": text}


def render_content(content: dict) -> List[dict]:
    """
    渲染整个 content 为结构化结果列表。
    所有消费者共用此函数。
    
    兼容旧数据：如果 `_display` 存在，渲染其中的字段（而非渲染 `_display` 本身）。
    """
    results = []
    
    # 检查 _display 旧数据兼容
    display_content = content.get("_display")
    if isinstance(display_content, dict) and len(display_content) > 0:
        # 旧数据兼容模式：渲染 _display 中的字段
        for key, value in display_content.items():
            if key.startswith("_"):
                continue
            results.append(render_field(key, value))
        return results
    
    # 正常模式：渲染 content 中的所有字段
    for key, value in content.items():
        if key.startswith("_"):
            continue
        results.append(render_field(key, value))
    return results


# ── HTML 渲染（供可视化消费者使用） ─────────────────────────────────


def _render_to_html(key: str, value: Any, mode: str) -> str:
    """将字段渲染为 HTML 片段"""
    if mode == "skip":
        return ""
    if mode == "tag":
        if isinstance(value, str):
            return f'<div class="field-item"><span class="label">{key}</span><span class="value">{_escape_html(value)}</span></div>'
        return f'<div class="field-item"><span class="label">{key}</span><span class="value">{_escape_html(str(value))}</span></div>'
    if mode == "textblock":
        text = str(value)[:600]
        return f'<div class="section"><h3>{key}</h3><div class="desc-text">{_escape_html(text)}</div></div>'
    if mode == "tagcloud":
        if isinstance(value, str):
            # 核心特质 如果被 LLM 写成逗号分隔的字符串，按 tagcloud 展示
            items = re.split(r"[，,、\s]+", value)
        else:
            items = list(value) if isinstance(value, list) else [str(value)]
        tags = " ".join(f'<span class="tag">{_escape_html(str(t))}</span>' for t in items if t)
        return f'<div class="section"><h3>{key}</h3><div class="tagcloud">{tags}</div></div>'
    if mode == "timeline":
        items = list(value) if isinstance(value, list) else []
        parts = []
        for i, item in enumerate(items[:15]):
            if isinstance(item, dict):
                evt = item.get("event") or str(item)
                t = item.get("time") or item.get("time_text") or ""
                time_str = f'<span class="tl-time">{_escape_html(t)}</span> ' if t else ""
                parts.append(f'<div class="tl-item">{time_str}<span class="tl-event">{_escape_html(str(evt)[:100])}</span></div>')
            else:
                parts.append(f'<div class="tl-item"><span class="tl-event">{_escape_html(str(item)[:100])}</span></div>')
        return f'<div class="section"><h3>{key}</h3><div class="timeline">{"".join(parts)}</div></div>'
    if mode == "relationlist":
        items = list(value) if isinstance(value, list) else []
        parts = []
        for item in items[:20]:
            if isinstance(item, dict):
                target = item.get("目标") or item.get("target") or ""
                rel = item.get("关系") or item.get("relation") or ""
                parts.append(f'<div class="rel-item"><span class="rel-target">{_escape_html(target)}</span> <span class="rel-type">({_escape_html(rel)})</span></div>')
            else:
                parts.append(f'<div class="rel-item">{_escape_html(str(item)[:50])}</div>')
        return f'<div class="section"><h3>{key}</h3>{"".join(parts)}</div>'
    if mode == "chart":
        if isinstance(value, dict):
            items = "".join(
                f'<div class="chart-item"><span class="chart-key">{_escape_html(k)}</span><span class="chart-val">{v}</span></div>'
                for k, v in value.items() if isinstance(v, (int, float))
            )
            return f'<div class="section"><h3>{key}</h3><div class="chart">{items}</div></div>'
        return _render_to_html(key, value, "group")
    if mode == "group":
        if isinstance(value, dict):
            children = "".join(
                _render_to_html(k, v, infer_render_mode(k, v))
                for k, v in value.items()
            )
            return f'<div class="section"><h3>{key}</h3><div class="group">{children}</div></div>'
        return _render_to_html(key, value, "tag")
    if mode == "list":
        return _render_to_html(key, value, "tagcloud")  # fallback
    
    return ""


def _escape_html(text: str) -> str:
    """HTML 转义"""
    return (text
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
            .replace("'", "&#39;"))


# ── 实体引用提取（供 relation_inferrer 使用） ──────────────────────


def extract_entity_refs(content: dict) -> List[str]:
    """
    从 content 中递归提取所有 entity_ref 字段中的实体名称列表。
    供 relation_inferrer 使用。
    """
    refs = set()
    _extract_entity_refs_recursive(content, refs)
    return list(refs)


def _extract_entity_refs_recursive(data: Any, refs: set):
    if isinstance(data, dict):
        for key, value in data.items():
            if key in ENTITY_REF_FIELDS and isinstance(value, list):
                for item in value:
                    if isinstance(item, str) and len(item) >= 2:
                        refs.add(item)
            elif isinstance(value, (dict, list)):
                _extract_entity_refs_recursive(value, refs)
    elif isinstance(data, list):
        for item in data:
            _extract_entity_refs_recursive(item, refs)
