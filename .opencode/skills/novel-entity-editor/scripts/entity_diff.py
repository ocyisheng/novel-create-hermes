"""entity_diff.py — 编辑前后 YAML 的语义化 diff 输出

用于 novel-entity-editor 技能，在编辑操作后输出变更摘要：
  - 仅展示有变化的字段（不输出整段 YAML）
  - 按模块分组（索引层/摘要层/完整档案）
  - 区分字段修改 vs 字段新增 vs 字段删除
  - 忽略 `_meta.updated_at` 等自动化字段

用法:
    python entity_diff.py <old.yaml> <new.yaml>
    python entity_diff.py <old.yaml> <new.yaml> --entity-type character
"""

import argparse
import sys
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:
    print("错误: 需要 PyYAML")
    sys.exit(1)


# ── 平坦化 ───────────────────────────────────────────────────────────────────

def flatten_dict(data: dict, prefix: str = "") -> dict[str, Any]:
    """将嵌套 dict 平坦化为点号路径格式"""
    result: dict[str, Any] = {}
    for key, value in data.items():
        path = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict):
            # 空 dict 保留为值
            if not value:
                result[path] = value
            else:
                result.update(flatten_dict(value, path))
        elif isinstance(value, list):
            # 列表按 JSON 字符串比较（语义化而非逐行）
            result[path] = _normalize_list(value)
        else:
            result[path] = value
    return result


def _normalize_list(lst: list) -> list:
    """规范化列表用于比较"""
    result = []
    for item in lst:
        if isinstance(item, dict):
            # 按 key 排序以保证一致性
            result.append({k: item[k] for k in sorted(item.keys())})
        else:
            result.append(item)
    return result


# ── Diff 生成 ─────────────────────────────────────────────────────────────────

IGNORE_PATTERNS = [
    "_meta.updated_at",
    "_meta.created_at",
]


def should_ignore(path: str) -> bool:
    return any(pat in path for pat in IGNORE_PATTERNS)


def generate_diff(
    old_data: dict, new_data: dict, entity_type: str | None = None
) -> dict:
    """生成结构化 diff

    Returns:
        {
            "modified": [{"field": "...", "before": ..., "after": ...}, ...],
            "added": [{"field": "...", "value": ...}, ...],
            "removed": [{"field": "...", "value": ...}, ...],
            "summary": "3 处修改, 1 处新增",
        }
    """
    old_flat = flatten_dict(old_data)
    new_flat = flatten_dict(new_data)

    modified = []
    added = []
    removed = []

    all_keys = set(old_flat.keys()) | set(new_flat.keys())

    for key in sorted(all_keys):
        if should_ignore(key):
            continue

        old_val = old_flat.get(key)
        new_val = new_flat.get(key)

        # 同时不存在（skip）
        if key not in old_flat and key not in new_flat:
            continue

        # 新增
        if key not in old_flat and key in new_flat:
            added.append({"field": key, "value": _format_value(new_val)})
            continue

        # 删除
        if key in old_flat and key not in new_flat:
            removed.append({"field": key, "value": _format_value(old_val)})
            continue

        # 修改
        if old_val != new_val:
            modified.append({
                "field": key,
                "before": _format_value(old_val),
                "after": _format_value(new_val),
            })

    # 按层级分组统计
    layer_map = {"_meta": [], "索引信息": [], "摘要": [],
                 "完整档案": [], "其他": []}
    for entry in modified + added + removed:
        field = entry.get("field", "")
        if field.startswith("_meta"):
            layer_map["_meta"].append(entry)
        elif field.startswith("索引信息"):
            layer_map["索引信息"].append(entry)
        elif field.startswith("摘要"):
            layer_map["摘要"].append(entry)
        elif field.startswith("完整档案"):
            layer_map["完整档案"].append(entry)
        else:
            layer_map["其他"].append(entry)

    change_count = len(modified) + len(added) + len(removed)
    parts = []
    if modified:
        parts.append(f"{len(modified)} 处修改")
    if added:
        parts.append(f"{len(added)} 处新增")
    if removed:
        parts.append(f"{len(removed)} 处删除")

    return {
        "modified": modified,
        "added": added,
        "removed": removed,
        "layer_stats": {k: len(v) for k, v in layer_map.items()},
        "summary": ", ".join(parts) if parts else "无变更",
        "total_changes": change_count,
    }


def _format_value(value: Any) -> str:
    """将值格式化为可读字符串"""
    if value is None:
        return "(空)"
    if isinstance(value, list):
        if len(value) > 5:
            return f"[{len(value)} 项] {str(value[:3])}..."
        return str(value)
    if isinstance(value, dict):
        if not value:
            return "{}"
        keys = list(value.keys())[:5]
        return "{" + ", ".join(keys) + "...}" if len(value) > 5 else str(value)
    s = str(value)
    if len(s) > 80:
        return s[:77] + "..."
    return s


# ── 输出 ─────────────────────────────────────────────────────────────────────

def print_diff_report(diff: dict) -> None:
    """打印人类可读的 diff 报告"""
    print("=" * 60)
    print(f"变更摘要: {diff['summary']}")
    print("=" * 60)

    # 按层级分组输出
    layer_order = ["_meta", "索引信息", "摘要", "完整档案", "其他"]
    layer_labels = {
        "_meta": "元信息", "索引信息": "索引层", "摘要": "摘要层",
        "完整档案": "完整档案", "其他": "其他",
    }

    for layer in layer_order:
        count = diff["layer_stats"].get(layer, 0)
        if count == 0:
            continue

        print(f"\n--- {layer_labels.get(layer, layer)} ({count}) ---")

        # 合并该层所有变更
        layer_entries = (
            [e for e in diff["modified"] if e["field"].startswith(layer)]
            + [e for e in diff["added"] if e["field"].startswith(layer)]
            + [e for e in diff["removed"] if e["field"].startswith(layer)]
        )

        for entry in layer_entries:
            field = entry["field"]
            short_field = field[len(layer) + 1:] if field.startswith(layer) else field

            if entry in diff["modified"]:
                print(f"  ✏️  {short_field}")
                print(f"     旧: {entry['before']}")
                print(f"     新: {entry['after']}")
            elif entry in diff["added"]:
                print(f"  ➕  {short_field}: {entry['value']}")
            elif entry in diff["removed"]:
                print(f"  ➖  {short_field}: {entry['value']}")

    print(f"\n{'=' * 60}")
    print(f"总计: {diff['total_changes']} 处变更")


# ── CLI ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        prog="entity_diff.py",
        description="YAML 实体编辑 diff 工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""示例:
  python entity_diff.py old.yaml new.yaml                    # 显示变更摘要
  python entity_diff.py old.yaml new.yaml --json             # JSON 格式输出
  python entity_diff.py old.yaml new.yaml -t character       # 指定实体类型过滤

说明:
  对比编辑前后的 YAML 实体文件，显示变更的字段和值。
  退出码: 0=无变更, 1=有变更"""
    )
    parser.add_argument("old_file", help="编辑前的 YAML 文件")
    parser.add_argument("new_file", help="编辑后的 YAML 文件")
    parser.add_argument("--entity-type", "-t", help="实体类型（可选，用于过滤）")
    parser.add_argument("--json", action="store_true", help="以 JSON 格式输出")
    args = parser.parse_args()

    old_path = Path(args.old_file)
    new_path = Path(args.new_file)

    if not old_path.exists():
        print(f"错误: 文件不存在: {old_path}", file=sys.stderr)
        sys.exit(1)
    if not new_path.exists():
        print(f"错误: 文件不存在: {new_path}", file=sys.stderr)
        sys.exit(1)

    with open(old_path, encoding="utf-8") as f:
        old_data = yaml.safe_load(f) or {}
    with open(new_path, encoding="utf-8") as f:
        new_data = yaml.safe_load(f) or {}

    diff = generate_diff(old_data, new_data, args.entity_type)

    if args.json:
        import json
        print(json.dumps(diff, ensure_ascii=False, indent=2))
    else:
        print_diff_report(diff)

    # exit code: 0=无变更, 1=有变更
    sys.exit(0 if diff["total_changes"] == 0 else 1)


if __name__ == "__main__":
    main()
