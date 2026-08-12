---
name: "novel-v2-planning"
description: "V2 规划子技能：为 novel-planner 提供规划角色定位与专属参考。共享操作层见 novel-v2-core（必须与 novel-v2-core 一起加载）。触发词：规划、设计、焦点选择、约束查询、方案生成"
license: "MIT"
version: "2.0.0"
compatibility: "OpenCode"
tags: ["novel", "v2", "planning", "planner"]
---

# novel-v2-planning

## 定位

本技能为 **novel-planner** 主 agent 提供规划角色的定位与专属参考。

> **必读**：角色路由、上下文契约、novel-tool 操作指南、HARD CONSTRAINTS 全部在 **novel-v2-core** 中。本技能与 `novel-v2-core` 成对加载：`load_skills=["novel-v2-core", "novel-v2-planning"]`。

负责：
- 焦点选择与约束查询
- 方案生成与灵感触发（grill → 创意 → 六维）
- 设计讨论与决策记录（唯一写类型：**NOTE 单元**）
- 设计成果写入后通知 downstream（novel-writer 物化）

## 领域参考

规划参考已集中至共享层：

- `novel-v2-core/references/planning/` — 结构化规划参考（structure / plot_thread / note）
- `novel-v2-core/references/relation_guide.md` — 关系操作指南

本技能不再持有重复副本。

## 与其他技能的关系

- 操作层：`novel-v2-core`（必读）
- 需求发现：`novel-grill`（skill() 自执行加载）
- 创意方案：`novel-ideation`（skill() 自执行加载，**非 subagent**）
- 方法论横切：`novel-six-dimensions`（六维冲突设计）
