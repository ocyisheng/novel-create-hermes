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

通过 `novel-tool` tool 执行。

### 新建项目

```
# V2 原生项目（推荐）
novel-tool --operation project.new --name "项目名" --genre "玄幻" --v2

# 标准三卷三幕（V1）
novel-tool --operation project.new --name "项目名" --genre "玄幻" --volumes 3 --acts 3

# 五卷五幕史诗结构
novel-tool --operation project.new --name "星辰帝国" --genre "玄幻" --volumes 5 --structure "五幕"
```

### 导入已有小说

```
novel-tool --operation project.import --name "项目名" --source_path "源路径"
```

### 查看状态

```
novel-tool --operation project.status --name "项目名"
```
可选 `--name "项目名" --phase "阶段"` 同时更新写作阶段。

### 续写

```
novel-tool --operation project.resume --name "项目名"
```

### 切换

```
novel-tool --operation project.switch --name "项目名"
```
试运行：`--name "项目名" --dryRun`

### 删除

```
novel-tool --operation project.delete --name "项目名" --force
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
