"""
handlers_knowledge.py — 知识库查询纯业务逻辑函数。

涵盖 2 个操作：read / list_books。
提取自 novel_tool.py _handle_knowledge。
"""

import json
import os
import sys
from pathlib import Path
from typing import Optional

from ._common import ensure_sys_path, _resolve_project, _find_novels_root

ensure_sys_path()


def _resolve_knowledge_root(root: str) -> str:
    """找到 knowledge/ 目录。"""
    p = Path(root)
    if (p / "knowledge").exists():
        return str(p / "knowledge")
    novels_root = _find_novels_root()
    return str(Path(novels_root).parent / "knowledge")


def handle_knowledge_read(project_root: str, slug: str, topic: str = "概要") -> dict:
    """查询知识库。"""
    project = _resolve_project(project_root)
    from knowledge_reader import KnowledgeReader

    root = _resolve_knowledge_root(str(project))
    reader = KnowledgeReader(root)

    # 查找 source 信息
    import yaml
    slug_dir = Path(project) / "knowledge" / slug
    if not slug_dir.exists():
        slug_dir = Path(_find_novels_root()).parent / "knowledge" / slug
    if not slug_dir.exists():
        slug_dir = Path(root) / slug

    source_info = {}
    sp = slug_dir / "source.yaml"
    if sp.exists():
        with open(sp, "r", encoding="utf-8") as f:
            source_info = yaml.safe_load(f) or {}

    title = source_info.get("title", slug)
    author = source_info.get("author", "")
    chapter_count = source_info.get("chapter_count", "?")

    topics = [t.strip() for t in topic.split("|") if t.strip()]
    content = reader.get(slug, topics=topics, max_chars=2000)

    return {
        "slug": slug,
        "title": title,
        "author": author,
        "chapter_count": chapter_count,
        "content": content,
    }


def handle_knowledge_list_books() -> dict:
    """列出所有已导入的知识库书籍。"""
    novels_root = _find_novels_root()
    root = _resolve_knowledge_root(novels_root)

    books = []
    kdir = Path(root) / "knowledge"
    if not kdir.exists():
        kdir = Path(root)

    if kdir.exists():
        import yaml
        for d in kdir.iterdir():
            if d.is_dir() and (d / "source.yaml").exists():
                with open(d / "source.yaml", "r", encoding="utf-8") as f:
                    info = yaml.safe_load(f) or {}
                books.append({
                    "slug": d.name,
                    "title": info.get("title", d.name),
                    "author": info.get("author", ""),
                    "chapter_count": info.get("chapter_count", "?"),
                })

    return {"books": books}
