#!/usr/bin/env python3
"""
last_100.py — 读取章节末尾 100 字（去除换行符，用于上下文衔接）

Usage:
    python last_100.py --project-root NOVELS_ROOT/项目名 --chapter chapters/第10章.txt

Example:
    python last_100.py --project-root novels/穿越三国成刘谌 --chapter chapters/第10章.txt
    # 输出最后 100 个字符（换行已去除），可直接粘贴到写作 prompt 的 CONTEXT 中
"""

import sys
from pathlib import Path


def last_n_chars(filepath: Path, n: int = 100) -> str:
    """读取文件末尾 n 个字符（去除所有换行符后计算）。"""
    if not filepath.is_file():
        print(f"Error: File not found: {filepath}", file=sys.stderr)
        sys.exit(1)

    text = filepath.read_text(encoding="utf-8")
    clean = text.replace("\n", "").replace("\r", "")
    return clean[-n:] if len(clean) > n else clean


def main():
    import argparse
    parser = argparse.ArgumentParser(description="读取章节末尾 100 字（去除换行符）")
    parser.add_argument("--project-root", required=True, help="项目根目录")
    parser.add_argument("--chapter", required=True, help="章节文件路径（相对于 --project-root，如 chapters/第10章.txt）")
    args = parser.parse_args()

    project_root = Path(args.project_root).resolve()
    chapter_path = Path(args.chapter)
    if not chapter_path.is_absolute():
        if not chapter_path.exists():
            chapter_path = (project_root / chapter_path).resolve()
    else:
        chapter_path = chapter_path.resolve()
    result = last_n_chars(chapter_path)
    print(result)


if __name__ == "__main__":
    main()
