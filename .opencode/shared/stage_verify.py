#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
stage_verify.py — 单文件结构验证

验证文件是否符合标准三层结构格式。用于标准化步骤中快速确认文件正确性。

用法:
    python stage_verify.py --file characters/林默.yaml
    python stage_verify.py --file outline/分纲/卷1/第3章.yaml --type chapter_outline

依赖: Python 3, stdlib + PyYAML
"""

import argparse
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print("错误: 需要 PyYAML，请运行 novel-env-setup 安装依赖", file=sys.stderr)
    sys.exit(1)


def verify_file(path: Path, expected_type: str = "") -> dict:
    """验证单个文件的结构完整性。"""
    suffix = path.suffix.lower()
    checks = {"file": str(path), "type": suffix, "valid": False}

    # 编码检查
    try:
        with open(path, "rb") as f:
            raw = f.read()
        if raw.startswith(b"\xef\xbb\xbf"):
            text = raw[3:].decode("utf-8")
        else:
            text = raw.decode("utf-8")
    except (UnicodeDecodeError, OSError) as e:
        checks["errors"] = [f"读取失败: {e}"]
        return checks

    # YAML 文件：三层结构检查
    if suffix in (".yaml", ".yml"):
        try:
            data = yaml.safe_load(text)
        except yaml.YAMLError as e:
            checks["errors"] = [f"YAML 解析错误: {e}"]
            return checks

        if not isinstance(data, dict):
            checks["errors"] = ["YAML 顶层不是字典"]
            return checks

        has_meta = "_meta" in data and isinstance(data["_meta"], dict)
        has_index = "索引信息" in data and isinstance(data["索引信息"], dict)
        has_summary = "摘要" in data and isinstance(data["摘要"], dict)
        has_full = "完整档案" in data and isinstance(data["完整档案"], dict)

        checks["has_meta"] = has_meta
        checks["has_index"] = has_index
        checks["has_summary"] = has_summary
        checks["has_full_archive"] = has_full
        checks["is_threelayer"] = all([has_meta, has_index, has_summary, has_full])

        if checks["is_threelayer"]:
            meta = data["_meta"]
            index = data["索引信息"]
            entity_type = meta.get("entity_type", "")
            checks["entity_type"] = entity_type
            checks["name_not_empty"] = bool(index.get("名称"))

            if entity_type == "chapter":
                checks["chapter_number"] = index.get("章节号", 0)

            if expected_type:
                type_map = {
                    "character": "character",
                    "chapter": "chapter",
                    "chapter_outline": "chapter",
                    "worldbuilding": "worldbuilding",
                    "plot_thread": "plot_thread",
                }
                mapped = type_map.get(expected_type)
                if mapped and entity_type != mapped:
                    checks["type_mismatch"] = f"期望 {expected_type}，实际 {entity_type}"

            checks["valid"] = bool(index.get("名称"))
        else:
            checks["valid"] = True  # 非三层 YAML 也可能合法

    # 文本文件：基本检查
    elif suffix == ".txt":
        stripped = text.strip()
        checks["valid"] = len(stripped) >= 10
        if not checks["valid"]:
            checks["warnings"] = ["内容过短"]
        checks["length"] = len(stripped)

    return checks


def main():
    parser = argparse.ArgumentParser(
        description="stage_verify.py — 单文件结构验证",
    )
    parser.add_argument("--file", required=True, help="文件路径")
    parser.add_argument("--type", default="", help="期望的实体类型，如 character / chapter / worldbuilding")
    args = parser.parse_args()

    file_path = Path(args.file).resolve()
    if not file_path.is_file():
        print(f"错误: 文件不存在: {file_path}", file=sys.stderr)
        sys.exit(1)

    result = verify_file(file_path, args.type)

    # 输出
    status = "✅" if result.get("valid") else "❌"
    print(f"  {status} {result['file']}")
    if result.get("is_threelayer"):
        n = "✓" if result.get("name_not_empty") else "✗"
        print(f"     类型: {result.get('entity_type', '?')} | 名称: {n}")
        if result.get("chapter_number"):
            print(f"     章节号: {result['chapter_number']}")
    if result.get("type_mismatch"):
        print(f"     ⚠️  {result['type_mismatch']}")
    if result.get("warnings"):
        for w in result["warnings"]:
            print(f"     ⚠️  {w}")
    if result.get("errors"):
        for e in result["errors"]:
            print(f"     ❌ {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
