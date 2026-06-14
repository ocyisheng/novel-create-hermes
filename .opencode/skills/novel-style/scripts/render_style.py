#!/usr/bin/env python3
"""
render_style.py — 将 style.yaml 渲染为 LLM 可用的提示词块

读取 7 维度风格定义文件，转换为自然语言格式，用于章节写作或风格一致性检查。

用法:
    python render_style.py --style builtin/悬疑推理风.yaml --mode chapter
    python render_style.py --style styles/我的风格.yaml --mode check

输出可直接内联到 extract_template.py 填充后的 prompt 中。
"""

import argparse
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print("错误: 需要 PyYAML", file=sys.stderr)
    sys.exit(1)


def load_style(style_path: Path) -> dict:
    with open(style_path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _fmt(v: dict) -> str:
    """将维度字典渲染为自然语言。"""
    parts = []
    desc = v.get("description", "")
    if desc:
        parts.append(desc)
    for key, label in [
        ("keywords", "关键词"), ("characteristics", "特征"),
        ("avg_sentence_length", "句长"), ("pattern", "模式"),
        ("attribution_pattern", "标记"), ("speech_patterns", "对话特征"),
        ("register_level", "语域"), ("distinctive_vocab", "推荐用词"),
        ("forbidden_vocab", "禁用词"), ("devices", "手法"),
        ("patterns", "禁止"),
    ]:
        val = v.get(key)
        if val:
            parts.append(f"{label}：{'、'.join(val) if isinstance(val, list) else val}")
    return "；".join(parts)


def render_chapter(style: dict) -> str:
    """渲染为章节写作的 STYLE REFERENCE 段。"""
    d = style.get("dimensions", {})
    lines = [
        f"-风格：{style.get('style_name', '')} — {style.get('description', '')}",
        "",
        "以下 7 个维度定义本风格的写作特征，写作时严格遵循：",
        "",
    ]
    for label, key in [
        ("叙事基调", "narrative_tone"), ("句子结构", "sentence_structure"),
        ("节奏", "pacing"), ("对话风格", "dialogue_style"),
        ("词汇选择", "vocabulary_register"), ("修辞特征", "rhetorical_features"),
        ("禁止模式", "forbidden_patterns"),
    ]:
        v = d.get(key)
        if v:
            lines.append(f"- {label}：{_fmt(v)}")
    lines.append("")
    lines.append("> 以上风格定义适用于叙述者，不影响角色对话的个性化声音。")
    return "\n".join(lines)


def render_check(style: dict) -> str:
    """渲染为风格一致性检查的评估 prompt。"""
    d = style.get("dimensions", {})
    lines = [
        "## 风格一致性检查",
        "",
        f"对照风格「{style.get('style_name', '')}」（{style.get('description', '')}），",
        "逐维度评估本章的偏离程度。每个维度必须引用 1-2 句本章原文作为证据。",
        "",
    ]
    for label, key, question in [
        ("叙事基调", "narrative_tone", "叙述视角、情感距离、氛围是否匹配"),
        ("句子结构", "sentence_structure", "句长分布、句式复杂度是否匹配"),
        ("节奏", "pacing", "详略分布是否符合风格节奏模式"),
        ("对话风格", "dialogue_style", "对话标签模式、信息密度是否匹配"),
        ("词汇选择", "vocabulary_register", "用词语域、特色词汇是否匹配，禁用词是否出现"),
        ("修辞特征", "rhetorical_features", "修辞手法类型和密度是否匹配"),
        ("禁止模式", "forbidden_patterns", "是否出现风格明确禁止的写法"),
    ]:
        v = d.get(key)
        if not v:
            continue
        lines.append(f"### {label}")
        lines.append(f"风格要求：{_fmt(v)}")
        lines.append(f"检查项：{question}")
        lines.append(f"偏离：[ ] 无偏离  [ ] 轻微  [ ] 明显  [ ] 严重")
        lines.append(f"证据（必须引用本章原文）：")
        lines.append("")

    lines.append("## 综合判断")
    lines.append("一致性等级：[ ] A-高度一致  [ ] B-基本一致  [ ] C-部分偏离  [ ] D-严重偏离")
    lines.append("总评：")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        prog="render_style.py",
        description="将 style.yaml 渲染为 LLM 提示词块",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""示例:
  python render_style.py --style styles/凡人修仙风.yaml --mode chapter  # 生成写作参考
  python render_style.py --style styles/金庸武侠风.yaml --mode check    # 生成一致性检查

说明:
  --mode chapter: 输出写作风格参考段落，注入到章节写作 prompt 中
  --mode check:   输出 7 维度评估表，用于检查章节与风格的一致性"""
    )
    parser.add_argument("--style", required=True, type=str, help="style.yaml 文件路径")
    parser.add_argument("--mode", required=True, choices=["chapter", "check"],
                        help="chapter: 写作风格参考 | check: 一致性检查")
    args = parser.parse_args()

    style_path = Path(args.style)
    if not style_path.is_file():
        print(f"错误: 风格文件未找到: {style_path}", file=sys.stderr)
        sys.exit(1)

    style = load_style(style_path)
    print(render_chapter(style) if args.mode == "chapter" else render_check(style))


if __name__ == "__main__":
    main()
