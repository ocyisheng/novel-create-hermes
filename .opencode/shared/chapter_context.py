#!/usr/bin/env python3
"""
chapter_context.py — 收集章节写作所需的全部上下文 + 上下文完整性评分

一次性收集 novel-chapter 技能所需的 13+ 个上下文槽位，
输出 JSON 格式供 extract_template.py 填充变量。
新增 assess_context_completeness() 评估数据维度缺口。

Usage:
    python chapter_context.py --project-root NOVELS_ROOT/项目名 --chapter 5
    python chapter_context.py --project-root NOVELS_ROOT/项目名 --chapter 5 --output /tmp/context.json
    python chapter_context.py --project-root NOVELS_ROOT/项目名 --chapter 5 --list-vars
    python chapter_context.py --project-root NOVELS_ROOT/项目名 --chapter 5 --assess  # 仅输出完整性评分
"""

import argparse
import json
import re
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print("错误: 需要 PyYAML，请运行 novel-env-setup 安装依赖", file=sys.stderr)
    sys.exit(1)

from _utils import load_yaml, get_nested


# ── 分纲查找 ─────────────────────────────────────────────────────────────────

def find_chapter_outline(project_root: Path, chapter_num: int) -> Path | None:
    """查找分纲文件：outline/分纲/卷*/第{N}章.yaml"""
    outline_dir = project_root / "outline" / "分纲"
    if not outline_dir.is_dir():
        return None
    target = f"第{chapter_num}章.yaml"
    for fpath in outline_dir.rglob(target):
        return fpath
    return None


# ── 前章摘要 ─────────────────────────────────────────────────────────────────

def load_previous_summary(project_root: Path, chapter_num: int) -> str:
    """从 outline/追踪/章节摘要.yaml 读取第{N-1}章摘要。"""
    if chapter_num <= 1:
        return "（第一章，无前章摘要）"

    summaries_path = project_root / "outline" / "追踪" / "章节摘要.yaml"
    data = load_yaml(summaries_path)

    # 尝试多种格式
    prev_key = f"第{chapter_num - 1}章"
    summary = data.get(prev_key, {})
    if isinstance(summary, dict):
        return summary.get("摘要", "")
    elif isinstance(summary, str):
        return summary

    # 尝试列表格式
    if isinstance(data.get("chapters"), list):
        for item in data["chapters"]:
            if item.get("章节号") == chapter_num - 1:
                return item.get("摘要", "")

    return ""


# ── 附近章分纲 ───────────────────────────────────────────────────────────────

def load_nearby_outlines(project_root: Path, chapter_num: int, range_n: int = 5) -> str:
    """读取当前章 ±N 章的上下文章节信息，提供就近情节点参考。

    数据来源：
      - 第 N-1 章（前章）：优先用 outline/追踪/章节摘要.yaml 写后记录（更准确）
      - 其他章节：outline/分纲/卷*/ 下分纲 Layer 2 摘要（写前规划）
    跳过不存在的分纲（尚未创建的章节自动忽略）和当前章自身。
    """
    parts = []
    start = max(1, chapter_num - range_n)
    end = chapter_num + range_n

    for n in range(start, end + 1):
        if n == chapter_num:
            continue

        # 第 N-1 章：使用追踪摘要（写后记录），比规划更准确
        if n == chapter_num - 1:
            prev_summary = load_previous_summary(project_root, chapter_num)
            if prev_summary and prev_summary not in ("（第一章，无前章摘要）", ""):
                line = f"  ◀ 第{n}章（前章·写后记录）: {prev_summary}"
                parts.append(line)
                continue

        # 其他附近章节：走分纲 Layer 2 摘要
        fpath = find_chapter_outline(project_root, n)
        if not fpath:
            continue
        data = load_yaml(fpath)
        if not data:
            continue
        summary = data.get("摘要", {})
        if not summary:
            continue

        one_line = summary.get("一句话描述", "")
        if not one_line:
            continue

        plot_points = summary.get("核心情节点", [])
        characters = summary.get("出场角色", [])
        story_time = summary.get("故事时间", "")
        is_crisis = summary.get("关键转折", False)

        label = f"第{n}章"
        if is_crisis:
            label += " ★关键转折"
        line = f"  {label}: {one_line}"
        if story_time:
            line += f" [{story_time}]"
        if plot_points:
            points = plot_points[:3]
            line += f" | {' → '.join(points)}"
        if characters:
            chars = characters[:5]
            line += f"  出场: {', '.join(chars)}"
        parts.append(line)

    if not parts:
        return "（无附近章节数据）"

    prev_count = chapter_num - start if chapter_num - start > 0 else 0
    next_count = end - chapter_num
    header = f"── 前{prev_count}章 → 后{next_count}章 ──"
    return f"{header}\n" + "\n".join(parts)


# ── 前一章衔接 ───────────────────────────────────────────────────────────────

def load_previous_linkage(project_root: Path, chapter_num: int) -> str:
    """读取前一章最后 100 字 + 前一章分纲的下章铺垫。"""
    if chapter_num <= 1:
        return "（第一章，无前章衔接）"

    # 读取前一章正文最后 100 字
    prev_chapter = project_root / "chapters" / f"第{chapter_num - 1}章.txt"
    last_100 = ""
    if prev_chapter.is_file():
        text = prev_chapter.read_text(encoding="utf-8")
        clean = text.replace("\n", "").replace("\r", "")
        last_100 = clean[-100:] if len(clean) > 100 else clean

    # 读取前一章分纲的下章铺垫
    prev_outline = find_chapter_outline(project_root, chapter_num - 1)
    pickup = ""
    if prev_outline:
        data = load_yaml(prev_outline)
        pickup = get_nested(data, "完整档案.结构规划.收尾.下章铺垫") or ""

    parts = []
    if last_100:
        parts.append(f"前章末尾：{last_100}")
    if pickup:
        parts.append(f"下章铺垫：{pickup}")
    return "\n".join(parts) if parts else ""


# ── 出场角色档案 ─────────────────────────────────────────────────────────────

def load_character_profiles(project_root: Path, chapter_num: int) -> str:
    """从分纲提取出场角色 → project_index 找路径 → 读取完整档案。"""
    outline_path = find_chapter_outline(project_root, chapter_num)
    if not outline_path:
        return ""

    outline = load_yaml(outline_path)

    # 从分纲提取角色名
    character_names = []
    for char in get_nested(outline, "完整档案.出场角色") or []:
        if isinstance(char, dict):
            name = char.get("角色名", "")
        elif isinstance(char, str):
            name = char
        else:
            continue
        if name:
            character_names.append(name)

    if not character_names:
        return ""

    # 加载 project_index.yaml
    index_path = project_root / "project_index.yaml"
    index = load_yaml(index_path)
    characters = index.get("characters", {})

    # 读取角色档案（摘要段优先）
    parts = []
    for name in character_names:
        # 在 project_index 中查找
        file_path = None
        for entity_id, entry in characters.items():
            if entry.get("name") == name:
                file_path = entry.get("file_path")
                break

        if not file_path:
            continue

        char_path = project_root / file_path
        if not char_path.is_file():
            continue

        char_data = load_yaml(char_path)
        summary = char_data.get("摘要", {})
        if summary:
            # 使用摘要段
            profile = f"### {name}\n"
            profile += f"一句话描述：{summary.get('一句话描述', '')}\n"
            profile += f"当前境况：{summary.get('当前境况', '')}\n"
            if summary.get("性格特征"):
                profile += f"性格特征：{', '.join(summary['性格特征'])}\n"
            if summary.get("能力特征"):
                profile += f"能力特征：{', '.join(summary['能力特征'])}\n"
            parts.append(profile)
        else:
            # 降级到完整档案
            full = char_data.get("完整档案", {})
            if full:
                parts.append(f"### {name}\n{json.dumps(full, ensure_ascii=False, indent=2)}")

    return "\n\n".join(parts)


# ── 世界观相关实体 ───────────────────────────────────────────────────────────

def load_worldbuilding_entities(project_root: Path, chapter_num: int) -> str:
    """从分纲"世界观补充"字段 → 读取 worldbuilding/ 对应文件。"""
    outline_path = find_chapter_outline(project_root, chapter_num)
    if not outline_path:
        return ""

    outline = load_yaml(outline_path)
    supplements = get_nested(outline, "完整档案.世界观补充") or []

    if not supplements:
        return ""

    # 加载 project_index.yaml
    index_path = project_root / "project_index.yaml"
    index = load_yaml(index_path)
    worldbuilding = index.get("worldbuilding", {})

    parts = []
    for item in supplements:
        if not isinstance(item, dict):
            continue
        content = item.get("内容描述", "")
        if content:
            parts.append(content)

    return "\n".join(parts) if parts else ""


# ── 待处理伏笔（规划 + 追踪合并） ────────────────────────────────────────────

def load_foreshadowing(project_root: Path, chapter_num: int) -> str:
    """从规划文件 + 追踪文件合并加载伏笔上下文。

    规划数据（outline/伏笔规划.yaml）提供完整设计意图（编号/名称/关联情节线/回收位置），
    追踪数据（outline/追踪/伏笔.yaml）提供实际写后状态（状态/回收章节）。
    若追踪文件不存在或为空，仅返回规划数据。

    Returns:
        格式化字符串，包含全局伏笔规划和当前待处理伏笔状态。
    """
    plan_path = project_root / "outline" / "伏笔规划.yaml"
    track_path = project_root / "outline" / "追踪" / "伏笔.yaml"

    parts = []
    track_lookup = {}  # 描述 → 追踪条目（用于合并状态）

    # 1. 加载追踪数据，建立描述→状态的查询表
    track_data = load_yaml(track_path)
    if track_data:
        foreshadowing_list = track_data.get("伏笔") or []
        for item in foreshadowing_list:
            desc = item.get("描述", "")
            if desc:
                track_lookup[desc] = item

    # 2. 从规划文件加载全局设计意图
    plan_data = load_yaml(plan_path)
    if plan_data and plan_data.get("伏笔规划"):
        parts.append("【全局伏笔规划】")
        for item in plan_data["伏笔规划"]:
            name = item.get("名称", "")
            desc = item.get("描述", "")
            relate = item.get("关联情节线", "")
            set_pos = item.get("设置位置", "")
            rec_pos = item.get("回收位置", "")
            roles = item.get("涉及角色", [])
            expected = item.get("预期回收状态", "")

            # 在追踪数据中查找同名伏笔的当前状态
            tracking_status = ""
            for t_desc, t_item in track_lookup.items():
                if name and name in t_desc:
                    ts = t_item.get("状态", "")
                    if ts:
                        tracking_status = f"（追踪状态：{ts}）"
                    break

            line = f"- {item.get('编号', '')} | {name}"
            if relate:
                line += f" [{relate}]"
            line += f"\n  描述：{desc.strip()}"
            if set_pos:
                line += f"\n  设置：{set_pos}"
            if rec_pos:
                line += f"\n  回收：{rec_pos}"
            if roles:
                line += f"\n  涉及：{'、'.join(roles) if isinstance(roles, list) else roles}"
            if expected:
                line += f"\n  预期：{expected}"
            if tracking_status:
                line += f"\n  {tracking_status}"
            parts.append(line)

    # 3. 从追踪文件筛选当前待处理的活跃伏笔
    if track_data:
        foreshadowing_list = track_data.get("伏笔") or []
        active_items = []
        for item in foreshadowing_list:
            status = item.get("状态", "")
            if status in ("待回收", "进行中", "需回收"):
                active_items.append(item)

        if active_items:
            parts.append("\n【当前待处理伏笔（追踪）】")
            for item in active_items:
                desc = item.get("描述", "")
                # 尝试查找规划编号
                plan_id = item.get("编号", "")
                if plan_id:
                    line = f"- {plan_id}: {desc}"
                else:
                    line = f"- {desc}"
                if item.get("预期回收章节"):
                    line += f"（预期回收：第{item['预期回收章节']}章）"
                parts.append(line)

    return "\n".join(parts) if parts else "（无伏笔数据）"


# ── 时间线规划 ───────────────────────────────────────────────────────────────

def load_timeline_plan(project_root: Path) -> str:
    """从 outline/时间线设计.yaml 加载全局时间线规划。

    按时代/阶段结构化的时间线设计，提供写前的时间线世界观参考。

    Returns:
        格式化字符串，包含全局时间线设计的简要呈现。
    """
    plan_path = project_root / "outline" / "时间线设计.yaml"
    data = load_yaml(plan_path)
    if not data:
        return "（无时间线设计数据）"

    parts = []
    desc = data.get("设计说明", "")
    calendar = data.get("纪年体系", "")
    if desc:
        parts.append(f"设计说明：{desc}")
    if calendar:
        parts.append(f"纪年体系：{calendar}")

    timeline = data.get("时间线设计", [])
    if timeline:
        parts.append("")
        for era in timeline:
            era_name = era.get("时代", "")
            era_desc = era.get("说明", "")
            title = f"【{era_name}】" if era_name else ""
            if title and era_desc:
                title += f" — {era_desc}"
            if title:
                parts.append(title)
            for event in era.get("事件", []):
                event_time = event.get("时间", "")
                event_desc = event.get("事件", "")
                if event_time and event_desc:
                    parts.append(f"  {event_time} | {event_desc}")
                elif event_desc:
                    parts.append(f"  {event_desc}")

    return "\n".join(parts) if parts else "（无时间线设计数据）"


# ── 支线状态 ─────────────────────────────────────────────────────────────────

def load_plot_threads(project_root: Path, chapter_num: int) -> str:
    """从 project_index.yaml 找活跃支线 → 读取当前节点。"""
    index_path = project_root / "project_index.yaml"
    index = load_yaml(index_path)
    plot_threads = index.get("plot_threads", {})

    parts = []
    for entity_id, entry in plot_threads.items():
        status = entry.get("status", "")
        if status not in ("active", "进行中", "活跃"):
            continue

        file_path = entry.get("file_path")
        if not file_path:
            continue

        thread_path = project_root / file_path
        if not thread_path.is_file():
            continue

        thread_data = load_yaml(thread_path)
        name = entry.get("name", entity_id)
        summary = thread_data.get("摘要", {}).get("一句话描述", "")
        parts.append(f"- {name}: {summary}")

    return "\n".join(parts) if parts else ""


# ── 出场节奏 ─────────────────────────────────────────────────────────────────

def load_appearance_rhythm(project_root: Path, chapter_num: int) -> str:
    """从所有情节线的 角色参与.出场节奏 聚合出场管理信息。

    返回当前章节的出场提醒：哪些角色应该出现、哪些不应出现。
    """
    index_path = project_root / "project_index.yaml"
    index = load_yaml(index_path)
    plot_threads = index.get("plot_threads", {})

    should_appear = []
    should_not_appear = []
    all_rhythms = []

    for entity_id, entry in plot_threads.items():
        file_path = entry.get("file_path")
        if not file_path:
            continue
        thread_path = project_root / file_path
        if not thread_path.is_file():
            continue

        data = load_yaml(thread_path)
        rhythms = get_nested(data, "完整档案.角色参与.出场节奏")
        if not rhythms:
            continue
        all_rhythms.extend(rhythms)

    for rhythm in all_rhythms:
        char_name = rhythm.get("角色", "")
        if not char_name:
            continue

        first = rhythm.get("首次出场", 0) or 0
        key_chapters = rhythm.get("关键章节", []) or []
        blackout = rhythm.get("不活跃区间", []) or []
        density = rhythm.get("出场密度", "正常")

        # 判断：是否在关键章节中
        if chapter_num in key_chapters:
            should_appear.append(f"{char_name}（关键章节）")
            continue

        # 判断：是否在不活跃区间内
        in_blackout = False
        for interval in blackout:
            if isinstance(interval, str) and "-" in interval:
                parts = interval.split("-")
                if len(parts) == 2:
                    try:
                        start, end = int(parts[0]), int(parts[1])
                        if start <= chapter_num <= end:
                            in_blackout = True
                            break
                    except ValueError:
                        pass
        if in_blackout:
            should_not_appear.append(char_name)
            continue

        # 判断：是否在首次出场前
        if first and chapter_num < first:
            should_not_appear.append(f"{char_name}（首次出场第{first}章）")

    parts = []
    if should_appear:
        parts.append("【本章应出场】" + "、".join(should_appear))
    if should_not_appear:
        parts.append("【本章不应出场】" + "、".join(should_not_appear))

    return "\n".join(parts) if parts else ""


# ── 已知问题 ─────────────────────────────────────────────────────────────────

def load_known_issues(project_root: Path) -> str:
    """从 novel-issues.md 读取已知问题。"""
    issues_path = project_root / "novel-issues.md"
    if not issues_path.is_file():
        return ""

    content = issues_path.read_text(encoding="utf-8")
    # 只读取前 2000 字符，避免过长
    if len(content) > 2000:
        content = content[:2000] + "\n... (已截断)"
    return content


# ── 活跃风格 ─────────────────────────────────────────────────────────────────

def load_active_style(project_root: Path) -> str:
    """从 config.yaml 读取活跃风格 → 读取风格文件。"""
    config_path = project_root / "config.yaml"
    config = load_yaml(config_path)

    active_style = config.get("活跃风格", "")
    if not active_style:
        return ""

    # 查找风格文件
    style_path = project_root / "styles" / f"{active_style}.yaml"
    if not style_path.is_file():
        # 尝试 builtin 风格
        builtin_dir = Path(__file__).parent.parent / "skills" / "novel-style" / "assets" / "builtin"
        style_path = builtin_dir / f"{active_style}.yaml"

    if not style_path.is_file():
        return f"风格文件未找到: {active_style}"

    style_data = load_yaml(style_path)

    # 简化渲染：只输出关键维度
    parts = [f"风格：{style_data.get('style_name', active_style)} — {style_data.get('description', '')}"]
    dimensions = style_data.get("dimensions", {})
    for label, key in [
        ("叙事基调", "narrative_tone"), ("句子结构", "sentence_structure"),
        ("节奏", "pacing"), ("对话风格", "dialogue_style"),
        ("词汇选择", "vocabulary_register"), ("修辞特征", "rhetorical_features"),
        ("禁止模式", "forbidden_patterns"),
    ]:
        v = dimensions.get(key)
        if v:
            desc = v.get("description", "")
            if desc:
                parts.append(f"{label}：{desc}")

    return "\n".join(parts)


# ── 叙事策略 ───────────────────────────────────────────────────────────────

def load_narrative_strategy(project_root: Path) -> str:
    """从 outline/叙事策略.yaml 加载叙事策略定义。

    叙事策略由 P4.5 阶段生成，定义视角、叙事手法、信息分配、展示讲述、笔法控制等规则。
    P8 章节写作时注入作为硬约束。

    Returns:
        格式化字符串，包含叙事策略的关键约束。
    """
    strategy_path = project_root / "outline" / "叙事策略.yaml"
    data = load_yaml(strategy_path)
    if not data:
        return "（无叙事策略数据）"

    parts = []

    # 视角选择
    pov = data.get("视角选择", {})
    if pov:
        main_pov = pov.get("主视角", "")
        main角色 = pov.get("主视角角色", "")
        if main_pov:
            parts.append(f"视角：{main_pov}")
        if main角色:
            parts.append(f"视角锚定角色：{main角色}")

        switch_rules = pov.get("切换规则", {})
        if switch_rules:
            max_switch = switch_rules.get("每章最多切换次数", 2)
            parts.append(f"视角切换限制：每章最多 {max_switch} 次")

    # 叙事手法
    technique = data.get("叙事手法", {})
    if technique:
        main_tech = technique.get("主要手法", "")
        if main_tech:
            parts.append(f"叙事手法：{main_tech}")

        forbidden = technique.get("禁忌手法", [])
        if forbidden:
            parts.append(f"禁忌手法：{'、'.join(forbidden)}")

    # 信息分配
    info = data.get("信息分配", {})
    if info:
        irony = info.get("戏剧反讽", {})
        if irony.get("启用"):
            parts.append("戏剧反讽：启用")

        suspense = info.get("悬念管理", {})
        if suspense:
            hooks = suspense.get("章节钩子", "")
            if hooks:
                parts.append(f"悬念要求：{hooks}")

    # 展示与讲述
    show_tell = data.get("展示与讲述", {})
    if show_tell:
        ratio = show_tell.get("比例建议", {})
        if ratio:
            show_pct = ratio.get("展示", 70)
            tell_pct = ratio.get("讲述", 30)
            parts.append(f"展示/讲述比例：{show_pct}%/{tell_pct}%")

    # 笔法控制
    pen = data.get("笔法控制", {})
    if pen:
        hot_scenes = pen.get("热笔场景", [])
        if hot_scenes:
            parts.append(f"热笔场景：{'、'.join(hot_scenes[:3])}")

    return "\n".join(parts) if parts else "（叙事策略数据为空）"


# ── 上下文完整性评分 ─────────────────────────────────────────────────────────

def assess_context_completeness(context: dict) -> dict:
    """评估上下文完整性，返回综合评分和缺口列表。

    维度权重（满分100）：
      - 场域规划 20分：场景级蓝图是高质量叙述的基础
      - 张力曲线 15分：量化节奏指导
      - 叙事策略 15分：视角/手法/信息分配规则
      - 伏笔状态 15分：伏笔一致性
      - 角色档案 10分：出场角色深度
      - 活跃风格 10分：风格一致性约束
      - 时间线规划 5分：时间线一致性
      - 支线状态 5分：主线/支线交叉感知
      - 对话规划 5分：对话节拍/潜台词（加分项）

    Returns:
        {"score": int, "gaps": [str], "suggestion": str}
    """
    score = 0
    gaps = []

    # 1. 场域规划 (20分)
    outline_yaml = context.get("本章分纲内容", "")
    has_scene = "场域规划" in outline_yaml and "场域名:" in outline_yaml
    if has_scene:
        score += 20
    else:
        gaps.append("缺少场域规划 (P7 场域蓝图) → 输出可能场景模糊、缺乏感官锚点")

    # 2. 张力曲线 (15分)
    has_tension = "张力曲线" in outline_yaml and "开场:" in outline_yaml
    if has_tension:
        score += 15
    else:
        gaps.append("缺少张力曲线 → 输出可能节奏平坦、缺乏起伏设计")

    # 3. 叙事策略 (15分)
    narrative = context.get("叙事策略", "")
    if narrative and narrative != "（无叙事策略数据）":
        score += 15
    else:
        gaps.append("缺少叙事策略 → 视角/手法/信息分配缺少约束")

    # 4. 伏笔状态 (15分)
    foreshadowing = context.get("伏笔状态", "")
    if foreshadowing and foreshadowing != "（无伏笔数据）":
        score += 15
    else:
        gaps.append("缺少伏笔状态 → 伏笔回收/设置可能脱节")

    # 5. 角色档案 (10分)
    profiles = context.get("出场角色档案", "")
    if profiles:
        score += 10
    else:
        gaps.append("缺少出场角色档案 → 角色行为可能偏离设定")

    # 6. 活跃风格 (10分)
    style = context.get("活跃风格", "")
    if style:
        score += 10
    else:
        gaps.append("缺少活跃风格 → 文风一致性无约束")

    # 7. 时间线规划 (5分)
    timeline = context.get("时间线规划", "")
    if timeline and timeline != "（无时间线设计数据）":
        score += 5
    else:
        gaps.append("缺少时间线规划 → 时间线一致性缺少参考")

    # 8. 支线状态 (5分)
    threads = context.get("支线状态", "")
    if threads:
        score += 5

    # 9. 对话规划 (加分项，5分)
    has_dialogue = "对话规划" in outline_yaml and "对话节拍:" in outline_yaml
    if has_dialogue:
        score += 5

    # 汇总
    if score >= 85:
        suggestion = "上下文完整性良好，可直接进入写作。"
    elif score >= 60:
        suggestion = "上下文基本完整，建议补充缺失维度以提升输出质量。"
    elif score >= 40:
        suggestion = "上下文缺口较多，强烈建议补充场域规划和张力曲线后再开始写作。"
    else:
        suggestion = "上下文严重不完整，大量关键维度缺失，请先完善分纲数据。"

    return {"score": min(score, 100), "gaps": gaps, "suggestion": suggestion}


def load_scene_beat_plan(project_root: Path, chapter_num: int) -> str:
    """从分纲提取场域规划数据。"""
    outline_path = find_chapter_outline(project_root, chapter_num)
    if not outline_path:
        return ""
    data = load_yaml(outline_path)
    scene_plan = get_nested(data, "完整档案.场域规划")
    if not scene_plan:
        return ""
    return yaml.dump(scene_plan, allow_unicode=True, default_flow_style=False)


def load_tension_curve(project_root: Path, chapter_num: int) -> str:
    """从分纲提取张力曲线数据。"""
    outline_path = find_chapter_outline(project_root, chapter_num)
    if not outline_path:
        return ""
    data = load_yaml(outline_path)
    tension = get_nested(data, "完整档案.张力曲线")
    if not tension:
        return ""
    return yaml.dump(tension, allow_unicode=True, default_flow_style=False)


def load_dialogue_plan(project_root: Path, chapter_num: int) -> str:
    """从分纲提取对话规划数据（可选）。"""
    outline_path = find_chapter_outline(project_root, chapter_num)
    if not outline_path:
        return ""
    data = load_yaml(outline_path)
    dialogue = get_nested(data, "完整档案.对话规划")
    if not dialogue:
        return ""
    return yaml.dump(dialogue, allow_unicode=True, default_flow_style=False)


# ── 主函数 ───────────────────────────────────────────────────────────────────

def collect_context(project_root: Path, chapter_num: int) -> dict:
    """收集章节写作所需的全部上下文。"""
    context = {}

    # 1. 本章分纲
    outline_path = find_chapter_outline(project_root, chapter_num)
    if outline_path:
        outline = load_yaml(outline_path)
        context["本章分纲内容"] = yaml.dump(outline, allow_unicode=True, default_flow_style=False)
    else:
        context["本章分纲内容"] = f"错误：未找到第{chapter_num}章分纲"

    # 2. 附近章分纲（含前章追踪摘要）
    context["附近章分纲"] = load_nearby_outlines(project_root, chapter_num)

    # 3. 前一章衔接
    context["前一章衔接"] = load_previous_linkage(project_root, chapter_num)

    # 4. 出场角色档案
    context["出场角色档案"] = load_character_profiles(project_root, chapter_num)

    # 5. 世界观相关实体
    context["世界观相关实体"] = load_worldbuilding_entities(project_root, chapter_num)

    # 6. 待处理伏笔（规划+追踪合并）
    context["伏笔状态"] = load_foreshadowing(project_root, chapter_num)

    # 7. 时间线规划
    context["时间线规划"] = load_timeline_plan(project_root)

    # 8. 支线状态
    context["支线状态"] = load_plot_threads(project_root, chapter_num)

    # 8b. 出场节奏（从情节线聚合）
    context["出场节奏"] = load_appearance_rhythm(project_root, chapter_num)

    # 8c. 已知问题
    context["已知问题"] = load_known_issues(project_root)

    # 9. 活跃风格
    context["活跃风格"] = load_active_style(project_root)

    # 10. 叙事策略
    context["叙事策略"] = load_narrative_strategy(project_root)

    # 11. 场域规划
    context["场域规划"] = load_scene_beat_plan(project_root, chapter_num)

    # 12. 张力曲线
    context["张力曲线"] = load_tension_curve(project_root, chapter_num)

    # 13. 对话规划（可选）
    context["对话规划"] = load_dialogue_plan(project_root, chapter_num)

    # 14. 上下文完整性评分
    context["上下文完整性"] = assess_context_completeness(context)

    return context


def main():
    parser = argparse.ArgumentParser(
        description="收集章节写作所需的全部上下文",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 收集第 5 章的上下文
  python chapter_context.py --project-root novels/穿越三国成刘谌 --chapter 5

  # 输出到文件
  python chapter_context.py --project-root novels/穿越三国成刘谌 --chapter 5 --output /tmp/context.json

  # 列出模板变量
  python chapter_context.py --project-root novels/穿越三国成刘谌 --chapter 5 --list-vars
""",
    )
    parser.add_argument(
        "--project-root", "-p",
        required=True,
        help="项目根目录（包含 config.yaml 的目录）",
    )
    parser.add_argument(
        "--chapter", "-c",
        required=True,
        type=int,
        help="章节号",
    )
    parser.add_argument(
        "--output", "-o",
        type=str,
        default=None,
        help="输出文件路径（默认 stdout）",
    )
    parser.add_argument(
        "--list-vars",
        action="store_true",
        help="仅列出模板变量名，不输出内容",
    )
    parser.add_argument(
        "--assess",
        action="store_true",
        help="仅输出上下文完整性评分，不输出完整上下文",
    )
    args = parser.parse_args()

    project_root = Path(args.project_root).resolve()
    if not project_root.is_dir():
        print(f"错误: 项目根目录不存在: {project_root}", file=sys.stderr)
        sys.exit(1)

    # --list-vars 模式
    if args.list_vars:
        vars = [
            "本章分纲内容", "附近章分纲", "前一章衔接",
            "出场角色档案", "世界观相关实体", "伏笔状态",
            "时间线规划", "支线状态", "已知问题", "活跃风格",
            "叙事策略", "场域规划", "张力曲线", "对话规划",
            "上下文完整性",
        ]
        for v in vars:
            print(v)
        return

    context = collect_context(project_root, args.chapter)

    # --assess 模式：仅输出完整性评分
    if args.assess:
        assessment = assess_context_completeness(context)
        print(json.dumps(assessment, ensure_ascii=False, indent=2))
        return

    if args.output:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(context, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"已写入: {out_path}", file=sys.stderr)
    else:
        print(json.dumps(context, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
