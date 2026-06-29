#!/usr/bin/env python3
"""
update_intent_log.py — 意图日志持久化

在编辑完成后记录用户意图和变更集，供后续编辑参考。
变更集 JSON 直接作为日志内容，无需解析自然语言摘要。

用法:
    python update_intent_log.py --project-root <路径> --entity-path <相对路径> \\
        --user-request <字符串> --change-set '<变更集 JSON>' --status pending
    python update_intent_log.py --project-root <路径> --entity-path <相对路径> \\
        --user-request <字符串> --change-set <@changeset.json> --status confirmed
"""

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path

import yaml


# ========== 工具函数 ==========

def entity_key_from_path(entity_path: str) -> str:
    """将实体文件路径转换为安全的 key：characters/韩鸣.yaml → characters_韩鸣。"""
    # 去掉 .yaml 后缀
    key = entity_path
    if key.endswith(".yaml"):
        key = key[:-5]
    # 替换路径分隔符
    key = key.replace("\\", "_").replace("/", "_")
    # 移除不安全字符
    key = re.sub(r'[^\w\u4e00-\u9fff_-]', '_', key)
    return key


def read_log(log_path: Path) -> dict:
    """读取已有的意图日志文件，不存在则返回空结构。"""
    if log_path.exists():
        with open(log_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or default_log()
    return default_log()


def default_log() -> dict:
    """返回默认的日志结构。"""
    return {
        "_meta": {
            "entity_path": "",
            "created_at": "",
            "last_updated": "",
            "total_rounds": 0,
        },
        "rounds": [],
        "current_direction": [],
        "overwritten_intents": [],
    }


def extract_current_direction(rounds: list) -> tuple:
    """从所有 confirmed rounds 中提取当前存活方向和被覆盖历史。

    规则：同字段路径以最新 round 为准，旧 round 入 overwritten。
    """
    field_latest = {}   # field → round_index (in rounds list)
    field_details = {}  # field → (round_number, user_request, summary)

    for i, r in enumerate(rounds):
        if r.get("status") != "confirmed_by_user":
            continue
        modified_fields = _extract_modified_paths(r.get("change_set", {}))
        for field in modified_fields:
            if field in field_latest:
                # 旧值入 overwritten（稍后处理）
                pass
            field_latest[field] = i
            field_details[field] = (r.get("round"), r.get("user_request", ""),
                                    r.get("change_set", {}).get("summary", ""))

    # 生成 current_direction 描述
    current = []
    for field, (round_num, req, summary) in field_details.items():
        short_field = field.split(".")[-1]
        desc = f"{field}: {summary[:60] if summary else req[:30]}"
        current.append(desc)

    # 生成 overwritten
    overwritten = []
    for i, r in enumerate(rounds):
        if r.get("status") != "confirmed_by_user":
            continue
        modified_fields = _extract_modified_paths(r.get("change_set", {}))
        r_num = r.get("round", i + 1)
        for field in modified_fields:
            latest_idx = field_latest.get(field)
            if latest_idx is not None and latest_idx != i:
                latest_r = rounds[latest_idx]
                overwritten.append({
                    "round": r_num,
                    "field": field,
                    "overwritten_by_round": latest_r.get("round", latest_idx + 1),
                    "reason": f"被第{latest_r.get('round', latest_idx + 1)}轮编辑覆盖",
                })

    return current, overwritten


def _extract_modified_paths(change_set: dict) -> list:
    """从变更集中提取所有被修改的字段路径。"""
    paths = []
    for change in change_set.get("changes", []):
        path = change.get("path")
        if path:
            paths.append(path)
    return paths


# ========== 主逻辑 ==========

def parse_args():
    parser = argparse.ArgumentParser(description="意图日志持久化")
    parser.add_argument("--project-root", "-p", required=True, help="项目根目录")
    parser.add_argument("--entity-path", required=True, help="实体文件相对路径，如 characters/韩鸣.yaml")
    parser.add_argument("--user-request", required=True, help="用户的原始修改请求")
    parser.add_argument("--change-set", required=True, help="变更集 JSON（支持 @file.json 语法）")
    parser.add_argument("--status", required=True,
                        choices=["pending", "confirmed_by_user", "rejected"],
                        help="当前状态")
    return parser.parse_args()


def main():
    args = parse_args()
    project_root = Path(args.project_root)
    entity_path = args.entity_path
    user_request = args.user_request
    status = args.status

    # 读取变更集
    changes_str = args.change_set
    if changes_str.startswith("@"):
        ref_path = Path(changes_str[1:])
        if not ref_path.exists():
            ref_path = project_root / changes_str[1:]
            if not ref_path.exists():
                # 尝试 shared 目录
                ref_path = Path(__file__).parent / changes_str[1:]
        if ref_path.exists():
            changes_str = ref_path.read_text(encoding="utf-8")
        else:
            print(json.dumps({"status": "error", "message": f"变更集文件不存在: {changes_str}"}))
            sys.exit(1)

    try:
        change_set = json.loads(changes_str)
    except json.JSONDecodeError as e:
        print(json.dumps({"status": "error", "message": f"变更集 JSON 解析错误: {e}"}))
        sys.exit(1)

    # 构建路径
    entity_key = entity_key_from_path(entity_path)
    intent_dir = project_root / "outline" / "追踪" / "intent"
    intent_dir.mkdir(parents=True, exist_ok=True)
    log_path = intent_dir / f"{entity_key}.intent.yaml"

    # 读取或初始化日志
    log = read_log(log_path)
    now = datetime.now().isoformat(timespec="seconds")

    # 初始化 _meta
    if not log["_meta"]["entity_path"]:
        log["_meta"]["entity_path"] = entity_path
        log["_meta"]["created_at"] = now
    log["_meta"]["last_updated"] = now
    log["_meta"]["total_rounds"] = len(log["rounds"]) + 1

    # 追加新 round
    new_round = {
        "round": len(log["rounds"]) + 1,
        "date": now,
        "user_request": user_request,
        "change_set": change_set,
        "status": status,
    }
    log["rounds"].append(new_round)

    # 更新 current_direction 和 overwritten
    current_direction, overwritten = extract_current_direction(log["rounds"])
    log["current_direction"] = current_direction
    log["overwritten_intents"] = overwritten

    # 备份后写入
    if log_path.exists():
        backup_path = log_path.with_suffix(log_path.suffix + ".bak")
        import shutil
        shutil.copy2(log_path, backup_path)

    with open(log_path, "w", encoding="utf-8") as f:
        yaml.dump(log, f, allow_unicode=True, sort_keys=False, default_flow_style=False)

    result = {
        "status": "ok",
        "log_file": str(log_path),
        "round": new_round["round"],
        "total_rounds": log["_meta"]["total_rounds"],
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
