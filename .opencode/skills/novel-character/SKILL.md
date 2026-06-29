---
name: "novel-character"
description: "角色创建：创建角色档案，包含性格、背景、能力、成长弧线等。触发词：角色、人物、创建角色、主角、配角"
license: "MIT"
version: "1.0.0"
compatibility: "OpenCode"
tags: ["novel", "character", "entity"]
---

# 角色创建技能

## 核心职责

按编排 Agent 传入的 CONTEXT 执行角色创建任务（P3）。创建角色档案的 YAML 实体文件。

> **路径说明**：下文所有 `{PROJECT_PATH}` 替换为编排层 CONTEXT 中传入的 `PROJECT PATH` 值。

## 上下文契约

编排层在调用本技能前按以下清单加载上下文：

| 槽位 | 文件路径 | 提取字段 | 加载方式 |
|------|---------|---------|---------|
| 创意方案 | `ideation/最终创意方案.yaml` | `最终方案.主角设定` `最终方案.核心冲突` | `read` 全文件 |
| 总纲 | `outline/总纲.yaml` | `关键角色` `关系网` | `read` 全文件 |
| 已有角色 | `project_index.yaml` | `characters` 段（已有角色名 + `type` `status`） | `read` 避免重复创建 |

## 角色创建

按 `assets/character.yaml` 模板创建角色文件。角色类型参考 → `references/character_types.md`，示例 → `references/character_profile_example.md`

### 输出

`characters/{角色名}.yaml` — 按 `assets/character.yaml` 模板，角色弧线（起始→变化→最终）为必填字段。

## 参考

- `references/character_types.md` — 角色类型与设计原则
- `references/character_profile_example.md` — 角色档案示例
- `assets/character.yaml` — 角色模板

## 写后处理（chain: `entity-base`）

输出写入后编排层自动执行以下脚本：

```bash
# 1. YAML 格式修正
python .opencode/shared/fix_yaml_indent.py "characters/{新文件名}.yaml"

# 2. 实体格式校验
python .opencode/shared/validate_entity_format.py --project-root {PROJECT_PATH}

# 3. 项目索引重建
python .opencode/shared/rebuild_project_index.py --project-root {PROJECT_PATH}

# 4. 阶段切换（P3→P4 角色创建→总纲撰写）
python .opencode/shared/config_manager.py set 当前阶段 "总纲撰写" --project-root {PROJECT_PATH}
```

> **禁止**：不要用 `edit`/`write` 手工修正 YAML 缩进或格式——交给 fix_yaml_indent.py 统一处理。你写完文件、标记好内容即可，脚本会自动格式化。

## HARD CONSTRAINTS

1. 每次创建 1 个 `characters/` 下的角色 YAML 文件
2. 严格遵循 `assets/character.yaml` 模板的三层结构
3. 角色弧线（起始→变化→最终）为必填字段
4. YAML 格式约束见 `templates/prompt_template.md`
5. 不修改 `project_index.yaml`（写后处理脚本自动更新）
