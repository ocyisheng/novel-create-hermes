"""小说发布导出脚本 — 生成 HTML/TXT/XHTML 格式

用法:
  python export.py --project-root NOVELS_ROOT/项目名 [--format FORMATS] [--author NAME]

示例:
  python export.py --project-root novels/星辰修仙路
  python export.py --project-root novels/星辰修仙路 --format html txt
  python export.py --project-root novels/星辰修仙路 --format html --author "作者名"

当前支持的格式:
  html  — 单文件 HTML，可直接在浏览器中阅读
  txt   — 纯文本，通用格式
  xhtml — XHTML 单文件，可导入 Calibre 等工具转为 EPUB

注意:
  EPUB/PDF/DOCX 需要额外依赖库（ebooklib/reportlab/python-docx），
  当前版本输出 XHTML 作为中间格式，可手动导入 Calibre 完成最终转换。
"""

import argparse
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print("错误: 需要 PyYAML，请运行 novel-env-setup 安装依赖")
    sys.exit(1)


from _utils import find_project_root

try:
    import yaml
except ImportError:
    print("错误: 需要 PyYAML，请运行 novel-env-setup 安装依赖")
    sys.exit(1)


def load_config(project_root: Path) -> dict:
    """加载项目配置"""
    config_path = project_root / "config.yaml"
    if not config_path.exists():
        print(f"错误: 未找到配置文件: {config_path}")
        return {}
    try:
        with open(config_path, encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except yaml.YAMLError as e:
        print(f"错误: 配置文件格式错误: {e}")
        return {}


def collect_chapters(project_root: Path) -> list[dict]:
    """收集并按章节号排序"""
    chapters_dir = project_root / "chapters"
    if not chapters_dir.exists():
        print(f"错误: chapters/ 目录不存在: {chapters_dir}")
        return []

    def chapter_num(filename: str) -> int:
        """从文件名提取章节号，如 第10章.txt → 10"""
        digits = ''.join(c for c in filename if c.isdigit())
        return int(digits) if digits else 0

    chapters = []
    for f in sorted(chapters_dir.glob("*.txt"), key=lambda f: chapter_num(f.name)):
        try:
            with open(f, encoding="utf-8") as fh:
                content = fh.read()
            # 去换行符算字数，与 word_count.py 一致
            word_count = len(content.replace("\n", "").replace("\r", ""))
            chapters.append({
                "filename": f.name,
                "title": f.stem,
                "content": content,
                "word_count": word_count,
            })
        except Exception as e:
            print(f"警告: 读取章节 {f.name} 失败: {e}")

    return chapters


def generate_html(project_root: Path, chapters: list[dict], config: dict) -> str:
    """生成 HTML 格式"""
    title = config.get("项目名称", "未命名小说")
    author = config.get("作者", "佚名")

    html_parts = [
        "<!DOCTYPE html>",
        '<html lang="zh-CN">',
        "<head>",
        f'<meta charset="UTF-8">',
        f"<title>{title}</title>",
        '<style>',
        'body { max-width: 800px; margin: 0 auto; padding: 20px; font-family: "SimSun", serif; line-height: 1.8; }',
        'h1 { text-align: center; }',
        'h2 { text-align: center; margin-top: 2em; }',
        'p { text-indent: 2em; }',
        '.chapter { margin-bottom: 3em; }',
        '.meta { text-align: center; color: #666; }',
        '</style>',
        "</head>",
        "<body>",
        f"<h1>{title}</h1>",
        f'<p class="meta">作者: {author}</p>',
        f'<p class="meta">共 {len(chapters)} 章</p>',
        "<hr>",
    ]

    for ch in chapters:
        html_parts.append(f'<div class="chapter">')
        html_parts.append(f"<h2>{ch['title']}</h2>")
        for para in ch['content'].split('\n\n'):
            if para.strip():
                html_parts.append(f"<p>{para.strip()}</p>")
        html_parts.append("</div>")

    html_parts.append("</body>")
    html_parts.append("</html>")

    return "\n".join(html_parts)


def generate_epub(project_root: Path, chapters: list[dict], config: dict) -> bytes:
    """生成 XHTML 格式（可导入 Calibre 转为 EPUB）。

    注意：这不是真正的 EPUB 格式。真正的 EPUB 需要 ZIP 容器 +
    META-INF/container.xml + OPF manifest + NCX 目录。
    如需完整 EPUB，请安装 ebooklib 或使用 Calibre 导入此 XHTML 文件。
    """
    html = generate_html(project_root, chapters, config)
    xhtml = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xml:lang="zh-CN">
<head>
  <meta charset="UTF-8"/>
  <title>{config.get("项目名称", "小说")}</title>
</head>
<body>
{html}
</body>
</html>"""
    return xhtml.encode("utf-8")


def generate_txt(chapters: list[dict]) -> str:
    """生成 TXT 格式"""
    parts = []
    for ch in chapters:
        parts.append(f"{'='*40}")
        parts.append(ch['title'])
        parts.append(f"{'='*40}")
        parts.append("")
        parts.append(ch['content'])
        parts.append("")
    return "\n".join(parts)


def export(project_root: Path, formats: list[str], author: str | None = None):
    """执行导出"""
    project_root = find_project_root(project_root)
    config = load_config(project_root)

    if author:
        config["作者"] = author

    chapters = collect_chapters(project_root)
    if not chapters:
        print("错误: 没有找到章节内容")
        return

    total_words = sum(ch["word_count"] for ch in chapters)
    print(f"项目: {config.get('项目名称', project_root.name)}")
    print(f"章节数: {len(chapters)}, 总字数: {total_words}")

    output_dir = project_root / "output"
    output_dir.mkdir(exist_ok=True)

    for fmt in formats:
        fmt = fmt.lower()
        if fmt == "html":
            html = generate_html(project_root, chapters, config)
            output_file = output_dir / f"{project_root.name}.html"
            output_file.write_text(html, encoding="utf-8")
            print(f"  - HTML: {output_file}")

        elif fmt == "epub" or fmt == "xhtml":
            epub = generate_epub(project_root, chapters, config)
            output_file = output_dir / f"{project_root.name}.xhtml"
            output_file.write_bytes(epub)
            print(f"  - XHTML: {output_file}（可用 Calibre 转为 EPUB）")

        elif fmt == "txt":
            txt = generate_txt(chapters)
            output_file = output_dir / f"{project_root.name}.txt"
            output_file.write_text(txt, encoding="utf-8")
            print(f"  - TXT: {output_file}")

        elif fmt == "pdf":
            # PDF 生成需要额外库，输出 HTML 作为替代
            html = generate_html(project_root, chapters, config)
            output_file = output_dir / f"{project_root.name}_for_pdf.html"
            output_file.write_text(html, encoding="utf-8")
            print(f"  - PDF(HTML): {output_file}（请用浏览器打印为PDF）")

        else:
            print(f"  - 不支持的格式: {fmt}")


def main():
    parser = argparse.ArgumentParser(description="小说导出脚本")
    parser.add_argument("--project-root", required=True, type=str, help="项目根目录")
    parser.add_argument("--format", "-f", type=str, nargs="+", default=["html"],
        choices=["html", "txt", "xhtml", "epub", "pdf", "docx"],
        help="导出格式（可多选）。epub/pdf/docx 输出 XHTML 中间格式")
    parser.add_argument("--author", "-a", type=str, help="作者名")
    args = parser.parse_args()

    export(Path(args.project_root), args.format, args.author)


if __name__ == "__main__":
    main()
