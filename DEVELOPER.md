# 开发者文档

## V2 架构：叙事单元网络

V2 是 novel-create-hermes 的架构，基于**叙事单元网络**替代了传统的线性阶段 + 离散 YAML 文件体系。

### 核心概念

V2 认为写作的基本单位不是"文档"而是**叙事单元**：

| 叙事单元类型 | 说明 | 对应旧体系 |
|-------------|------|-----------|
| `scene` | 场景：时间×地点×人物组的叙事切片 | 分纲.yaml |
| `character_arc` | 角色弧线：跨章节的成长轨迹 | 角色.yaml |
| `plot_thread` | 情节线：完整的故事脉络 | 情节线.yaml |
| `world_rule` | 世界观规则：世界运行的核心法则 | 世界观.yaml |
| `thematic_motif` | 主题意象：反复出现的象征性元素 | — |
| `note` | 创作笔记：备忘和灵感 | ideation/ |
| `chunk` | 正文片段：已写成的文字 | 章节.txt |
| `narrative_voice` | 叙述腔调：腔调谱系、视角、笔法约定 | 风格.yaml |
| `outline` | 总纲：故事整体框架 | 大纲.yaml |
| `arc_plan` / `volume_plan` / `chapter_plan` | 分卷/分章计划 | 分纲.yaml |
| `structure` | 结构节点（废弃兼容，归一化为 outline/arc_plan 等） | — |
| `temporal_event` | 时间事件：从焦点内容自动抽取的时序事件 | — |

> 单元类型定义集中在 `v2/unit_types/*.yaml`，由 `TypeRegistry` 加载校验。内容字段 schema 由 `schemas.py` 门面从类型定义读取。

### 架构层次

```
orchestrator.md（唯一入口）→ 意图识别 + 基建自处理 + 领域扇出
        │
        ├─ novel-planner（设计）   → grill → 创意 → 六维 → NOTE 单元（唯一写类型）
        ├─ novel-writer（物化）    → 业务单元 + 关系 + 质检（actor 门禁白名单）
        ├─ novel-analyzer（诊断）  → 快速检索自执行 / 调度 novel-diagnose
        └─ subagents              → novel-diagnose / novel-lore-search / novel-book-importer
        │                      │
        │              load_skills=["novel-v2-core", "<角色技能>", ...]
        │                      │
        ▼                      ▼
┌─────────────────────────────────────────────┐
│          shared/v2/（数据层）                 │
│                                              │
│  GraphStore      — 节点/关系 CRUD + 事件溯源  │
│  SearchEngine    — 关键词/正则/实体搜索       │
│                    + 一致性检查               │
│  ConstraintEngine— 约束匹配器编排（6 类）     │
│  DeviationMgr    — 偏差状态持久化（YAML）     │
│  Workspace       — 焦点预热 + 上下文构建      │
│  Projection      — graph → 文件系统投影       │
│  RelationInf     — 自动关系推断               │
│  Session         — 会话管理 + 用户状态        │
│  EventExtractor  — 焦点内容→时间事件抽取      │
│  TemporalIndex   — 全类型时间线派生视图       │
│  Telemetry       — 调用级遥测 + 按天分片      │
└──────────────────────┬──────────────────────┘
                       │ JSONL 持久化 + 事件溯源
                       ▼
          graph/（存储层）→ nodes.jsonl + edges.jsonl + events.olog
```

### 代码组织（shared/）

所有 Python 实现位于 `.opencode/shared/`，按职责分层：

| 目录 | 职责 |
|------|------|
| `handlers/` | 纯业务逻辑，每域一个文件（graph/project/env/session/deviation/knowledge/analyze/summary/server），经 `OPERATION_REGISTRY` + `run_operation()` 路由 |
| `v2/` | 核心引擎：数据模型、存储、搜索、约束、投影、会话、遥测等 |
| `v2/matchers/` | 6 个 `PatternMatcher` 实现：temporal / referential_integrity / cardinality / boundary / state_conservation / pattern |
| `v2/web/` | FastAPI 可视化服务（graph/edges/nodes/search/stats/pages 路由） |
| `tools/` | `novel_tool.py` 薄 JSON 适配层（参数映射 → run_operation → JSON 输出），零业务逻辑 |
| `env/` | `.venv` 发现 + 依赖检查/修复 |
| `project/` | 项目脚手架（旧桥接，委托给 handlers） |
| `tests/` | pytest 测试套件 + conftest 共享夹具 |

### 数据层核心模块

| 模块 | 职责 |
|------|------|
| `graph_schema.py` | NarrativeUnit / Relation / Event dataclass + 枚举定义 |
| `graph_store.py` | JSONL 持久化 CRUD + 事件溯源 + 快照 |
| `search_engine.py` | 纯机械关键词/正则/实体搜索（无 LLM）+ 一致性检查 |
| `constraint_engine.py` | 基于类型自描述编排 matchers，flush 后自动检查并持久化偏差 |
| `deviation_manager.py` | 偏差状态 YAML 持久化（LLM 跨 session 分析存储） |
| `workspace.py` | 按焦点构建最小必要上下文 + 预热 |
| `projection_engine.py` | graph → 文件系统视图投影（文件非真相源） |
| `relation_inferrer.py` | 写作时从单元内容自动提取关系 |
| `session.py` | 创作会话 + UserState（嵌套循环创作模型） |
| `event_extractor.py` | 焦点内容 → TEMPORAL_EVENT 结构化事件抽取 |
| `temporal_index.py` | 全类型时间线派生视图（read-time 计算） |
| `telemetry.py` | 工具调用遥测 → `.engine/telemetry/{date}.ndjson` |
| `usage_analyzer.py` | 使用数据收集与分析报告 |
| `engine_log.py` | 遥测/daemon 共用的按天分片日志写入基类 |
| `type_registry.py` | UnitType YAML 模式加载/校验 |
| `character_timeline.py` | 角色时间线账本 |
| `time_utils.py` | 统一 story time 读写（`extra["time"]`） |
| `migrate.py` | V1 项目 → graph 迁移工具 |

### 子 Agent 体系

编排层负责三个子 Agent 的调度，每个子 Agent 有独立的权限和职责边界：

| 子 Agent | 职责 | 权限 |
|---------|------|------|
| `orchestrator` | 总编排（唯一入口）：意图识别、基建自处理、领域扇出调度 | `novel-tool` + `task()` 调度 |
| `novel-planner` | 设计讨论：grill 需求发现 → 创意方案 → 六维冲突设计 → NOTE 单元（唯一写类型） | `read`, `novel-tool`, `skill()` |
| `novel-writer` | 写作物化：单元内容创作、关系构建、质量检查、写后处理（actor 门禁白名单） | `read`, `novel-tool`, `skill()` |
| `novel-analyzer` | 诊断编排：快检自执行（novel-search-analysis 方法论）、深度诊断调度 novel-diagnose | `read`, `novel-tool`, `skill()` |
| `novel-diagnose` | 深度诊断 subagent：align/cross-ref/gap/full-diagnose（只读 + deviation.merge 唯一写例外） | `read`, `novel-tool` **仅** |
| `novel-lore-search` | 跨库检索 subagent：graph + knowledge/ + 文件系统全文检索（只读） | `read`, `novel-tool` **仅** |
| `novel-book-importer` | 书籍导入 subagent：book-to-knowledge 全管道（写 knowledge/） | `read`, `write`, `bash` |

子 Agent 不走链式调用，编排层收到结果后直接决策下一步。

> **开发模式（OMODE 非 release）**：novel-writer 按需加载 `novel-dev-ops` 技能，承载遥测记录、数据分析、会话总结、聚合分析、优化闭环。所有工具调用自动记录到 `.engine/telemetry/`。

### 编排层路由

#### 创作路由

```
用户请求 → 明确指令? → 是 → orchestrator 路由到 novel-writer（写作物化）/ novel-planner（设计讨论）/ novel-analyzer（诊断）
                  → 否 → skill("novel-grill") 收敛需求 → 用户确认 → 按领域路由
```

Grill 后可选 `skill("novel-ideation")` 生成方案（由 novel-planner 自执行加载），再进入设计/写作闭环。

#### 搜索分析路由

```
搜索分析请求
  ├─ 简单数据检索（"找找天道宗在哪"）→ novel-tool graph.search（直接调 tool）
  └─ 深度诊断（分析/核验/对齐/整体检测）→ task(subagent_type="novel-diagnose", ...)
```

简单数据检索不需要 LLM 分析，直接走 tool；深度诊断需要 LLM 推理，走子 Agent。

### 与旧架构的关键差异

| 维度 | 旧架构 | V2 |
|------|--------|-----|
| **数据模型** | 三层 YAML（_meta + 索引 + 摘要 + 完整档案） | 叙事单元网络（NarrativeUnit + Relation） |
| **存储** | 离散 YAML + 手动索引重建 | JSONL (graph/) + 事件溯源 |
| **阶段** | 线性状态机 | 创作循环（焦点驱动，无阶段概念） |
| **上下文** | chapter_context.py 全量推送 | WorkspaceBuilder 按焦点按需加载 |
| **信息获取** | 编排层决定你需要什么 | 子 Agent 通过 novel-tool 自主请求 |
| **后处理** | fix_yaml_indent + rebuild_index + set-phase | store.flush() + 可选投影重建 |
| **回滚** | .bak 文件还原 | 事件溯源 + 快照 |
| **灵感** | 无捕获机制 | NOTE 类型 + 意图列表 |

> **迁移映射**：V1 的 `quality/*.yaml`（质量分析文件）在迁移时映射为 NOTE 类型叙事单元导入 graph。

### 迁移

旧项目可通过迁移工具导入到 V2：

```bash
python .opencode/shared/cli.py migrate --project-root NOVELS_ROOT/项目名 --verify --report
```

迁移后原有文件不变，新增 `graph/` 目录作为真相源。
