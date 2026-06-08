---
name: "novel-env-setup"
description: "环境初始化。检测 Python、创建 .venv、安装依赖、验证环境。触发词：环境初始化、setup、check env、环境检查、依赖安装、venv、conda、环境修复、python 环境"
license: "MIT"
version: "2.0.0"
compatibility: "OpenCode"
tags: ["novel", "environment", "setup"]
---

# 环境初始化

检测 Python 环境，自动创建 `.venv` 虚拟环境并安装依赖。

## 前提

系统已安装 Python 3.8+。若无，提示用户手动安装。

## 操作方式

```bash
# Windows
.opencode/skills/novel-env-setup/scripts/setup_env.bat

# macOS/Linux
chmod +x .opencode/skills/novel-env-setup/scripts/setup_env.sh && ./.opencode/skills/novel-env-setup/scripts/setup_env.sh
```

脚本自动检测 Python 来源（系统 Python → conda），创建 `.venv` + `pip install -r scripts/requirements.txt`。

### 验证环境
```bash
python ./.opencode/skills/novel-env-setup/scripts/setup.py                 # 检查
python .opencode/skills/novel-env-setup/scripts/setup.py --fix           # 修复
python ./.opencode/skills/novel-env-setup/scripts/setup_opencode_config.py  # 配置插件
```

## 流程

1. 检测 `python --version` / `conda --version`
2. 两者皆无 → 提示用户安装，终止
3. 有任一 → 执行 `.bat`/`.sh` 创建 `.venv` + 安装 PyYAML 依赖
4. `setup.py` 验证通过 → 环境就绪
5. 运行 `setup_opencode_config.py` → 创建/更新 OhMyOpenAgent 插件配置（novel category 路由）

## HARD CONSTRAINTS

1. 必须通过 `.bat`/`.sh` 脚本创建环境，不用 Python 创建
2. 不替用户安装系统 Python 或 conda
3. 第 5 步的配置脚本必须运行（即使环境已初始化过，也应确保配置存在）

## 参考文件

- `references/troubleshooting.md` — 常见环境问题排查指南
