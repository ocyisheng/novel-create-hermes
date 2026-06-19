#!/usr/bin/env python3
"""
fix_yaml_indent.py — YAML 缩进规范化（栈式建树）

逐行解析 YAML，基于缩进层级用栈确定每行的父节点，然后统一重写缩进。
当前行缩进 = 父节点缩进 + 2，根级键强制为 0。

和旧版的核心区别：不猜测父子关系，直接建树。单轮确定性输出，无震荡。

用法：
    python fix_yaml_indent.py <输入文件> [输出文件]
    python fix_yaml_indent.py --dir DIR [--recursive] [--check]
    python fix_yaml_indent.py --staging-dir DIR [--recursive]
    python fix_yaml_indent.py --dir DIR --recursive --max-passes 3
    python fix_yaml_indent.py <输入文件> --check

要求：pip install pyyaml
"""

import argparse
import difflib
import re
import sys
import tempfile
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
    __slots__ = ('number', 'raw', 'indent', 'stripped', 'type_', 'parent', 'value_parent_idx')

    def __init__(self, number: int, raw: str):
        self.number = number
        self.raw = raw
        self.indent = len(raw) - len(raw.lstrip(' '))
        self.stripped = raw.lstrip(' ')
        self.type_ = None
        self.parent = None  # 父节点 Line
        self.value_parent_idx = None  # VALUE_CONT 行的 VALUE 父行索引（build_tree 中解析）

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
                nxt.value_parent_idx = i  # 续行的 VALUE 父行索引（build_tree 中解析）
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
            # 从 value_parent_idx 解析父节点（由 _mark_value_continuations 记录）
            if line.value_parent_idx is not None:
                line.parent = lines[line.value_parent_idx]
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
    """根据父节点计算正确缩进并生成新行。

    同步更新 line.indent 为规范化值，确保子节点始终使用父节点的规范化缩进
    （而非原始文件中的旧缩进），使单轮输出即达到稳定状态。
    """
    result = []

    for line in lines:
        if line.type_ == LineType.EMPTY:
            continue

        if line.type_ == LineType.COMMENT:
            # 注释全部顶格
            result.append(line.stripped)
            line.indent = 0
            continue

        if line.type_ == LineType.BLOCK_CONTENT:
            # 块标量内容：指示符缩进 + 2
            if line.parent:
                indent = line.parent.indent + 2
            else:
                indent = 2
            result.append(' ' * indent + line.stripped)
            line.indent = indent
            continue

        if line.type_ == LineType.ROOT_KEY:
            result.append(line.stripped)  # 缩进 0
            line.indent = 0
            continue

        # 其余：父节点缩进 + 2
        if line.parent:
            indent = line.parent.indent + 2
        else:
            indent = 0
        result.append(' ' * indent + line.stripped)
        line.indent = indent

    return result


# ── 混排修复 ────────────────────────────────────────────────────────────────

def _fix_mixed_children(lines: list[Line]) -> None:
    """修复父节点下列表项与映射键混排导致的 YAML 结构错误。

    同一父节点下，所有子节点的输出缩进均为 parent.indent + 2。
    只要父节点同时有 LIST_ITEM 和非 LIST_ITEM 直接子节点，就会产生无效 YAML。
    将非列表项全部重新挂到祖父节点，使其成为兄弟而非子节点。

    场景：特殊区域: 下有列表项 - 名称: 乱星海，又有映射键 连接通道:
          → 连接通道 提升到与 特殊区域 同级
    """
    children_by_parent: dict[int, list[Line]] = {}
    for line in lines:
        if line.parent is not None and line.type_ not in (LineType.EMPTY, LineType.COMMENT):
            pid = id(line.parent)
            if pid not in children_by_parent:
                children_by_parent[pid] = []
            children_by_parent[pid].append(line)

    for pid, kids in children_by_parent.items():
        parent = kids[0].parent

        # 仅处理映射键父节点（KEY/ROOT_KEY/VALUE/BLOCK_INDICATOR）
        # 列表项（LIST_ITEM）下的描述键是合法子节点，不触发混排修复
        if parent.type_ == LineType.LIST_ITEM:
            continue

        has_list = any(k.type_ == LineType.LIST_ITEM for k in kids)
        has_nonlist = any(
            k.type_ in (LineType.KEY, LineType.VALUE, LineType.BLOCK_INDICATOR)
            for k in kids
        )
        if not has_list or not has_nonlist:
            continue

        # 父节点下同时有列表项和非列表项 → 全部非列表项提升到祖父
        fixed = 0
        for k in kids:
            if k.type_ != LineType.LIST_ITEM:
                k.parent = parent.parent
                fixed += 1

        if fixed:
            print(f"  [混排修复] L{parent.number+1} '{parent.stripped}' "
                  f"下 {fixed} 个映射键提升到祖父节点")


# ── 嵌套列表修复 ────────────────────────────────────────────────────────────

def _fix_nested_lists(lines: list[Line]) -> None:
    """修复列表项下错误嵌套的兄弟列表项（缩进错位导致）。

    实体 YAML 中列表项应平级排列（缩进相同），不应嵌套。
    当某列表项的父节点也是列表项时，将其提升为祖父节点的子节点（兄弟）。

    场景：- 名称: 五龙海（缩进 4）
            - 名称: 无边海（缩进 5，应为 4 → 被误判为子节点）
          → 无边海 提升为与 五龙海 同级
    """
    fixed = 0
    for line in lines:
        if line.type_ != LineType.LIST_ITEM:
            continue
        if line.parent is None or line.parent.type_ != LineType.LIST_ITEM:
            continue
        # 列表项的父节点也是列表项 → 缩进错位，提升为兄弟
        line.parent = line.parent.parent
        fixed += 1

    if fixed:
        print(f"  [嵌套列表修复] {fixed} 个错位列表项提升为兄弟节点")


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


# ── 检查模式 ────────────────────────────────────────────────────────────────

def _check_file(filepath: str, max_passes: int = 3) -> bool:
    """检查模式：计算规范化输出，与原文对比 diff，PyYAML 校验。不写文件。

    返回 True 表示无需修改（已规范），False 表示需要修改。
    """
    filepath_p = Path(filepath)

    with open(filepath_p, 'r', encoding='utf-8') as f:
        original_lines = [line.rstrip('\n') for line in f.readlines()]

    # 运行一次完整管线
    lines = [Line(i, raw) for i, raw in enumerate(original_lines)]
    _fix_unclosed_quotes(lines)
    for line in lines:
        _classify(line)
    _mark_block_content(lines)
    _mark_value_continuations(lines)
    _build_tree(lines)
    _fix_mixed_children(lines)
    _fix_nested_lists(lines)
    normalized = _normalize_indent(lines)

    # PyYAML 校验规范化输出
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode='w', suffix='.yaml', delete=False, encoding='utf-8'
        ) as tmp:
            tmp_path = tmp.name
            for l in normalized:
                tmp.write(l + '\n')
        ok, err = _validate_yaml(tmp_path)
    finally:
        if tmp_path:
            Path(tmp_path).unlink(missing_ok=True)

    # 对比（原文去空行，规范化输出不含空行）
    original_no_empty = [l for l in original_lines if l.strip()]
    diff = list(difflib.unified_diff(
        original_no_empty, normalized,
        fromfile=f'{filepath} (原始)',
        tofile=f'{filepath} (规范化)',
        lineterm=''
    ))

    if not ok:
        print(f"\n📄 {filepath}")
        print(f"  ❌ YAML 校验失败: {err}")
        if diff:
            print(f"  📝 缩进差异（独立于结构错误）:")
            for line in diff:
                print(f"  {line}")
        return False

    if diff:
        print(f"\n📄 {filepath}")
        for line in diff:
            print(line)
        return False

    print(f"✅ {filepath}: 缩进已规范，无需修改")
    return True


def fix_yaml_indent(filepath: str, output: str | None = None, max_passes: int = 3, check: bool = False) -> bool:
    """修复 YAML 缩进。

    多轮修复用于处理块标量内容行在重写后可能需要微调的情况。
    大多数文件一轮即可。

    check=True 时仅对比差异 + PyYAML 校验，不写文件。
    """
    if check:
        return _check_file(filepath, max_passes)

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

        # 混排修复
        _fix_mixed_children(lines)

        # 嵌套列表修复
        _fix_nested_lists(lines)

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


def fix_dir(dir_path: str, recursive: bool = False, max_passes: int = 3, check: bool = False) -> int:
    """批量修复目录。返回成功数（检查模式下返回已规范数）。"""
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
        if fix_yaml_indent(str(f), str(f), max_passes=max_passes, check=check):
            ok += 1
        else:
            fail += 1

    if check:
        print(f"\n📝 检查完成: {ok} 已规范, {fail} 需修复 (共 {len(yaml_files)})")
    else:
        print(f"\n📝 完成: {ok} 通过, {fail} 失败 (共 {len(yaml_files)})")
    return ok


def main():
    parser = argparse.ArgumentParser(description="fix_yaml_indent.py — YAML 缩进修复（栈式建树）")
    parser.add_argument("input", nargs="?", help="输入文件路径")
    parser.add_argument("output", nargs="?", help="输出文件路径（默认覆盖输入）")
    parser.add_argument("--dir", default="", help="批量修复目录")
    parser.add_argument("--staging-dir", default="", help="批量修复目录（--dir 别名）")
    parser.add_argument("--recursive", action="store_true", help="递归子目录")
    parser.add_argument("--max-passes", type=int, default=3, help="最大修复轮数（默认 3）")
    parser.add_argument("--check", action="store_true", help="检查模式：仅对比差异 + YAML 校验，不修改文件")

    args = parser.parse_args()

    target_dir = args.dir or args.staging_dir
    if target_dir:
        fix_dir(target_dir, recursive=args.recursive, max_passes=args.max_passes, check=args.check)
        return

    if args.input:
        fix_yaml_indent(args.input, args.output, max_passes=args.max_passes, check=args.check)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == '__main__':
    main()
