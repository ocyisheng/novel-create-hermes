---
name: "novel-dev-ops"
description: "开发模式工具集：子 Agent 调度摘要(telemetry)、数据分析、会话总结、聚合分析、优化闭环。仅当 OMODE 非 release 时由编排层 novel-writer 加载。触发词：收集使用数据、分析数据、分析遥测、看故障模式、记录总结、会话总结、历史总结、优化线索、综合分析、更新优化线索、优化闭环、执行改进、subagent.save"
license: "MIT"
version: "1.0.0"
compatibility: "OpenCode"
tags: ["novel", "dev", "telemetry", "analytics", "v2"]
---

# 开发模式工具集（novel-dev-ops）

## 定位

本技能承载 novel-writer 编排层的**开发模式工具**——遥测记录、数据分析、会话总结、聚合分析、优化闭环。仅在 `OMODE` 未设置或非 `release` 时加载。

**加载方式**：编排层在处理任何请求之前调用 `skill("novel-dev-ops")` 加载本技能；`OMODE=release` 时**不加载**，编排层 prompt 保持精简。

## 能力一览

| 能力 | 入口 | 详情 |
|------|------|------|
| 遥测记录 | 每次 `task()` 返回后 | §1 |
| 数据分析 | "收集使用数据" / "分析数据" / "看故障模式" | §2 |
| 会话总结 | "记录这次会话的总结" / "记录总结" | §3 + `references/session-summary.md` |
| 聚合分析 | "分析优化线索" / "综合分析" | §4 + `references/aggregate-analysis.md` |
| 优化闭环 | "优化闭环" / "执行改进" | §5 + `references/optimization-loop.md` |

## 上下文契约

> 由编排层提供 `CURRENT PROJECT`（项目名）与 `PROJECT PATH`（项目绝对路径）。所有 novel-tool 调用均携带 `project` 参数。

## §1 遥测记录（规则 T1）

**每次 `task()` 返回后**，编排层执行以下流程（同会话总结模式）：

```
收到 task() 返回（同步结果 / background_output(id=bg_xxx)）
  ↓
读取 background_output 中的完整对话
  ↓
提取摘要：task_id、subagent 类型、焦点、做了什么、结果如何、用户意图摘要
  ↓
调用 subagent.save 写入 metadata（含 user_intent 字段，用于路由分歧检测）
```

**不存原始对话**——`background_output` 本身是运行时给的，凭 `id` 就能回溯。`subagent.save` 只存 review 后提取的摘要信息。

```text
# 保存摘要（tool 函数调用格式，勿用 PowerShell CLI）
novel-tool(operation="subagent.save", project="{PROJECT}",
  task_id="{bg_xxx | ses_xxx}",
  subagent="explore",
  focus_type="chapter_plan",
  focus_name="第53章",
  result="success",
  prompt_summary="读第53-60章章纲",
  result_summary="返回8个chapter_plan的完整content",
  new_units=0,
  updated_units=8,
  duration_estimate_ms=3500,
  user_intent="帮我看一下第53-60章章纲")   # 用户原始输入摘要，用于路由分歧检测

# 查询摘要
novel-tool(operation="subagent.list", project="{PROJECT}", limit=10)
novel-tool(operation="subagent.list", subagent="explore", result="failed")
```

## §2 数据分析路由

| 用户意图 | 操作 |
|---------|------|
| "收集使用数据" / "分析数据" | `novel-tool(operation="analyze.usage", project="{PROJECT}")` → 输出量化报告 |
| "分析遥测数据" / "看故障模式" | `novel-tool(operation="analyze.telemetry", project="{PROJECT}")` → 输出故障模式和优化建议 |
| "查看会话总结" / "历史总结" | `novel-tool(operation="summary.list", project="{PROJECT}")` |

## §3 会话总结

用户说"记录这次会话的总结"/"记录总结"时，执行完整流程（回顾 → 生成结构化总结 → 保存 → 确认）。

**完整流程见 `references/session-summary.md`**，要点：

- **A.1 回顾对话**：意图识别、路由决策、工具调用、子 agent 调用、冲突决策、诊断发现、失败复盘、迭代过程、优化线索
- **A.2 生成结构化总结**：含两种优化线索格式（简格式 + 过程追踪格式）
- **A.3 保存**：`novel-tool(operation="summary.save", project="{PROJECT}", content="{总结内容}", focus_type="{焦点类型}", focus_name="{焦点名称}", tags="{逗号分隔的标签}")`
- **A.4 返回确认**：回复保存位置与焦点/标签

## §4 聚合分析

用户说"分析优化线索"/"综合分析"/"更新优化线索"时执行。读取本项目所有历史总结，聚合同类优化线索，输出优先级排序的改进清单。

**完整流程见 `references/aggregate-analysis.md`**，要点：

- **B.1 收集线索**：`summary.list` → 逐条 `summary.read` → 提取 `### 优化线索` 段落的结构化行 → 记录来源文件名（含 B.1.5 路由分歧检测）
- **B.2 归并聚类**：按 `类型 + 组件` 聚类，严重程度自动升级规则，流程类线索完整性校验
- **B.3 输出改进清单**：按严重程度降序
- **B.4 持久化**：`novel-tool(operation="analysis.save", content="{改进清单全文}", sources={["{来源文件名}"]})` → `.engine/analysis/clues_aggregated.md`（版本化覆盖，旧版自动归档 `history/`）

## §5 优化闭环

聚合分析产出改进清单后，编排层将其映射为具体改进任务。

**完整流程见 `references/optimization-loop.md`**，要点：

- **C.1 改进维度映射**：`schema` / `prompt` / `handler` / `skill` / `workflow` / `tool` → 改进目标 + 多步可执行清单
- **C.2 生成改进任务清单**：`analysis.read` 读取清单 → 转化为具体任务（含来源线索、过程回放、改动范围、验证方式）
- **C.3 执行策略**：用户确认后执行、按维度并行、最小改动原则
- **C.4 反馈验证**：重新触发聚合分析，对比版本区分遗留/新/已消除线索

## HARD CONSTRAINTS

1. **仅开发模式加载** — `OMODE=release` 时编排层不加载本技能
2. **不存原始对话** — `subagent.save` 只存摘要，凭 `task_id` 回溯完整对话
3. **不自动执行改进** — 优化闭环的任务清单必须等用户确认后再执行
4. **最小改动原则** — 每次改进只改必要文件，不顺带重构
5. **不自动触发递归** — 偏差/优化处理由用户驱动，发现 pending 问题只通知不自动修复

## 参考文件

| 文件 | 内容 |
|:----|:-----|
| `references/session-summary.md` | 会话总结完整流程（A.1-A.4） |
| `references/aggregate-analysis.md` | 聚合分析完整流程（B.1-B.4 + B.1.5 路由分歧检测） |
| `references/optimization-loop.md` | 优化闭环完整流程（C.1-C.4） |
