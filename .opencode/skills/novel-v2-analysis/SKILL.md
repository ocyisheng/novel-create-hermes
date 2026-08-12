---
name: "novel-v2-analysis"
description: "V2 分析子技能：为 novel-analyzer / novel-diagnose 提供分析角色定位与专属参考。共享操作层见 novel-v2-core（必须与 novel-v2-core 一起加载）。触发词：分析、诊断、偏差、质检"
license: "MIT"
version: "2.0.0"
compatibility: "OpenCode"
tags: ["novel", "v2", "analysis", "analyzer", "quality"]
---

# novel-v2-analysis

## 定位

本技能为 **novel-analyzer** 主 agent 与 **novel-diagnose** subagent 提供分析角色的定位与专属参考。

> **必读**：角色路由、上下文契约、novel-tool 操作指南、HARD CONSTRAINTS 全部在 **novel-v2-core** 中。本技能与 `novel-v2-core` 成对加载：`load_skills=["novel-v2-core", "novel-v2-analysis"]`。

负责：
- 偏差检测与分类
- 质量检查与验证（quality_check / constraint.check）
- 优化建议与修复
- 会话分析与统计

## 领域参考

分析角色专属参考（本技能目录）：

- `references/analysis/quality_methodology.md` — 质量检查方法论

## 与其他技能的关系

- 操作层：`novel-v2-core`（必读）
- 诊断方法论：`novel-search-analysis`（4 模式：align / cross-ref / gap / full-diagnose）
- 只读约束：诊断路径只读（`deviation.merge` 是偏差库的写入通道，多方可调用，按 `dimension+entity` 键控合并，见 novel-diagnose agent 契约）
