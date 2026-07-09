# novel-create-hermes — 项目上下文指引

## 项目性质

这是一个基于 Agent Skills 的 V2 小说创作工具。当前项目**不是被创作的小说本身**，
而是一个"创作引擎"——以**叙事单元网络（graph）** 为核心存储，提供 6 个技能覆盖从环境安装、
创意构思、写作执行、风格管理、知识库到质量把控的全流程。

V2 架构要点：
- **graph 是单一真相源**：所有数据（角色、场景、设定、章节）都存储在 `graph/nodes.jsonl` + `graph/edges.jsonl`
- **无固定写作顺序**：可以随时写章节、改角色、调设定，数据一致性由 graph 的事件溯源保障
- **按需上下文**：创作时自动收集焦点单元及其邻居，不加载无用数据
- **文件系统只是投影**：`chapters/` `characters/` 等目录由 `ProjectionEngine` 从 graph 生成，不是源存储

## 目录结构

```
novel-create-hermes/              ← 工具项目根目录
├── AGENTS.md                      ← 本文件 — Sisyphus 上下文指引
├── DEVELOPER.md                   ← 开发者文档（五层架构、技能表、工作流）
├── opencode.json                  ← 项目级配置（已注册 6+ 个 skill）
├── README.md                      ← 用户入门指南
├── knowledge/                     ← 结构化知识库（由 book-to-knowledge 生成）
├── .opencode/
│   ├── agents/
│   │   ├── novel-writer.md        ← 主调度 Agent prompt（V2 创作调度中心）
│   │   └── novel-v2-crafter.md    ← V2 统一创作子引擎
│   ├── skills/                    ← 6 个项目技能（novel-v2 / project-manager / env-setup / search-analysis / book-knowledge / book-to-knowledge）
│   └── shared/v2/                 ← V2 引擎核心代码
│       ├── graph_store.py          ← 叙事单元 CRUD + 事件溯源
│       ├── search_engine.py        ← 搜索/一致性检查引擎
│       ├── deviation_manager.py    ← 偏差状态持久化管理
│       ├── v2_cli.py               ← CLI 入口（search/check/report/viz/stats/list-units）
│       ├── v2_cli.py               ← CLI 入口（search/check/report/viz/stats/list-units）
│       ├── v2_graph_viz.py         ← 关系图/时间线可视化
│       ├── projection_engine.py    ← graph → 文件系统投影
│       ├── migrate.py              ← V1 → V2 迁移
│       ├── workspace.py            ← 上下文收集与焦点预热
│       └── schemas.py / adapter.py / session.py / render_utils.py ...
├── .omo/
│   ├── plans/                     ← 小说创作工作计划（非本项目开发计划）
│   └── notepads/                  ← 创作上下文持久化（novel-context.md, novel-issues.md）
└── docs/                          ← 历史开发文档（不代表当前规范）

NOVELS_ROOT/                       ← 小说项目根目录（novel-create-hermes/novels/）
├── .venv/                         ← 共享 Python 虚拟环境
└── {小说名}/                       ← 单个小说项目
    ├── config.yaml                ← 项目配置（架构、风格、目标字数的）
    ├── graph/                     ← V2 叙事单元网络（单一真相源）
    │   ├── nodes.jsonl             ← 所有叙事单元（角色/场景/世界观/情节线/正文/笔记…）
    │   ├── edges.jsonl             ← 所有关系（参与/引用/平行/盟友…）
    │   ├── events.olog             ← 操作事件日志（仅供调试及事件溯源）
    │   ├── snapshots/              ← 数据快照（用于恢复和回退）
    │   └── viz/                    ← 可视化 HTML 文件缓存
    ├── output/                    ← 导出文件输出目录
    ├── quality/                    ← 质量检查记录（由 ProjectionEngine 投影生成）
    └── styles/                    ← 写作风格定义（可选，默认"通俗网文风"）
```

> V2 项目：`graph/nodes.jsonl` 存在即为 V2 项目。V1 项目的 `chapters/characters/ideation/outline/worldbuilding/` 等目录在迁移后变为投影目录，不应直接编辑。

## 技能一览

| 技能 | 场景 | 调用方式 |
|------|------|---------|
| `novel-v2` | **V2 统一创作** — 章节写作、角色管理、世界观建设、情节设计、总纲大纲、风格切换、编辑修订、导出全部格式 | `Task(subagent_type="novel-v2-crafter", load_skills=["novel-v2"], ...)` + focus / preheat / mode |
| `novel-project-manager` | 新建/导入/查看状态/续写/切换/删除项目 | `skill("novel-project-manager")` |
| `novel-env-setup` | 环境初始化 / .venv 故障修复 | `skill("novel-env-setup")` |
| `novel-search-analysis` | V2 搜索分析 — 机械搜索（SearchEngine）+ 偏差管理（DeviationManager）+ LLM 分析框架（4 种分析模式） | `task(subagent_type="novel-search-analysis", load_skills=["novel-search-analysis"], ...)` 编排层调度 |
| `novel-grill` | 需求发现：创作前交互式追问收敛需求 | `skill("novel-grill")` |
| `book-knowledge` | 知识库管理：检索、查询、引用已导入的知识 | `skill("book-knowledge")` |
| `book-to-knowledge` | 将书籍（PDF/EPUB/TXT/HTML/MOBI）导入为结构化知识库 | `skill("book-to-knowledge")` |

> **V2 创作路由**：所有创作任务（章节/角色/世界观/情节/总纲/大纲/编辑/质检/导出）统一走 `novel-v2-crafter`，通过 `FOCUS TYPE`、`PREHEAT LEVEL`、`WRITING MODE` 参数区分操作类型。详见 `novel-writer.md` V2 路由表。
>
> **搜索分析**：简单数据检索走 `novel-tool graph.search` 直接调 tool；深度诊断（align/cross-ref/gap/full-diagnose 四种模式）由 orchestrator 通过 `task(subagent_type="novel-search-analysis")` 调度子 Agent。SearchEngine（纯机械搜索）+ DeviationManager（偏差状态持久化）是 Tool 层，子 Agent 在其上做 LLM 语义分析。
>
> **历史 V1 技能**（novel-ideation/style/worldbuilding/character/synopsis/plot/outline/chapter/edit/export/quality）：在 V2 中不再使用独立 subagent，其能力已整合到 `novel-v2` 技能中，通过不同的 focus type 调用。
