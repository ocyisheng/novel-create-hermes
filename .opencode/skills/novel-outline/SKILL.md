---
name: "novel-outline"
description: "大纲与分纲：总纲撰写（P2）、分卷大纲生成（P3）、情节构建（P4）、分纲撰写（P7）。触发词：大纲、总纲、分卷、分纲、情节、主线、支线、框架、结构"
license: "MIT"
version: "2.1.0"
compatibility: "OpenCode"
tags: ["novel", "outline", "plot"]
---

# 大纲与分纲技能

## PROMPT_TEMPLATE

> 模板定义在 `templates/prompt_template.md`。编排层使用 `extract_template.py` 加载并填充变量。

## 核心职责

按编排 Agent 传入的 CONTEXT 执行四个阶段的创作任务：

| 阶段 | 任务 | 输出 |
|------|------|------|
| P2 | 总纲撰写 | `outline/总纲.yaml` |
| P3 | 分卷大纲生成 | `outline/分卷/卷{N}_{名称}.yaml` |
| P4 | 情节构建 | `outline/情节线/*.yaml` |
| P7 | 分纲撰写 | `outline/分纲/卷{卷号}/第{N}章.yaml` |

> **路径说明**：下文所有 `{PROJECT_PATH}` 替换为编排层 CONTEXT 中传入的 `PROJECT PATH` 值。

## 上下文契约

编排层在调用本技能前按以下清单加载上下文。

### P2 总纲撰写

读取创意方案，输出总纲骨架。

| 槽位 | 文件路径 | 提取字段 | 加载方式 |
|------|---------|---------|---------|
| 创意方案 | `ideation/最终创意方案.yaml` | `最终方案.一句话概述` `最终方案.主角设定` `最终方案.核心冲突` `最终方案.世界观概述` | `read` 全文件后提取以上字段 |

输出：`outline/总纲.yaml`，参见 `assets/outline.yaml` 模板。

### P3 分卷大纲生成

读取总纲+创意方案，为每卷输出完整大纲。

| 槽位 | 文件路径 | 提取字段 | 加载方式 |
|------|---------|---------|---------|
| 总纲 | `outline/总纲.yaml` | `结构配置.卷数` `分卷[].卷号/卷名/章节范围` `故事结构.幕[].幕号/名称/章节范围` `核心概念` | `read` 全文件 |
| 创意方案 | `ideation/最终创意方案.yaml` | `主角设定` `核心冲突` `世界观概述` `情节主线` | `read` 全文件 |
| 已有分卷文件 | `outline/分卷/*.yaml` | 已存在分卷的 `卷信息.核心冲突` `卷信息.章节范围` | `glob` + `read` 摘要段 |

输出：`outline/分卷/卷{N}_{名称}.yaml`（每卷独立文件），参见 `assets/volume.yaml` 模板。每卷必须包含：卷信息（卷号/卷名/所属阶段/章节范围/时间跨度/核心冲突）、叙事任务、主角状态（起点/终点/年龄）、微弧分割（2-4弧×章节范围/核心事件/高潮）、POV分布（主视角+POV角色及功能）、间奏章节、关键事件清单（分类）、角色发展、本卷节奏（基调/情感曲线）、卷末钩子。

### P4 情节构建

读取总纲，设计主线+支线。

| 槽位 | 文件路径 | 提取字段 | 加载方式 |
|------|---------|---------|---------|
| 总纲 | `outline/总纲.yaml` | `幕结构` `分卷` `关键事件` `节奏安排` | `read` 全文件 |
| 已有情节线 | `outline/情节线/*.yaml` | 每条线的 `索引信息.实体ID` | `glob` + `read` 摘要段 |
| 情节线进度 | `outline/追踪/情节线进度.yaml` | 进度列表 | `read` 筛选活跃线 |

输出：`outline/情节线/主线.yaml` + `outline/情节线/支线_{名称}.yaml`，参见 `assets/plot_thread.yaml` 模板。

### P7 分纲构建

读取总纲+分卷+情节线+角色列表，为每章输出分纲。

| 槽位 | 文件路径 | 提取字段 | 加载方式 |
|------|---------|---------|---------|
| 总纲 | `outline/总纲.yaml` | `章节规划` `节奏安排` | `read` 全文件 |
| 分卷 | `outline/分卷/*.yaml` | 目标卷的 `卷信息.核心冲突` `微弧分割` | `glob` + `read` |
| 情节线 | `outline/情节线/*.yaml` | 每条线的 `摘要.一句话描述` `摘要.当前状态` | `glob` + `read` 摘要段 |
| 主索引 | `outline/情节线/主索引.yaml`（如存在） | `多线交织总图`（交汇章节） `节奏总览`（各阶段线程分配） | `read` 全文件（如存在） |
| 角色列表 | `project_index.yaml` | `characters` 段（所有角色的 `name` `status` `one_line`） | `read` 筛选活跃角色 |

输出：`outline/分纲/卷{卷号}/第{N}章.yaml`，参见 `assets/chapter.yaml` 三层契约模板。

## 输出文件一览

| 阶段 | 文件 | 模板 | 写入方式 |
|------|------|------|---------|
| P2 | `outline/总纲.yaml` | `assets/outline.yaml` | `write` / `edit` |
| P3 | `outline/分卷/卷{N}_{名称}.yaml` | `assets/volume.yaml` | `write` / `edit` |
| P4 | `outline/情节线/主线.yaml` | `assets/plot_thread.yaml` | `write` / `edit` |
| P4 | `outline/情节线/支线_{名称}.yaml` | `assets/plot_thread.yaml` | `write` / `edit` |
| P7 | `outline/分纲/卷{卷号}/第{N}章.yaml` | `assets/chapter.yaml` | `write` / `edit` |

写入规则：新文件用 `write`，已有文件用 `edit` 增量修改，覆盖前先创建 `.bak` 备份。

## 参考文件

- `references/structure_comparison.md` — 三幕/五幕结构详解
- `references/outline_templates.md` — 分纲模板与命名规则
- `references/outline_examples.md` — 分纲示例
- `references/plot_examples.md` — 情节设计示例
- `references/foreshadowing.md` — 伏笔设计参考

## 维护

```bash
python .opencode/shared/rebuild_project_index.py --project-root {PROJECT_PATH}
```

由编排层在 P3/P7 实体创建后执行，子 Agent 无需调用。

## HARD CONSTRAINTS

> 约束已移入 `templates/prompt_template.md`。编排层通过 `extract_template.py` 加载模板时一并注入 LLM prompt。
