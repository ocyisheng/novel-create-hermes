#!/usr/bin/env python3
"""
extract_template.py — 加载 prompt 模板并填充变量

框架无关工具。任何 Agent 程序（OpenCode / LangChain / AutoGen / CrewAI / 手写脚本）
均可通过 CLI 调用，将填充后的 prompt 喂给 LLM。

Usage:
    # 基本用法（模板文件优先）
    python .opencode/shared/extract_template.py \
        --skill .opencode/skills/novel-chapter/SKILL.md \
        --var 项目名 "星辰修仙路" \
        --var 章节号 "5"

    # 多行变量从 stdin 读入（--var 值传 "-"）
    echo "分纲内容..." | python extract_template.py \
        --skill ... --var 章节正文 -

    # 写入文件
    python extract_template.py --skill ... --output /tmp/prompt.txt

    # 查看模板有哪些变量（用于编排层预先收集数据）
    python extract_template.py --skill ... --list-vars

工作原理:
    1. 先查 SKILL.md 同级的 templates/prompt_template.md（独立模板文件）→ 直接读
    2. 降级：从 SKILL.md 内 ```markdown 代码块提取（旧版兼容）
    3. 替换 {变量名} 占位符 → 输出填充后的 prompt
"""

import argparse
import re
import sys
from pathlib import Path


# ── 模板加载 ─────────────────────────────────────────────────────────────────

def load_template(skill_path: Path) -> str:
    """加载 prompt 模板。

    优先级：
    1. {skill_dir}/templates/prompt_template.md — 独立模板文件（推荐）
    2. SKILL.md 内的 ```markdown 代码块（旧版兼容）
    3. SKILL.md 内裸 markdown（旧旧版兼容，警告）
    """
    # 方式一：独立模板文件
    template_file = skill_path.parent / "templates" / "prompt_template.md"
    if template_file.is_file():
        return template_file.read_text(encoding="utf-8").strip()

    # 方式二：从 SKILL.md 解析
    content = skill_path.read_text(encoding="utf-8")

    # 新版：代码块包裹
    match = re.search(
        r'## PROMPT_TEMPLATE\b.*?```markdown\s*\n(.*?)\n\s*```',
        content, re.DOTALL
    )
    if match:
        print(
            f"提示: {skill_path.name} 模板内嵌在 SKILL.md 中，"
            "建议迁移至 templates/prompt_template.md。",
            file=sys.stderr,
        )
        return match.group(1).rstrip()

    # 旧版：裸 markdown，/v1/PROMPT_TEMPLATE 边界
    match_old = re.search(
        r'## PROMPT_TEMPLATE\b\n(.*?)\n/v1/PROMPT_TEMPLATE\b',
        content, re.DOTALL
    )
    if match_old:
        print(
            f"警告: {skill_path.name} 使用旧版 PROMPT_TEMPLATE 格式（未包裹在代码块中）。",
            file=sys.stderr,
        )
        return match_old.group(1).strip()

    print(f"错误: {skill_path.name} 中未找到 PROMPT_TEMPLATE 段", file=sys.stderr)
    sys.exit(1)


# ── 变量填充 ─────────────────────────────────────────────────────────────────

def fill_variables(template: str, variables: dict[str, str]) -> str:
    """替换模板中的 {变量名} 占位符。

    按变量名长度降序替换，避免短名误匹配长名的子串。
    未匹配的占位符输出 stderr 警告但不阻断。
    """
    result = template

    for name, value in sorted(variables.items(), key=lambda kv: -len(kv[0])):
        placeholder = "{" + name + "}"
        result = result.replace(placeholder, value)

    unreplaced = re.findall(r'\{([^}]+)\}', result)
    if unreplaced:
        print(f"警告: 以下变量未被填充: {unreplaced}", file=sys.stderr)

    return result


def list_template_vars(template: str) -> list[str]:
    """提取模板中所有 {变量名} 列表。"""
    return sorted(set(re.findall(r'\{([^}]+)\}', template)))


# ── CLI ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="加载 prompt 模板并填充变量",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 基本填充
  python extract_template.py --skill novel-chapter/SKILL.md \\
      --var 项目名 "星辰修仙路" --var 章节号 "5"

  # 多行变量从 stdin 读入
  cat /tmp/chapter_body.txt | python extract_template.py \\
      --skill novel-chapter/SKILL.md --var 章节正文 -

  # 仅列出变量名（编排层用）
  python extract_template.py --skill novel-chapter/SKILL.md --list-vars
""",
    )
    parser.add_argument(
        "--skill", required=True, type=str,
        help="SKILL.md 文件路径（脚本自动查找同级 templates/prompt_template.md）",
    )
    parser.add_argument(
        "--var", nargs=2, action="append", default=[],
        metavar=("NAME", "VALUE"),
        help="变量名和值。VALUE 为 '-' 时从 stdin 读取。可多次使用。",
    )
    parser.add_argument(
        "--output", type=str, default=None,
        help="输出文件路径（默认 stdout）",
    )
    parser.add_argument(
        "--list-vars", action="store_true",
        help="仅列出模板中的变量名，不填充",
    )
    args = parser.parse_args()

    skill_path = Path(args.skill).resolve()
    if not skill_path.is_file():
        print(f"错误: SKILL.md 未找到: {skill_path}", file=sys.stderr)
        sys.exit(1)

    template = load_template(skill_path)

    # --list-vars 模式
    if args.list_vars:
        for name in list_template_vars(template):
            print(name)
        return

    # 收集变量
    variables: dict[str, str] = {}
    for name, value in args.var:
        if value == "-":
            variables[name] = sys.stdin.read()
        else:
            variables[name] = value

    filled = fill_variables(template, variables)

    if args.output:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(filled, encoding="utf-8")
        print(f"已写入: {out_path}", file=sys.stderr)
    else:
        print(filled)


if __name__ == "__main__":
    main()
