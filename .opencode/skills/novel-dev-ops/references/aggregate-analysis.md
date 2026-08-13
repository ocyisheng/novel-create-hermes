# 聚合分析流程（附录 B）

用户说"分析优化线索"/"综合分析"时执行。读取本项目所有历史总结，聚合同类优化线索，输出优先级排序的改进清单。

## B.1 收集线索

1. 调用 `novel-tool(operation="summary.list", project="{PROJECT}")` 获取**主 Agent** 会话总结索引（默认只含 `record_type="main"`）
2. 对每条索引调用 `novel-tool(operation="summary.read", project="{PROJECT}", file="{filename}")` 读取内容
3. 调用 `novel-tool(operation="summary.list", project="{PROJECT}", record_type="subagent")` 获取子 Agent 总结索引，对每条 `summary.read(record_type="subagent")` 读取内容——**子 Agent 的失败复盘与优化线索同样进聚合**（与主会话同构）
4. 从每份总结的 `### 优化线索` 段落中提取结构化线索行（格式 `[类型][严重程度] 组件：描述（证据：...）`），主会话与子 Agent 同一提取规则
5. **记录来源文件名**：为每条提取的线索标记来源 `{filename}`，供 B.4 持久化时组装 `sources` 证据链（子 Agent 来源为其 `.subagent.md` 文件名）

## B.1.5 路由分歧检测

在同一项目的多份总结（主 Agent 的 `### 意图与路由` + 子 Agent 的 `## 用户意图`）中，检测同一意图类型是否走了不同路由路径：

**判断逻辑**：
1. 从每份总结提取用户意图与路由路径：
   - 主 Agent 总结：`### 意图与路由` 段落的 `用户意图：{描述}` 与 `路由路径：{分支名}`
   - 子 Agent 总结：`## 用户意图` 段落；路由路径取其 frontmatter/index 的 `subagent` 类型（explore / novel-writer / novel-planner / novel-diagnose / novel-lore-search / novel-book-importer）
2. 对用户意图做模糊归类（按关键词分组，如含"检查"/"找找"归为搜索类，含"写第"/"写作"归为创作类）
3. 同一类意图在不同总结中走了不同路由路径 → 标记为 `[workflow][auto] 路由分歧`
4. 同一意图在不同总结中走了相同路径但结果不一致 → 标记为 `[workflow][auto] 执行不一致`

**自动生成的线索格式**：

```
<!-- 自动检测，无需人工标注 -->
- [workflow][auto] 路由树：同类意图「{归类名}」走了 {N} 个不同路径
  路由分布：
  · {路径A}: {M1} 次
  · {路径B}: {M2} 次
  涉及总结：{filename1}、{filename2}
  建议：检查 §2 路由树对该类意图的分支条件是否与其他 §3.x 决策表一致
```

> 路由分歧检测只产生 `[auto]` 级别的线索（严重程度固定为 `low`，不参与自动升级），供人工审查时参考。不会自动触发优化闭环。

## B.2 归并聚类

按 `类型 + 组件` 作为聚类键，将所有线索归并：

```
聚类示例：
- [schema][graph_store] × 3次 → "timeline_unit 缺少 location 字段"
  - 第1次 (low): 时间线事件无法标注位置
  - 第2次 (medium): 与分卷大纲位置冲突需手动排查
  - 第3次 (medium): 角色移动路径缺少起点终点
- [prompt][orchestrator.md] × 2次 → "路由表缺少时间线查询分支"
  - 第1次 (low): 简单查询走了深度诊断
  - 第2次 (low): 用户问"韩致在哪出现过"触发了 cross-ref
```

**严重程度自动升级规则**：

脚本类（schema / handler / tool / skill）：
- 同一聚类出现 ≥ 3 次 → 自动升级为 `critical`
- 同一聚类出现 2 次 → 自动升级为 `high`
- 仅出现 1 次 → 保持原严重程度

流程类（workflow / prompt）：
- 同一聚类出现 ≥ 2 次 → 自动升级为 `critical`
- 同一聚类出现 1 次 → 自动升级为 `high`（因为一次流程缺陷可能导致多轮无效操作）

**线索完整性校验**（仅流程类）：
- 如果 workflow/prompt 线索的「过程回放」字段缺失 → 标记为 `incomplete`
- `incomplete` 线索在输出清单中排在所有完整线索之后
- 聚合分析报告顶部输出：`⚠ {N} 条流程类线索缺失过程回放，需补充后再分析`

## B.3 输出改进清单

按严重程度降序排列，输出：

```markdown
## 优化线索聚合分析（共 {N} 份总结，{M} 条线索，{K} 个聚类）

### critical（阻塞工作流，建议立即修复）
1. **[schema] graph_store**：timeline_unit 缺少 location 字段（出现 3 次）
   - 影响：时间线与分卷大纲无法自动校验位置一致性
   - 证据链：[2026-07-21 位置冲突] [2026-07-22 角色路径断裂] [2026-07-23 移动节点缺失]
   - 建议：在 timeline_event 单元 schema 中增加 `location` 和 `volume_ref` 字段

### high（反复出现，建议近期修复）
...

### medium（偶发问题，可排期处理）
...

### low（仅出现一次，记录备查）
...
```

## B.4 持久化分析结果

通过命令写入引擎级存储 `.engine/analysis/clues_YYYYMMDD_HHMMSS_fff.md`（跨项目共享），供优化闭环流程读取：

```text
novel-tool(operation="analysis.save", content="{改进清单全文}", sources={["{来源文件名1}", "{来源文件名2}"]}, project="{项目名，可选}")
```

`sources` 传入本次聚合所读取的全部 summary 文件名（B.1 第 4 步记录），写入清单头部 JSON front-matter 作为证据链（格式与 summary 存储一致）：

```markdown
---
{"sources": ["凡人之诡影重重_2026-07-27_025440.summary.md", "凡人之诡影重重_2026-07-29_030746.summary.md"], "aggregated_at": "2026-07-31T21:00:00+08:00", "total_summaries": 2, "project": "凡人之诡影重重"}
---
```

每次 save 生成**独立的版本化文件**（毫秒级防同秒冲突），并**自动登记 `.engine/analysis/index.json`**（与 summaries/subagents 的 index.json 同模式）——条目含 `file / timestamp / project / sources / total_summaries / clues（从正文提取的线索标识列表）/ resolved（已修复线索）`：

```text
novel-tool(operation="analysis.read")                      # 读取最新改进清单（自动返回 sources + clues + resolved 状态）
novel-tool(operation="analysis.read", file="{文件名}")     # 读取指定版本
novel-tool(operation="analysis.list")                      # 列出全部版本（含各自线索与修复状态，resolved_count 汇总）
```

### B.4.1 标记线索已修复（analysis.resolve）

修复后标记对应线索，避免新一轮 DEV 重复报告：

```text
novel-tool(operation="analysis.resolve", clue="{线索标识}", note="{修复说明}")                # 默认标记最新清单
novel-tool(operation="analysis.resolve", file="{清单文件名}", clue="{线索标识}", note="{修复说明}")  # 指定版本
```

`clue` 用线索标识（如 `[workflow] 规划主 agent·创建/拆分前查重`），支持包含匹配（传子串即可命中）；未命中清单线索列表时按原样记录（宽容模式）。修复状态写入 index.json 对应条目的 `resolved` 列表（含 `resolved_at` 与 `note`），供下一轮聚合读取。

### B.4.2 新一轮聚合识别已修复线索

新一轮聚合分析前，先读取历史修复状态：

```text
novel-tool(operation="analysis.list")
```

从返回的 `entries[].resolved` 收集已修复线索集合。聚类生成新清单时：
- 已 resolve 且本轮无新证据 → 标注 `✅ 已修复（{resolved_at}）`，不再列为待办
- 已 resolve 但本轮出现新证据 → 重新列为线索（可附注"此前标记已修复，本轮复发"）
- 未 resolve → 正常列为待办

这样已优化过的问题不会在新一轮 DEV 中重复出现。
