#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
self_check.py — novel-checkpoint-service 环境自检快捷入口

用法:
    python self_check.py
"""

import sys
from pathlib import Path

# 添加同级目录到路径（以便 import checkpoint_service）
sys.path.insert(0, str(Path(__file__).parent))

from checkpoint_service import self_check


def main():
    results = self_check()
    all_pass = True

    print("=" * 50)
    print(" novel-checkpoint-service 自检")
    print("=" * 50)

    for item in results:
        status_icon = "✅" if item["status"] == "pass" else "❌"
        print(f"  {status_icon} {item['name']}: {item['detail']}")
        if item["status"] != "pass":
            all_pass = False

    print("=" * 50)
    if all_pass:
        print(" ✅ novel-checkpoint-service 自检通过")
    else:
        print(" ⚠️  novel-checkpoint-service 自检未完全通过")

    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(main())
