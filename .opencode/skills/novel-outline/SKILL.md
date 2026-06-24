---
name: "novel-outline"
description: "分卷大纲与分纲：分卷大纲生成（P6）和分纲撰写（P7）。触发词：分卷、分纲、章节大纲、章纲、卷大纲"
license: "MIT"
version: "2.2.0"
compatibility: "OpenCode"
tags: ["novel", "outline", "volume", "chapter"]
---

# 分卷大纲与分纲技能

## 核心职责

按编排 Agent 传入的 CONTEXT 执行两个阶段的创作任务：

| 阶段 | 任务 | 输出 |
|------|------|------|
| P6 | 分卷大纲生成 | `outline/分卷/卷{N}_{名称}.yaml` |
| P7 | 分纲撰写 | `outline/分纲/卷{卷号}/第{N}章.yaml` |

> **路径说明**：下文所有 `{PROJECT_PATH}` 替换为编排层 CONTEXT 中传入的 `PROJECT PATH` 值。

## 上下文契约

### P6 分卷大纲生成

读取总纲+创意方案，为每卷输出完整大纲。

| 槽位 | 文件路径 | 提取字段 | 加载方式 |
|------|---------|---------|---------|
| 总纲 | `outline/总纲.yaml` | `结构配置.卷数` `分卷[].卷号/卷名/章节范围` `故事结构.幕[].幕号/名称/章节范围` `核心概念` | `read` 全文件 |
| 创意方案 | `ideation/最终创意方案.yaml` | `主角设定` `核心冲突` `世界观概述` `情节主线` | `read` 全文件 |
| 已有分卷文件 | `outline/分卷/*.yaml` | 已存在分卷的 `卷信息.核心冲突` `卷信息.章节范围` | `glob` + `read` 摘要段 |

输出：`outline/分卷/卷{N}_{名称}.yaml`（每卷独立文件），参见 `assets/volume.yaml` 模板。

每卷必须包含：卷信息（卷号/卷名/所属阶段/章节范围/时间跨度/核心冲突）、叙事任务、主角状态（起点/终点/年龄）、微弧分割（2-4弧×章节范围/核心事件/高潮）、POV分布（主视角+POV角色及功能）、间奏章节、关键事件清单（分类）、角色发展、本卷节奏（基调/情感曲线）、卷末钩子。

### P7 分纲构建

读取总纲+分卷+情节线+角色列表+叙事策略，为每章输出分纲。

| 槽位 | 文件路径 | 提取字段 | 加载方式 |
|------|---------|---------|---------|
| 总纲 | `outline/总纲.yaml` | `章节规划` `节奏安排` | `read` 全文件 |
| 分卷 | `outline/分卷/*.yaml` | 目标卷的 `卷信息.核心冲突` `微弧分割` | `glob` + `read` |
| 情节线 | `outline/情节线/*.yaml` | 每条线的 `摘要.一句话描述` `摘要.当前状态` | `glob` + `read` 摘要段 |
| 主索引 | `outline/情节线/主索引.yaml`（如存在） | `多线交织总图`（交汇章节） `节奏总览`（各阶段线程分配） | `read` 全文件（如存在） |
| 角色列表 | `project_index.yaml` | `characters` 段（所有角色的 `name` `status` `one_line`） | `read` 筛选活跃角色 |
| 叙事策略 | `outline/叙事策略.yaml` | `视角选择` `叙事手法` `信息分配` | `read` 全文件 |

输出：`outline/分纲/卷{卷号}/第{N}章.yaml`，参见 `assets/chapter.yaml` 三层契约模板。

**P7 扩展字段（v3.1.0）**：生成分纲时请创建以下新段：

1. **场域规划**（替代原`情节点`）：每个场域需包含场域名、POV角色、持续时间（预期字数）、故事内时间、功能、氛围（情感基调+感官锚点+环境要素）、节奏控制（开场/中场/高潮张力，1-10量化）、进入/退出方式、涉及角色及状态。默认每章 3-5 个场域。
2. **张力曲线**：量化本章节奏指标——开场、第一场域高潮、中点转折、章节高潮、结尾（均1-10），以及下章悬念。
3. **对话规划**（可选）：仅对话密集的场域使用，含对话节拍（节拍+意图+要点）、声线提醒（角色→说话风格映射）、潜台词提示。
4. **关联情节线**（可选）：直接声明本章归属的情节线实体ID，用于全量重建时精确匹配（替代角色交集 fallback）。

## 输出文件一览

| 阶段 | 文件 | 模板 | 写入方式 |
|------|------|------|---------|
| P6 | `outline/分卷/卷{N}_{名称}.yaml` | `assets/volume.yaml` | `write` / `edit` |
| P7 | `outline/分纲/卷{卷号}/第{N}章.yaml` | `assets/chapter.yaml` | `write` / `edit` |

写入规则：新文件用 `write`，已有文件用 `edit` 增量修改，覆盖前先创建 `.bak` 备份。

## 参考文件

- `references/outline_templates.md` — 分纲模板与命名规则
- `references/outline_examples.md` — 分纲示例

## 写后处理

输出写入后执行以下脚本：

```bash
# 1. YAML 格式修正
python .opencode/shared/fix_yaml_indent.py "outline/{新文件路径}"

# 2. 项目索引重建
python .opencode/shared/rebuild_project_index.py --project-root {PROJECT_PATH}

# 3. 阶段切换（P6→P7 分卷→分纲 / P7→P8 分纲→章节）
python .opencode/shared/config_manager.py set 当前阶段 {新阶段} --project-root {PROJECT_PATH}
```

## HARD CONSTRAINTS

> 约束已移入 `templates/prompt_template.md`。编排层通过 `extract_template.py` 加载模板时一并注入。
