---
name: "novel-entity"
description: "角色与世界观：角色档案创建、世界观建设、YAML 格式规范。触发词：角色、人物、创建角色、世界观、设定、规则、体系、势力"
license: "MIT"
version: "2.0.0"
compatibility: "OpenCode"
tags: ["novel", "character", "worldbuilding", "entity"]
---

# 角色与世界观技能

## PROMPT_TEMPLATE

> 模板定义在 `templates/prompt_template.md`。编排层使用 `extract_template.py` 加载并填充变量。

## 核心职责

按编排 Agent 传入的 CONTEXT 执行角色创建和世界观建设任务。

> **路径说明**：下文所有 `{PROJECT_PATH}` 替换为编排层 CONTEXT 中传入的 `PROJECT PATH` 值。

## 上下文契约

编排层（或手工操作者）在调用本技能前按以下清单加载上下文：

### P5 世界观建设

| 槽位 | 文件路径 | 提取字段 | 加载方式 |
|------|---------|---------|---------|
| 创意方案 | `ideation/最终创意方案.yaml` | `最终方案.世界观概述` `最终方案.核心设定` | `read` 全文件 |
| 总纲 | `outline/总纲.yaml` | 世界观相关 `关键设定` `势力格局` `地理信息` | `read` 全文件 |
| 已有实体 | `project_index.yaml` | `worldbuilding` 段（已有实体 ID + `name` `subtype`） | `read` 避免重复创建 |

### P6 角色创建

| 槽位 | 文件路径 | 提取字段 | 加载方式 |
|------|---------|---------|---------|
| 创意方案 | `ideation/最终创意方案.yaml` | `最终方案.主角设定` `最终方案.核心冲突` | `read` 全文件 |
| 总纲 | `outline/总纲.yaml` | `关键角色` `关系网` | `read` 全文件 |
| 已有角色 | `project_index.yaml` | `characters` 段（已有角色名 + `type` `status`） | `read` 避免重复创建 |

## 角色创建

按 `assets/character.yaml` 模板创建角色文件。角色类型参考 → `references/character_types.md`，示例 → `references/character_profile_example.md`


### 输出

`characters/{角色名}.yaml` — 按 `assets/character.yaml` 模板，角色弧线（起始→变化→最终）为必填字段。

## 世界观建设

按 `assets/worldview.yaml` 模板创建。要素详解 → `references/setting_details.md`

### 输出

worldbuilding/ 下 7 个文件（基本信息、核心规则、力量体系、势力格局、地理位置、历史、文化）

## 参考

- `references/character_types.md` — 角色类型与设计原则
- `references/character_profile_example.md` — 角色档案示例
- `references/setting_details.md` — 世界观要素详解
- `references/worldview_examples.md` — 世界观工作流示例
- `assets/character.yaml` `assets/worldview.yaml` — 实体模板

## 写后处理

输出写入后执行以下脚本：

```bash
# 1. YAML 格式修正
python .opencode/shared/fix_yaml_indent.py "characters/{新文件名}.yaml"
# 或批量修正
python .opencode/shared/fix_yaml_indent.py --dir characters/

# 2. 实体一致性校验（角色档案 vs 分纲出场角色）
python .opencode/shared/validate_entity_consistency.py --project-root {PROJECT_PATH}

# 3. 项目索引重建
python .opencode/shared/rebuild_project_index.py --project-root {PROJECT_PATH}
```

## HARD CONSTRAINTS

> 约束已移入 `templates/prompt_template.md`。编排层通过 `extract_template.py` 加载模板时一并注入 LLM prompt。
