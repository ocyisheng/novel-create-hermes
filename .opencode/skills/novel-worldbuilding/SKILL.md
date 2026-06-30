---
name: "novel-worldbuilding"
description: "世界观建设：创建力量体系、势力格局、地理、历史等世界观设定文件。触发词：世界观、设定、规则、体系、势力、世界背景"
license: "MIT"
version: "1.0.0"
compatibility: "OpenCode"
tags: ["novel", "worldbuilding", "setting"]
---

# 世界观建设技能

## 核心职责

按编排 Agent 传入的 CONTEXT 执行世界观建设任务（P2）。创建世界观设定的 YAML 实体文件。

> **路径说明**：下文所有 `{PROJECT_PATH}` 替换为编排层 CONTEXT 中传入的 `PROJECT PATH` 值。

## 上下文契约

编排层在调用本技能前按以下清单加载上下文：

|槽位|文件路径|提取字段|加载方式|
|------|---------|---------|---------|
|创意方案|`ideation/最终创意方案.yaml`|`最终方案.世界观概述` `最终方案.核心设定`|`read` 全文件|
|总纲|`outline/总纲.yaml`|世界观相关 `关键设定` `势力格局` `地理信息`|`read` 全文件|
|已有实体|`project_index.yaml`|`worldbuilding` 段（已有实体 ID + `name` `subtype`）|`read` 避免重复创建|

## 世界观建设

创建前先做两个方法论决策，再按模板输出。

### 决策一：方法论选择

|路径|适用场景|操作|
|------|---------|------|
|**体系化建置**|玄幻、西幻、科幻|按10个标准模板输出力量体系×地理×种族×年表|
|**笔记传统**|现实主义、文艺向|散点随笔组织，一点切入、神韵全出（汪曾祺式"花是乱的"）|
|**混合方案**|多数长篇|宏观架构用体系化建置 + 微观细节用笔记传统填充|

### 决策二：自洽性定位

世界观不必追求滴水不漏的物理级自洽。**区分"开放区的矛盾"（刻意保留）与"粗心的矛盾"（失误）**。在核心规则文件中声明哪些区域是"开放区"——允许未知、允许"洪荒"状态。

### 输出

按 `assets/worldview.yaml` 模板创建。要素详解 → `references/setting_details.md`

输出到 `worldbuilding/` 下10个标准文件（基本信息、核心规则、力量体系、势力格局、地理位置、历史、文化、经济体系、政治制度、社会阶层）。**自洽性检验**：用"在这个世界里它是否自洽"替代"在现实中它是否可能"来判断设定合理性。

## 参考

- `references/setting_details.md` — 世界观要素详解
- `references/worldview_examples.md` — 世界观工作流示例
- `assets/worldview.yaml` — 世界观模板

## 写后处理（chain: `entity-base`）

输出写入后编排层自动执行以下脚本：

```bash
# 1. YAML 格式修正
python .opencode/shared/fix_yaml_indent.py "worldbuilding/{新文件名}.yaml"
# 或批量修正
python .opencode/shared/fix_yaml_indent.py --dir worldbuilding/

# 2. 实体格式校验
python .opencode/shared/validate_entity_format.py --project-root {PROJECT_PATH}

# 3. 项目索引重建
python .opencode/shared/rebuild_project_index.py --project-root {PROJECT_PATH}

# 4. 阶段切换（P2→P3 世界观建设→角色创建）
python .opencode/shared/config_manager.py set 当前阶段 "角色创建" --project-root {PROJECT_PATH}
```

> **禁止**：不要用 `edit`/`write` 手工修正 YAML 缩进或格式——交给 fix_yaml_indent.py 统一处理。你写完文件、标记好内容即可，脚本会自动格式化。

## HARD CONSTRAINTS

1. 每次创建 1 个 `worldbuilding/` 下的 YAML 文件
2. 严格遵循 `assets/worldview.yaml` 模板的三层结构（_meta + 索引信息 + 完整档案）
3. YAML 格式约束见 `templates/prompt_template.md`
4. 不修改 `project_index.yaml`（写后处理脚本自动更新）
