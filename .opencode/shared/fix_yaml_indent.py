
#!/usr/bin/env python3
"""
fix_yaml_indent_even.py - 将 YAML 缩进强制规范为偶数（0,2,4,6,8...）

用法：
    python fix_yaml_indent.py <输入文件> [输出文件]
    若不提供输出文件，则直接覆盖输入文件。

要求：
    pip install pyyaml
"""

import re
import sys
from collections import Counter

# 匹配 YAML 块标量指示符（|, > 及其修饰符如 |2, |+, |-, >2 等）
BLOCK_SCALAR_RE = re.compile(r':\s*[|>][0-9+\-]*\s*$')

# 匹配已有标量值的映射键（如 key: "value"、key: 'value'、key: plain_scalar）
# 特征：key: 后跟非空内容，且不是块标量指示符
MAPPING_KEY_WITH_VALUE_RE = re.compile(r'^[^:]+:\s+.+$')


def find_block_scalar_content(lines):
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

def even_up(indent):
    """将缩进向上取整为偶数（2的倍数）"""
    if indent % 2 == 0:
        return indent
    else:
        return ((indent + 2) // 2) * 2  # 等价于 (indent + 1) // 2 * 2，此处确保向上

def fix_yaml_indent(filepath, output=None):
    with open(filepath, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    original_lines = [line.rstrip('\n') for line in lines]
    fixed_lines = original_lines.copy()

    # 预计算：哪些行是块标量内容（纯文本，缩进不能修改）
    block_content_lines = find_block_scalar_content(original_lines)

    # ------- 第一步：所有行缩进取整为偶数 -------
    for i, line in enumerate(original_lines):
        if line.strip() == '' or line.strip().startswith('#'):
            continue
        if i in block_content_lines:
            continue  # 块标量内容是纯文本，不修改缩进
        stripped = line.lstrip(' ')
        indent = len(line) - len(stripped)
        if indent % 2 != 0:
            new_indent = even_up(indent)
            fixed_lines[i] = ' ' * new_indent + stripped
            print(f"  [取整] L{i+1}: {indent} -> {new_indent}  | {stripped[:60]}")

    # ------- 第二步：同一父级下列表项缩进对齐（众数） -------
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
        stripped = line.lstrip(' ')
        if stripped.startswith('- '):
            indent = len(line) - len(stripped)
            list_entries.append((i, indent, stripped))

    # 按父级行索引分组（确保只有同一父级下的列表项才参与众数对齐）
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

    # ------- 第三步：列表项内同级键缩进修正 -------
    # 场景 A：非列表键是列表项的子属性 → 缩进到 parent_indent + 2（与 - key 对齐）
    # 场景 B：非列表键与列表项同缩进 → 它是父级映射的兄弟键 → 提升到 parent_indent
    for i, line in enumerate(fixed_lines):
        stripped = line.lstrip(' ')
        if stripped == '' or stripped.startswith('#') or stripped.startswith('- '):
            continue
        if i in block_content_lines:
            continue  # 块标量内容是纯文本，不参与对齐
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

        # 场景 B：最近的上方行是同缩进的列表项 → 当前行是父级映射的兄弟键
        if nearest_stripped.startswith('- ') and nearest_indent == indent:
            # 向上找到包含此列表的映射键（缩进 < nearest_indent 的非列表行）
            for j in range(nearest_above_idx - 1, -1, -1):
                prev = fixed_lines[j]
                if prev.strip() == '' or prev.strip().startswith('#'):
                    continue
                ps = prev.lstrip(' ')
                pi = len(prev) - len(ps)
                if not ps.startswith('- ') and pi < nearest_indent:
                    # ps 是映射键，当前行应与其同缩进
                    if indent != pi:
                        fixed_lines[i] = ' ' * pi + stripped
                        print(f"  [提升到映射键] L{i+1}: {indent} -> {pi}  | {stripped[:60]}")
                    break
            continue

        # 场景 C：最近的上方行是已有标量值的映射键 → 当前行不应是其子键，应提升到父级
        if (not nearest_stripped.startswith('- ')
                and nearest_indent < indent
                and MAPPING_KEY_WITH_VALUE_RE.match(nearest_stripped)):
            # 向上找到包含此映射键的父级（缩进 < nearest_indent 的非列表行）
            for j in range(nearest_above_idx - 1, -1, -1):
                prev = fixed_lines[j]
                if prev.strip() == '' or prev.strip().startswith('#'):
                    continue
                ps = prev.lstrip(' ')
                pi = len(prev) - len(ps)
                if pi < nearest_indent:
                    # 当前行应与 nearest_above 同缩进（兄弟键）
                    if indent != nearest_indent:
                        fixed_lines[i] = ' ' * nearest_indent + stripped
                        print(f"  [提升到映射键] L{i+1}: {indent} -> {nearest_indent}  | {stripped[:60]}")
                    break
            continue

        # 场景 A：最近的上方行是缩进更小的列表项 → 当前行是其子属性
        if nearest_stripped.startswith('- ') and nearest_indent < indent:
            correct_indent = nearest_indent + 2
            if indent != correct_indent:
                fixed_lines[i] = ' ' * correct_indent + stripped
                print(f"  [列表项内对齐] L{i+1}: {indent} -> {correct_indent}  | {stripped[:60]}")
            continue

        # 其他情况：最近的上方行是非列表行，继续向上找列表项
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
            continue

        parent_indent = len(fixed_lines[parent_list_idx]) - len(fixed_lines[parent_list_idx].lstrip(' '))
        if indent <= parent_indent:
            continue
        correct_indent = parent_indent + 2
        if indent != correct_indent:
            fixed_lines[i] = ' ' * correct_indent + stripped
            print(f"  [列表项内对齐] L{i+1}: {indent} -> {correct_indent}  | {stripped[:60]}")

    # 写回文件
    if fixed_lines == original_lines:
        print("✅ 无需修改，缩进已符合规范。")
        return
    

    output_path = output if output else filepath
    with open(output_path, 'w', encoding='utf-8') as f:
        for line in fixed_lines:
            f.write(line + '\n')
    print(f"📝 修复完毕，写入 {output_path}")

    # 验证
    try:
        import yaml
        with open(output_path, 'r', encoding='utf-8') as f:
            yaml.safe_load(f)
        print("✅ YAML 格式验证通过！")
    except ImportError:
        print("⚠️ 未安装 PyYAML，跳过格式验证。请执行：pip install pyyaml")
    except Exception as e:
        print(f"❌ 验证失败，仍存在格式错误: {e}")

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    in_file = sys.argv[1]
    out_file = sys.argv[2] if len(sys.argv) > 2 else None
    fix_yaml_indent(in_file, out_file)