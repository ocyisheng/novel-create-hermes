---
name: "novel-project-manager"
description: "小说项目管理（V2）。新建/导入/查看状态/续写/切换/删除。触发词：新建项目、导入项目、查看状态、续写、切换项目、删除项目、项目管理、novel project"
license: "MIT"
version: "4.0.0"
compatibility: "OpenCode"
tags: ["novel", "project-management", "v2"]
---

# 小说项目管理

## 操作方式

通过 `novel-tool` tool 执行。

### 新建项目

```
novel-tool(operation="project.new", project="项目名", genre="玄幻")
```

### 导入已有小说

```
novel-tool(operation="project.import", project="项目名", source_path="源路径")
```

### 查看状态

```
novel-tool(operation="project.status", project="项目名")
```
可选参数：`project="项目名", phase="阶段"` 同时更新写作阶段。

### 续写

```
novel-tool(operation="project.resume", project="项目名")
```

### 切换

```
novel-tool(operation="project.switch", project="项目名")
```
试运行：`novel-tool(operation="project.switch", project="项目名", dry_run=true)`

### 删除

```
novel-tool(operation="project.delete", project="项目名", force=true)
```

## 前提

- Python 环境已初始化（先调用 `novel-env-setup`）
- 项目目录所在父目录存在 `.venv/`

## 参考文件

- `references/project_structure.md` — 小说项目标准目录结构


## 操作速查

| novel-tool 调用 | 用途 | 关键参数 |
|--------|------|----------|
| `novel-tool(operation="project.new")` | 新建项目（V2 原生，graph/ 为真相源） | `genre` |
| `novel-tool(operation="project.import")` | 导入旧项目 | `source_path` |
| `novel-tool(operation="project.status")` | 查看/更新状态 | `phase` |
| `novel-tool(operation="project.resume")` | 续写项目（同一项目刷新） | — |
| `novel-tool(operation="project.switch")` | 切换项目（不同项目间原子化） | `dry_run=true` |
| `novel-tool(operation="project.delete")` | 删除项目 | `force=true` |

## HARD CONSTRAINTS

1. 首次使用前确保 `.venv` 存在（调用 `novel-env-setup`）
2. 输出为 YAML 格式
3. 删除操作无 `force=true` 时必须确认
4. 切换项目优先使用 `novel-tool(operation="project.switch")`（原子化），不要手动 read/write notepad
5. `novel-tool(operation="project.switch", dry_run=true)` 可用于检查切换计划而不修改任何文件
6. `novel-tool(operation="project.new")` 默认创建 V2 原生项目（graph/ 为单一真相源）
