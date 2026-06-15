#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
classify_import.py — 基于文件内容的智能分类、路由与格式转换

替代 ProjectImporter 中的硬编码文件名/关键词分类规则，通过读取文件实际内容
判断文件类型，路由到标准目录，并自动转换为三层结构 YAML。

双模式:
  CLI:  python classify_import.py --staging-dir PATH --project-root PATH
  库:   from classify_import import classify_and_route

依赖: Python 3, stdlib + PyYAML
"""

import argparse
import io
import math
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

try:
    import yaml
except ImportError:
    print("错误: 需要 PyYAML，请运行 novel-env-setup 安装依赖", file=sys.stderr)
    sys.exit(1)


# ═══════════════════════════════════════════════════════════════════════════════
# 数据结构
# ═══════════════════════════════════════════════════════════════════════════════

# 文件类型枚举
FILE_TYPE_CHARACTER = "character"
FILE_TYPE_WORLDBUILDING = "worldbuilding"
FILE_TYPE_PLOT_THREAD = "plot_thread"
FILE_TYPE_CHAPTER_OUTLINE = "chapter_outline"
FILE_TYPE_OUTLINE_META = "outline_meta"
FILE_TYPE_CHAPTER_TEXT = "chapter_text"
FILE_TYPE_TRACKING = "tracking"
FILE_TYPE_STYLE = "style"
FILE_TYPE_UNKNOWN = "unknown"

# 类型分组（决定是否做三层转换）
THREE_LAYER_TYPES = {
    FILE_TYPE_CHARACTER,
    FILE_TYPE_WORLDBUILDING,
    FILE_TYPE_PLOT_THREAD,
    FILE_TYPE_CHAPTER_OUTLINE,
}


# ═══════════════════════════════════════════════════════════════════════════════
# 增强型内容分类器
# ═══════════════════════════════════════════════════════════════════════════════

def _load_yaml_safe(path: Path) -> Optional[dict]:
    """安全读取 YAML，失败返回 None。"""
    try:
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        return data if isinstance(data, dict) else None
    except (OSError, yaml.YAMLError):
        return None


def _detect_threelayer_type(data: dict) -> Optional[str]:
    """检测是否已是三层结构 YAML。如是，从 _meta.entity_type 推断类型。

    三层结构标志：同时存在 _meta + 索引信息 + 摘要。
    """
    meta = data.get("_meta")
    if not isinstance(meta, dict):
        return None
    if "索引信息" not in data or "摘要" not in data:
        return None
    if not isinstance(data["索引信息"], dict) or not isinstance(data["摘要"], dict):
        return None
    # 从 _meta 读类型
    entity_type = meta.get("entity_type", "")
    if entity_type in THREE_LAYER_TYPES:
        return entity_type
    if entity_type == "chapter":
        return FILE_TYPE_CHAPTER_OUTLINE
    return None


def _detect_type_from_yaml_keys(data: dict) -> str:
    """基于 YAML 顶层 key 集合判断内容类型，覆盖更广的特征集。

    不使用文件名，仅分析内容结构。检测顺序：特化 → 通用。
    """
    keys = set(data.keys())
    all_keys = " ".join(str(k) for k in keys)

    # ── 特化检测（更精确的特征） ──

    # 大纲/总纲：故事全局框架
    outline_indicators = {
        "大纲", "故事结构", "三幕结构", "五幕结构", "核心概念",
        "人物与世界", "分卷", "故事梗概", "作品简介",
    }
    if keys & outline_indicators:
        return FILE_TYPE_OUTLINE_META
    if any(kw in all_keys for kw in ("幕结构", "幕号", "总纲")):
        return FILE_TYPE_OUTLINE_META

    # 情节线：事件链条描述
    plot_indicators = {"情节线", "主线", "支线", "事件链", "情节线程", "关键事件"}
    if keys & plot_indicators:
        return FILE_TYPE_PLOT_THREAD
    if "关键事件" in keys and "冲突核心" in all_keys:
        return FILE_TYPE_PLOT_THREAD

    # 章节正文/分纲：单章内容
    chapter_indicators = {"章节", "正文", "本章", "分纲"}
    if keys & chapter_indicators:
        # 区分分纲（结构化）和正文（含对话/描写）
        if "场景" in keys or "情节点" in keys or "出场角色" in keys or "结构规划" in keys:
            return FILE_TYPE_CHAPTER_OUTLINE
        return FILE_TYPE_CHAPTER_TEXT

    # 多章节分纲：顶层 key 为 第N章 / Chapter N 模式（≥2 个）
    chapter_key_pattern = re.compile(r"^(?:第\s*)?\d+\s*(?:章|节|Chapter|chapter|ch)\s*$")
    chapter_keys = [k for k in data if isinstance(k, str) and chapter_key_pattern.match(k)]
    if len(chapter_keys) >= 2:
        return FILE_TYPE_CHAPTER_OUTLINE

    # 角色：人物属性
    char_indicators = {"角色", "人物", "角色档案", "人物设定", "角色设定"}
    if keys & char_indicators:
        return FILE_TYPE_CHARACTER
    # 角色常见字段
    char_fields = {"姓名", "年龄", "性别", "性格", "外貌", "背景故事", "身世"}
    if keys & char_fields:
        return FILE_TYPE_CHARACTER
    if "角色类型" in keys or "角色弧线" in keys or "核心特质" in keys:
        return FILE_TYPE_CHARACTER

    # 世界观：设定类
    wb_indicators = {
        "世界名称", "世界观", "力量体系", "势力格局", "核心规则",
        "地理", "版图", "历史", "文化", "世界设定",
    }
    if keys & wb_indicators:
        return FILE_TYPE_WORLDBUILDING
    if any(kw in all_keys for kw in ("纪元", "种族", "势力")):
        return FILE_TYPE_WORLDBUILDING

    # 伏笔/时间线追踪
    tracking_indicators = {"伏笔", "时间线", "追踪"}
    if keys & tracking_indicators:
        return FILE_TYPE_TRACKING

    # 风格文件
    style_indicators = {"风格名称", "文风", "语气", "句式", "用词"}
    if keys & style_indicators:
        return FILE_TYPE_STYLE

    # ── 更通用的启发式 ──

    # 如果包含 4 个以上角色相关字段 → character
    char_heuristic = {"姓名", "性格", "年龄", "性别", "身份", "外貌", "特长", "目标"}
    matched_char = sum(1 for k in keys if k in char_heuristic)
    if matched_char >= 3:
        return FILE_TYPE_CHARACTER

    # 如果包含 3 个以上世界观相关字段 → worldbuilding
    wb_heuristic = {"名称", "描述", "等级", "划分", "体系", "规则", "势力", "区域"}
    matched_wb = sum(1 for k in keys if k in wb_heuristic)
    # 只有"名称"+"描述"可能很多文件都有，需要更多证据
    if matched_wb >= 4:
        return FILE_TYPE_WORLDBUILDING

    return FILE_TYPE_UNKNOWN


def _is_narrative_text(text: str, sample_size: int = 2000) -> bool:
    """判断纯文本是否为叙事性章节正文。

    通过检测对话标记（引号/冒号）、场景描写、人物动作等叙事特征。
    """
    # 去除 BOM
    if text.startswith("\ufeff"):
        text = text[1:]
    if len(text.strip()) < 100:
        return False
    sample = text[:sample_size]
    # 对话检测：中文引号或冒号对话（含 ASCII " 和 ''）
    dialogue_count = len(re.findall(r'[""」』]\s*$|[""「『]|：|：\n', sample, re.MULTILINE))
    # 段落数（空行分隔）
    paragraphs = [p for p in sample.split("\n\n") if p.strip()]
    para_count = len(paragraphs)
    # 叙事特征：每段平均字数 > 30
    avg_para_len = len(sample) / max(para_count, 1)
    # 叙事性内容通常段落连贯、有对话
    if dialogue_count >= 3 and para_count >= 3 and avg_para_len > 30:
        return True
    return False


def _detect_chapter_number(text: str, filename: str) -> int:
    """从文件名或内容中提取章节号。"""
    # 先从文件名提取
    m = re.search(r"(\d+)", filename)
    if m:
        return int(m.group(1))
    # 从内容首部提取：第N章 / 第 N 章 / Chapter N
    m = re.search(r"(?:第\s*)?(\d+)\s*(?:章|节|Chapter|chapter|ch)", text[:500])
    if m:
        return int(m.group(1))
    return 0


def _detect_entity_name(data: dict, preferred_keys: list[str]) -> str:
    """从 dict 中按优先级提取名称。"""
    for key in preferred_keys:
        val = data.get(key)
        if val and isinstance(val, str) and val.strip():
            return val.strip()
    return ""


def _detect_chapter_number_from_yaml(data: dict) -> int:
    """从 YAML 数据中提取章节号。"""
    idx = data.get("索引信息", {})
    if isinstance(idx, dict):
        ch = idx.get("章节号", 0)
        if ch:
            return int(ch)
    # 搜索各层
    for field in ("章节号", "章节", "章号", "chapter"):
        val = data.get(field, 0)
        if val:
            return int(val)
    return 0


# ═══════════════════════════════════════════════════════════════════════════════
# 文件分类主函数
# ═══════════════════════════════════════════════════════════════════════════════

def classify_file(file_path: Path) -> dict:
    """对单个文件进行基于内容的分类。

    Args:
        file_path: 文件绝对路径

    Returns:
        dict 包含:
          - type: 文件类型常量
          - confidence: 置信度 0.0-1.0
          - subtype: 子类型（可选）
          - entity_id: 建议的实体ID（可选）
          - entity_name: 建议的显示名（可选）
          - chapter_number: 章节号（可选）
          - raw_type: 原始检测依据（调试用）
    """
    result = {
        "type": FILE_TYPE_UNKNOWN,
        "confidence": 0.0,
        "subtype": "",
        "entity_id": "",
        "entity_name": "",
        "chapter_number": 0,
        "raw_type": "",
        "needs_splitting": False,
        "suggested_split": [],
    }

    suffix = file_path.suffix.lower()
    stem = file_path.stem

    # ── .txt 文件 ──────────────────────────────────────────────────────
    if suffix == ".txt":
        try:
            text = file_path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            text = ""

        if _is_narrative_text(text):
            ch_num = _detect_chapter_number(text, file_path.name)
            result.update({
                "type": FILE_TYPE_CHAPTER_TEXT,
                "confidence": 0.8,
                "chapter_number": ch_num,
                "raw_type": "narrative_text",
            })
        else:
            # 非叙事文本：可能是笔记、大纲文本等 → 标记 review
            result.update({
                "type": FILE_TYPE_UNKNOWN,
                "confidence": 0.3,
                "raw_type": "non_narrative_text",
            })
        return result

    # ── .yaml / .yml 文件 ──────────────────────────────────────────────
    if suffix in (".yaml", ".yml"):
        data = _load_yaml_safe(file_path)
        if data is None:
            result["raw_type"] = "yaml_parse_error"
            return result

        # 1. 先检查是否为三层结构
        three_type = _detect_threelayer_type(data)
        if three_type:
            idx = data.get("索引信息", {})
            entity_id = idx.get("实体ID", stem)
            name = idx.get("名称", stem)
            ch_num = 0
            if three_type == FILE_TYPE_CHAPTER_OUTLINE:
                ch_num = idx.get("章节号", 0)
            result.update({
                "type": three_type,
                "confidence": 0.95,
                "entity_id": entity_id,
                "entity_name": name,
                "chapter_number": ch_num,
                "raw_type": f"threelayer_{three_type}",
            })
            return result

        # 2. 基于 key 检测类型
        detected = _detect_type_from_yaml_keys(data)

        if detected == FILE_TYPE_CHARACTER:
            name = (
                _detect_entity_name(data, ["姓名", "名称", "name", "角色名", "角色名称"])
                or stem
            )
            entity_id = re.sub(r"[^a-zA-Z0-9_\u4e00-\u9fff]", "_", name)
            result.update({
                "type": detected,
                "confidence": 0.8,
                "entity_id": entity_id,
                "entity_name": name,
                "raw_type": "yaml_key_character",
            })

        elif detected == FILE_TYPE_WORLDBUILDING:
            name = (
                _detect_entity_name(data, [
                    "世界名称", "体系名称", "势力名称", "名称",
                    "地点名称", "世界观名称", "name",
                ]) or stem
            )
            entity_id = re.sub(r"[^a-zA-Z0-9_\u4e00-\u9fff]", "_", name)
            result.update({
                "type": detected,
                "confidence": 0.8,
                "entity_id": entity_id,
                "entity_name": name,
                "subtype": _detect_worldbuilding_subtype(data, stem),
                "raw_type": "yaml_key_worldbuilding",
            })

        elif detected == FILE_TYPE_PLOT_THREAD:
            name = _detect_entity_name(data, ["名称", "情节线名", "name", "主线名", "线索名"]) or stem
            entity_id = re.sub(r"[^a-zA-Z0-9_\u4e00-\u9fff]", "_", name)
            plot_type = "main" if "主线" in stem or "main" in stem.lower() else "sub"
            result.update({
                "type": detected,
                "confidence": 0.75,
                "entity_id": entity_id,
                "entity_name": name,
                "subtype": plot_type,
                "raw_type": "yaml_key_plot_thread",
            })

        elif detected == FILE_TYPE_CHAPTER_OUTLINE:
            ch_num = _detect_chapter_number_from_yaml(data)
            name = f"第{ch_num}章" if ch_num else stem
            entity_id = f"chapter_{ch_num}" if ch_num else stem
            result.update({
                "type": detected,
                "confidence": 0.75,
                "entity_id": entity_id,
                "entity_name": name,
                "chapter_number": ch_num,
                "raw_type": "yaml_key_chapter_outline",
            })

        elif detected == FILE_TYPE_OUTLINE_META:
            result.update({
                "type": detected,
                "confidence": 0.75,
                "raw_type": "yaml_key_outline_meta",
            })

        elif detected == FILE_TYPE_TRACKING:
            result.update({
                "type": detected,
                "confidence": 0.8,
                "raw_type": "yaml_key_tracking",
            })

        elif detected == FILE_TYPE_STYLE:
            name = _detect_entity_name(data, ["风格名称", "名称", "name"]) or stem
            result.update({
                "type": detected,
                "confidence": 0.75,
                "entity_name": name,
                "raw_type": "yaml_key_style",
            })

        else:
            # 完全无法识别
            result["raw_type"] = "unrecognized_yaml"

        return result

    # ── 其他格式（.md, .json, 无扩展名等） ────────────────────────────
    try:
        text = file_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        text = ""

    if _is_narrative_text(text):
        ch_num = _detect_chapter_number(text, file_path.name)
        result.update({
            "type": FILE_TYPE_CHAPTER_TEXT,
            "confidence": 0.6,
            "chapter_number": ch_num,
            "raw_type": f"narrative_{suffix}",
        })
    else:
        result["raw_type"] = f"unknown_{suffix}"

    return result


def _detect_worldbuilding_subtype(data: dict, stem: str) -> str:
    """从内容推断世界观子类型。"""
    # 优先从文件名判断
    subtype_map = {
        "基本信息": "world_overview",
        "核心规则": "rule",
        "力量体系": "power_system",
        "势力格局": "faction",
        "地理位置": "location",
        "历史": "history",
        "文化": "culture",
    }
    if stem in subtype_map:
        return subtype_map[stem]

    keys = set(data.keys())
    # 从内容特征判断
    if keys & {"等级划分", "体系名称", "力量来源", "晋升条件"}:
        return "power_system"
    if keys & {"势力名称", "领袖", "势力平衡", "势力列表"}:
        return "faction"
    if keys & {"物理法则", "禁忌与限制", "因果规律"}:
        return "rule"
    if keys & {"地点名称", "区域描述", "气候", "版图"}:
        return "location"
    if keys & {"纪元划分", "重大事件", "历史"}:
        return "history"
    if keys & {"种族", "宗教", "社会结构", "风俗"}:
        return "culture"
    return "worldbuilding"


# ═══════════════════════════════════════════════════════════════════════════════
# 三层结构转换器
# ═══════════════════════════════════════════════════════════════════════════════

def convert_to_threelayer(data: dict, classification: dict,
                          file_path: Path, project_root: Path) -> Optional[str]:
    """将原始 YAML 数据转换为标准三层结构。

    Args:
        data: 原始 YAML 数据
        classification: classify_file 的输出
        file_path: 原文件路径（用于提取文件名等回退信息）
        project_root: 项目根目录

    Returns:
        三层结构的 YAML 字符串，或 None（转换失败/无需转换）
    """
    ftype = classification["type"]
    if ftype not in THREE_LAYER_TYPES:
        return None

    stem = file_path.stem
    now = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    eid = classification.get("entity_id") or stem
    ename = classification.get("entity_name") or stem

    if ftype == FILE_TYPE_CHARACTER:
        return _convert_character(data, eid, ename, now)

    if ftype == FILE_TYPE_WORLDBUILDING:
        return _convert_worldbuilding(data, eid, ename,
                                       classification.get("subtype", "worldbuilding"), now)

    if ftype == FILE_TYPE_PLOT_THREAD:
        return _convert_plot_thread(data, eid, ename,
                                     classification.get("subtype", "sub"), now)

    if ftype == FILE_TYPE_CHAPTER_OUTLINE:
        ch_num = classification.get("chapter_number", 0)
        return _convert_chapter_outline(data, eid, ename, ch_num, now)

    return None


def _convert_character(data: dict, eid: str, ename: str, now: str) -> str:
    """角色 → 三层结构。"""
    # 从原数据提取现有字段
    role_type = (
        data.get("角色类型")
        or data.get("定位")
        or data.get("类型")
        or ""
    )
    status = data.get("状态") or data.get("status") or "active"
    first_ch = data.get("首次出场章节") or data.get("首章") or 0
    curr_ch = data.get("当前章节位置") or data.get("当前章节") or 0
    one_line = (data.get("一句话描述") or data.get("简介")
                or data.get("description") or data.get("角色简介") or "")
    core_traits = data.get("核心特质") or data.get("性格特点") or data.get("特质") or []
    current_goal = data.get("当前目标") or data.get("目标") or ""
    key_relations = data.get("关键关系") or data.get("关系") or []

    upgraded = {
        "_meta": {
            "entity_type": "character",
            "schema_version": "3.0",
            "created_at": now,
            "updated_at": now,
        },
        "索引信息": {
            "实体ID": eid,
            "名称": ename,
            "角色类型": role_type if isinstance(role_type, str) else str(role_type),
            "状态": str(status),
            "首次出场章节": int(first_ch) if str(first_ch).isdigit() else 0,
            "当前章节位置": int(curr_ch) if str(curr_ch).isdigit() else 0,
        },
        "摘要": {
            "一句话描述": str(one_line) if one_line else "",
            "当前境况": data.get("当前境况", ""),
            "核心特质": core_traits if isinstance(core_traits, list) else [],
            "当前目标": str(current_goal) if current_goal else "",
            "关键关系": key_relations if isinstance(key_relations, list) else [],
        },
        "完整档案": data,
    }
    return _yaml_dump(upgraded)


def _convert_worldbuilding(data: dict, eid: str, ename: str,
                            subtype: str, now: str) -> str:
    """世界观 → 三层结构。"""
    one_liner = (data.pop("一句话概述", "") or data.pop("一句话描述", "")
                 or data.pop("简介", "") or "")
    upgraded = {
        "_meta": {
            "entity_type": subtype,
            "schema_version": "1.0",
            "created_at": now,
            "updated_at": now,
        },
        "索引信息": {
            "实体ID": eid,
            "名称": ename,
            "实体子类型": subtype,
            "状态": "active",
        },
        "摘要": {
            "一句话描述": str(one_liner),
            "章节关联": data.get("章节关联", []),
            "关键词": data.get("关键词", []),
        },
        "完整档案": data,
    }
    return _yaml_dump(upgraded)


def _convert_plot_thread(data: dict, eid: str, ename: str,
                          ptype: str, now: str) -> str:
    """情节线 → 三层结构。"""
    one_line = (data.get("一句话描述") or data.get("描述") or data.get("简介") or "")
    current_situation = data.get("当前境况") or data.get("当前状态") or ""
    core_traits = data.get("核心特质") or data.get("特质") or []
    current_goal = data.get("当前目标") or data.get("目标") or ""
    key_relations = data.get("关键关系") or data.get("涉及角色") or data.get("关联角色") or []

    start_ch = data.get("起始章节") or data.get("开始章节") or 0
    curr_ch = data.get("当前章节位置") or data.get("当前章节") or 0

    upgraded = {
        "_meta": {
            "entity_type": "plot_thread",
            "schema_version": "3.0",
            "created_at": now,
            "updated_at": now,
        },
        "索引信息": {
            "实体ID": eid,
            "名称": ename,
            "类型": ptype,
            "状态": data.get("状态", "active"),
            "起始章节": int(start_ch) if str(start_ch).isdigit() else 0,
            "当前章节位置": int(curr_ch) if str(curr_ch).isdigit() else 0,
        },
        "摘要": {
            "一句话描述": str(one_line),
            "当前境况": str(current_situation),
            "核心特质": core_traits if isinstance(core_traits, list) else [],
            "当前目标": str(current_goal),
            "关键关系": key_relations if isinstance(key_relations, list) else [],
            "当前区间": data.get("当前区间", ""),
            "区间情节点": data.get("区间情节点", []),
            "关联角色": data.get("关联角色", []),
        },
        "完整档案": data,
    }
    return _yaml_dump(upgraded)


def _convert_chapter_outline(data: dict, eid: str, ename: str,
                              ch_num: int, now: str) -> str:
    """分纲 → 三层结构。"""
    one_line = (data.get("一句话描述") or data.get("描述") or data.get("简介")
                or data.get("本章概述") or "")
    current_situation = data.get("当前境况") or data.get("当前状态") or ""
    core_traits = data.get("核心特质") or data.get("关键词") or []
    current_goal = data.get("当前目标") or data.get("本章目标") or ""
    key_relations = data.get("关键关系") or []
    characters = data.get("出场角色") or data.get("角色") or []
    plot_points = data.get("核心情节点") or data.get("情节点") or data.get("场景") or []
    story_time = data.get("故事时间") or data.get("时间") or ""

    upgraded = {
        "_meta": {
            "entity_type": "chapter",
            "schema_version": "3.0",
            "created_at": now,
            "updated_at": now,
        },
        "索引信息": {
            "实体ID": eid,
            "名称": ename,
            "章节号": ch_num,
            "所属分卷": 0,  # 路由时填充
            "状态": "draft",
            "字数": 0,
        },
        "摘要": {
            "一句话描述": str(one_line),
            "当前境况": str(current_situation),
            "故事时间": str(story_time),
            "时间跨度": data.get("时间跨度", ""),
            "核心特质": core_traits if isinstance(core_traits, list) else [],
            "当前目标": str(current_goal),
            "关键关系": key_relations if isinstance(key_relations, list) else [],
            "出场角色": characters if isinstance(characters, list) else [],
            "核心情节点": plot_points if isinstance(plot_points, list) else [],
            "关键转折": data.get("关键转折", False),
        },
        "完整档案": data,
    }
    return _yaml_dump(upgraded)


def _yaml_dump(data: dict) -> str:
    """安全导出 YAML 字符串。"""
    buf = io.StringIO()
    yaml.safe_dump(data, buf, default_flow_style=False, sort_keys=False,
                   allow_unicode=True)
    return buf.getvalue()


# ═══════════════════════════════════════════════════════════════════════════════
# 大文件拆分检测
# ═══════════════════════════════════════════════════════════════════════════════

def _has_multiple_chapters(data: dict) -> bool:
    """检测一个 YAML 是否包含多个章节的分纲。"""
    # 情况1：顶层 key 包含多章数据（如 "第1章", "第2章" 作为 key）
    chapter_keys = [k for k in data if re.search(r"第\s*\d+\s*章", k)]
    if len(chapter_keys) >= 2:
        return True
    # 情况2：列表型章节集合
    for key in ("章节", "分纲", "chapters"):
        val = data.get(key)
        if isinstance(val, list) and len(val) >= 2:
            # 检查列表项是否包含章节号
            for item in val:
                if isinstance(item, dict) and ("章节号" in item or "章" in str(item.get("名称", ""))):
                    return True
        if isinstance(val, dict):
            ch_keys = [k for k in val if re.search(r"\d+", str(k))]
            if len(ch_keys) >= 2:
                return True
    return False


def _split_multi_chapter_outline(data: dict, file_path: Path,
                                  project_root: Path, volume_count: int) -> list[dict]:
    """拆分多章节 YAML 为单个分纲文件。

    Returns:
        list[dict]: 每个元素为 {target_path, yaml_content}
    """
    splits = []
    ch_per_vol = max(1, math.ceil(100 / max(volume_count, 1)))
    stem = file_path.stem

    # 情况1：key 名为 "第N章"
    for key, value in data.items():
        m = re.search(r"第\s*(\d+)\s*章", key)
        if m and isinstance(value, dict):
            ch_num = int(m.group(1))
            vol_num = min(math.ceil(ch_num / ch_per_vol), volume_count)
            vol_dir = project_root / "outline" / "分纲" / f"卷{vol_num}"
            target = vol_dir / f"第{ch_num}章.yaml"
            splits.append({
                "target_path": target,
                "chapter_number": ch_num,
                "data": value,
            })
        elif isinstance(value, dict):
            # 检查内嵌的章节号
            inner_ch = value.get("章节号") or value.get("章")
            if inner_ch:
                ch_num = int(inner_ch)
                vol_num = min(math.ceil(ch_num / ch_per_vol), volume_count)
                vol_dir = project_root / "outline" / "分纲" / f"卷{vol_num}"
                target = vol_dir / f"第{ch_num}章.yaml"
                splits.append({
                    "target_path": target,
                    "chapter_number": ch_num,
                    "data": value,
                })

    # 情况2：列表型
    for key in ("章节", "分纲", "chapters"):
        val = data.get(key)
        if isinstance(val, list):
            for item in val:
                if isinstance(item, dict):
                    ch_num = (item.get("章节号") or item.get("章")
                              or _detect_chapter_number(str(item), ""))
                    if ch_num and ch_num > 0:
                        vol_num = min(math.ceil(ch_num / ch_per_vol), volume_count)
                        vol_dir = project_root / "outline" / "分纲" / f"卷{vol_num}"
                        target = vol_dir / f"第{ch_num}章.yaml"
                        splits.append({
                            "target_path": target,
                            "chapter_number": ch_num,
                            "data": item,
                        })

    return splits


# ═══════════════════════════════════════════════════════════════════════════════
# 路由执行器
# ═══════════════════════════════════════════════════════════════════════════════

def route_file(file_path: Path, classification: dict,
               project_root: Path, volume_count: int = 3,
               dry_run: bool = False) -> dict:
    """根据分类结果将文件路由到标准目录，必要时转换格式。

    Args:
        file_path: 暂存区中的源文件路径
        classification: classify_file 的输出
        project_root: 目标项目根目录
        volume_count: 卷数（影响分纲目录划分）
        dry_run: 仅打印不动文件

    Returns:
        dict: {status, target_path, action, error}
    """
    result = {
        "status": "ok",
        "target_path": "",
        "action": "",       # moved / converted / split / skipped
        "error": "",
    }

    ftype = classification["type"]
    suffix = file_path.suffix.lower()
    ch_per_vol = max(1, math.ceil(100 / max(volume_count, 1)))

    # ── 章节正文 ───────────────────────────────────────────────────────
    if ftype == FILE_TYPE_CHAPTER_TEXT:
        ch_num = classification.get("chapter_number", 0)
        if not ch_num:
            # 按顺序分配章节号
            existing = list(project_root.glob("chapters/*.txt"))
            ch_num = len(existing) + 1
        target = project_root / "chapters" / f"第{ch_num}章{suffix}"
        if not dry_run:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(file_path, target)
        result["target_path"] = str(target)
        result["action"] = "moved"
        return result

    # ── 角色 ────────────────────────────────────────────────────────────
    if ftype == FILE_TYPE_CHARACTER:
        ename = classification.get("entity_name") or file_path.stem
        target = project_root / "characters" / f"{ename}.yaml"
        if not dry_run:
            target.parent.mkdir(parents=True, exist_ok=True)
            data = _load_yaml_safe(file_path)
            if data and classification.get("confidence", 0) >= 0.5:
                yaml_str = convert_to_threelayer(data, classification, file_path, project_root)
                if yaml_str:
                    target.write_text(yaml_str, encoding="utf-8")
                    result["action"] = "converted"
                else:
                    shutil.copy2(file_path, target)
                    result["action"] = "moved"
            else:
                shutil.copy2(file_path, target)
                result["action"] = "moved"
        result["target_path"] = str(target)
        return result

    # ── 世界观 ─────────────────────────────────────────────────────────
    if ftype == FILE_TYPE_WORLDBUILDING:
        ename = classification.get("entity_name") or file_path.stem
        target = project_root / "worldbuilding" / f"{ename}.yaml"
        if not dry_run:
            target.parent.mkdir(parents=True, exist_ok=True)
            data = _load_yaml_safe(file_path)
            if data and classification.get("confidence", 0) >= 0.5:
                yaml_str = convert_to_threelayer(data, classification, file_path, project_root)
                if yaml_str:
                    target.write_text(yaml_str, encoding="utf-8")
                    result["action"] = "converted"
                else:
                    shutil.copy2(file_path, target)
                    result["action"] = "moved"
            else:
                shutil.copy2(file_path, target)
                result["action"] = "moved"
        result["target_path"] = str(target)
        return result

    # ── 情节线 ─────────────────────────────────────────────────────────
    if ftype == FILE_TYPE_PLOT_THREAD:
        ptype = classification.get("subtype", "sub")
        prefix = "主线" if ptype == "main" else "支线"
        ename = classification.get("entity_name") or file_path.stem
        target = project_root / "outline" / "情节线" / f"{prefix}_{ename}.yaml"
        if not dry_run:
            target.parent.mkdir(parents=True, exist_ok=True)
            data = _load_yaml_safe(file_path)
            if data and classification.get("confidence", 0) >= 0.5:
                yaml_str = convert_to_threelayer(data, classification, file_path, project_root)
                if yaml_str:
                    target.write_text(yaml_str, encoding="utf-8")
                    result["action"] = "converted"
                else:
                    shutil.copy2(file_path, target)
                    result["action"] = "moved"
            else:
                shutil.copy2(file_path, target)
                result["action"] = "moved"
        result["target_path"] = str(target)
        return result

    # ── 分纲（单章） ──────────────────────────────────────────────────────
    if ftype == FILE_TYPE_CHAPTER_OUTLINE:
        ch_num = classification.get("chapter_number", 0)
        if not ch_num:
            result["status"] = "needs_review"
            result["action"] = "skipped"
            result["error"] = "无法确定章节号"
            return result
        vol_num = min(math.ceil(ch_num / ch_per_vol), volume_count)
        vol = f"卷{vol_num}"
        target = project_root / "outline" / "分纲" / vol / f"第{ch_num}章.yaml"
        if not dry_run:
            target.parent.mkdir(parents=True, exist_ok=True)
            data = _load_yaml_safe(file_path)
            if data and classification.get("confidence", 0) >= 0.5:
                yaml_str = convert_to_threelayer(data, classification, file_path, project_root)
                if yaml_str:
                    target.write_text(yaml_str, encoding="utf-8")
                    result["action"] = "converted"
                else:
                    shutil.copy2(file_path, target)
                    result["action"] = "moved"
            else:
                shutil.copy2(file_path, target)
                result["action"] = "moved"
        result["target_path"] = str(target)
        return result

    # ── 大纲元文档 ─────────────────────────────────────────────────────
    if ftype == FILE_TYPE_OUTLINE_META:
        # 判断是总纲还是分卷
        if file_path.stem in ("总纲", "故事结构", "大纲"):
            target = project_root / "outline" / "总纲.yaml"
        elif "分卷" in file_path.stem:
            target = project_root / "outline" / "分卷" / file_path.name
        else:
            target = project_root / "outline" / file_path.name
        if not dry_run:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(file_path, target)
        result["target_path"] = str(target)
        result["action"] = "moved"
        return result

    # ── 追踪数据 ───────────────────────────────────────────────────────
    if ftype == FILE_TYPE_TRACKING:
        target = project_root / "outline" / "追踪" / file_path.name
        if not dry_run:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(file_path, target)
        result["target_path"] = str(target)
        result["action"] = "moved"
        return result

    # ── 风格 ────────────────────────────────────────────────────────────
    if ftype == FILE_TYPE_STYLE:
        target = project_root / "styles" / file_path.name
        if not dry_run:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(file_path, target)
        result["target_path"] = str(target)
        result["action"] = "moved"
        return result

    # ── 无法识别 ───────────────────────────────────────────────────────
    result["status"] = "needs_review"
    result["action"] = "skipped"
    result["error"] = f"无法分类: {classification.get('raw_type', 'unknown')}"
    return result


# ═══════════════════════════════════════════════════════════════════════════════
# 主编排
# ═══════════════════════════════════════════════════════════════════════════════

def classify_and_route(staging_dir: Path, project_root: Path,
                       volume_count: int = 3, dry_run: bool = False) -> dict:
    """对暂存区所有文件执行分类→路由→转换，返回汇总结果。

    Args:
        staging_dir: _migration_staging 目录路径
        project_root: 目标项目根目录
        volume_count: 卷数
        dry_run: 仅分析不写文件

    Returns:
        dict: {
            routed: [{file, target, action, type, ...}],
            converted_count: int,
            split_count: int,
            needs_review: [file_path, ...],
            needs_review_count: int,
            stats: {by_type: {character: N, worldbuilding: N, ...}},
        }
    """
    routed = []
    needs_review = []
    stats: dict[str, int] = {}
    converted_count = 0
    split_count = 0

    if not staging_dir.is_dir():
        return {
            "routed": [],
            "converted_count": 0,
            "split_count": 0,
            "needs_review": [],
            "needs_review_count": 0,
            "stats": {},
        }

    for item in sorted(staging_dir.rglob("*")):
        if not item.is_file():
            continue
        if item.name.startswith("."):
            continue

        # 1. 分类
        classification = classify_file(item)
        ftype = classification["type"]

        # 更新统计
        stats[ftype] = stats.get(ftype, 0) + 1

        # 2. 多章节拆分检测
        if ftype == FILE_TYPE_CHAPTER_OUTLINE:
            data = _load_yaml_safe(item)
            if data and _has_multiple_chapters(data):
                splits = _split_multi_chapter_outline(
                    data, item, project_root, volume_count
                )
                if len(splits) >= 2:
                    if not dry_run:
                        for sp in splits:
                            sp["target_path"].parent.mkdir(parents=True, exist_ok=True)
                            # 对每个拆分项单独分类和转换
                            sp_class = classify_file.__wrapped__ if hasattr(classify_file, "__wrapped__") else None
                            sp_data = sp.get("data", {})
                            # 简单包装为 YAML 内容
                            yaml_str = convert_to_threelayer(
                                sp_data,
                                {
                                    "type": FILE_TYPE_CHAPTER_OUTLINE,
                                    "confidence": 0.8,
                                    "entity_id": f"chapter_{sp['chapter_number']}",
                                    "entity_name": f"第{sp['chapter_number']}章",
                                    "chapter_number": sp["chapter_number"],
                                },
                                item, project_root
                            )
                            if yaml_str:
                                sp["target_path"].write_text(yaml_str, encoding="utf-8")
                            else:
                                with open(sp["target_path"], "w", encoding="utf-8") as f:
                                    yaml.safe_dump(sp_data, f, allow_unicode=True,
                                                   default_flow_style=False, sort_keys=False)
                    split_count += len(splits)
                    routed.append({
                        "file": str(item.relative_to(staging_dir)),
                        "target": f"outline/分纲/（拆分为 {len(splits)} 个文件）",
                        "type": ftype,
                        "action": "split",
                        "split_count": len(splits),
                    })
                    continue  # 跳过普通路由

        # 3. 路由
        route_result = route_file(item, classification, project_root,
                                   volume_count, dry_run)

        if route_result["status"] == "needs_review":
            needs_review.append(str(item.relative_to(staging_dir)))

        if route_result["action"] == "converted":
            converted_count += 1

        routed.append({
            "file": str(item.relative_to(staging_dir)),
            "target": route_result.get("target_path", ""),
            "type": ftype,
            "action": route_result.get("action", "skipped"),
            "confidence": classification.get("confidence", 0),
            "entity_name": classification.get("entity_name", ""),
            "error": route_result.get("error", ""),
        })

    return {
        "routed": routed,
        "converted_count": converted_count,
        "split_count": split_count,
        "needs_review": needs_review,
        "needs_review_count": len(needs_review),
        "stats": stats,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# Migration Report 生成
# ═══════════════════════════════════════════════════════════════════════════════

def generate_migration_report(staging_dir: Path, project_root: Path,
                               classify_result: dict, source_path: str = "") -> dict:
    """生成与旧格式兼容的 migration_report.yaml 数据。"""
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    auto_classified = []
    needs_agent_review = []

    for entry in classify_result.get("routed", []):
        item = {
            "path": entry["file"],
            "classification": entry["type"],
            "confidence": entry.get("confidence", 0),
            "action": entry["action"],
            "target": entry.get("target", ""),
            "entity_name": entry.get("entity_name", ""),
        }
        if entry["action"] == "split":
            item["split_count"] = entry.get("split_count", 0)

        if entry.get("error"):
            needs_agent_review.append(item)
        else:
            auto_classified.append(item)

    for file_path in classify_result.get("needs_review", []):
        needs_agent_review.append({
            "path": file_path,
            "classification": "unknown",
            "confidence": 0,
            "action": "needs_review",
            "error": "无法自动分类",
        })

    report = {
        "migration_report": {
            "source_path": source_path or str(staging_dir),
            "imported_at": now,
            "status": "pending_agent_review",
            "classifier": "content_based_v2",
            "auto_classified": auto_classified,
            "needs_agent_review": needs_agent_review,
            "summary": {
                "total_files": len(classify_result.get("routed", [])) + classify_result.get("needs_review_count", 0),
                "auto_classified_count": len(auto_classified),
                "needs_review_count": len(needs_agent_review),
                "converted_count": classify_result.get("converted_count", 0),
                "split_count": classify_result.get("split_count", 0),
                "by_type": classify_result.get("stats", {}),
            },
        }
    }

    return report


# ═══════════════════════════════════════════════════════════════════════════════
# CLI 入口
# ═══════════════════════════════════════════════════════════════════════════════

def _cmd_classify(args):
    """子命令：分类单个文件。"""
    file_path = Path(args.file).resolve()
    if not file_path.is_file():
        print(f"错误: 文件不存在: {file_path}", file=sys.stderr)
        sys.exit(1)
    result = classify_file(file_path)
    # 输出为 YAML
    output = {
        "file": str(file_path),
        "type": result["type"],
        "confidence": result["confidence"],
        "entity_name": result.get("entity_name", ""),
        "entity_id": result.get("entity_id", ""),
        "chapter_number": result.get("chapter_number", 0),
        "raw_type": result.get("raw_type", ""),
        "needs_splitting": result.get("needs_splitting", False),
    }
    yaml.safe_dump(output, sys.stdout, allow_unicode=True,
                   default_flow_style=False, sort_keys=False)


def _cmd_convert(args):
    """子命令：转换单个文件为三层结构。"""
    file_path = Path(args.file).resolve()
    if not file_path.is_file():
        print(f"错误: 文件不存在: {file_path}", file=sys.stderr)
        sys.exit(1)

    type_map = {
        "character": FILE_TYPE_CHARACTER,
        "worldbuilding": FILE_TYPE_WORLDBUILDING,
        "chapter": FILE_TYPE_CHAPTER_OUTLINE,
        "plot_thread": FILE_TYPE_PLOT_THREAD,
    }
    ftype = type_map.get(args.type)
    if not ftype:
        print(f"错误: 不支持的实体类型 '{args.type}'，可选: {list(type_map.keys())}", file=sys.stderr)
        sys.exit(1)

    data = _load_yaml_safe(file_path)
    if data is None:
        print(f"错误: 无法解析 YAML 文件: {file_path}", file=sys.stderr)
        sys.exit(1)

    classification = {
        "type": ftype,
        "confidence": 0.9,
        "entity_id": args.name or file_path.stem,
        "entity_name": args.name or file_path.stem,
        "chapter_number": args.chapter or 0,
        "subtype": args.subtype or "",
    }

    project_root = Path(args.project_root or ".").resolve()
    yaml_str = convert_to_threelayer(data, classification, file_path, project_root)
    if yaml_str is None:
        print(f"跳过: 类型 '{args.type}' 不需要三层转换", file=sys.stderr)
        return

    if args.out:
        out_path = Path(args.out).resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(yaml_str, encoding="utf-8")
        print(f"已写入: {out_path}")
    else:
        print(yaml_str)


CMD_MAP = {
    "classify": _cmd_classify,
    "convert": _cmd_convert,
}


def main():
    parser = argparse.ArgumentParser(
        description="classify_import.py — 基于文件内容的智能分类、路由与格式转换",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("command", nargs="?",
                        help=f"子命令: {'/'.join(CMD_MAP.keys())}（省略则使用全量模式）")
    parser.add_argument("file", nargs="?", help="目标文件路径（子命令模式）")
    # 全量模式参数
    parser.add_argument("--staging-dir", help="迁移暂存目录路径（_migration_staging）")
    parser.add_argument("--project-root", default="", help="目标项目根目录")
    parser.add_argument("--volumes", type=int, default=3, help="卷数（默认 3）")
    parser.add_argument("--dry-run", action="store_true", help="仅分析，不写文件")
    parser.add_argument("--source-path", default="", help="源项目路径（用于 migration_report）")
    # 子命令参数
    parser.add_argument("--type", default="", help="实体类型（character/worldbuilding/chapter/plot_thread）")
    parser.add_argument("--name", default="", help="实体名称")
    parser.add_argument("--subtype", default="", help="子类型")
    parser.add_argument("--chapter", type=int, default=0, help="章节号")
    parser.add_argument("--out", default="", help="输出路径（convert 子命令）")

    args = parser.parse_args()

    # ── 子命令模式 ──────────────────────────────────────────────────────
    if args.command in CMD_MAP:
        if not args.file:
            print(f"错误: 子命令 '{args.command}' 需要文件路径参数", file=sys.stderr)
            sys.exit(1)
        CMD_MAP[args.command](args)
        return

    # ── 全量模式（向后兼容） ────────────────────────────────────────────
    if not args.staging_dir:
        parser.print_help()
        sys.exit(1)

    staging_dir = Path(args.staging_dir).resolve()
    project_root = Path(args.project_root).resolve() if args.project_root else staging_dir.parent

    if not staging_dir.is_dir():
        print(f"错误: 暂存目录不存在: {staging_dir}", file=sys.stderr)
        sys.exit(1)
    if not project_root.is_dir():
        print(f"错误: 项目目录不存在: {project_root}", file=sys.stderr)
        sys.exit(1)

    # 执行分类和路由
    result = classify_and_route(
        staging_dir, project_root,
        volume_count=args.volumes,
        dry_run=args.dry_run,
    )

    # 输出摘要
    stats = result.get("stats", {})
    print(f"📂 文件分类统计:")
    for ftype, count in sorted(stats.items()):
        if count > 0:
            print(f"   {ftype}: {count}")
    print(f"   total: {sum(stats.values())}")
    print()
    if result["converted_count"] > 0:
        print(f"🔄 三层结构转换: {result['converted_count']} 个文件")
    if result["split_count"] > 0:
        print(f"✂️  大文件拆分: {result['split_count']} 个分纲文件")
    if result["needs_review_count"] > 0:
        print(f"⚠️  待审查: {result['needs_review_count']} 个文件")
    print()
    for entry in result.get("routed", []):
        action_icon = {"converted": "🔄", "moved": "📋", "split": "✂️", "skipped": "❓"}.get(entry["action"], "📄")
        print(f"  {action_icon} {entry['file']} → {entry['type']} ({entry['action']})")

    # 生成 migration_report
    report = generate_migration_report(
        staging_dir, project_root, result, args.source_path,
    )
    report_path = project_root / "migration_report.yaml"
    if not args.dry_run:
        with open(report_path, "w", encoding="utf-8") as f:
            yaml.safe_dump(report, f, allow_unicode=True, default_flow_style=False)
        print(f"\n📄 迁移报告: {report_path}")
    else:
        print(f"\n🧪 DRY RUN: 未写入文件")


if __name__ == "__main__":
    main()
