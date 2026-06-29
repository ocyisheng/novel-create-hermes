#!/usr/bin/env python3
"""
word_count.py — 统计章节正文字数（不含换行符）

Usage:
    python word_count.py --project-root NOVELS_ROOT/项目名 --chapter chapters/第1章.txt

Example:
    python word_count.py --project-root novels/穿越三国成刘谌 --chapter chapters/第1章.txt
    # 输出: 字数: 4237
"""

import sys
from pathlib import Path


def count_chars(filepath: Path) -> int:
    """读取文件，去除所有换行符后统计字符数。"""
    if not filepath.is_file():
        print(f"Error: File not found: {filepath}", file=sys.stderr)
        sys.exit(1)

    text = filepath.read_text(encoding="utf-8")
    text = text.replace("\n", "").replace("\r", "")
    return len(text)


def main():
    import argparse
    parser = argparse.ArgumentParser(
        prog="word_count.py",
        description="统计章节正文字数（不含换行符）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""示例:
  python word_count.py --project-root novels/穿越三国成刘谌 --chapter chapters/第1章.txt
  python word_count.py --project-root novels/穿越三国成刘谌 --chapter chapters/第5章.txt

说明:
  统计指定章节文件的字数（不含换行符）。
  --chapter 支持相对路径（相对于 --project-root）或绝对路径。"""
    )
    parser.add_argument("--project-root", "-p", required=True, help="项目根目录")
    parser.add_argument("--chapter", "-c", required=True, help="章节文件路径（相对于 --project-root，如 chapters/第1章.txt）")
    args = parser.parse_args()

    project_root = Path(args.project_root).resolve()
    chapter_path = Path(args.chapter)
    if not chapter_path.is_absolute():
        if not chapter_path.exists():
            chapter_path = (project_root / chapter_path).resolve()
    else:
        chapter_path = chapter_path.resolve()
    count = count_chars(chapter_path)
    print(f"字数: {count}")


if __name__ == "__main__":
    main()
