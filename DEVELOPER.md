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

### 架构层次

```
novel-writer.md（编排层）→ 意图识别 + 焦点映射 + 需求发现（grill）
        │
        ├─ task(subagent_type="novel-v2-crafter", ...)    ← V2 统一创作
        ├─ task(subagent_type="novel-ideation", ...)      ← 创意方案生成
        └─ task(subagent_type="novel-search-analysis")    ← 深度诊断
        │                      │
        │              load_skills=["novel-v2"]
        │                      │
        ▼                      ▼
┌─────────────────────────────────────────────┐
│          shared/v2/（数据层）                 │
│                                              │
│  GraphStore     — 节点/关系 CRUD + 事件溯源   │
│  SearchEngine   — 关键词/正则/实体搜索        │
│                   + 一致性检查（R1-R4）        │
│  DeviationMgr   — 偏差状态持久化（YAML）       │
│  Workspace      — 焦点预热 + 上下文构建        │
│  Projection     — graph → 文件系统投影         │
│  RelationInf    — 自动关系推断                  │
│  Session        — 会话管理 + 用户状态           │
└──────────────────────┬──────────────────────┘
                       │ JSONL 持久化 + 事件溯源
                       ▼
          graph/（存储层）→ nodes.jsonl + edges.jsonl + events.olog
```

### 子 Agent 体系

编排层负责三个子 Agent 的调度，每个子 Agent 有独立的权限和职责边界：

| 子 Agent | 职责 | 权限 |
|---------|------|------|
| `novel-v2-crafter` | 全部创作任务：章节写作、角色管理、世界观建设、情节设计、质检、导出 | `edit`, `bash`, `read`, `write`, `novel-tool` |
| `novel-ideation` | 创意方案生成：在 grill 收敛需求后生成可选方案 | `edit`, `bash`, `read`, `write`, `novel-tool` |
| `novel-search-analysis` | 深度诊断：完整性扫描、意图对齐、交叉引用、Gap 分析（只读） | `read`, `novel-tool` **仅** |

子 Agent 不走链式调用，编排层收到结果后直接决策下一步。

### 编排层路由

#### 创作路由

```
用户请求 → 明确指令? → 是 → 直接调 crafter（注入 FOCUS TYPE / FOCUS ID / PREHEAT LEVEL / WRITING MODE）
                  → 否 → skill("novel-grill") 收敛需求 → 用户确认 → 调 crafter
```

Grill 后可选 `novel-ideation` 生成方案再路由到 crafter。

#### 搜索分析路由

```
搜索分析请求
  ├─ 简单数据检索（"找找天道宗在哪"）→ novel-tool graph.search（直接调 tool）
  └─ 深度诊断（分析/核验/对齐/整体检测）→ task(subagent_type="novel-search-analysis", ...)
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

### 迁移

旧项目可通过迁移工具导入到 V2：

```bash
python .opencode/shared/cli.py migrate --project-root NOVELS_ROOT/项目名 --verify --report
```

迁移后原有文件不变，新增 `graph/` 目录作为真相源。
