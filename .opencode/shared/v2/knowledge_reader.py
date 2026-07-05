"""
知识库读取器（KnowledgeReader）——共享的知识库访问模块。

替代 workspace.py 和 query.py 中各自独立实现的知识读取逻辑。
支持多文件、多关键词搜索，消除 sections.index() 之类的重复 bug。

用法：
    reader = KnowledgeReader(resolve_knowledge_root(project_root))
    content = reader.get("fanren-xiuxian", topics=["鬼道", "阴冥"], max_chars=2000)
"""

from __future__ import annotations

import os
import sys
from typing import List, Optional


class KnowledgeReader:
    """知识库读取器：按 slug 和 topics 搜索 knowledge/<slug>/ 下的内容。"""

    SOURCE_PRIORITY = [
        "knowledge.md",
        "patterns.md",
    ]

    def __init__(self, knowledge_root: str):
        self.knowledge_root = knowledge_root

    def get(
        self,
        slug: str,
        topics: Optional[List[str]] = None,
        max_chars: int = 2000,
    ) -> str:
        """
        从知识库读取匹配主题的内容。

        遍历 knowledge/<slug>/ 下的多个源文件，按优先级收集匹配 topics 的段落。
        topics 是多关键词 OR 匹配；不传 topics 时返回 knowledge.md 开头。

        Args:
            slug: 知识库标识（如 fanren-xiuxian）
            topics: 关键词列表，OR 匹配。None 或缺省返回通用参考
            max_chars: 最大返回字符数

        Returns:
            匹配的内容文本，为空时返回 ""
        """
        slug_dir = os.path.join(self.knowledge_root, slug)
        if not os.path.isdir(slug_dir):
            return ""

        sources = self._collect_sources(slug_dir)
        result_parts: List[str] = []
        char_count = 0

        for filepath, label in sources:
            if char_count >= max_chars:
                break

            content = self._read_file(filepath)
            if not content:
                continue

            if topics:
                matched = self._match_sections(content, topics)
                if not matched:
                    continue
            else:
                matched = content

            header = f"\n## [{label}]\n" if label else ""
            trimmed = (header + matched)[: max_chars - char_count]
            result_parts.append(trimmed)
            char_count += len(trimmed)

        if result_parts:
            return "\n".join(result_parts)[:max_chars]

        # 全空时回退到 knowledge.md 开头
        kmd = os.path.join(slug_dir, "knowledge.md")
        if os.path.isfile(kmd):
            raw = self._read_file(kmd)
            if raw:
                return raw[:max_chars]
        return ""

    # ── 源文件收集 ──────────────────────────────────────────────────────

    def _collect_sources(self, slug_dir: str) -> List[tuple]:
        """列出知识库目录下所有可读源文件，按优先级排序。"""
        seen: set = set()
        sources: List[tuple] = []

        def add(path: str, label: str):
            if path not in seen and os.path.isfile(path):
                seen.add(path)
                sources.append((path, label))

        # 1. 核心文件
        for fname in self.SOURCE_PRIORITY:
            add(os.path.join(slug_dir, fname), fname.replace(".md", ""))

        # 2. 索引目录（取每个目录下的 index.md 或首文件）
        for dirname in ["patterns", "cheatsheet", "glossary"]:
            d = os.path.join(slug_dir, dirname)
            if os.path.isdir(d):
                candidates = sorted(os.listdir(d))
                for f in ["index.md", "README.md"] + candidates:
                    if f.endswith(".md") and os.path.isfile(os.path.join(d, f)):
                        add(os.path.join(d, f), f"{dirname}/{f}")
                        break

        # 3. 卷摘要
        for f in sorted(os.listdir(slug_dir)):
            if f.startswith("vol-") and f.endswith(".md"):
                add(os.path.join(slug_dir, f), f.replace(".md", ""))

        # 4. 章节文件（限前 15 个）
        ch_dir = os.path.join(slug_dir, "chapters")
        if os.path.isdir(ch_dir):
            for i, f in enumerate(sorted(os.listdir(ch_dir))):
                if i >= 15:
                    break
                if f.endswith(".md"):
                    add(os.path.join(ch_dir, f), f.replace(".md", ""))

        return sources

    # ── 文件 I/O ────────────────────────────────────────────────────────

    def _read_file(self, path: str) -> str:
        try:
            with open(path, "r", encoding="utf-8") as f:
                return f.read()
        except Exception as e:
            print(f"[KnowledgeReader] 读取失败 {path}: {e}", file=sys.stderr)
            return ""

    # ── 匹配逻辑 ────────────────────────────────────────────────────────

    def _match_sections(self, content: str, topics: List[str]) -> str:
        """
        按 ## 标题分段扫描，多关键词 OR 匹配。

        修复了原 workspace.py/query.py 中 sections.index() 返回首索引的 bug。
        """
        topics_lower = [t.lower() for t in topics if len(t) >= 2]
        if not topics_lower:
            return ""

        sections = content.split("\n## ")
        matched: List[str] = []

        for idx, section in enumerate(sections):
            section_lower = section.lower()
            if any(t in section_lower for t in topics_lower):
                section_text = ("## " + section) if idx > 0 else section
                matched.append(section_text)

        return "\n".join(matched)

    # ── 辅助方法 ────────────────────────────────────────────────────────

    def resolve_slug_alias(self, alias: str) -> Optional[str]:
        """通过 index.yaml 解析别名（中文书名 → slug）。"""
        index_path = os.path.join(self.knowledge_root, "index.yaml")
        if not os.path.isfile(index_path):
            return None

        try:
            import yaml
            with open(index_path, "r", encoding="utf-8") as f:
                index = yaml.safe_load(f)
            entries = index.get("entries", []) if isinstance(index, dict) else []
            for e in entries:
                slug = e.get("slug", "")
                title = e.get("title", "")
                tags = e.get("tags", [])
                if alias in (slug, title) or alias in tags:
                    return slug
        except Exception as ex:
            print(f"[KnowledgeReader] index.yaml 解析失败: {ex}", file=sys.stderr)
        return None

    def list_available_books(self) -> List[str]:
        """列出所有可用知识库。"""
        index_path = os.path.join(self.knowledge_root, "index.yaml")
        if os.path.isfile(index_path):
            try:
                import yaml
                with open(index_path, "r", encoding="utf-8") as f:
                    index = yaml.safe_load(f)
                entries = index.get("entries", []) if isinstance(index, dict) else []
                if entries:
                    return [
                        f"{e.get('title', e.get('slug', '?'))} ({e.get('slug', '?')})"
                        for e in entries
                    ]
            except Exception:
                pass

        books = []
        try:
            for item in sorted(os.listdir(self.knowledge_root)):
                ip = os.path.join(self.knowledge_root, item)
                if os.path.isdir(ip) and os.path.isfile(os.path.join(ip, "knowledge.md")):
                    books.append(item)
        except Exception:
            pass
        return books


# ── 模块级工具函数 ──────────────────────────────────────────────────────


def resolve_knowledge_root(project_root: str) -> str:
    """
    解析知识库根目录路径。

    优先级: KNOWLEDGE_ROOT 环境变量 > 从 project_root 向上查找 knowledge/index.yaml
    """
    env_root = os.environ.get("KNOWLEDGE_ROOT", "")
    if env_root:
        return env_root

    current = project_root
    for _ in range(5):
        candidate = os.path.join(current, "knowledge")
        if os.path.isdir(candidate) and os.path.isfile(os.path.join(candidate, "index.yaml")):
            return candidate
        parent = os.path.dirname(current)
        if parent == current:
            break
        current = parent

    return os.path.join(project_root, "knowledge")
