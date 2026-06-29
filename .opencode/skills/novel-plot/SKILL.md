---
name: "novel-plot"
description: "情节构建：设计主线与支线情节、伏笔规划、角色出场规划。触发词：情节、主线、支线、故事线、伏笔"
license: "MIT"
version: "1.0.0"
compatibility: "OpenCode"
tags: ["novel", "plot", "thread"]
---

# 情节构建技能

## 核心职责

按编排 Agent 传入的 CONTEXT 执行情节构建任务（P5）。设计主线+支线，并生成全局伏笔规划。

> **路径说明**：下文所有 `{PROJECT_PATH}` 替换为编排层 CONTEXT 中传入的 `PROJECT PATH` 值。

## 上下文契约

编排层在调用本技能前按以下清单加载上下文：

| 槽位 | 文件路径 | 提取字段 | 加载方式 |
|------|---------|---------|---------|
| 总纲 | `outline/总纲.yaml` | `幕结构` `分卷` `关键事件` `节奏安排` | `read` 全文件 |
| 叙事策略 | `outline/叙事策略.yaml` | `信息分配.戏剧反讽` `信息分配.悬念管理` `叙事手法` | `read` 全文件 |
| 已有情节线 | `outline/情节线/*.yaml` | 每条线的 `索引信息.实体ID` | `glob` + `read` 摘要段 |
| 情节线进度 | `outline/追踪/情节线进度.yaml` | 进度列表 | `read` 筛选活跃线 |
| 时间线设计 | `outline/时间线设计.yaml` | `时间线设计` 段（如存在，作为伏笔设置的时序参考） | `read` 全文件 |

输出：
- `outline/情节线/主线.yaml` + `outline/情节线/支线_{名称}.yaml`，参见 `assets/plot_thread.yaml` 模板
- `outline/伏笔规划.yaml`，参见 `assets/foreshadowing_plan.yaml` 模板
- `outline/角色出场规划.yaml`（可选），参见 `assets/character_appearance_plan.yaml` 模板
- `outline/情节线/主索引.yaml`（可选），参见 `assets/plot_index.yaml` 模板

## 输出文件一览

| 文件 | 模板 | 写入方式 |
|------|------|---------|
| `outline/情节线/主线.yaml` | `assets/plot_thread.yaml` | `write` / `edit` |
| `outline/情节线/支线_{名称}.yaml` | `assets/plot_thread.yaml` | `write` / `edit` |
| `outline/伏笔规划.yaml` | `assets/foreshadowing_plan.yaml` | `write` |
| `outline/角色出场规划.yaml`（可选） | `assets/character_appearance_plan.yaml` | `write` |
| `outline/情节线/主索引.yaml`（可选） | `assets/plot_index.yaml` | `write` |

## 写后处理（chain: `entity-plot`）

输出写入后编排层自动执行以下脚本：

```bash
# 1. YAML 格式修正
python .opencode/shared/fix_yaml_indent.py "outline/{新文件路径}"

# 2. 实体格式校验
python .opencode/shared/validate_entity_format.py --project-root {PROJECT_PATH}

# 3. 项目索引重建
python .opencode/shared/rebuild_project_index.py --project-root {PROJECT_PATH}

# 4. 情节线进度重建
python .opencode/shared/rebuild_plot_progress.py --project-root {PROJECT_PATH}

# 5. 阶段切换（P5→P6 情节→分卷）
python .opencode/shared/config_manager.py set 当前阶段 "分卷大纲生成" --project-root {PROJECT_PATH}
```

> **禁止**：不要用 `edit`/`write` 手工修正 YAML 缩进或格式——交给 fix_yaml_indent.py 统一处理。你写完文件、标记好内容即可，脚本会自动格式化。

## 参考文件

- `references/plot_examples.md` — 情节设计示例
- `references/foreshadowing.md` — 伏笔设计参考
- `assets/plot_thread.yaml` — 情节线模板
- `assets/foreshadowing_plan.yaml` — 伏笔规划模板
- `assets/character_appearance_plan.yaml` — 角色出场规划模板
- `assets/plot_index.yaml` — 主索引模板

## HARD CONSTRAINTS

> 约束已移入 `templates/prompt_template.md`。编排层通过 `extract_template.py` 加载模板时一并注入。
