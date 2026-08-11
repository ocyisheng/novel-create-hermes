---
name: "novel-dev-ops"
description: "开发模式工具集：子 Agent 调度摘要(telemetry)、数据分析、会话总结、聚合分析、优化闭环。仅当运行时模式（novel-context.md 的 __MODE__）非 release 时由 4 个主 agent（router/planner/writer/analyzer）加载。触发词：收集使用数据、分析数据、分析遥测、看故障模式、记录总结、会话总结、历史总结、优化线索、综合分析、更新优化线索、优化闭环、执行改进"
license: "MIT"
version: "1.0.0"
compatibility: "OpenCode"
tags: ["novel", "dev", "telemetry", "analytics", "v2"]
---

# 开发模式工具集（novel-dev-ops）

## 定位

本技能承载 4 个主 agent（router/planner/writer/analyzer）的**开发模式工具**——遥测记录、数据分析、会话总结、聚合分析、优化闭环。仅在运行时模式（`.context/novel-context.md` 的 `__MODE__`，默认 `release`）非 `release` 时加载。

**加载方式**：4 个主 agent（router/planner/writer/analyzer）在处理任何请求之前读取 `__MODE__`，非 `release` 时均调用 `skill("novel-dev-ops")` 加载本技能；`__MODE__: release`（默认）时**不加载**，主 agent prompt 保持精简。

## 能力一览

| 能力 | 入口 | 详情 |
|------|------|------|
| 遥测记录 | 用户请求"会话总结"时，回顾本次对话中的所有 Task | §1 |
| 数据分析 | "收集使用数据" / "分析数据" / "看故障模式" | §2 |
| 会话总结 | "记录这次会话的总结" / "记录总结" | §3 + `references/session-summary.md` |
| 聚合分析 | "分析优化线索" / "综合分析" | §4 + `references/aggregate-analysis.md` |
| 优化闭环 | "优化闭环" / "执行改进" | §5 + `references/optimization-loop.md` |

## 上下文契约

> 由主 agent 提供 `CURRENT PROJECT`（项目名）与 `PROJECT PATH`（项目绝对路径）。所有 novel-tool 调用均携带 `project` 参数。

## §1 遥测记录（规则 T1）

**触发条件**：dev模式下，用户请求"会话总结"时，回顾本次对话中所有 `task()` 调用，为每个未保存的子Agent补充生成子agent总结。

**执行流程**：
```
用户请求"会话总结"（且 __MODE__: dev）
  ↓
回顾本次对话，识别所有 task() 调用（提取 task_id / subagent_type / focus 等信息）
  ↓
检查 .engine/subagents/ 中是否已有对应总结
  ↓
为未保存的子Agent执行会话总结流程（与 §3 A.1-A.4 一致）：
  任务摘要    ← prompt 意图（对齐 A.1「意图识别」）
  结果摘要    ← 产出与结果状态（对齐 A.1「工具调用/子agent调用」的成效）
  用户意图    ← 用户原始输入（供路由分歧检测）
  冲突决策    ← 取舍与依据（对齐 A.1「冲突决策」）
  失败复盘    ← 失败原因/被否决方案（对齐 A.1「失败复盘」）
  错误信息    ← 具体错误摘要（如有）
  优化线索    ← 发现的可改进点（对齐 A.1「优化线索」）
  ↓
生成结构化总结（A.2 Markdown content）→ 调用 summary.save 落盘 .md 总结（record_type="subagent"，content 为正文）
  ↓
继续执行主 Agent 会话总结（§3 A.1-A.4）
```

**维度映射说明**：子 Agent 通常单轮执行，A.1 九维度中「路由决策/工具调用」信息已并入任务/结果摘要；「诊断发现」如有并入失败复盘或结果摘要；「迭代过程」如有多轮修正并入失败复盘。

> **子 Agent 总结与主 Agent 同一流程：`content`（整篇 Markdown）即正文，`record_type="subagent"` 只决定存储路径与 frontmatter 元数据**；结构化字段（`task_id`/`subagent`/`result`/`new_units`/...）是元数据，供过滤与聚合分析。content 为空时子 Agent 回退用结构化字段组装分节（兼容旧调用）。

**不存原始对话**——与主 agent 会话同规：原始内容留在运行时层（opencode 会话），凭 `task_id` 可回溯。存储与 summary 同一套脚本（`handlers_summary.py`），仅 `record_type` 区分来源、路径分流：

```
主 Agent 会话总结  →  .engine/summaries/{YYYY-MM}/{project}_{ts}.summary.md   （summary.save 默认 main）
子 Agent 调用总结  →  .engine/subagents/{YYYY-MM}/{project}_{ts}.subagent.md   （summary.save record_type="subagent"）
```

两者各自独立 `index.json`，文件结构（frontmatter JSON 单行 + 分节正文）完全一致，便于人工阅读与聚合分析。

```text
# 保存结构化总结（tool 函数调用格式，勿用 PowerShell CLI；主/子 Agent 同一入口，record_type 区分）
# 主 Agent 会话总结
novel-tool(operation="summary.save", project="{PROJECT}",
  content="{A.2 整篇 Markdown 总结}",
  focus_type="{焦点类型}", focus_name="{焦点名称}",
  tags="正常创作,优化线索")               # record_type 省略，默认 main

# 子 Agent 调用总结（record_type="subagent"，content 为正文，结构化字段是元数据）
novel-tool(operation="summary.save", project="{PROJECT}", record_type="subagent",
  content="{A.2 整篇 Markdown 总结}",
  task_id="{bg_xxx | ses_xxx}",
  subagent="explore",
  focus_type="chapter_plan",
  focus_name="第53章",
  result="success",
  new_units=0,
  updated_units=8,
  duration_estimate_ms=3500,
  user_intent="帮我看一下第53-60章章纲",   # 用户原始输入摘要，用于路由分歧检测
  tags="正常创作,优化线索")               # 逗号分隔标签

# 查询/读取总结（record_type 区分主/子 Agent）
novel-tool(operation="summary.list", project="{PROJECT}", limit=10)              # 默认只列主 Agent 会话总结
novel-tool(operation="summary.list", project="{PROJECT}", record_type="subagent") # 只列子 Agent 调用总结
novel-tool(operation="summary.list", project="{PROJECT}", record_type="")         # 全部（合并两索引）
novel-tool(operation="summary.list", project="{PROJECT}", record_type="subagent", subagent="explore", result="failed")  # 按类型/结果过滤
novel-tool(operation="summary.read", project="{PROJECT}", file="{文件名}")        # 读主 Agent 总结（默认 main）
novel-tool(operation="summary.read", project="{PROJECT}", record_type="subagent", file="{文件名}")  # 读子 Agent 总结
```

## §2 数据分析路由

| 用户意图 | 操作 |
|---------|------|
| "收集使用数据" / "分析数据" | `novel-tool(operation="analyze.usage", project="{PROJECT}")` → 输出量化报告 |
| "分析遥测数据" / "看故障模式" | `novel-tool(operation="analyze.telemetry", project="{PROJECT}")` → 输出故障模式和优化建议 |
| "查看会话总结" / "历史总结" | `novel-tool(operation="summary.list", project="{PROJECT}")` — 默认只列主 Agent 会话总结；要含子 Agent 调用总结用 `record_type=""`（全部）或 `record_type="subagent"` |

## §3 会话总结

**统一流程，覆盖主 Agent 与子 Agent**：会话总结 = 回顾 → 生成结构化总结 → 保存 → 确认（A.1-A.4，子 Agent 确认环节豁免、静默保存，见 A.4），主 Agent 会话总结与子 Agent 调用总结走同一流程，**仅存储区分**（`record_type` 与路径，见 §1）：

- **主 Agent**：用户说"记录这次会话的总结"/"记录总结"时触发 → `summary.save`（默认 `record_type="main"`，存 `.engine/summaries/`）
- **子 Agent**：用户请求"会话总结"时，由 §1 T1 回顾本次对话中的 Task 调用并补充生成 → `summary.save`（`record_type="subagent"`，存 `.engine/subagents/`）

**完整流程见 `references/session-summary.md`**（A.1-A.4 两者通用，A.4 确认环节子 Agent 豁免），要点：

- **A.1 回顾对话**：意图识别、路由决策、工具调用、子 agent 调用、冲突决策、诊断发现、失败复盘、迭代过程、优化线索
- **A.2 生成结构化总结**：含两种优化线索格式（简格式 + 过程追踪格式）
- **A.3 保存**：主 Agent → `summary.save(content="{总结内容}", ...)`；子 Agent → `summary.save(record_type="subagent", content="{总结内容}", 结构化元数据...)`；`record_type` 只决定存储路径
- **A.4 返回确认**：仅主 Agent 场景执行（回复保存位置与焦点/标签）；子 Agent 总结在主 Agent 会话总结中确认

## §4 聚合分析

用户说"分析优化线索"/"综合分析"/"更新优化线索"时执行。读取本项目所有历史总结，聚合同类优化线索，输出优先级排序的改进清单。

**完整流程见 `references/aggregate-analysis.md`**，要点：

- **B.1 收集线索**：`summary.list`（主 Agent）→ 逐条 `summary.read`；`summary.list(record_type="subagent")`（子 Agent）→ 逐条 `summary.read(record_type="subagent")` → 提取 `### 优化线索` 段落的结构化行 → 记录来源文件名（含 B.1.5 路由分歧检测）
- **B.2 归并聚类**：按 `类型 + 组件` 聚类，严重程度自动升级规则，流程类线索完整性校验
- **B.3 输出改进清单**：按严重程度降序
- **B.4 持久化**：`novel-tool(operation="analysis.save", content="{改进清单全文}", sources={["{来源文件名}"]}, project="{项目名，可选}")` → `.engine/analysis/clues_YYYYMMDD_HHMMSS_fff.md`（版本化文件，自动登记 `index.json`，含线索清单 + 修复状态）
- **B.4.1 修复标记**：修复后 `analysis.resolve(clue="{线索标识}", note="{说明}")` → 写入 index.json 的 resolved 列表
- **B.4.2 新轮去重**：新一轮聚合前 `analysis.list` 读取已 resolve 线索 → 跳过/标注，避免重复报告

## §5 优化闭环

聚合分析产出改进清单后，主 agent 将其映射为具体改进任务。

**完整流程见 `references/optimization-loop.md`**，要点：

- **C.1 改进维度映射**：`schema` / `prompt` / `handler` / `skill` / `workflow` / `tool` → 改进目标 + 多步可执行清单
- **C.2 生成改进任务清单**：`analysis.read` 读取清单 → 转化为具体任务（含来源线索、过程回放、改动范围、验证方式）
- **C.3 执行策略**：用户确认后执行、按维度并行、最小改动原则
- **C.4 反馈验证**：修复后用 `analysis.resolve` 标记线索已解决；新一轮聚合通过 `analysis.list` 识别已修复线索，对比版本区分遗留/新/已消除线索

## HARD CONSTRAINTS

1. **仅开发模式加载** — `__MODE__: release`（默认）时主 agent 不加载本技能
2. **不存原始对话** — `summary.save(record_type="subagent")` 只存摘要，凭 `task_id` 回溯完整对话
3. **不自动执行改进** — 优化闭环的任务清单必须等用户确认后再执行
4. **最小改动原则** — 每次改进只改必要文件，不顺带重构
5. **会话总结时补充子Agent** — 遥测记录不在 task() 返回后自动执行，而是在用户请求会话总结时回顾并补充
6. **不产出 graph 数据偏差** — 不写 `graph/deviation_state.yaml`（偏差管理由 novel-search-analysis 负责）

## 参考文件

| 文件 | 内容 |
|:----|:-----|
| `references/session-summary.md` | 会话总结完整流程（A.1-A.4） |
| `references/aggregate-analysis.md` | 聚合分析完整流程（B.1-B.4 + B.1.5 路由分歧检测） |
| `references/optimization-loop.md` | 优化闭环完整流程（C.1-C.4） |
