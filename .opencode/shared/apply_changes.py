#!/usr/bin/env python3
"""
apply_changes.py — 变更集应用引擎

确定性应用变更集（Change Set）到 YAML 实体文件。
不涉及任何 AI 调用，100% 确定性。

用法:
    python apply_changes.py --file <YAML路径> --changes '<JSON>'
    python apply_changes.py --file <YAML路径> --changes '<JSON>' --dry-run
    echo '<JSON>' | python apply_changes.py --file <YAML路径>
"""

import argparse
import json
import shutil
import sys
from copy import deepcopy
from pathlib import Path

import yaml


# ========== 嵌套路径工具 ==========

def get_nested(obj, keys):
    """沿 keys 列表向下导航到目标值的父容器和最后一个 key。"""
    current = obj
    for key in keys[:-1]:
        if isinstance(current, dict):
            current = current.get(key)
        elif isinstance(current, list):
            try:
                current = current[int(key)]
            except (ValueError, IndexError):
                return None, None
        else:
            return None, None
        if current is None:
            return None, None
    return current, keys[-1]


# ========== 变更操作实现 ==========

def op_replace(data, change):
    """替换字段值，验证 old_value 匹配。"""
    path = change["path"]
    keys = path.split(".")
    parent, last_key = get_nested(data, keys)
    if parent is None or last_key not in parent:
        return {"status": "error", "code": "PATH_NOT_FOUND",
                "message": f"路径 '{path}' 不存在"}
    current_val = parent[last_key]
    old_val = change.get("old_value")
    if old_val is not None and current_val != old_val:
        return {"status": "error", "code": "CONFLICT",
                "message": f"字段 '{path}' 的当前值不匹配预期: "
                           f"当前={repr(current_val)}, 预期={repr(old_val)}"}
    parent[last_key] = change["new_value"]
    return {"status": "ok"}


def op_add(data, change):
    """新增字段。"""
    path = change["path"]
    keys = path.split(".")
    parent, last_key = get_nested(data, keys)
    if parent is None:
        return {"status": "error", "code": "PATH_NOT_FOUND",
                "message": f"路径 '{path}' 的父级不存在"}
    if isinstance(parent, dict) and last_key in parent:
        return {"status": "error", "code": "FIELD_EXISTS",
                "message": f"字段 '{path}' 已存在，如需替换请用 replace 操作"}
    if isinstance(parent, dict):
        parent[last_key] = change["value"]
    elif isinstance(parent, list):
        parent.insert(int(last_key) if last_key.isdigit() else len(parent), change["value"])
    return {"status": "ok"}


def op_remove(data, change):
    """删除字段或列表项。"""
    path = change["path"]
    keys = path.split(".")
    parent, last_key = get_nested(data, keys)
    if parent is None or (isinstance(parent, dict) and last_key not in parent):
        return {"status": "error", "code": "PATH_NOT_FOUND",
                "message": f"路径 '{path}' 不存在"}
    if isinstance(parent, dict):
        del parent[last_key]
    elif isinstance(parent, list):
        try:
            parent.pop(int(last_key))
        except IndexError:
            return {"status": "error", "code": "INDEX_OUT_OF_RANGE",
                    "message": f"列表索引 {last_key} 超出范围"}
    return {"status": "ok"}


def op_add_to_list(data, change):
    """向列表追加或插入元素。"""
    path = change["path"]
    keys = path.split(".")
    parent, last_key = get_nested(data, keys)
    if parent is None or last_key not in parent:
        return {"status": "error", "code": "PATH_NOT_FOUND",
                "message": f"路径 '{path}' 不存在"}
    lst = parent[last_key]
    if not isinstance(lst, list):
        return {"status": "error", "code": "NOT_A_LIST",
                "message": f"路径 '{path}' 不是列表类型"}
    pos = change.get("position", len(lst))
    lst.insert(pos, change["value"])
    return {"status": "ok"}


def op_remove_from_list(data, change):
    """从列表删除指定索引的元素。"""
    path = change["path"]
    keys = path.split(".")
    parent, last_key = get_nested(data, keys)
    if parent is None or last_key not in parent:
        return {"status": "error", "code": "PATH_NOT_FOUND",
                "message": f"路径 '{path}' 不存在"}
    lst = parent[last_key]
    if not isinstance(lst, list):
        return {"status": "error", "code": "NOT_A_LIST",
                "message": f"路径 '{path}' 不是列表类型"}
    try:
        lst.pop(change["index"])
    except IndexError:
        return {"status": "error", "code": "INDEX_OUT_OF_RANGE",
                "message": f"列表索引 {change['index']} 超出范围 (长度 {len(lst)})"}
    return {"status": "ok"}


OPERATIONS = {
    "replace": op_replace,
    "add": op_add,
    "remove": op_remove,
    "add_to_list": op_add_to_list,
    "remove_from_list": op_remove_from_list,
}


def apply_changes(data, changes_list):
    """按顺序应用变更。返回 (成功列表, 失败列表)。"""
    successes = []
    failures = []
    for i, change in enumerate(changes_list):
        op = change.get("op")
        if op not in OPERATIONS:
            failures.append({"index": i, "change": change,
                             "error": f"不支持的操作: {op}"})
            continue
        result = OPERATIONS[op](data, change)
        if result["status"] == "ok":
            successes.append({"index": i, "path": change.get("path")})
        else:
            result["index"] = i
            result["change"] = change
            failures.append(result)
    return successes, failures


def load_yaml(file_path):
    """安全加载 YAML 文件。"""
    with open(file_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def dump_yaml(file_path, data):
    """写出 YAML 文件（保持键顺序，支持中文）。"""
    with open(file_path, "w", encoding="utf-8") as f:
        yaml.dump(data, f, allow_unicode=True, sort_keys=False, default_flow_style=False)


# ========== CLI ==========

def parse_args():
    parser = argparse.ArgumentParser(
        description="确定性应用变更集到 YAML 实体文件",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python apply_changes.py --file characters/韩鸣.yaml --changes '{"changes": [{"op": "replace", "path": "性格.核心特质", "old_value": "隐忍谨慎", "new_value": "杀伐果断"}]}'
  python apply_changes.py --file characters/韩鸣.yaml --changes @changes.json
  echo '{"changes":...}' | python apply_changes.py --file characters/韩鸣.yaml
        """,
    )
    parser.add_argument("--file", "-f", required=True, help="目标 YAML 文件路径")
    parser.add_argument("--changes", help="变更集 JSON（支持 @file.json 语法从文件读取）")
    parser.add_argument("--dry-run", "-n", action="store_true", help="只显示变更结果，不写文件")
    parser.add_argument("--no-backup", action="store_true", help="不创建 .bak 备份")
    return parser.parse_args()


def main():
    args = parse_args()
    file_path = Path(args.file)

    if not file_path.exists():
        print(json.dumps({"status": "error", "code": "FILE_NOT_FOUND",
                          "message": f"文件不存在: {file_path}"}))
        sys.exit(3)

    # 读取变更集
    changes_str = args.changes
    if not changes_str and not sys.stdin.isatty():
        changes_str = sys.stdin.read().strip()
    if not changes_str:
        print(json.dumps({"status": "error", "code": "NO_CHANGES",
                          "message": "未提供变更集"}))
        sys.exit(3)

    # 支持 @file.json 语法
    if changes_str.startswith("@"):
        ref_path = Path(changes_str[1:])
        if not ref_path.exists():
            # 尝试相对 shared 目录
            ref_path = Path(__file__).parent / changes_str[1:]
        changes_str = ref_path.read_text(encoding="utf-8")

    try:
        change_set = json.loads(changes_str)
    except json.JSONDecodeError as e:
        print(json.dumps({"status": "error", "code": "JSON_PARSE_ERROR",
                          "message": f"JSON 解析错误: {e}"}))
        sys.exit(3)

    changes_list = change_set.get("changes", [])
    if not changes_list:
        print(json.dumps({"status": "error", "code": "EMPTY_CHANGES",
                          "message": "变更集为空"}))
        sys.exit(3)

    # 加载原始数据
    original_data = load_yaml(file_path)
    working_data = deepcopy(original_data)

    # 应用变更
    successes, failures = apply_changes(working_data, changes_list)

    # 构建结果
    result = {
        "status": "ok" if not failures else "partial",
        "file": str(file_path),
        "changes_requested": len(changes_list),
        "changes_applied": len(successes),
        "changes_failed": len(failures),
        "backup": None,
        "summary": change_set.get("summary", ""),
        "details": {
            "applied": successes,
            "failed": failures,
        }
    }

    if failures:
        result["status"] = "partial"

    if args.dry_run:
        # 展示 diff
        print(f"--- {file_path}")
        print(f"+++ (dry-run)")
        applied_paths = {s["path"] for s in successes if "path" in s}
        for s in successes:
            p = s.get("path", f"#[{s['index']}]")
            print(f"  ~ {p}")
        for f in failures:
            p = f.get("change", {}).get("path", f"#[{f['index']}]")
            print(f"  ! {p}: {f['message']}")
        print(json.dumps(result, ensure_ascii=False, indent=2))
        sys.exit(0 if not failures else 1)

    # 写入
    if not args.no_backup:
        backup_path = file_path.with_suffix(file_path.suffix + ".bak")
        shutil.copy2(file_path, backup_path)
        result["backup"] = str(backup_path)

    dump_yaml(file_path, working_data)
    print(json.dumps(result, ensure_ascii=False, indent=2))

    # 退出码
    if failures:
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
