#!/usr/bin/env python3
"""
chapter_context.py — 收集章节写作所需的全部上下文

一次性收集 novel-chapter 技能所需的 12 个上下文槽位，
输出 JSON 格式供 extract_template.py 填充变量。

Usage:
    python chapter_context.py --project-root NOVELS_ROOT/项目名 --chapter 5
    python chapter_context.py --project-root NOVELS_ROOT/项目名 --chapter 5 --output /tmp/context.json
    python chapter_context.py --project-root NOVELS_ROOT/项目名 --chapter 5 --list-vars

Output (JSON):
    {
        "本章分纲内容": "...",
        "前章摘要": "...",
        "前一章衔接": "...",
        "出场角色档案": "...",
        "世界观相关实体": "...",
        "伏笔状态": "...",
        "支线状态": "...",
        "已知问题": "...",
        "活跃风格": "..."
    }
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


# ── YAML 工具 ─────────────────────────────────────────────────────────────────

def load_yaml(path: Path) -> dict:
    """安全读取 YAML 文件，不存在或格式错误时返回 {}。"""
    if not path.exists():
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except yaml.YAMLError:
        return {}


def get_nested(data: dict, dot_path: str):
    """按点号路径访问嵌套字典。"""
    keys = dot_path.split(".")
    current = data
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


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


# ── 待处理伏笔 ───────────────────────────────────────────────────────────────

def load_foreshadowing(project_root: Path, chapter_num: int) -> str:
    """从 outline/追踪/伏笔.yaml 筛选进行中/需回收的伏笔。"""
    fs_path = project_root / "outline" / "追踪" / "伏笔.yaml"
    data = load_yaml(fs_path)

    parts = []
    for item in data.get("伏笔", []):
        status = item.get("状态", "")
        if status in ("进行中", "需回收"):
            line = f"- {item.get('伏笔ID', '')}: {item.get('描述', '')}"
            if item.get("预期回收章节"):
                line += f"（预期回收：第{item['预期回收章节']}章）"
            parts.append(line)

    return "\n".join(parts) if parts else ""


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

    # 2. 前章摘要
    context["前章摘要"] = load_previous_summary(project_root, chapter_num)

    # 3. 前一章衔接
    context["前一章衔接"] = load_previous_linkage(project_root, chapter_num)

    # 4. 出场角色档案
    context["出场角色档案"] = load_character_profiles(project_root, chapter_num)

    # 5. 世界观相关实体
    context["世界观相关实体"] = load_worldbuilding_entities(project_root, chapter_num)

    # 6. 待处理伏笔
    context["伏笔状态"] = load_foreshadowing(project_root, chapter_num)

    # 7. 支线状态
    context["支线状态"] = load_plot_threads(project_root, chapter_num)

    # 8. 已知问题
    context["已知问题"] = load_known_issues(project_root)

    # 9. 活跃风格
    context["活跃风格"] = load_active_style(project_root)

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
    args = parser.parse_args()

    project_root = Path(args.project_root).resolve()
    if not project_root.is_dir():
        print(f"错误: 项目根目录不存在: {project_root}", file=sys.stderr)
        sys.exit(1)

    # --list-vars 模式
    if args.list_vars:
        vars = [
            "本章分纲内容", "前章摘要", "前一章衔接",
            "出场角色档案", "世界观相关实体", "伏笔状态",
            "支线状态", "已知问题", "活跃风格",
        ]
        for v in vars:
            print(v)
        return

    context = collect_context(project_root, args.chapter)

    if args.output:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(context, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"已写入: {out_path}", file=sys.stderr)
    else:
        print(json.dumps(context, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
