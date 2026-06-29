#!/usr/bin/env python3
"""
search_content.py — 跨文件全文搜索工具

为 novel-search-analysis 技能提供基础的文本搜索能力。
支持按目录范围搜索、上下文行数控制、结果数量限制。

用法:
    python search_content.py --project-root NOVELS_ROOT/项目名 --keyword "天道宗"
    python search_content.py --project-root NOVELS_ROOT/项目名 --keyword "林昭" --scope chapters --context-lines 5
    python search_content.py --project-root NOVELS_ROOT/项目名 --keyword "筑基" --scope all --max-results 20 --case-sensitive

导入:
    from search_content import search_project
    results = search_project(project_root, "天道宗")

依赖: Python 3, stdlib only
"""

import argparse
import fnmatch
import re
import sys
from pathlib import Path
from typing import Generator

try:
    import yaml
except ImportError:
    print("错误: 需要 PyYAML，请运行 novel-env-setup 安装依赖", file=sys.stderr)
    sys.exit(1)


# ── 范围配置 ──────────────────────────────────────────────────────────────

SCOPE_CONFIG = {
    "all": {
        "dirs": ["chapters", "characters", "worldbuilding", "outline", "ideation", "quality"],
        "patterns": ["*.txt", "*.yaml"],
    },
    "chapters": {
        "dirs": ["chapters"],
        "patterns": ["*.txt"],
    },
    "characters": {
        "dirs": ["characters"],
        "patterns": ["*.yaml"],
    },
    "worldbuilding": {
        "dirs": ["worldbuilding"],
        "patterns": ["*.yaml"],
    },
    "outline": {
        "dirs": ["outline"],
        "patterns": ["*.yaml"],
    },
    "ideation": {
        "dirs": ["ideation"],
        "patterns": ["*.yaml"],
    },
    "quality": {
        "dirs": ["quality"],
        "patterns": ["*.yaml"],
    },
}


# ── 文件扫描 ──────────────────────────────────────────────────────────────

from _utils import find_project_root_or_none as find_project_root


def scan_files(project_root: Path, scope: str) -> list[Path]:
    """根据范围配置扫描匹配的文件。"""
    config = SCOPE_CONFIG.get(scope, SCOPE_CONFIG["all"])
    files: list[Path] = []

    for dirname in config["dirs"]:
        target_dir = project_root / dirname
        if not target_dir.is_dir():
            continue
        for pattern in config["patterns"]:
            # rglob for recursive search
            for f in sorted(target_dir.rglob(pattern)):
                # Skip .bak files and summary files
                if ".bak" in f.suffixes:
                    continue
                if ".summary" in f.parts:
                    continue
                files.append(f)

    # Always include project_index.yaml and config.yaml for context
    index_file = project_root / "project_index.yaml"
    if index_file.is_file() and scope != "chapters":
        files.append(index_file)

    return files


# ── 搜索执行 ──────────────────────────────────────────────────────────────

def search_in_file(
    filepath: Path,
    keyword: str,
    case_sensitive: bool = False,
    context_lines: int = 3,
) -> list[dict]:
    """在单个文件中搜索关键词，返回匹配行及其上下文。"""
    results: list[dict] = []

    try:
        with open(filepath, encoding="utf-8") as f:
            lines = f.readlines()
    except (OSError, UnicodeDecodeError):
        return results

    # Determine file type for result metadata
    suffix = filepath.suffix.lower()
    if suffix == ".txt":
        file_type = "chapter"
    elif suffix == ".yaml":
        file_type = "yaml"
    else:
        file_type = "other"

    # Normalize keyword for search
    if not case_sensitive:
        keyword_lower = keyword.lower()
    else:
        keyword_lower = keyword

    for i, line in enumerate(lines):
        line_stripped = line.rstrip("\n").rstrip("\r")

        # Check match
        if not case_sensitive:
            match = keyword_lower in line_stripped.lower()
        else:
            match = keyword in line_stripped

        if not match:
            continue

        # Collect context lines
        start = max(0, i - context_lines)
        end = min(len(lines), i + context_lines + 1)

        context = []
        for j in range(start, end):
            prefix = ">" if j == i else " "
            context.append(f"{prefix} {lines[j].rstrip(chr(10)).rstrip(chr(13))}")

        results.append({
            "line": i + 1,
            "type": file_type,
            "context": "\n".join(context),
        })

    return results


# ── 结果输出 ──────────────────────────────────────────────────────────────

def format_results(
    keyword: str,
    scope: str,
    all_results: dict[str, list[dict]],
    max_results: int = 50,
    case_sensitive: bool = False,
) -> dict:
    """将搜索结果格式化为结构化 YAML 字典。"""
    total_matches = sum(len(v) for v in all_results.values())
    files_scanned = len(all_results)

    # Sort file paths for deterministic output
    sorted_files = sorted(all_results.keys())

    # Build results list, respecting max_results
    results_list = []
    running_count = 0

    for filepath in sorted_files:
        matches = all_results[filepath]
        if not matches:
            continue

        # Determine result type category
        path_obj = Path(filepath)

        # Determine category based on parent directory
        parts = path_obj.parts
        category = "other"
        for part in parts:
            if part in SCOPE_CONFIG:
                category = part
                break
        if "分纲" in str(path_obj) or "分卷" in str(path_obj):
            category = "outline"
        if "情节线" in str(path_obj):
            category = "outline"
        if "追踪" in str(path_obj):
            category = "outline"
        if "总纲" in str(path_obj):
            category = "outline"

        entry = {
            "file": str(path_obj),
            "type": category,
            "matches": matches[:max_results - running_count],
        }
        results_list.append(entry)
        running_count += len(matches)
        if running_count >= max_results:
            break

    return {
        "summary": {
            "keyword": keyword,
            "scope": scope,
            "case_sensitive": case_sensitive,
            "total_matches": total_matches,
            "files_scanned": files_scanned,
            "files_with_matches": len(results_list),
            "truncated": running_count >= max_results and total_matches > max_results,
        },
        "results": results_list,
    }


def output_yaml(data: dict, output_path: str | None = None) -> None:
    """输出 YAML 到文件或 stdout。"""
    yaml_str = yaml.safe_dump(
        data,
        default_flow_style=False,
        sort_keys=False,
        allow_unicode=True,
    )
    if output_path:
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        with open(out, "w", encoding="utf-8") as f:
            f.write(yaml_str)
    else:
        print(yaml_str)


# ── CLI ───────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="跨文件全文搜索工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python search_content.py --project-root novels/测试仙途 --keyword "天道宗"
  python search_content.py --project-root novels/测试仙途 --keyword "林昭" --scope chapters
  python search_content.py --project-root novels/测试仙途 --keyword "筑基" --max-results 20
        """,
    )
    parser.add_argument("--project-root", "-p", required=True, help="项目根目录")
    parser.add_argument("--keyword", required=True, help="搜索关键词")
    parser.add_argument(
        "--scope",
        default="all",
        choices=list(SCOPE_CONFIG.keys()),
        help="搜索范围（默认 all）",
    )
    parser.add_argument("--context-lines", type=int, default=3, help="上下文行数（默认 3）")
    parser.add_argument("--max-results", type=int, default=50, help="最大结果数（默认 50）")
    parser.add_argument("--case-sensitive", action="store_true", help="区分大小写")
    parser.add_argument("--output", "-o", help="输出文件路径（默认 stdout）")
    args = parser.parse_args()

    # Resolve project root
    project_root = Path(args.project_root).resolve()
    if not project_root.is_dir():
        # Try to find config.yaml parent
        found = find_project_root(project_root)
        if found:
            project_root = found
        else:
            print(f"错误: 项目根目录不存在: {project_root}", file=sys.stderr)
            sys.exit(1)

    # Scan files
    files = scan_files(project_root, args.scope)
    if not files:
        print(f"警告: 在 {project_root} 中未找到匹配的文件", file=sys.stderr)
        empty_result = {
            "summary": {
                "keyword": args.keyword,
                "scope": args.scope,
                "case_sensitive": args.case_sensitive,
                "total_matches": 0,
                "files_scanned": 0,
                "files_with_matches": 0,
                "truncated": False,
            },
            "results": [],
        }
        output_yaml(empty_result, args.output)
        sys.exit(0)

    # Search each file
    all_results: dict[str, list[dict]] = {}
    for filepath in files:
        matches = search_in_file(
            filepath,
            args.keyword,
            case_sensitive=args.case_sensitive,
            context_lines=args.context_lines,
        )
        if matches:
            all_results[str(filepath)] = matches

    # Format and output
    result = format_results(
        args.keyword,
        args.scope,
        all_results,
        max_results=args.max_results,
        case_sensitive=args.case_sensitive,
    )

    output_yaml(result, args.output)


if __name__ == "__main__":
    main()
