# V2 项目结构

V2 项目使用 `graph/` 作为**单一真相源**，全部创作数据通过 novel-tool（底层 GraphStore API）读写。`chapters/`、`characters/`、`worldbuilding/`、`outline/分纲/` 目录由 ProjectionEngine 从 graph 自动投影生成（派生视图，按需重建，勿直接编辑）；`ideation/` 目录 V2 不再生成。

```
{项目名}/
├── config.yaml              # 项目配置（含 架构: v2 标记）
├── graph/                   # 叙事单元网络（真相源）
│   ├── nodes.jsonl          # 全部叙事单元
│   ├── edges.jsonl          # 单元间关系
│   ├── events.olog          # 事件溯源日志
│   └── snapshots/           # 时间点快照
├── chapters/                # 章节正文（投影生成，勿直接编辑）
├── characters/              # 角色档案（投影生成，勿直接编辑）
├── worldbuilding/           # 世界观设定（投影生成，勿直接编辑）
├── outline/分纲/            # 分卷分纲（投影生成，勿直接编辑）
├── quality/                 # 质量检测报告（由 ProjectionEngine 投影生成）
├── styles/                  # 写作风格定义
└── output/                  # 导出产物
```

> **注**：`.engine/`（引擎级存储）与 `.omo/`（OpenCode 运行时记忆）均位于**工具根目录**（`novel-create-hermes/`），跨项目共享，不在各小说项目目录内：
> ```
> .engine/
> ├── analysis/            # 改进清单（如 clues_aggregated.md）
> ├── daemon/              # daemon 运行日志
> ├── telemetry/           # 工具调用遥测（按天分片 ndjson）
> ├── subagents/           # 子 Agent 调度摘要
> ├── summaries/           # 会话总结
> └── web-server/          # Web 服务日志与状态
>
> .omo/
> ├── notepads/
> └── plans/
> ```
> `.engine/` 子目录由 orchestrator 维护、代码层不读写（`subagents/`/`summaries/` 除外——由 novel-tool 操作写入）。

## graph 文件说明

| 文件 | 内容 | 维护方式 |
|------|------|---------|
| `graph/nodes.jsonl` | 全部叙事单元（场景/角色弧线/情节线/世界观规则/笔记/正文片段/结构设计/叙述腔调/主题意象） | novel-tool(operation="graph.*") 自动维护 |
| `graph/edges.jsonl` | 单元间关系（26 种类型，含成对正/逆） | novel-tool(operation="graph.*") 自动维护 |
| `graph/events.olog` | 事件溯源日志（每次修改的记录） | graph.flush 时自动追加 |
| `graph/snapshots/` | 时间点快照 | novel-tool(operation="session.start") 可触发 |

## 核心原则

1. **graph 是单一真相源** — 所有创作数据存储在 graph 中，文件系统只是投影
2. **按需加载** — 通过预热级别（cold/warm/hot）控制加载上下文量，不加载无用数据
3. **操作统一入口** — 所有读写操作通过 `novel-tool` tool，不直接编辑 JSONL 文件
4. **事件溯源** — 每次修改自动记录事件，支持故障恢复和回退
