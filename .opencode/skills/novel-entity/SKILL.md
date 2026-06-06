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

按编排 Agent 传入的 CONTEXT 执行角色创建和世界观建设任务。暂停/继续决策由编排层通过 checkpoint 服务控制。

> **路径说明**：下文所有 `{PROJECT_PATH}` 替换为编排层 CONTEXT 中传入的 `PROJECT PATH` 值。

## 上下文契约

编排层（或手工操作者）在调用本技能前按以下清单加载上下文：

### P4 世界观建设

| 槽位 | 文件路径 | 提取字段 | 加载方式 |
|------|---------|---------|---------|
| 创意方案 | `ideation/最终创意方案.yaml` | `最终方案.世界观概述` `最终方案.核心设定` | `read` 全文件 |
| 总纲 | `outline/总纲.yaml` | 世界观相关 `关键设定` `势力格局` `地理信息` | `read` 全文件 |
| 已有实体 | `project_index.yaml` | `worldbuilding` 段（已有实体 ID + `name` `subtype`） | `read` 避免重复创建 |

### P5 角色创建

| 槽位 | 文件路径 | 提取字段 | 加载方式 |
|------|---------|---------|---------|
| 创意方案 | `ideation/最终创意方案.yaml` | `最终方案.主角设定` `最终方案.核心冲突` | `read` 全文件 |
| 总纲 | `outline/总纲.yaml` | `关键角色` `关系网` | `read` 全文件 |
| 已有角色 | `project_index.yaml` | `characters` 段（已有角色名 + `type` `status`） | `read` 避免重复创建 |

## 角色创建

按 `assets/character.yaml` 模板创建角色文件。角色类型参考 → `references/character_types.md`，示例 → `references/character_profile_example.md`

### YAML 格式规则（必须遵守）

1. **缩进**：统一 2 空格缩进，禁止使用 tab
2. **引号**：所有字符串值必须用双引号 `""` 包裹
3. **多段落文本**：模板中标注 `|` 的字段（如成长经历、心理创伤、动机根源、角色弧线等）使用 YAML literal block scalar：
   ```yaml
   成长经历: |
     第一段正文内容，比键名多 2 空格缩进。
     
     段落之间保留一个空行，空行同样比键名多缩进 2 空格。
   ```
4. **列表项**：`-` 比父级键多缩进 2 空格（即缩进 4 空格或更深的偶数层）
5. **段间空行**：顶层键（`_meta:`、`索引信息:`、`摘要:`、`完整档案:`）之间保留一个空行分割

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

## 维护

> 由编排层执行，子 Agent 无需调用。

```bash
python .opencode/shared/rebuild_project_index.py --project-root {PROJECT_PATH}
```

## HARD CONSTRAINTS

> 约束已移入 `templates/prompt_template.md`。编排层通过 `extract_template.py` 加载模板时一并注入 LLM prompt。
