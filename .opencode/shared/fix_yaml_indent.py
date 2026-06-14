
#!/usr/bin/env python3
"""
fix_yaml_indent.py — 将 YAML 缩进强制规范为偶数（0,2,4,6,8...）

支持最多 max_passes 次递归修复，每次修复后验证 YAML 合法性，
收敛（无变更）或验证通过即提前退出。

用法：
    python fix_yaml_indent.py <输入文件> [输出文件]       # 单文件
    python fix_yaml_indent.py --dir DIR [--recursive]    # 批量
    python fix_yaml_indent.py --staging-dir DIR          # 暂存区

要求：
    pip install pyyaml
"""

import argparse
import re
import sys
from collections import Counter
from pathlib import Path

# 匹配 YAML 块标量指示符（|, > 及其修饰符如 |2, |+, |-, >2 等）
BLOCK_SCALAR_RE = re.compile(r':\s*[|>][0-9+\-]*\s*$')

# 匹配已有标量值的映射键（如 key: "value"、key: 'value'、key: plain_scalar）
# 特征：key: 后跟非空内容，且不是块标量指示符
MAPPING_KEY_WITH_VALUE_RE = re.compile(r'^[^:]+:\s+.+$')

# 实体 YAML 中必须始终为根级（缩进 0）的顶层键
ROOT_KEYS = {'_meta:', '索引信息:', '摘要:', '完整档案:'}


def _validate_yaml(filepath):
    """尝试用 PyYAML 加载文件，返回 (ok, error_msg)。"""
    try:
        import yaml
        with open(filepath, 'r', encoding='utf-8') as f:
            yaml.safe_load(f)
        return True, None
    except ImportError:
        return True, None  # 未安装 PyYAML，跳过验证
    except Exception as e:
        return False, str(e)


def _find_block_scalar_content(lines):
    """返回所有属于块标量（| / >）内容的行号集合，这些行是纯文本，不应修改缩进"""
    content_lines = set()
    for i, line in enumerate(lines):
        stripped = line.lstrip(' ')
        if BLOCK_SCALAR_RE.search(stripped):
            key_indent = len(line) - len(stripped)
            for j in range(i + 1, len(lines)):
                next_line = lines[j]
                next_stripped = next_line.strip()
                if next_stripped == '' or next_stripped.startswith('#'):
                    content_lines.add(j)
                    continue
                next_indent = len(next_line) - len(next_line.lstrip(' '))
                if next_indent > key_indent:
                    content_lines.add(j)
                else:
                    break
    return content_lines


def _is_root_key_line(stripped):
    """检查行首是否是必须恒在根级（缩进 0）的顶层键。"""
    for key in ROOT_KEYS:
        if stripped.startswith(key):
            return True
    return False


def _even_up(indent, is_list=False, parent_indent=None):
    """将缩进规范为偶数。

    - 先规范化父级缩进（奇数向上取偶）
    - 列表项：对齐到 parent + 2（取偶）
    - 普通键：向上取整为偶数
    """
    # 规范化父级
    if parent_indent is not None and parent_indent >= 0 and parent_indent % 2 != 0:
        parent_indent = ((parent_indent + 2) // 2) * 2
    # 列表项对齐到父级+2
    if is_list and parent_indent is not None and parent_indent >= 0:
        ideal = ((parent_indent + 2) // 2) * 2
        if abs(indent - ideal) <= 2:
            return ideal
        return ((indent + 2) // 2) * 2
    # 普通键：向上取整
    if indent % 2 == 0:
        return indent
    return ((indent + 2) // 2) * 2


def _fix_block_scalar_content_indent(lines):
    """规范化块标量（| / >）内容行的缩进一致性。

    对每个块标量指示符，收集其内容行，将所有内容行对齐到统一缩进（取最小值）。
    返回 (fixed_lines, changed)。
    """
    fixed = list(lines)
    changed = False
    i = 0
    while i < len(fixed):
        stripped = fixed[i].lstrip(' ')
        if not BLOCK_SCALAR_RE.search(stripped):
            i += 1
            continue

        key_indent = len(fixed[i]) - len(stripped)

        # 收集此块标量的内容行
        content_start = i + 1
        content_inds = []  # (line_index, indent)
        for j in range(content_start, len(fixed)):
            s = fixed[j].strip()
            if s == '' or s.startswith('#'):
                content_inds.append((j, None))  # 空行/注释，跳过
                continue
            ci = len(fixed[j]) - len(fixed[j].lstrip(' '))
            if ci > key_indent:
                content_inds.append((j, ci))
            else:
                break

        # 找到有实际内容的行的最小缩进
        real_indents = [ind for _, ind in content_inds if ind is not None]
        if not real_indents:
            i += 1
            continue

        min_indent = min(real_indents)
        if min_indent == key_indent:
            min_indent = key_indent + 2  # 至少比键缩进多 2

        # 对齐所有内容行到 min_indent
        for j, ind in content_inds:
            if ind is not None and ind != min_indent:
                s = fixed[j].lstrip(' ')
                fixed[j] = ' ' * min_indent + s
                print(f"  [块标量对齐] L{j+1}: {ind} -> {min_indent}  | {s[:60]}")
                changed = True

        # 跳过已处理的内容行
        i = content_start + len(content_inds)

    return fixed, changed


def _apply_fix_pass(lines, block_content_lines):
    """对 lines 执行一次完整的四步缩进修复，返回 (fixed_lines, changed)。

    四步流水线：
      Step 1 — 所有行缩进取整为偶数
      Step 2 — 同一父级下列表项缩进对齐（众数）
      Step 3 — 列表项内同级键缩进修正
      Step 4 — 块标量（| / >）内容行缩进一致性规范化
    """
    fixed_lines = list(lines)
    changed = False

    # ------- 预计算父级缩进 -------
    parent_indents = {}
    for i, line in enumerate(lines):
        if line.strip() == '' or line.strip().startswith('#'):
            continue
        stripped = line.lstrip(' ')
        indent = len(line) - len(stripped)
        is_this_list = stripped.startswith('- ')
        for j in range(i - 1, -1, -1):
            prev = lines[j]
            if prev.strip() == '' or prev.strip().startswith('#'):
                continue
            ps = prev.lstrip(' ')
            pi = len(prev) - len(ps)
            if is_this_list and ps.startswith('- ') and pi <= indent:
                continue
            if pi < indent:
                parent_indents[i] = pi
                break

    root_key_lines = set()

    # ------- Step 1：所有行缩进取整为偶数 -------
    for i, line in enumerate(lines):
        if line.strip() == '' or line.strip().startswith('#'):
            continue
        if i in block_content_lines:
            continue
        stripped = line.lstrip(' ')
        indent = len(line) - len(stripped)

        # 实体顶层键强制缩进 0
        if _is_root_key_line(stripped):
            if indent != 0:
                fixed_lines[i] = stripped
                print(f"  [根级强制] L{i+1}: {indent} -> 0  | {stripped[:60]}")
                changed = True
            root_key_lines.add(i)
            continue

        if indent % 2 != 0:
            is_list = stripped.startswith('- ')
            p_indent = parent_indents.get(i)
            new_indent = _even_up(indent, is_list=is_list, parent_indent=p_indent)
            if new_indent != indent:
                fixed_lines[i] = ' ' * new_indent + stripped
                print(f"  [取整] L{i+1}: {indent} -> {new_indent}  | {stripped[:60]}")
                changed = True

    # ------- Step 2：同一父级下列表项缩进对齐（众数） -------
    def find_parent(line_idx, lines_list):
        """向上查找第一个缩进更小的非空非注释行，返回 (索引, 缩进, 是否为映射键)"""
        for j in range(line_idx - 1, -1, -1):
            prev = lines_list[j]
            if prev.strip() == '' or prev.strip().startswith('#'):
                continue
            prev_indent = len(prev) - len(prev.lstrip(' '))
            if prev_indent < len(lines_list[line_idx]) - len(lines_list[line_idx].lstrip(' ')):
                is_mapping = not prev.lstrip(' ').startswith('- ')
                return j, prev_indent, is_mapping
        return None, None, False

    # 收集所有列表项
    list_entries = []
    for i, line in enumerate(fixed_lines):
        if i in root_key_lines:
            continue
        stripped = line.lstrip(' ')
        if stripped.startswith('- '):
            indent = len(line) - len(stripped)
            list_entries.append((i, indent, stripped))

    # 按父级行索引分组
    groups = {}
    for idx, indent, content in list_entries:
        parent_idx, parent_indent, is_mapping = find_parent(idx, fixed_lines)
        groups.setdefault(parent_idx, []).append((idx, indent, content))

    # 对每组列表项统一缩进
    for parent_idx, items in groups.items():
        indents = [indent for _, indent, _ in items]
        if len(set(indents)) <= 1:
            continue
        most_common = Counter(indents).most_common(1)[0][0]
        for idx, indent, content in items:
            if indent != most_common:
                fixed_lines[idx] = ' ' * most_common + content
                print(f"  [列表对齐] L{idx+1}: {indent} -> {most_common}  | {content[:60]}")
                changed = True

    # ------- Step 3：列表项内同级键缩进修正 -------
    for i, line in enumerate(fixed_lines):
        if i in root_key_lines:
            continue
        stripped = line.lstrip(' ')
        if stripped == '' or stripped.startswith('#') or stripped.startswith('- '):
            continue
        if i in block_content_lines:
            continue
        indent = len(line) - len(stripped)

        # 向上扫描，找最近的非空非注释行
        nearest_above = None
        nearest_above_idx = None
        for j in range(i - 1, -1, -1):
            prev = fixed_lines[j]
            if prev.strip() == '' or prev.strip().startswith('#'):
                continue
            nearest_above = prev
            nearest_above_idx = j
            break
        if nearest_above is None:
            continue

        nearest_stripped = nearest_above.lstrip(' ')
        nearest_indent = len(nearest_above) - len(nearest_stripped)

        # 场景 B：最近的上方行是同缩进的列表项
        if nearest_stripped.startswith('- ') and nearest_indent == indent:
            has_deeper_children = False
            for j in range(nearest_above_idx + 1, i):
                check_line = fixed_lines[j]
                if check_line.strip() == '' or check_line.strip().startswith('#'):
                    continue
                check_indent = len(check_line) - len(check_line.lstrip(' '))
                if check_indent > nearest_indent:
                    has_deeper_children = True
                    break
            if has_deeper_children:
                continue

            current_key = stripped.split(':')[0].strip()
            check2_is_child = False
            for j in range(nearest_above_idx - 1, -1, -1):
                prev = fixed_lines[j]
                if prev.strip() == '' or prev.strip().startswith('#'):
                    continue
                ps = prev.lstrip(' ')
                pi = len(prev) - len(ps)
                if ps.startswith('- ') and pi < indent:
                    break
                if pi > nearest_indent:
                    prev_key = ps.split(':')[0].strip()
                    if prev_key == current_key:
                        check2_is_child = True
                        break
            if check2_is_child:
                correct = nearest_indent + 2
                if indent != correct:
                    fixed_lines[i] = ' ' * correct + stripped
                    print(f"  [修正为子键] L{i+1}: {indent} -> {correct}  | {stripped[:60]}")
                    changed = True
                continue

            for j in range(nearest_above_idx - 1, -1, -1):
                prev = fixed_lines[j]
                if prev.strip() == '' or prev.strip().startswith('#'):
                    continue
                ps = prev.lstrip(' ')
                pi = len(prev) - len(ps)
                if not ps.startswith('- ') and pi < nearest_indent:
                    if indent != pi:
                        fixed_lines[i] = ' ' * pi + stripped
                        print(f"  [提升到映射键] L{i+1}: {indent} -> {pi}  | {stripped[:60]}")
                        changed = True
                    break
            continue

        # 场景 C：最近的上方行是已有标量值的映射键
        if (not nearest_stripped.startswith('- ')
                and nearest_indent < indent
                and MAPPING_KEY_WITH_VALUE_RE.match(nearest_stripped)):
            for j in range(nearest_above_idx - 1, -1, -1):
                prev = fixed_lines[j]
                if prev.strip() == '' or prev.strip().startswith('#'):
                    continue
                ps = prev.lstrip(' ')
                pi = len(prev) - len(ps)
                if pi < nearest_indent:
                    if indent != nearest_indent:
                        fixed_lines[i] = ' ' * nearest_indent + stripped
                        print(f"  [提升到映射键] L{i+1}: {indent} -> {nearest_indent}  | {stripped[:60]}")
                        changed = True
                    break
            continue

        # 场景 A：最近的上方行是缩进更小的列表项
        if nearest_stripped.startswith('- ') and nearest_indent < indent:
            correct_indent = nearest_indent + 2
            if indent != correct_indent:
                fixed_lines[i] = ' ' * correct_indent + stripped
            print(f"  [列表项内对齐] L{i+1}: {indent} -> {correct_indent}  | {stripped[:60]}")
            changed = True
            continue

        # 其他情况：尝试向上找列表项
        parent_list_idx = None
        for j in range(i - 1, -1, -1):
            prev = fixed_lines[j]
            if prev.strip() == '' or prev.strip().startswith('#'):
                continue
            ps = prev.lstrip(' ')
            pi = len(prev) - len(ps)
            if ps.startswith('- ') and pi < indent:
                parent_list_idx = j
                break
        if parent_list_idx is None:
            if (not nearest_stripped.startswith('- ')
                    and MAPPING_KEY_WITH_VALUE_RE.match(nearest_stripped)
                    and not BLOCK_SCALAR_RE.search(nearest_stripped)
                    and indent < nearest_indent):
                fixed_lines[i] = ' ' * nearest_indent + stripped
                print(f"  [同级对齐] L{i+1}: {indent} -> {nearest_indent}  | {stripped[:60]}")
                changed = True
            continue

        parent_indent = len(fixed_lines[parent_list_idx]) - len(fixed_lines[parent_list_idx].lstrip(' '))
        if indent <= parent_indent:
            if (not nearest_stripped.startswith('- ')
                    and MAPPING_KEY_WITH_VALUE_RE.match(nearest_stripped)
                    and not BLOCK_SCALAR_RE.search(nearest_stripped)
                    and indent < nearest_indent):
                fixed_lines[i] = ' ' * nearest_indent + stripped
                print(f"  [同级对齐] L{i+1}: {indent} -> {nearest_indent}  | {stripped[:60]}")
                changed = True
            continue
        correct_indent = parent_indent + 2
        if indent != correct_indent:
            fixed_lines[i] = ' ' * correct_indent + stripped
            print(f"  [列表项内对齐] L{i+1}: {indent} -> {correct_indent}  | {stripped[:60]}")
            changed = True

    # ------- Step 4：块标量内容缩进一致性 -------
    fixed_lines, changed4 = _fix_block_scalar_content_indent(fixed_lines)
    changed = changed or changed4

    return fixed_lines, changed


def fix_yaml_indent(filepath, output=None, max_passes=3):
    """修复 YAML 缩进，最多执行 max_passes 次递归修复。

    每次修复后验证 YAML 合法性：
    - 验证通过 → 立即写入并退出
    - 无变更（收敛）→ 写入并退出
    - 未通过 → 继续下一轮修复
    - 达到 max_passes → 写入最终结果并报告
    """
    with open(filepath, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    original_lines = [line.rstrip('\n') for line in lines]

    block_content_lines = _find_block_scalar_content(original_lines)

    current_lines = original_lines
    for pass_num in range(1, max_passes + 1):
        print(f"\n--- Pass {pass_num}/{max_passes} ---")
        fixed_lines, changed = _apply_fix_pass(current_lines, block_content_lines)

        if not changed:
            print(f"✅ Pass {pass_num}: 无变更，已收敛。")
            current_lines = fixed_lines
            break

        current_lines = fixed_lines

        # 每轮修复后临时写入文件以验证
        output_path = output if output else filepath
        with open(output_path, 'w', encoding='utf-8') as f:
            for line in current_lines:
                f.write(line + '\n')

        ok, err = _validate_yaml(output_path)
        if ok:
            print(f"✅ Pass {pass_num}: YAML 验证通过。")
            return
        else:
            print(f"⚠️  Pass {pass_num}: YAML 验证失败: {err}，继续修复...")

    # 写入最终结果
    output_path = output if output else filepath
    with open(output_path, 'w', encoding='utf-8') as f:
        for line in current_lines:
            f.write(line + '\n')

    if current_lines == original_lines:
        print("✅ 无需修改，缩进已符合规范。")
    else:
        print(f"📝 修复完毕（{max_passes} 轮），写入 {output_path}")

    ok, err = _validate_yaml(output_path)
    if ok:
        print("✅ YAML 格式验证通过！")
    else:
        print(f"❌ {max_passes} 轮修复后仍存在格式错误: {err}")


def fix_dir(dir_path: str, recursive: bool = False) -> int:
    """批量修复目录下所有 .yaml/.yml 文件。返回修复的文件数。"""
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

    fixed = 0
    for f in yaml_files:
        try:
            fix_yaml_indent(str(f), str(f))
            fixed += 1
        except Exception as e:
            print(f"❌ {f.name}: {e}", file=sys.stderr)
    print(f"\n📝 批量修复完成: {fixed}/{len(yaml_files)} 个文件")
    return fixed


def main():
    parser = argparse.ArgumentParser(
        description="fix_yaml_indent.py — YAML 缩进修复（偶数缩进规范）",
    )

    # 旧模式：位置参数
    parser.add_argument("input", nargs="?",
                        help="输入文件路径（省略则用 --dir/--staging-dir）")
    parser.add_argument("output", nargs="?",
                        help="输出文件路径（可选，默认覆盖输入）")

    # 新模式
    parser.add_argument("--dir", default="", help="批量修复目录下所有 YAML 文件")
    parser.add_argument("--staging-dir", default="", help="修复暂存区所有 YAML 文件")
    parser.add_argument("--recursive", action="store_true",
                        help="递归扫描子目录（与 --dir 搭配）")
    parser.add_argument("--max-passes", type=int, default=3,
                        help="最大递归修复轮数（默认 3）")

    args = parser.parse_args()

    # 批量模式
    if args.dir:
        fix_dir(args.dir, recursive=args.recursive)
        return
    if args.staging_dir:
        fix_dir(args.staging_dir, recursive=True)
        return

    # 单文件模式（向后兼容）
    if args.input:
        fix_yaml_indent(args.input, args.output, max_passes=args.max_passes)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == '__main__':
    main()
