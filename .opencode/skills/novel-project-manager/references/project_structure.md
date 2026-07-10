# V2 项目结构

V2 项目使用 `graph/` 作为**单一真相源**，不再生成 `characters/`、`worldbuilding/`、`outline/`、`chapters/`、`ideation/` 目录。全部创作数据通过 novel-tool（底层 GraphStore API）读写。

```
{项目名}/
├── config.yaml              # 项目配置（含 架构: v2 标记）
├── graph/                   # 叙事单元网络（真相源）
│   ├── nodes.jsonl          # 全部叙事单元
│   ├── edges.jsonl          # 单元间关系
│   ├── events.olog          # 事件溯源日志
│   └── snapshots/           # 时间点快照
├── quality/                 # 质量检测报告（由 ProjectionEngine 投影生成）
├── styles/                  # 写作风格定义
├── output/                  # 导出产物
└── .omo/                    # OpenCode 运行时记忆
    ├── notepads/
    └── plans/
```

## graph 文件说明

| 文件 | 内容 | 维护方式 |
|------|------|---------|
| `graph/nodes.jsonl` | 全部叙事单元（场景/角色弧线/情节线/世界观规则/笔记/正文片段/结构设计/叙述腔调/主题意象） | novel-tool --operation graph.* 自动维护 |
| `graph/edges.jsonl` | 单元间关系（18 种类型 + 反向关系） | novel-tool --operation graph.* 自动维护 |
| `graph/events.olog` | 事件溯源日志（每次修改的记录） | graph.flush 时自动追加 |
| `graph/snapshots/` | 时间点快照 | novel-tool --operation session.start 可触发 |

## 核心原则

1. **graph 是单一真相源** — 所有创作数据存储在 graph 中，文件系统只是投影
2. **按需加载** — 通过预热级别（cold/warm/hot）控制加载上下文量，不加载无用数据
3. **操作统一入口** — 所有读写操作通过 `novel-tool` tool，不直接编辑 JSONL 文件
4. **事件溯源** — 每次修改自动记录事件，支持故障恢复和回退
