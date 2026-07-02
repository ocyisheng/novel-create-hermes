#!/usr/bin/env python3
"""
deviation_manager.py — 偏差状态管理器

管理 deviation_state.yaml 的生命周期：新增、合并、解决、保留、展示过滤。
与 project_graph.py 配合使用，依赖 graph 的 entity_id + field_path 作为唯一 key。

用法:
    # 合并新偏差（align 运行后调用）
    python deviation_manager.py --project-root NOVELS_ROOT/项目名 merge \\
        --new-deviations <新偏差 YAML 文件路径>

    # 解决一个偏差（用户确认修正后调用）
    python deviation_manager.py --project-root NOVELS_ROOT/项目名 resolve \\
        --dev-id dev_20260701_001 --resolved-by user_correction

    # 自动解决（编辑后处理链调用，C2）
    python deviation_manager.py --project-root NOVELS_ROOT/项目名 auto-resolve \\
        --entity-path "characters/林昭.yaml"

    # 用户保留一个偏差
    python deviation_manager.py --project-root NOVELS_ROOT/项目名 retain \\
        --dev-id dev_20260701_001 --user-statement "这就是我想要的人设"

    # 获取待呈现的偏差列表（应用 B1 频次控制）
    python deviation_manager.py --project-root NOVELS_ROOT/项目名 filter-for-presentation

    # 获取待处理数量
    python deviation_manager.py --project-root NOVELS_ROOT/项目名 pending-count

依赖: Python 3, PyYAML
"""

import argparse
import sys
from datetime import datetime, timedelta
from pathlib import Path

try:
    import yaml
except ImportError:
    print("错误: 需要 PyYAML，请运行 novel-env-setup 安装依赖", file=sys.stderr)
    sys.exit(1)

from _utils import load_yaml, load_yaml_safe, save_yaml


# ── 常量 ─────────────────────────────────────────────────────────────────────

GRAPH_DIR_NAME = "graph"
GRAPH_RELATIVE_PATH = Path("relation") / GRAPH_DIR_NAME
FILE_DEVIATIONS = "02_deviation_state.yaml"

# B1 频次控制阈值
MAX_SHOW_COUNT = 2          # 同一偏差最多展示 N 次（之后折叠）
MIN_DAYS_BETWEEN_SHOWS = 3  # 距上次展示不到 N 天不重复展示

# 状态枚举
STATUS_PENDING = "pending"
STATUS_RESOLVED = "resolved"
STATUS_USER_RETAINED = "user_retained"


# ── 路径工具 ─────────────────────────────────────────────────────────────────

def get_graph_dir(project_root: Path) -> Path:
    """返回 graph/ 目录路径。"""
    return project_root / GRAPH_RELATIVE_PATH


def get_deviations_path(graph_dir: Path) -> Path:
    """返回 deviation_state.yaml 路径。"""
    return graph_dir / FILE_DEVIATIONS


# ── 状态管理核心 ─────────────────────────────────────────────────────────────

def default_state() -> dict:
    """返回空的偏差状态结构。"""
    return {
        "version": 1,
        "last_updated": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        "summary": {
            "total_tracked": 0,
            "resolved": 0,
            "pending": 0,
            "user_retained": 0,
        },
        "items": [],
    }


def load_state(project_root: Path) -> dict:
    """加载偏差状态文件，不存在则返回默认结构。"""
    graph_dir = get_graph_dir(project_root)
    path = get_deviations_path(graph_dir)
    data = load_yaml_safe(path)
    if data:
        return data
    return default_state()


def save_state(project_root: Path, state: dict) -> None:
    """保存偏差状态文件。"""
    graph_dir = get_graph_dir(project_root)
    graph_dir.mkdir(parents=True, exist_ok=True)
    path = get_deviations_path(graph_dir)

    # 更新汇总
    items = state.get("items", [])
    resolved = sum(1 for i in items if i.get("status") == STATUS_RESOLVED)
    pending = sum(1 for i in items if i.get("status") == STATUS_PENDING)
    retained = sum(1 for i in items if i.get("status") == STATUS_USER_RETAINED)
    state["summary"] = {
        "total_tracked": len(items),
        "resolved": resolved,
        "pending": pending,
        "user_retained": retained,
    }
    state["last_updated"] = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")

    save_yaml(path, state)


def _next_dev_id(state: dict) -> str:
    """生成下一个自增偏差 ID。"""
    today = datetime.now().strftime("%Y%m%d")
    existing = [
        int(i.get("id", "").split("_")[-1])
        for i in state.get("items", [])
        if i.get("id", "").startswith(f"dev_{today}")
    ]
    seq = max(existing) + 1 if existing else 1
    return f"dev_{today}_{seq:03d}"


def _find_item(state: dict, entity_id: str, field_path: str) -> int | None:
    """按 entity_id + field_path 查找偏差项，返回索引。"""
    for idx, item in enumerate(state.get("items", [])):
        if item.get("entity_id") == entity_id and item.get("field_path") == field_path:
            return idx
    return None


# ── 合并新偏差 ───────────────────────────────────────────────────────────────

def merge_deviations(project_root: Path, new_deviations: list[dict]) -> dict:
    """将新的偏差检测结果合并到状态文件中。

    Args:
        project_root: 项目根目录
        new_deviations: [{entity_id, field_path, dimension, expected, actual, suggested_changeset, ...}]

    Returns:
        更新后的完整状态
    """
    state = load_state(project_root)
    now = datetime.now()
    now_str = now.strftime("%Y-%m-%dT%H:%M:%S")

    for new_dev in new_deviations:
        entity_id = new_dev.get("entity_id", "")
        field_path = new_dev.get("field_path", "")

        if not entity_id or not field_path:
            continue

        idx = _find_item(state, entity_id, field_path)

        if idx is not None:
            # 已存在条目
            existing = state["items"][idx]
            existing_status = existing.get("status")

            if existing_status == STATUS_RESOLVED:
                # 已解决：检查 content_hash（通过 graph）是否需要重新评估
                # 如果 field_path 对应的值没变，跳过
                if new_dev.get("content_hash_changed", False):
                    # 文件改了，可能需要重新评估
                    existing["status"] = STATUS_PENDING
                    existing["actual_before"] = existing.get("actual_now", "")
                    existing["actual_now"] = new_dev.get("actual", "")
                    existing["detection_count"] = existing.get("detection_count", 0) + 1
                    existing["last_presented"] = existing.get("last_presented", "")
                    existing_changeset = existing.get("suggested_changeset")
                    if not existing_changeset and new_dev.get("suggested_changeset"):
                        existing["suggested_changeset"] = new_dev["suggested_changeset"]

            elif existing_status == STATUS_USER_RETAINED:
                # 用户保留：跳过，不更新计数
                pass

            else:
                # Pending：更新计数和值
                existing["detection_count"] = existing.get("detection_count", 0) + 1
                if new_dev.get("actual"):
                    existing["actual_now"] = new_dev["actual"]
                # 如果之前没有变更集，现在有了则补上
                if not existing.get("suggested_changeset") and new_dev.get("suggested_changeset"):
                    existing["suggested_changeset"] = new_dev["suggested_changeset"]

        else:
            # 新偏差条目
            dev_id = _next_dev_id(state)
            item = {
                "id": dev_id,
                "entity_id": entity_id,
                "field_path": field_path,
                "dimension": new_dev.get("dimension", "unknown"),
                "status": STATUS_PENDING,

                "expected": new_dev.get("expected", ""),
                "actual_before": "",
                "actual_now": new_dev.get("actual", ""),

                "suggested_changeset": new_dev.get("suggested_changeset"),

                "first_detected": now_str,
                "detection_count": 1,
                "last_presented": "",

                "intent_log_ref": new_dev.get("intent_log_ref", ""),
                "related_deviations": new_dev.get("related_deviations", []),
            }
            state["items"].append(item)

    save_state(project_root, state)
    return state


# ── 解决偏差 ─────────────────────────────────────────────────────────────────

def resolve_deviation(
    project_root: Path,
    dev_id: str,
    resolved_by: str = "user_correction",
) -> dict | None:
    """标记一个偏差为已解决。

    Args:
        project_root: 项目根目录
        dev_id: 偏差 ID
        resolved_by: user_correction | cascade_auto | user_retained

    Returns:
        更新后的条目，未找到返回 None
    """
    state = load_state(project_root)
    now_str = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")

    for item in state.get("items", []):
        if item.get("id") == dev_id:
            item["status"] = STATUS_RESOLVED
            item["resolved_by"] = resolved_by
            item["resolved_at"] = now_str
            save_state(project_root, state)
            return item

    print(f"警告: 未找到偏差 {dev_id}", file=sys.stderr)
    return None


def retain_deviation(
    project_root: Path,
    dev_id: str,
    user_statement: str,
) -> dict | None:
    """标记一个偏差为用户保留（不再提醒）。

    Args:
        project_root: 项目根目录
        dev_id: 偏差 ID
        user_statement: 用户原话

    Returns:
        更新后的条目，未找到返回 None
    """
    state = load_state(project_root)
    now_str = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")

    for item in state.get("items", []):
        if item.get("id") == dev_id:
            item["status"] = STATUS_USER_RETAINED
            item["user_statement"] = user_statement
            item["retained_at"] = now_str
            save_state(project_root, state)
            return item

    print(f"警告: 未找到偏差 {dev_id}", file=sys.stderr)
    return None


# ── 自动解决（C2）────────────────────────────────────────────────────────────

def auto_resolve(project_root: Path, entity_path: str) -> list[dict]:
    """编辑后自动检查并解决偏差（C2 方案）。

    逻辑: 读取刚刚被编辑的实体文件 → 提取各字段值
    → 与 deviation_state 中该实体的所有 pending 条目的 expected 值对比
    → 匹配上则标记为 resolved

    Args:
        project_root: 项目根目录
        entity_path: 相对于项目根目录的实体文件路径

    Returns:
        被自动解决的偏差列表
    """
    state = load_state(project_root)
    file_path = project_root / entity_path
    if not file_path.is_file():
        return []

    # 读取编辑后的文件
    data = load_yaml_safe(file_path)
    if not data:
        return []

    # 获取该文件对应的实体 ID
    # 尝试从文件内容中提取
    entity_id = ""
    entity_id = data.get("索引信息", {}).get("实体ID", "")
    if not entity_id:
        entity_id = data.get("基本信息", {}).get("实体ID", "")
    if not entity_id:
        entity_id = data.get("id", "")
    if not entity_id:
        # 用文件名（去掉后缀）作为 fallback
        entity_id = f"unknown_{file_path.stem}"

    resolved_ids: list[str] = []
    now_str = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")

    for item in state.get("items", []):
        if item.get("entity_id") != entity_id:
            continue
        if item.get("status") != STATUS_PENDING:
            continue

        field_path = item.get("field_path", "")
        expected = item.get("expected", "")
        if not field_path or not expected:
            continue

        # 按 field_path 从 data 中提取当前值
        actual_value = _get_field_value(data, field_path)

        # 如果当前值与 expected 匹配，或者 changeset 已应用
        if actual_value is not None and _values_match(actual_value, expected):
            item["status"] = STATUS_RESOLVED
            item["resolved_by"] = "cascade_auto"
            item["resolved_at"] = now_str
            item["actual_now"] = str(actual_value)
            resolved_ids.append(item.get("id", ""))

    if resolved_ids:
        save_state(project_root, state)

    return resolved_ids


def _deep_search_key(data, target_key: str, max_depth: int = 6) -> str | None:
    """深度递归搜索数据，查找第一个匹配 target_key 的值（字符串）。
    
    agent 生成的 YAML 字段路径可能不按模板，这个 fallback 做最大努力查找。
    """
    if max_depth <= 0:
        return None

    if isinstance(data, dict):
        # 当前层匹配
        if target_key in data:
            val = data[target_key]
            if isinstance(val, str):
                return val
            if isinstance(val, (int, float)):
                return str(val)
        # 递归子层
        for v in data.values():
            result = _deep_search_key(v, target_key, max_depth - 1)
            if result is not None:
                return result

    elif isinstance(data, list):
        for item in data:
            result = _deep_search_key(item, target_key, max_depth - 1)
            if result is not None:
                return result

    return None


def _get_field_value(data: dict | list, field_path: str):
    """按点号路径从嵌套数据中提取值。
    
    策略：
    1. 精确路径导航（标准模板结构）
    2. 精确路径失败 → 递归搜索最后一级 key（agent 非常规结构）
    """
    if not field_path:
        return None

    # 去掉已知前缀
    stripped = field_path
    for prefix in ["完整档案.", "索引信息.", "基本信息."]:
        if stripped.startswith(prefix):
            stripped = stripped[len(prefix):]
            break

    keys = stripped.split(".")
    current = data

    # 策略 1: 精确路径导航
    for key in keys:
        if isinstance(current, dict):
            current = current.get(key)
        elif isinstance(current, list):
            try:
                idx = int(key)
                if 0 <= idx < len(current):
                    current = current[idx]
                else:
                    current = None
                    break
            except (ValueError, IndexError):
                current = None
                break
        else:
            current = None
            break

    if current is not None:
        return _normalize_value(current)

    # 策略 2: 递归搜索最后一级 key
    last_key = keys[-1]
    found = _deep_search_key(data, last_key)
    return _normalize_value(found) if found else None


def _normalize_value(val):
    """统一值为可比较的字符串。"""
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return str(val)
    if isinstance(val, str):
        return val
    if isinstance(val, list):
        return ", ".join(str(v) for v in val)
    if isinstance(val, dict):
        # 提取所有字符串值拼接
        parts = []
        for v in val.values():
            if isinstance(v, str):
                parts.append(v)
            elif isinstance(v, (int, float)):
                parts.append(str(v))
        return ", ".join(parts) if parts else str(val)
    return str(val)


def _strip_punctuation(s: str) -> str:
    """去掉常见标点和前后空白。"""
    import re
    return re.sub(r'[，。！？、；：,.!?;:\s"\']', '', s).strip()


def _values_match(actual, expected) -> bool:
    """比较两个值是否匹配（逐步松弛）。
    
    严格 -> 去标点 -> 子串包含（应对 agent 添加额外描述）。
    """
    if actual is None and expected is None:
        return True
    if actual is None or expected is None:
        return False

    a = str(actual).strip()
    e = str(expected).strip()

    # 1. 精确匹配
    if a == e:
        return True

    # 2. 去标点后匹配
    a_clean = _strip_punctuation(a)
    e_clean = _strip_punctuation(e)
    if a_clean == e_clean:
        return True

    # 3. 子串匹配（一方完整包含另一方，长度差不大）
    if len(a_clean) >= 2 and len(e_clean) >= 2:
        if a_clean in e_clean or e_clean in a_clean:
            longer = max(len(a_clean), len(e_clean))
            shorter = min(len(a_clean), len(e_clean))
            # 短串至少是长串的一半
            if shorter / longer >= 0.5:
                return True

    return False


# ── 展示过滤（B1 频次控制）────────────────────────────────────────────────

def filter_for_presentation(project_root: Path) -> dict:
    """获取待呈现的偏差列表（应用 B1 频次控制）。

    规则:
        - resolved + user_retained → 跳过（脚注注明）
        - pending + detection_count > MAX_SHOW_COUNT
           且距 last_presented < MIN_DAYS_BETWEEN_SHOWS 天
           → 折叠到"另有 N 项未处理的旧偏差"
        - 其他 pending → 正常展示

    Returns:
        {
            "show": [偏差项列表],         # 需要展示的
            "folded_count": int,          # 折叠的旧偏差数
            "skipped_resolved": int,      # 已解决的
            "skipped_retained": int,      # 用户保留的
        }
    """
    state = load_state(project_root)
    now = datetime.now()

    show: list[dict] = []
    folded_count = 0
    skipped_resolved = 0
    skipped_retained = 0

    for item in state.get("items", []):
        status = item.get("status", "")

        if status == STATUS_RESOLVED:
            skipped_resolved += 1
            continue

        if status == STATUS_USER_RETAINED:
            skipped_retained += 1
            continue

        # Pending：应用 B1 控制
        detection_count = item.get("detection_count", 1)
        last_presented_str = item.get("last_presented", "")

        should_show = True
        if detection_count > MAX_SHOW_COUNT and last_presented_str:
            try:
                last_date = datetime.strptime(
                    last_presented_str.split("T")[0], "%Y-%m-%d"
                )
                days_since = (now - last_date).days
                if days_since < MIN_DAYS_BETWEEN_SHOWS:
                    should_show = False
            except (ValueError, IndexError):
                pass

        if should_show:
            show.append(item)
        else:
            folded_count += 1

    return {
        "show": show,
        "folded_count": folded_count,
        "skipped_resolved": skipped_resolved,
        "skipped_retained": skipped_retained,
    }


# ── 快捷查询 ─────────────────────────────────────────────────────────────────

def get_pending_count(project_root: Path) -> int:
    """快速获取待处理偏差数量。"""
    state = load_state(project_root)
    return state.get("summary", {}).get("pending", 0)


def mark_presented(project_root: Path, dev_ids: list[str]) -> None:
    """将指定偏差标记为"已展示"。"""
    state = load_state(project_root)
    now_str = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    updated = False

    for item in state.get("items", []):
        if item.get("id") in dev_ids:
            item["last_presented"] = now_str
            updated = True

    if updated:
        save_state(project_root, state)


# ── 批量解析新偏差 ──────────────────────────────────────────────────────────

def parse_new_deviations(yaml_file: str) -> list[dict]:
    """从 YAML 文件读取新偏差列表。"""
    path = Path(yaml_file)
    if not path.is_file():
        print(f"错误: 文件不存在: {yaml_file}", file=sys.stderr)
        sys.exit(1)

    data = load_yaml_safe(path)
    if not data:
        return []

    # 支持两种格式：
    # 1. 直接是列表：[{entity_id, field_path, ...}, ...]
    # 2. 有 deviations 键：{"deviations": [...], "summary": {...}}
    if isinstance(data, list):
        return data
    elif isinstance(data, dict):
        return data.get("deviations", data.get("items", []))
    return []


# ── CLI ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="deviation_manager.py — 偏差状态管理器",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用示例:
  # 合并新偏差
  python deviation_manager.py --project-root novels/项目名 merge \\
      --new-deviations /tmp/new_deviations.yaml

  # 解决偏差
  python deviation_manager.py --project-root novels/项目名 resolve \\
      --dev-id dev_20260701_001 --resolved-by user_correction

  # 自动解决
  python deviation_manager.py --project-root novels/项目名 auto-resolve \\
      --entity-path "characters/林昭.yaml"

  # 用户保留
  python deviation_manager.py --project-root novels/项目名 retain \\
      --dev-id dev_20260701_001 --user-statement "这就是我想要的人设"

  # 获取展示列表
  python deviation_manager.py --project-root novels/项目名 filter-for-presentation

  # 待处理数量
  python deviation_manager.py --project-root novels/项目名 pending-count
        """,
    )
    parser.add_argument("--project-root", "-p", required=True, help="项目根目录")
    parser.add_argument("command", choices=[
        "merge", "resolve", "auto-resolve", "retain",
        "filter-for-presentation", "pending-count",
    ], help="操作命令")
    parser.add_argument("--new-deviations", help="新偏差 YAML 文件路径（merge 命令）")
    parser.add_argument("--dev-id", help="偏差 ID（resolve/retain 命令）")
    parser.add_argument("--resolved-by", default="user_correction",
                        choices=["user_correction", "cascade_auto"],
                        help="解决方式")
    parser.add_argument("--entity-path", help="实体文件路径（auto-resolve 命令）")
    parser.add_argument("--user-statement", help="用户保留原因（retain 命令）")
    args = parser.parse_args()

    project_root = Path(args.project_root).resolve()

    # 尝试解析项目根
    from _utils import find_project_root_or_none
    if not project_root.is_dir():
        found = find_project_root_or_none(project_root)
        if found:
            project_root = found
        else:
            print(f"错误: 项目根目录不存在: {project_root}", file=sys.stderr)
            sys.exit(1)

    if args.command == "merge":
        if not args.new_deviations:
            print("错误: --new-deviations 是必填参数", file=sys.stderr)
            sys.exit(1)
        new_devs = parse_new_deviations(args.new_deviations)
        state = merge_deviations(project_root, new_devs)
        pending = state.get("summary", {}).get("pending", 0)
        print(f"✅ 合并完成: 新增/更新 {len(new_devs)} 条偏差")
        print(f"   当前待处理: {pending} 条")

    elif args.command == "resolve":
        if not args.dev_id:
            print("错误: --dev-id 是必填参数", file=sys.stderr)
            sys.exit(1)
        result = resolve_deviation(project_root, args.dev_id, args.resolved_by)
        if result:
            print(f"✅ 已解决: {args.dev_id}")
            print(f"   解决方式: {args.resolved_by}")

    elif args.command == "auto-resolve":
        if not args.entity_path:
            print("错误: --entity-path 是必填参数", file=sys.stderr)
            sys.exit(1)
        resolved = auto_resolve(project_root, args.entity_path)
        if resolved:
            print(f"✅ 自动解决 {len(resolved)} 条偏差:")
            for dev_id in resolved:
                print(f"   - {dev_id}")
        else:
            print("ℹ️  没有可自动解决的偏差")

    elif args.command == "retain":
        if not args.dev_id or not args.user_statement:
            print("错误: --dev-id 和 --user-statement 是必填参数", file=sys.stderr)
            sys.exit(1)
        result = retain_deviation(project_root, args.dev_id, args.user_statement)
        if result:
            print(f"✅ 已标记为保留: {args.dev_id}")
            print(f"   用户原话: {args.user_statement}")

    elif args.command == "filter-for-presentation":
        result = filter_for_presentation(project_root)
        result["project_root"] = str(project_root)
        print(yaml.dump(result, allow_unicode=True, default_flow_style=False, sort_keys=False))

    elif args.command == "pending-count":
        count = get_pending_count(project_root)
        print(count)


if __name__ == "__main__":
    main()
