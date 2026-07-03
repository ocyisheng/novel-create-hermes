---
name: "novel-project-manager"
description: "小说项目管理。新建/导入/查看状态/续写/切换/删除。触发词：新建项目、导入项目、查看状态、续写、切换项目、删除项目、项目管理、novel project"
license: "MIT"
version: "3.1.0"
compatibility: "OpenCode"
tags: ["novel", "project-management"]
---

# 小说项目管理

## 操作方式

通过 `bash` 执行 Python 脚本：

### 新建项目
```bash
# 标准三卷三幕（默认）
python .opencode/shared/project/project_init.py new "项目名" "玄幻"

# 五卷五幕史诗结构
python .opencode/shared/project/project_init.py new "星辰帝国" "玄幻" --volumes 5 --structure 五幕

# 四卷三幕（自定义幕数）
python .opencode/shared/project/project_init.py new "迷雾追踪" "悬疑" --volumes 4 --acts 3

# V2 原生项目（跳过旧 YAML 目录，直接初始化 graph/）
python .opencode/shared/project/project_init.py new "龙渊" "玄幻" --v2
```
创建标准目录、config.yaml、模板文件。使用 `--v2` 创建 V2 原生项目，不建旧 YAML 目录。项目默认创建到工具根目录下的 `novels/` 子目录（可通过 `-d` 指定其他位置）。卷数 (`--volumes`) 和幕结构 (`--structure`/`--acts`) 控制生成的分纲目录数和总纲模板格式。

💡 项目创建完成后，init.py 已自动完成初始实体索引（无需手动运行）。

### 导入已有小说
```bash
python .opencode/shared/project/project_init.py import "源路径" "项目名"
```
导入完成。

💡 导入完成后，init.py 已自动完成初始实体索引（无需手动运行）。

### 查看状态
```bash
python .opencode/shared/project/project_init.py status "项目名" [--phase 阶段]
```

### 续写
```bash
python .opencode/shared/project/project_init.py resume "项目名"
```

### 切换

```bash
# 标准切换：同步旧项目→持久化旧→同步新→推导新 notepad→验证一致性
python .opencode/shared/project/project_init.py switch "项目名"

# 仅预览，不修改任何文件
python .opencode/shared/project/project_init.py switch "项目名" --dry-run

# 跳过索引同步（紧急情况下，避免触发 rebuild）
python .opencode/shared/project/project_init.py switch "项目名" --skip-sync

# 跳过 phase_detect 一致性验证
python .opencode/shared/project/project_init.py switch "项目名" --no-verify
```

### 删除
```bash
python .opencode/shared/project/project_init.py delete "项目名" [--force]
```

## 前提

- Python 环境已初始化（先调用 `novel-env-setup`）
- 项目目录所在父目录存在 `.venv/`

## 参考文件

- `references/project_structure.md` — 小说项目标准目录结构


## 子命令速查

| 子命令 | 用途 | 关键 flag |
|--------|------|----------|
| `new` | 新建项目 | `--volumes`, `--acts`, `--structure`, `--v2` |
| `import` | 导入旧项目 | `--root`, `--volumes` |
| `status` | 查看/更新状态 | `--phase` |
| `resume` | 续写项目（同一项目刷新） | — |
| `switch` | 切换项目（不同项目间原子化） | `--dry-run`, `--skip-sync`, `--no-verify` |
| `delete` | 删除项目 | `--force` |

## HARD CONSTRAINTS

1. 首次使用前确保 `.venv` 存在（调用 `novel-env-setup`）
2. 输出为 YAML 格式
3. 删除操作无 `--force` 时必须确认
4. 切换项目优先使用 `switch` 子命令（原子化），不要手动 read/write notepad
5. `switch --dry-run` 可用于检查切换计划而不修改任何文件
