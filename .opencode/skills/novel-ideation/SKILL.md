---
name: "novel-ideation"
description: "创意方案生成：基于约束库和焦点上下文，为下游 crafter 生成可选方案。不直接操作 graph，输出为自然语言方案清单。供规划主 agent（novel-planner）通过 subagent_type='novel-ideation' + load_skills=['novel-ideation'] 调度。触发词：创意、构思、方案、方向、灵感"
license: "MIT"
version: "4.0.0"
compatibility: "OpenCode"
tags: ["novel", "ideation", "v2"]
---

# 创意方案生成技能（V2）

## 定位

本技能供规划主 agent（novel-planner）通过 `subagent_type="novel-ideation"` + `load_skills=["novel-ideation"]` 调度时注入。ideation 是 grill 和 crafter 之间的可选步骤——grill 收敛需求后，规划主 agent（novel-planner）可选择是否让 ideation 生成几套方案。

ideation 是**只读**步骤——输出仅通过 task 响应文本传递，**MUST NOT 写入 graph**（不调用任何 graph 写操作）。由规划主 agent（novel-planner）直接消费并注入 crafter TASK。

## 操作模式

### divergent — 纯概念发散

**场景**：用户想创建全新项目，尚无焦点单元。

**输入**：`### 创作需求`（来自 grill，含类型/基调/核心元素）

**方法**：
1. 从 `references/constraints_library.md` 按类型推荐组合选取 3-5 个约束
2. 按 `references/genres_compendium.md` 定位类型特征
3. 在约束框架内生成 3-5 个概念方向

**输出**：按 `references/ideation_mode.md` 内容构成输出 3-5 个自然语言方向

### focused — 方案生成

**场景**：用户已有焦点单元，需要基于已有体系生成可选方案。

**输入**：
- `### 创作需求`（来自 grill）
- FOCUS TYPE（scene/character_arc/plot_thread/world_rule/narrative_voice/thematic_motif/structure）/ FOCUS ID / FOCUS NAME + 焦点单元 1 度邻居
- 可选：`### 知识库参考`（规划主 agent（novel-planner）注入，用于 with_knowledge 场景）

**方法**：
1. 阅读焦点单元邻居（已有角色/设定/情节线）
2. 结合 grill 需求作为约束条件
3. 从 `references/constraints_library.md` 选取匹配的约束
4. 在已有框架内生成 3 个不冲突的方案

**输出**：按 `references/ideation_mode.md` 内容构成输出 3 个自然语言方案

## 输出格式

按 `references/ideation_mode.md` 的内容构成要求组织每个方案。每个方案用标题分隔，自然语言描述，无需 YAML 或代码块包装。

## 核心约束

1. 每个方案必须包含"如何落地到当前项目"的具体路径
2. focused 模式下必须验证与已有单元的兼容性
3. 方案必须基于约束，不能是无约束的随意发散
4. 仅通过响应文本传递，**MUST NOT 写入 graph**（只读）

## 参考文件
- `references/constraints_library.md` — 30 个约束模板 + 组合策略
- `references/genres_compendium.md` — 5 大类型总览 + 融合指南
- `references/ideation_mode.md` — 方案内容构成指南
- `references/genres_quick_reference.md` — 类型快速诊断
