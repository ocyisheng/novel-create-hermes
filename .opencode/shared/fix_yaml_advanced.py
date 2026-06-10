#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
自动修复 YAML 文件常见格式错误（缩进混乱、Tab/空格混用、
列表项或键值对缺少空格等）。

--- 技能/Agent 的调用流程 ---

技能写完 YAML 文件后，接入此脚本做自愈：

    写入 YAML → _utils.load_yaml() 或 yaml.safe_load() 校验
         ↓ 失败
    调用 fix_yaml_file(path) → 修复成功 → 重新校验
         ↓ 仍失败
    记录错误到日志/notepad，不阻塞流程

负责 YAML 写入的技能:
    novel-entity       写入角色档案、世界观 YAML
    novel-outline      写入总纲、分卷、分纲 YAML
    novel-project-manager 写入/更新 config.yaml
    novel-style        写入风格配置 YAML
    novel-quality      读取和校验以上 YAML 时也可调用

用法:
    python .opencode/shared/fix_yaml_advanced.py <file.yaml> [out.yaml]
"""

import sys
import re

import yaml


def preprocess_yaml(text, indent_size=2):
    """在 YAML 解析前修复常见格式错误。"""
    # 1. Tab 转空格
    text = text.replace("\t", " " * indent_size)

    # 2. 去除行尾空格
    lines = [line.rstrip() for line in text.splitlines()]

    # 3. 确保列表项 "- " 后跟非空白字符时有空格分隔
    lines = [re.sub(r"^(\s*-)(\S)", r"\1 \2", line) for line in lines]

    # 4. 确保映射键冒号后有空格（跳过 http:// https:// 等）
    fixed_lines = []
    for line in lines:
        m = re.match(r"^(\s*[\w\-]+):(\S)", line)
        if m and not line.strip().startswith(("http:", "https:")):
            line = f"{m.group(1)}: {m.group(2)}"
        fixed_lines.append(line)

    return "\n".join(fixed_lines)


def fix_yaml_file(input_path, output_path=None):
    """读取 → 预处理 → 解析 → 规范化写出。

    返回值: (成功=True/False, 修复后的数据或None)
    """
    with open(input_path, "r", encoding="utf-8") as f:
        raw = f.read()

    cleaned = preprocess_yaml(raw)

    try:
        data = yaml.safe_load(cleaned)
    except yaml.YAMLError as e:
        print(f"fix_yaml_advanced: 修复失败，仍有语法错误: {e}")
        return False, None

    output_path = output_path or input_path
    with open(output_path, "w", encoding="utf-8") as f:
        if data is None:
            f.write(cleaned)
        else:
            yaml.dump(
                data,
                f,
                default_flow_style=False,
                indent=2,
                allow_unicode=True,
                sort_keys=False,
            )

    print(f"fix_yaml_advanced: 修复完成 -> {output_path}")
    return True, data


def fix_yaml_file_cli(input_path, output_path=None):
    """CLI 入口，保持与之前一致的打印行为。"""
    success, _ = fix_yaml_file(input_path, output_path)
    return success


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(f"用法: python {__file__} <file.yaml> [out.yaml]")
        sys.exit(1)

    infile = sys.argv[1]
    outfile = sys.argv[2] if len(sys.argv) > 2 else None
    sys.exit(0 if fix_yaml_file_cli(infile, outfile) else 1)
