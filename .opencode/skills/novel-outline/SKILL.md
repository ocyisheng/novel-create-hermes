---
name: "novel-outline"
description: "大纲与分纲：故事结构规划、分卷设计、分纲撰写、情节构建。触发词：大纲、总纲、分卷、分纲、情节、主线、支线、框架、结构"
license: "MIT"
version: "2.0.0"
compatibility: "OpenCode"
tags: ["novel", "outline", "plot"]
---

# 大纲与分纲技能

## PROMPT_TEMPLATE

> 模板定义在 `templates/prompt_template.md`。编排层使用 `extract_template.py` 加载并填充变量。

## 核心职责

按编排 Agent 传入的 CONTEXT 执行故事结构规划、分纲撰写和情节构建任务。暂停/继续决策由编排层通过 checkpoint 服务控制。

> **路径说明**：下文所有 `{PROJECT_PATH}` 替换为编排层 CONTEXT 中传入的 `PROJECT PATH` 值。

## 上下文契约

编排层（或手工操作者）在调用本技能前按以下清单加载上下文：

### P2 大纲规划

| 槽位 | 文件路径 | 提取字段 | 加载方式 |
|------|---------|---------|---------|
| 创意方案 | `ideation/最终创意方案.yaml` | `最终方案.一句话概述` `最终方案.主角设定` `最终方案.核心冲突` `最终方案.世界观概述` | `read` 全文件后提取以上字段 |

### P3 情节构建

| 槽位 | 文件路径 | 提取字段 | 加载方式 |
|------|---------|---------|---------|
| 总纲 | `outline/总纲.yaml` | `幕结构` `分卷` `关键事件` `节奏安排` | `read` 全文件 |
| 已有情节线 | `outline/情节线/*.yaml`（跳过 `主索引.yaml`） | 每条线的 `索引信息.实体ID` `索引信息.当前章节位置` | `glob` + `read` 摘要段 |

### P6 分纲构建

| 槽位 | 文件路径 | 提取字段 | 加载方式 |
|------|---------|---------|---------|
| 总纲 | `outline/总纲.yaml` | `章节规划` `节奏安排` | `read` 全文件 |
| 情节线 | `outline/情节线/*.yaml` | 每条线的 `摘要.一句话描述` `摘要.当前状态` | `glob` + `read` 摘要段 |
| 角色列表 | `project_index.yaml` | `characters` 段（所有角色的 `name` `status` `one_line`） | `read` 筛选活跃角色 |

## 故事大纲

使用三幕/五幕结构规划宏观框架。结构选择和关键节点 → `references/structure_comparison.md`

### 输出文件

| 文件 | 内容 | 写入方式 |
|------|------|---------|
| `outline/总纲.yaml` | 宏观骨架、幕列表、分卷、节奏 | `write` / `edit` |
| `outline/分卷/卷{N}_{名称}.yaml` | 分卷规划（数量由 config.yaml 决定） | `write` / `edit` |
| `outline/情节线/主线.yaml` | 主线推进、冲突核心、关键事件 | `write` / `edit` |
| `outline/情节线/支线_{名称}.yaml` | 支线穿插（多条） | `write` / `edit` |
| `outline/追踪/伏笔.yaml` | 由 auto_update.py 管理 | — |
| `outline/追踪/时间线.yaml` | 由 auto_update.py 管理 | — |

YAML 写入规则：新文件用 `write`，已有文件用 `edit` 增量修改，覆盖前先创建 `.bak` 备份。

## 分纲撰写

基于总纲的章节级蓝图。

### 输入

outline/总纲.yaml、outline/分卷/*.yaml、情节线/主线.yaml + 支线_*.yaml

### 输出

`outline/分纲/卷{卷号}/第{N}章.yaml`，遵循 chapter_schema.yaml 三层契约，含：
- 章节号、标题、对应总纲阶段
- 本章情节点（≥2个）、出场角色、预计字数、关键转折
- 完整模板和命名规则 → `references/outline_templates.md`

## 情节构建

微观情节设计。转折设计 → `references/plot_examples.md`，伏笔管理 → `novel-chapter/references/foreshadowing.md`

## 参考

- `references/structure_comparison.md` — 三幕/五幕结构详解
- `references/outline_templates.md` — 分纲模板与命名规则
- `references/outline_examples.md` — 分纲示例
- `references/plot_examples.md` — 情节设计示例
- `assets/outline.yaml` `assets/volume.yaml` `assets/plot_thread.yaml` `assets/chapter.yaml` — 模板文件
- `novel-chapter/references/foreshadowing.md` — 伏笔设计

## 维护

> 由编排层执行，子 Agent 无需调用。

```bash
python .opencode/shared/rebuild_project_index.py --project-root {PROJECT_PATH}
```

## HARD CONSTRAINTS

> 约束已移入 `templates/prompt_template.md`。编排层通过 `extract_template.py` 加载模板时一并注入 LLM prompt。
