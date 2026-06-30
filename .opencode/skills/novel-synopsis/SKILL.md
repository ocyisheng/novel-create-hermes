---
name: "novel-synopsis"
description: "总纲与叙事策略：总纲撰写（P4）和叙事策略设计（P4.5）。触发词：总纲、大纲、故事框架、叙事策略、叙事手法、视角"
license: "MIT"
version: "1.0.0"
compatibility: "OpenCode"
tags: ["novel", "synopsis", "outline", "narrative"]
---

# 总纲与叙事策略技能

## 核心职责

按编排 Agent 传入的 CONTEXT 执行两个阶段的创作任务：

|阶段|任务|输出|
|------|------|------|
|P4|总纲撰写|`outline/总纲.yaml` + `outline/时间线设计.yaml`|
|P4.5|叙事策略设计|`outline/叙事策略.yaml`|

> **路径说明**：下文所有 `{PROJECT_PATH}` 替换为编排层 CONTEXT 中传入的 `PROJECT PATH` 值。

## 上下文契约

### P4 总纲撰写

读取创意方案，输出总纲骨架 + 时间线设计。

|槽位|文件路径|提取字段|加载方式|
|------|---------|---------|---------|
|创意方案|`ideation/最终创意方案.yaml`|`最终方案.一句话概述` `最终方案.主角设定` `最终方案.核心冲突` `最终方案.世界观概述`|`read` 全文件后提取以上字段|

输出：
- `outline/总纲.yaml`，参见 `assets/outline.yaml` 模板
- `outline/时间线设计.yaml`，参见 `assets/timeline_plan.yaml` 模板

### P4.5 叙事策略设计

在 P4 总纲完成后、P5 情节构建前执行。读取总纲 + 创意方案，输出叙事策略定义。

|槽位|文件路径|提取字段|加载方式|
|------|---------|---------|---------|
|总纲|`outline/总纲.yaml`|`核心概念` `故事结构` `分卷`|`read` 全文件|
|创意方案|`ideation/最终创意方案.yaml`|`最终方案.类型` `最终方案.基调` `最终方案.主角设定`|`read` 全文件|

输出：`outline/叙事策略.yaml`，参见 `assets/narrative_strategy.yaml` 模板。

**叙事策略定义以下维度**：

|维度|内容|决策要点|
|------|------|-----------------|
|**底层驱动**|故事驱动（"然后呢"）vs 情节驱动（"为什么"）|决定悬念密度和信息分配策略|
|**因果律警戒线**|哪些环节允许因果律断裂、"王后在花园里散步"式的不可解释之美|因果律是叙事的"安全装置"，过度依赖束缚自由|
|**离心力规划**|哪些章为"离心章"（允许偏离主线）、哪些为"向心章"（收敛聚焦）|离题是美学手段，离心与向心交替构成张力|
|**双重时间**|物理时间推进（强制）与价值时间密度（选择）的平衡|彻底脱离时间的小说必定失败|
|**模式与节奏**|模式选择（沙漏/长链/对称/无固定）+ 节奏标记物（重复-展开-变奏的意象/情境）|总纲不必"完成"，应保持"扩展"的开放姿态|

## 输出文件一览

|阶段|文件|模板|写入方式|
|------|------|------|---------|
|P4|`outline/总纲.yaml`|`assets/outline.yaml`|`write` / `edit`|
|P4|`outline/时间线设计.yaml`|`assets/timeline_plan.yaml`|`write` / `edit`|
|P4.5|`outline/叙事策略.yaml`|`assets/narrative_strategy.yaml`|`write`|

## 写后处理（chain: `entity-base`）

输出写入后编排层自动执行以下脚本：

```bash
# 1. YAML 格式修正
python .opencode/shared/fix_yaml_indent.py "outline/{新文件路径}"

# 2. 实体格式校验
python .opencode/shared/validate_entity_format.py --project-root {PROJECT_PATH}

# 3. 项目索引重建
python .opencode/shared/rebuild_project_index.py --project-root {PROJECT_PATH}

# 4. 阶段切换（P4→P4.5 / P4.5→P5）
python .opencode/shared/config_manager.py set 当前阶段 {新阶段} --project-root {PROJECT_PATH}
```

> **禁止**：不要用 `edit`/`write` 手工修正 YAML 缩进或格式——交给 fix_yaml_indent.py 统一处理。你写完文件、标记好内容即可，脚本会自动格式化。

## 参考文件

- `references/synopsis_design.md` — 总纲设计指导（P4）
- `references/narrative_strategy_design.md` — 叙事策略设计指导（P4.5）

## HARD CONSTRAINTS

> 约束已移入 `templates/prompt_template.md`。编排层通过 `extract_template.py` 加载模板时一并注入。
