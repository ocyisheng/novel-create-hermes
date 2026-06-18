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


def _quantify_sentence_length(length: str) -> str:
    """将句长描述转换为更具体的指导。"""
    mapping = {
        "short": "15字以内",
        "medium": "15-30字",
        "long": "30字以上",
        "mixed": "长短交错（15-30字为主）"
    }
    return mapping.get(length, length)


def _fmt_dimension(label: str, v: dict, add_examples: bool = True) -> list:
    """将单个维度渲染为多行格式，每个字段独立成行。"""
    lines = []
    desc = v.get("description", "")
    
    # 根据维度类型添加优先级标记
    priority = "[必须]" if label in ["句子结构", "词汇选择", "禁止模式"] else "[建议]"
    
    if desc:
        lines.append(f"  {priority} {desc}")
    
    # 处理各个字段
    for key, field_label in [
        ("keywords", "关键词"), ("characteristics", "特征"),
        ("avg_sentence_length", "句长"), ("pattern", "模式"),
        ("attribution_pattern", "标记"), ("speech_patterns", "对话特征"),
        ("register_level", "语域"), ("distinctive_vocab", "推荐用词"),
        ("forbidden_vocab", "禁用词"), ("devices", "手法"),
        ("patterns", "禁止"),
    ]:
        val = v.get(key)
        if val:
            # 量化句长描述
            if key == "avg_sentence_length":
                val = _quantify_sentence_length(val)
                field_label = "句长（每句）"
            
            # 格式化列表值
            if isinstance(val, list):
                val_str = "、".join(val)
            else:
                val_str = val
            
            # 为推荐用词和禁用词添加强调
            if key == "distinctive_vocab":
                lines.append(f"  ✓ 优先使用：{val_str}")
            elif key == "forbidden_vocab":
                lines.append(f"  ✗ 绝对禁止：{val_str}")
            elif key == "patterns":
                lines.append(f"  ✗ 绝对禁止：{val_str}")
            else:
                lines.append(f"  {field_label}：{val_str}")
    
    # 添加具体示例（从模板文件中读取）
    if add_examples:
        example = _get_example_from_dimension(v)
        if example:
            lines.append(f"  示例：{example}")
    
    return lines


def _get_example_from_dimension(v: dict) -> str:
    """从维度字典中获取示例字段。"""
    return v.get("example", "")


def render_chapter(style: dict) -> str:
    """渲染为章节写作的 STYLE REFERENCE 段。"""
    d = style.get("dimensions", {})
    style_name = style.get('style_name', '')
    description = style.get('description', '')
    
    lines = [
        f"**{style_name}** — {description}",
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
            # 使用简洁格式：一行描述 + 关键约束
            desc = v.get("description", "")
            priority = "⚠️" if label in ["句子结构", "词汇选择", "禁止模式"] else "•"
            
            # 构建关键约束
            constraints = []
            if label == "句子结构":
                length = v.get("avg_sentence_length", "")
                if length:
                    constraints.append(f"句长：{_quantify_sentence_length(length)}")
            elif label == "词汇选择":
                distinctive = v.get("distinctive_vocab", [])
                forbidden = v.get("forbidden_vocab", [])
                if distinctive:
                    constraints.append(f"用{'、'.join(distinctive[:3])}")
                if forbidden:
                    constraints.append(f"禁{'、'.join(forbidden[:2])}")
            elif label == "禁止模式":
                patterns = v.get("patterns", [])
                if patterns:
                    constraints.append(f"禁{'、'.join(patterns[:3])}")
            
            # 获取示例
            example = v.get("example", "")
            
            # 构建输出行
            constraint_str = f"（{'；'.join(constraints)}）" if constraints else ""
            example_str = f" 示例：{example}" if example else ""
            
            lines.append(f"{priority} **{label}**：{desc}{constraint_str}{example_str}")
    
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
        lines.append(f"风格要求：")
        lines.extend(_fmt_dimension(label, v, add_examples=False))
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
