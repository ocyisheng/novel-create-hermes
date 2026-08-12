---
name: "novel-v2-writing"
description: "V2 写作子技能：为 novel-writer 提供写作角色定位与专属参考。共享操作层见 novel-v2-core（必须与 novel-v2-core 一起加载）。触发词：写作、物化、单元内容、关系构建"
license: "MIT"
version: "2.0.0"
compatibility: "OpenCode"
tags: ["novel", "v2", "writing", "writer", "graph", "content"]
---

# novel-v2-writing

## 定位

本技能为 **novel-writer** 主 agent 提供写作角色的定位与专属参考。

> **必读**：角色路由、上下文契约、novel-tool 操作指南、HARD CONSTRAINTS 全部在 **novel-v2-core** 中。本技能与 `novel-v2-core` 成对加载：`load_skills=["novel-v2-core", "novel-v2-writing"]`。

负责：
- 单元内容创作与优化（scene / chunk / character_arc / world_rule / thematic_motif / narrative_voice）
- 关系构建与验证（add_relation / remove_relation / update_relation）
- 质量检查与偏差管理（quality_check / deviation）
- 上下文预热与结构化（session.start / build_workspace）
- 写后处理（写前检查 R7-R10 → 物化 → 偏差检核 + 质量自检）

## 领域参考

写作角色专属参考（本技能目录）：

- `references/writing/` — 写作流程与最佳实践（scene / chunk / character_arc / world_rule / thematic_motif / narrative_voice）
- `references/writing/content字段参考.md` — content 字段规范

共享参考（在 novel-v2-core）：

- `novel-v2-core/references/planning/` — 结构化规划参考（structure / plot_thread / note）
- `novel-v2-core/references/relation_guide.md` — 关系操作指南

## 与其他技能的关系

- 操作层：`novel-v2-core`（必读）
- 方法论横切：`novel-six-dimensions`（六维冲突设计）
- 文本后处理：`humanizer-zh-enhanced`（去 AI 味）
- 搜索核验：`novel-search-analysis`（写前查重 / 一致性检查）
