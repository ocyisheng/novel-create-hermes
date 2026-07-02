# 开发者文档

## V2 架构：叙事单元网络

V2 是 novel-create-hermes 的新一代架构，基于**叙事单元网络**替代了传统的 P1-P15 线性阶段 + 离散 YAML 文件体系。

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
novel-writer.md（编排层）→ 意图识别 + 焦点映射
        │ task(subagent_type="novel-v2-crafter", load_skills=["novel-v2"])
        ▼
novel-v2-crafter（创作引擎）→ 统一处理全部创作任务
        │ GraphStore API → QUERY 协议 → WorkspaceBuilder
        ▼
shared/v2/（数据层）→ GraphStore + ProjectionEngine + SessionManager
        │ JSONL 持久化 + 事件溯源 + 快照
        ▼
graph/（存储层）→ nodes.jsonl + edges.jsonl + events.olog
        │ 投影引擎负责 ↔ 旧 YAML 文件体系兼容
```

### 与旧架构的关键差异

| 维度 | 旧架构 | V2 |
|------|--------|-----|
| **数据模型** | 三层 YAML（_meta + 索引 + 摘要 + 完整档案） | 叙事单元网络（NarrativeUnit + Relation） |
| **存储** | 离散YAML + 手动索引重建 | JSONL (graph/) + 事件溯源 |
| **阶段** | P1-P15 线性状态机 | 创作循环（焦点驱动，无阶段概念） |
| **上下文** | chapter_context.py 全量推送 | WorkspaceBuilder 按焦点按需加载 |
| **信息获取** | 编排层决定你需要什么 | 子 Agent 通过 QUERY 协议自主请求 |
| **后处理** | fix_yaml_indent + rebuild_index + set-phase | store.flush() + 可选投影重建 |
| **回滚** | .bak 文件还原 | 事件溯源 + 快照 |
| **灵感** | 无捕获机制 | NOTE 类型 + 意图列表 |

### 迁移

旧项目可通过迁移工具导入到 V2：

```bash
python .opencode/shared/v2/migrate.py --project-root NOVELS_ROOT/项目名 --verify --report
```

迁移后原有文件不变，新增 `graph/` 目录作为真相源。
