#!/usr/bin/env python3
"""
fix_yaml_indent.py — YAML 缩进规范化（栈式建树）

逐行解析 YAML，基于缩进层级用栈确定每行的父节点，然后统一重写缩进。
当前行缩进 = 父节点缩进 + 2，根级键强制为 0。

和旧版的核心区别：不猜测父子关系，直接建树。单轮确定性输出，无震荡。

用法：
    python fix_yaml_indent.py <输入文件> [输出文件]
    python fix_yaml_indent.py --dir DIR [--recursive]
    python fix_yaml_indent.py --dir DIR --recursive --max-passes 3

要求：pip install pyyaml
"""

import argparse
import re
import sys
from pathlib import Path

# ── 行分类正则 ──────────────────────────────────────────────────────────────

# 块标量指示符：key: | 或 key: > 及其修饰符
BLOCK_INDICATOR_RE = re.compile(r'^[^:]+:\s*[|>][0-9+\-]*\s*$')

# 空行 / 注释
EMPTY_RE = re.compile(r'^\s*$')
COMMENT_RE = re.compile(r'^\s*#')

# 列表项
LIST_ITEM_RE = re.compile(r'^\s*-\s+')

# 映射键（无值）：key:
KEY_RE = re.compile(r'^\s*[^:]+:\s*$')

# 映射键（有值）：key: value
VALUE_RE = re.compile(r'^\s*[^:]+:\s+.+$')

# 必须为根级缩进 0 的顶层键（实体 YAML 的四层结构）
ROOT_KEYS = {'_meta:', '索引信息:', '摘要:', '完整档案:'}

# ── 行类型枚举 ──────────────────────────────────────────────────────────────

class LineType:
    ROOT_KEY = 'root_key'
    KEY = 'key'
    LIST_ITEM = 'list_item'
    VALUE = 'value'
    VALUE_CONT = 'value_cont'
    BLOCK_INDICATOR = 'block_indicator'
    BLOCK_CONTENT = 'block_content'
    EMPTY = 'empty'
    COMMENT = 'comment'


class Line:
    """YAML 中的一行。"""
    __slots__ = ('number', 'raw', 'indent', 'stripped', 'type_', 'parent')

    def __init__(self, number: int, raw: str):
        self.number = number
        self.raw = raw
        self.indent = len(raw) - len(raw.lstrip(' '))
        self.stripped = raw.lstrip(' ')
        self.type_ = None
        self.parent = None  # 父节点 Line

    def is_structural(self) -> bool:
        """是否参与树结构（作为潜在父节点）。"""
        return self.type_ in (LineType.ROOT_KEY, LineType.KEY, LineType.LIST_ITEM, LineType.BLOCK_INDICATOR)


# ── 引号补全 ────────────────────────────────────────────────────────────────

UNCLOSED_QUOTE_RE = re.compile(r'^(\s*[^:]+:\s*)"([^"]*)$')

def _fix_unclosed_quotes(lines: list[Line]) -> None:
    """补全缺失闭合引号的行。

    场景：- 伏笔名: "灵气在经脉中...
         缺结尾 "
    """
    for line in lines:
        m = UNCLOSED_QUOTE_RE.match(line.raw)
        if m:
            line.raw = m.group(1) + '"' + m.group(2) + '"'
            line.stripped = line.raw.lstrip(' ')
            print(f"  [补引号] L{line.number+1}")


# ── 分类 ───────────────────────────────────────────────────────────────────

def _is_root_key(stripped: str) -> bool:
    for key in ROOT_KEYS:
        if stripped.startswith(key):
            return True
    return False


def _classify(line: Line) -> None:
    """根据当前缩进和内容给行分类。"""
    s = line.stripped

    if EMPTY_RE.match(s):
        line.type_ = LineType.EMPTY
    elif COMMENT_RE.match(s):
        line.type_ = LineType.COMMENT
    elif _is_root_key(s):
        line.type_ = LineType.ROOT_KEY
    elif LIST_ITEM_RE.match(s):
        line.type_ = LineType.LIST_ITEM
    elif BLOCK_INDICATOR_RE.match(s):
        line.type_ = LineType.BLOCK_INDICATOR
    elif KEY_RE.match(s):
        line.type_ = LineType.KEY
    elif VALUE_RE.match(s):
        line.type_ = LineType.VALUE
    else:
        # 兜底：无法识别的行，按普通键处理
        line.type_ = LineType.KEY


# ── 块标量范围标记 ─────────────────────────────────────────────────────────

def _mark_block_content(lines: list[Line]) -> None:
    """将块标量指示符下方的内容行标记为 BLOCK_CONTENT。"""
    for i, line in enumerate(lines):
        if line.type_ != LineType.BLOCK_INDICATOR:
            continue
        key_indent = line.indent
        for j in range(i + 1, len(lines)):
            nxt = lines[j]
            if nxt.type_ in (LineType.EMPTY, LineType.COMMENT):
                continue
            if nxt.indent > key_indent:
                nxt.type_ = LineType.BLOCK_CONTENT
            else:
                break


# ── 多行值续行标记 ─────────────────────────────────────────────────────────

def _mark_value_continuations(lines: list[Line]) -> None:
    """将 VALUE 行下方无冒号无列表符的续行标记为 VALUE_CONT。
    
    场景：情节价值: 林逸的科学修仙...——
         同样数量的灵气...                ← 续行
    """
    for i, line in enumerate(lines):
        if line.type_ not in (LineType.VALUE, LineType.VALUE_CONT):
            continue
        base_indent = line.indent
        for j in range(i + 1, len(lines)):
            nxt = lines[j]
            if nxt.type_ in (LineType.EMPTY, LineType.COMMENT):
                continue
            # 只处理 KEY 兜底分类的行（无冒号、非列表、非空）
            if nxt.type_ != LineType.KEY:
                break
            if nxt.stripped.startswith('- ') or ':' in nxt.stripped:
                break
            if nxt.indent >= base_indent:
                nxt.type_ = LineType.VALUE_CONT
                nxt.parent = line  # 续行的父节点是 VALUE 行本身
            else:
                break


# ── 栈式建树 ───────────────────────────────────────────────────────────────

def _build_tree(lines: list[Line]) -> None:
    """基于缩进用栈确定每行的父节点。

    规则：若当前行缩进 <= 栈顶缩进，弹出直到栈顶缩进 < 当前行缩进。
          栈顶即为父节点。空行和注释继承上一个结构行的父节点。
    """
    stack: list[Line] = []

    for line in lines:
        if line.type_ in (LineType.EMPTY, LineType.COMMENT):
            continue

        if line.type_ == LineType.BLOCK_CONTENT:
            if stack:
                line.parent = stack[-1]
            continue

        if line.type_ == LineType.VALUE_CONT:
            # parent 已在 _mark_value_continuations 设置，不覆盖
            continue

        # 非根级键：向上查找父节点
        if line.type_ != LineType.ROOT_KEY:
            while stack and stack[-1].indent >= line.indent:
                stack.pop()
            if stack:
                line.parent = stack[-1]

        if line.is_structural():
            stack.append(line)


# ── 缩进重写 ───────────────────────────────────────────────────────────────

def _normalize_indent(lines: list[Line]) -> list[str]:
    """根据父节点计算正确缩进并生成新行。"""
    result = []

    for line in lines:
        if line.type_ == LineType.EMPTY:
            continue

        if line.type_ == LineType.COMMENT:
            # 注释全部顶格
            result.append(line.stripped)
            continue

        if line.type_ == LineType.BLOCK_CONTENT:
            # 块标量内容：指示符缩进 + 2
            if line.parent:
                indent = line.parent.indent + 2
            else:
                indent = 2
            result.append(' ' * indent + line.stripped)
            continue

        if line.type_ == LineType.ROOT_KEY:
            result.append(line.stripped)  # 缩进 0
            continue

        # 其余：父节点缩进 + 2
        if line.parent:
            indent = line.parent.indent + 2
        else:
            indent = 0
        result.append(' ' * indent + line.stripped)

    return result


# ── 修复入口 ────────────────────────────────────────────────────────────────

def _validate_yaml(filepath: str) -> tuple[bool, str | None]:
    """PyYAML 校验。未安装则跳过。"""
    try:
        import yaml
        with open(filepath, 'r', encoding='utf-8') as f:
            yaml.safe_load(f)
        return True, None
    except ImportError:
        return True, None
    except Exception as e:
        return False, str(e)


def fix_yaml_indent(filepath: str, output: str | None = None, max_passes: int = 3) -> bool:
    """修复 YAML 缩进。

    多轮修复用于处理块标量内容行在重写后可能需要微调的情况。
    大多数文件一轮即可。
    """
    output_path = output or filepath
    filepath_p = Path(filepath)

    for pass_num in range(1, max_passes + 1):
        # 读入
        with open(filepath_p, 'r', encoding='utf-8') as f:
            raw_lines = [line.rstrip('\n') for line in f.readlines()]

        # 建行对象
        lines = [Line(i, raw) for i, raw in enumerate(raw_lines)]

        # 补全引号（前置，避免影响后续分类）
        _fix_unclosed_quotes(lines)

        # 分类
        for line in lines:
            _classify(line)

        # 标记块标量内容
        _mark_block_content(lines)

        # 标记多行值续行
        _mark_value_continuations(lines)

        # 建树
        _build_tree(lines)

        # 重写
        normalized = _normalize_indent(lines)

        # 写入
        with open(output_path, 'w', encoding='utf-8') as f:
            for l in normalized:
                f.write(l + '\n')

        # 验证
        ok, err = _validate_yaml(output_path)
        if ok:
            if pass_num == 1:
                print(f"✅ YAML 格式已修复并验证通过: {output_path}")
            else:
                print(f"✅ Pass {pass_num}: YAML 验证通过: {output_path}")
            return True

        if pass_num < max_passes:
            print(f"⚠️  Pass {pass_num}: YAML 验证失败: {err}，继续修复...")
            filepath_p = Path(output_path)

    print(f"❌ {max_passes} 轮后仍存在格式错误: {err}")
    return False


def fix_dir(dir_path: str, recursive: bool = False, max_passes: int = 3) -> int:
    """批量修复目录。返回成功数。"""
    p = Path(dir_path).resolve()
    if not p.is_dir():
        print(f"错误: 目录不存在: {p}", file=sys.stderr)
        return 0

    if recursive:
        yaml_files = list(p.rglob("*.yaml")) + list(p.rglob("*.yml"))
    else:
        yaml_files = list(p.glob("*.yaml")) + list(p.glob("*.yml"))

    if not yaml_files:
        print(f"📂 目录 '{p}' 中没有 YAML 文件")
        return 0

    ok = fail = 0
    for f in yaml_files:
        if fix_yaml_indent(str(f), str(f), max_passes=max_passes):
            ok += 1
        else:
            fail += 1
    print(f"\n📝 完成: {ok} 通过, {fail} 失败 (共 {len(yaml_files)})")
    return ok


def main():
    parser = argparse.ArgumentParser(description="fix_yaml_indent.py — YAML 缩进修复（栈式建树）")
    parser.add_argument("input", nargs="?", help="输入文件路径")
    parser.add_argument("output", nargs="?", help="输出文件路径（默认覆盖输入）")
    parser.add_argument("--dir", default="", help="批量修复目录")
    parser.add_argument("--recursive", action="store_true", help="递归子目录")
    parser.add_argument("--max-passes", type=int, default=3, help="最大修复轮数（默认 3）")

    args = parser.parse_args()

    if args.dir:
        fix_dir(args.dir, recursive=args.recursive, max_passes=args.max_passes)
        return

    if args.input:
        fix_yaml_indent(args.input, args.output, max_passes=args.max_passes)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == '__main__':
    main()
