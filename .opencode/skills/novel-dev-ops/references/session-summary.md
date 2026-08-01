# 会话总结流程（附录 A）

**适用范围**：主 Agent 会话总结与子 Agent 调用总结使用**同一套流程**（回顾 → 生成 → 保存 → 确认，A.1-A.4），仅存储区分——主 Agent 存 `.engine/summaries/`（`record_type="main"`），子 Agent 存 `.engine/subagents/`（`record_type="subagent"`）。主 Agent 由用户触发（"记录这次会话的总结"）；子 Agent 由 T1 在每次 `task()` 返回后自动触发。以下流程两者通用，子 Agent 的回顾维度映射见 SKILL.md §1。

用户说"记录这次会话的总结"/"记录总结"时，执行以下流程：

## A.1 回顾对话

编排层回顾本轮对话（从用户首次请求到当前），提取：
- **意图识别**：用户一开始想做什么，是否有模糊→收敛的过程
- **路由决策**：走的是哪条路径（crafter/ideation/search-analysis/direct-tool）
- **工具调用**：调用了哪些 novel-tool 操作，参数是什么，结果如何
- **子agent调用**：调度了哪些子agent（crafter/ideation/search-analysis），参数是什么，执行结果如何，会话ID是多少
- **冲突决策**：是否有两难选择，用户做了什么决策
- **诊断发现**：会话中是否涉及错误/偏差/一致性问题的诊断。如有，记录：
  - 发现了什么（具体错误类型、涉及的实体/单元）
  - 错误模式（如"韩家角色 × 鬼道反派 系统性 `allied_with` 误标"）
  - 根因分析（自动推断误判/人工录入错误/跨单元不一致）
  - 是否已修复（resolved/pending/retained）
- **失败复盘**：是否有工具调用失败，原因是什么
- **迭代过程**：是否有需要多轮修正才能收敛的操作。记录每一轮的：
  - 我做了什么（工具/参数/判断）
  - 用户纠正了什么（用户的具体反馈）
  - 根因分析（为什么这轮会错）
  - 最终如何收敛
- **优化线索**：是否发现 prompt/handler/schema 需要改进的地方（参见 A.2 结构化格式）

## A.2 生成结构化总结

输出格式：

```markdown
## 会话总结

### 意图与路由
用户意图：{原始请求}
路由路径：{走了哪条分支}

### 工具调用
- novel-tool {操作名} × N → {成功/失败/具体问题}
- novel-tool {操作名} × N → ...

### 子agent调用（如有）
- {子agent类型}({焦点类型}:{焦点名称}) × N → {成功/失败/具体问题} → 详见 `subagents/{YYYY-MM}/{文件名}.subagent.md`
- {子agent类型}({焦点类型}:{焦点名称}) × N → {成功/失败/具体问题} → 详见 `subagents/{YYYY-MM}/{文件名}.subagent.md`

> **单一数据源**：子 Agent 调用的完整结构化总结（任务摘要/结果摘要/冲突决策/失败复盘/优化线索）由 T1 独立落盘到 `.engine/subagents/`，此处仅保留一行简引用于关联追溯，**不再内联完整摘要**（避免与 `subagent.md` 双写）。读取详情用 `summary.read(record_type="subagent")`。

### 冲突决策（如有）
{选择题} → 用户选择 {X} → 依据：{用户给的理由或推断的理由}

### 诊断发现（如有）
会话中深度检查/修复错误偏差时记录。格式：

- [维度] 实体A ↔ 实体B：问题描述 → 根因 → 状态
- [relation_semantic] 韩松 ↔ 鬼两：标记为 allied_with，但王护法曾重创韩松 → 应为 hostile_to → ✅ resolved

### 失败复盘（如有）
1. {失败现象} → 原因：{根因} → 解决：{怎么修的}

### 优化线索（如有）

线索分两种格式，根据类型选择：

**① 简格式**（schema / handler / tool / skill 等脚本类问题，有明确堆栈或数据路径）：
```text
<!-- 格式：- [类型][严重程度] 组件名：描述（证据：来源） -->
- [schema][medium] graph_store：timeline_unit 缺少 location 字段，导致时间线与分卷大纲无法自动校验（证据：时间线事件与分卷大纲的位置冲突需手动排查）
```

**② 过程追踪格式**（workflow / prompt 等流程类问题，需记录决策迭代才能定位根因）：

``` text
<!-- 格式：- [类型][严重程度] 组件名：根本问题 -->
<!-- 过程回放：每轮记录 操作→纠正→根因，直到收敛 -->
- [workflow][high] 编排层·跨卷角色路径规划：缺少跨卷关键事件列表前置检查
  过程回放：
  · 第1轮：凭单卷数据规划吕风路径（救韩林后同行走完整卷）
    → 用户纠正：中途走散了，不是一路
    → 根因：未加载吕风的关键事件列表，不知道千竹教→竹南岛的过渡
  · 第2轮：改为走散后韩致独自到风都国
    → 用户纠正：千竹教→竹南岛→风都国，漏了两个中间节点
    → 根因：单卷 chapter_plan 只覆盖到本卷终点，不包含跨卷过渡节点
  · 第3轮：补千竹教+竹南岛过渡再重逢
    → 用户纠正：重逢是碰上的不是找到的，极西之地地理隔绝限制了主动寻找
    → 根因：忽略了 distance 元数据对角色行动逻辑的约束
  最终收敛：跨卷角色路径 = 加载角色关键事件列表 → 标注过渡节点 → 检查地理约束 → 再执行
  缺失的流程节点：编排层在处理跨卷角色路径前，应先调 `novel-tool(operation="graph.get_neighbors", id="{character_arc ID}")` 获取关键事件列表
  证据：2026-07-24 吕风路径规划 3 轮修正才收敛
```

**过程追踪格式字段说明**：

| 字段 | 说明 |
|------|------|
| 过程回放 | 每轮记录「我的操作 → 用户纠正内容 → 根因分析」 |
| 最终收敛 | 多轮后正确的方案是什么 |
| 缺失的流程节点 | 如果能定位到编排流程中具体缺了哪一步，写在这里 |
| 证据 | 时间 + 场景，便于聚合时溯源 |

**简格式字段说明（同原规范）**：

| 字段 | 可选值 | 说明 |
|------|--------|------|
| 类型 | `schema` / `prompt` / `handler` / `skill` / `workflow` / `tool` | 问题归属的改进维度 |
| 严重程度 | `critical` / `high` / `medium` / `low` | 是否阻塞当前工作流 |
| 组件 | 具体文件名或模块名 | 如 `graph_store.py`、`novel-v2 skill`、`handlers_graph.py` |
| 描述 | 一句话说明问题 | 简洁、具体、可操作 |
| 证据 | 来源说明 | 本次会话中哪个现象触发了这条线索 |

> 聚合分析时，相同类型+组件的线索会自动归并。workflow/prompt 类线索如果缺失「过程回放」字段会被标记为 `incomplete`，需在下次会话中补充。见聚合分析流程 B。

## A.3 保存总结

通过 novel-tool tool 函数调用（**不要**使用 PowerShell CLI 格式）。保存形式按 Agent 类型区分（同一流程，`content` 都是正文，`record_type` 只决定存储路径）：

**主 Agent（`record_type="main"`，存 `.engine/summaries/`）**：
```
novel-tool(operation="summary.save", project="{PROJECT}", content="{生成的总结内容}", focus_type="{焦点类型}", focus_name="{焦点名称}", tags="{逗号分隔的标签}")
```

**子 Agent（`record_type="subagent"`，存 `.engine/subagents/`）**：
```
novel-tool(operation="summary.save", project="{PROJECT}", record_type="subagent",
  content="{生成的总结内容}",
  task_id="{bg_xxx / ses_xxx}", subagent="{子agent类型}", focus_type="{焦点类型}", focus_name="{焦点名称}",
  result="success", new_units="{新建单元数}", updated_units="{更新单元数}",
  tags="{逗号分隔的标签}")
```

> `content` 对主/子 Agent 一视同仁（整篇 Markdown 正文）；结构化字段（`task_id`/`subagent`/`result`/`new_units`/...）是**元数据**，写入 frontmatter 供过滤与聚合分析，不参与正文组装。content 为空时子 Agent 回退用结构化字段组装分节（兼容旧调用）。

**焦点字段获取规则**：
- `focus_type`：当前操作涉及的主要叙事单元类型（如 `character_arc`、`scene`、`note`）。多焦点操作用 `multi`，纯查询无焦点用空字符串
- `focus_name`：当前操作涉及的具体单元名称（如 `韩致`、`第1卷大纲`）。多焦点时用 `multi`，无焦点时留空

**标签选取规则**（用于聚合分析的分类维度）：
- 涉及冲突决策 → `冲突决策`
- 有工具调用失败 → `失败复盘`
- 有系统性诊断发现 → `诊断发现`
- 发现 prompt/handler/schema 问题 → `优化线索`
- 纯创作（无异常）→ `正常创作`

## A.4 返回确认

**仅主 Agent 场景执行**（用户主动请求的总结，需向用户确认）。保存后回复用户：
```
✅ 会话总结已保存（{累计条数} 条记录）
焦点：{focus_type}:{focus_name}
标签：{tags}
```

**子 Agent 场景不执行本环节**：T1 在 task() 返回后自动触发，属静默保存——不回复用户、不打断创作对话。用户主动查看总结时，通过 `summary.list` / `summary.read` 汇报。
