---
name: "novel-v2-writing"
description: "V2 写作子技能：为 novel-v2-crafter 提供内容生成能力，包括单元内容创作、关系构建、质量检查等"
license: "MIT"
version: "2.0.0"
compatibility: "OpenCode"
tags: ["novel", "v2", "writing", "novel-v2-crafter", "graph", "content"]
---

# novel-v2-writing

## 定位

本技能为 **novel-v2-crafter** 主 agent 提供内容生成能力，负责：
- 单元内容创作与优化
- 关系构建与验证
- 质量检查与偏差管理
- 上下文预热与结构化

## 角色路由

| 角色 | 触发词 | 行为 |
|------|--------|------|
| **planner** | `novel-planner`, `规划`, `planning` | 执行规划任务：焦点选择、约束查询、方案生成、单元创建 |
| **crafter** | `novel-v2-crafter`, `写作`, `writing`, `crafter` | 执行写作任务：单元内容生成、关系构建、质量检查 |
| **analyzer** | `novel-v2-analyzer`, `分析`, `analysis`, `analyzer` | 执行分析任务：偏差检测、质量检查、优化建议 |

## 领域参考

### IF YOU ARE planner → references/planning/

规划阶段参考文档：
- `planning/` - 规划流程与最佳实践
- `relation_guide.md` - 关系操作指南
- `content字段参考.md` - content 字段规范

### IF YOU ARE writer/crafter → references/writing/ + references/planning/

写作阶段参考文档：
- `writing/` - 写作流程与最佳实践
- `planning/` - 结构化规划参考
- `relation_guide.md` - 关系操作指南
- `content字段参考.md` - content 字段规范

### IF YOU ARE analyzer → references/analysis/

分析阶段参考文档：
- `analysis/` - 分析流程与最佳实践

## 脚本 vs 提示词分工

| 层级 | 负责内容 | 示例 |
|------|----------|------|
| **脚本层** | 图操作、数据持久化、约束检查 | `novel_tool` → `GraphStore` → `DeviationManager` |
| **提示词层** | 业务逻辑、领域知识、创作指导 | `novel-v2-crafter` → `novel-v2-writing` → `novel-v2-analysis` |

## 上下文契约

### 输入契约

```python
{
    "project": "项目名",
    "focus_name": "焦点名称（单元名，如 第53章 / 韩致）",
    "focus_type": "会话焦点类型 (scene/character_arc 等)",
    "session_id": "关联的创作 session ID（如 ses_xxx）",
    "user_intent": "用户原始输入摘要（summary.save record_type=subagent 用）",
    "preheat_level": "预热级别 (cold/warm/hot)",
    "humanize": "是否去 AI 味",
    "prompt_summary": "子 Agent prompt 自然语言摘要",
    "result_summary": "子 Agent 结果自然语言摘要",
    "new_units": "新建单元数",
    "updated_units": "更新单元数",
    "duration_estimate_ms": "预估耗时（ms）",
    "error_summary": "错误摘要（如有）",
    "result": "结果状态 (success/partial/failed)",
    "scope": "搜索范围（逗号分隔的类型）",
    "regex": "启用正则搜索",
    "case_sensitive": "区分大小写",
    "cycle_type": "会话循环类型 (ideation/expansion/refinement/proofing/planning)",
    "phase": "会话阶段 (ideation/planning/expansion/refinement/proofing)",
    "new_type": "目标类型（用于 graph.change_type 操作）",
    "verify": "迁移时验证",
    "report": "迁移时输出报告",
    "since_version": "起始版本号",
    "version": "分析清单版本名（如 clues_20260731_134643_123.md）",
    "sources": "来源 summary 文件名列表（证据链）",
    "clue": "线索标识（如 [workflow] 编排层·创建/拆分前查重）",
    "note": "修复说明（analysis.resolve 用）",
    "findings": "偏差发现列表(JSON数组)",
    "scan_version": "扫描版本号",
    "full_scan_version": "全量扫描版本号",
    "out": "导出目录",
    "host": "Web 服务绑定地址（默认 127.0.0.1）",
    "port": "Web 服务端口（默认 8766）",
    "ids": "ID 列表（逗号分隔，如 purge_archived 指定删除）",
    "record_type": "summary.save 记录类型 (orchestrator/subagent)",
    "conflict_decision": "偏差冲突处理决策（deviation 相关）",
    "failure_analysis": "故障分析（优化闭环相关）",
    "optimization_clue": "优化线索（优化闭环相关）"
}
```

### 输出契约

```python
{
    "status": "success/partial/failed",
    "data": {
        "units": [...],  # 创建/更新的单元列表
        "relations": [...],  # 创建的关系列表
        "deviations": [...],  # 检测到的偏差
        "summary": {...},  # 会话摘要
        "analysis": {...},  # 分析结果
        "telemetry": {...}  # 使用数据
    },
    "error": "错误信息（如有）"
}
```

## V2 操作指南

### 核心图操作

#### 1. 单元创建与查询

```python
# 创建单元
novel_tool(
    operation="graph.create_unit",
    project="项目名",
    name="单元名",
    unit_type="SCENE/CHARACTER_ARC/...",
    content="单元内容（JSON 字符串）",
    chapter=1,
    volume=1,
    parent_id="父级单元 ID",
    tags="标签（逗号分隔）",
    if_exists="error/skip/create",
    verbose=True
)

# 查询单元
novel_tool(
    operation="graph.find_unit",
    project="项目名",
    keyword="关键词",
    unit_type="SCENE",
    verbose=True
)

# 列出单元
novel_tool(
    operation="graph.list_units",
    project="项目名",
    unit_type="SCENE",
    chapter=1,
    volume=1,
    status="mature",
    limit=10,
    offset=0
)
```

#### 2. 关系操作

```python
# 创建关系
novel_tool(
    operation="graph.add_relation",
    project="项目名",
    source="源单元 ID",
    target="目标单元 ID",
    rel_type="CONTAINS/CHARACTER_ARC/...",
    label="关系语义标签（如 师徒/同盟）",
    weight=0.8,
    bidirectional=True,
    source_role="源端点角色",
    target_role="目标端点角色",
    description="关系描述",
    payload="关系 payload（JSON 字符串）",
    tags="标签（逗号分隔）"
)

# 查询关系
novel_tool(
    operation="graph.get_relations",
    project="项目名",
    source="源单元 ID",
    target="目标单元 ID",
    rel_type="CONTAINS",
    label="关系语义标签",
    weight=0.5,
    min_weight=0.0,
    max_weight=1.0,
    bidirectional=True,
    verbose=True
)

# 删除关系
novel_tool(
    operation="graph.remove_relation",
    project="项目名",
    source="源单元 ID",
    target="目标单元 ID",
    rel_type="CONTAINS",
    label="关系语义标签"
)
```

#### 3. 单元更新与删除

```python
# 更新单元
novel_tool(
    operation="graph.update_unit",
    project="项目名",
    id="单元 ID",
    name="新单元名",
    content="新单元内容",
    status="mature",
    tags="新标签（逗号分隔）"
)

# 删除单元
novel_tool(
    operation="graph.archive_unit",
    project="项目名",
    id="单元 ID"
)

# 批量归档
novel_tool(
    operation="graph.purge_archived",
    project="项目名",
    ids="ID 列表（逗号分隔）"
)
```

#### 4. 搜索与推断

```python
# 关键词搜索
novel_tool(
    operation="graph.search",
    project="项目名",
    keyword="关键词",
    unit_type="SCENE",
    scope="SCENE,CHARACTER_ARC",
    regex=False,
    case_sensitive=False,
    limit=10
)

# 正则搜索
novel_tool(
    operation="graph.search",
    project="项目名",
    keyword="(?s)韩致.*修炼",
    regex=True,
    case_sensitive=False,
    limit=10
)

# 关系推断
novel_tool(
    operation="graph.batch_infer",
    project="项目名",
    infer_type="relation",
    verbose=True
)

# 结构重建
novel_tool(
    operation="graph.rebuild_structure_path",
    project="项目名",
    verbose=True
)

# 结构迁移
novel_tool(
    operation="graph.migrate_structure_to_edges",
    project="project",
    verify=True,
    report=True
)
```

#### 5. 偏差管理

```python
# 列出偏差
novel_tool(
    operation="deviation.list",
    project="项目名",
    severity="warning",
    dimension="character",
    limit=10
)

# 解决偏差
novel_tool(
    operation="deviation.resolve",
    project="项目名",
    id="偏差 ID",
    conflict_decision="merge/ignore/reject",
    note="修复说明"
)

# 删除偏差
novel_tool(
    operation="deviation.delete",
    project="项目名",
    id="偏差 ID"
)
```

#### 6. 会话管理

```python
# 启动会话
novel_tool(
    operation="session.start",
    project="项目名",
    focus_name="焦点名称",
    focus_type="scene",
    cycle_type="ideation",
    phase="ideation",
    preheat_level="warm",
    verbose=True
)

# 设置会话循环
novel_tool(
    operation="session.set_cycle",
    project="项目名",
    cycle_type="ideation/expansion/refinement/proofing/planning"
)

# 设置会话阶段
novel_tool(
    operation="session.set_phase",
    project="项目名",
    phase="ideation/planning/expansion/refinement/proofing"
)

# 构建工作区
novel_tool(
    operation="session.build_workspace",
    project="项目名",
    focus_name="焦点名称",
    focus_type="scene",
    preheat_level="warm",
    verbose=True
)

# 会话信息
novel_tool(
    operation="session.info",
    project="项目名",
    session_id="ses_xxx"
)
```

#### 7. 项目管理

```python
# 新建项目
novel_tool(
    operation="project.new",
    project="项目名",
    genre="玄幻/仙侠等",
    volumes=1,
    acts=1,
    structure="linear",
    v2=True,
    dry_run=False
)

# 导入项目
novel_tool(
    operation="project.import",
    project="项目名",
    source_path="导入源路径",
    dry_run=False
)

# 查看状态
novel_tool(
    operation="project.status",
    project="项目名"
)

# 续写
novel_tool(
    operation="project.resume",
    project="项目名"
)

# 切换项目
novel_tool(
    operation="project.switch",
    project="项目名"
)

# 删除项目
novel_tool(
    operation="project.delete",
    project="项目名"
)
```

#### 8. 知识库操作

```python
# 列出知识库
novel_tool(
    operation="knowledge.list_books",
    slug="fanren-xiuxian",
    limit=10
)

# 读取知识库
novel_tool(
    operation="knowledge.read",
    slug="fanren-xiuxian",
    topic="修炼体系",
    limit=10
)
```

#### 9. 分析与统计

```python
# 会话摘要
novel_tool(
    operation="summary.save",
    project="项目名",
    record_type="subagent",
    user_intent="用户原始输入摘要",
    result_summary="子 Agent 结果自然语言摘要",
    new_units=1,
    updated_units=0,
    duration_estimate_ms=5000,
    error_summary="",
    result="success"
)

# 列出摘要
novel_tool(
    operation="summary.list",
    project="项目名",
    tag="scene",
    limit=10
)

# 读取摘要
novel_tool(
    operation="summary.read",
    project="项目名",
    id="摘要 ID"
)

# 分析保存
novel_tool(
    operation="analysis.save",
    project="项目名",
    record_type="subagent",
    user_intent="用户原始输入摘要",
    result_summary="子 Agent 结果自然语言摘要",
    new_units=1,
    updated_units=0,
    duration_estimate_ms=5000,
    error_summary="",
    result="success"
)

# 列出分析
novel_tool(
    operation="analysis.list",
    project="项目名",
    tag="scene",
    limit=10
)

# 读取分析
novel_tool(
    operation="analysis.read",
    project="项目名",
    id="分析 ID"
)

# 解决分析
novel_tool(
    operation="analysis.resolve",
    project="项目名",
    id="分析 ID",
    clue="线索标识",
    note="修复说明"
)

# 使用分析
novel_tool(
    operation="analyze.usage",
    project="项目名",
    mode="quick",
    json_output=False
)

# 遥测分析
novel_tool(
    operation="analyze.telemetry",
    project="项目名",
    mode="quick",
    json_output=False
)
```

#### 10. Web 服务

```python
# 启动 Web 服务
novel_tool(
    operation="web.start",
    project="项目名",
    host="127.0.0.1",
    port=8766
)

# 停止 Web 服务
novel_tool(
    operation="web.stop",
    project="项目名"
)

# 重启 Web 服务
novel_tool(
    operation="web.restart",
    project="项目名"
)
```

### 约束检查

```python
# 检查约束
novel_tool(
    operation="graph.check",
    project="项目名",
    full=False,
    verbose=True
)

# 强制修复
novel_tool(
    operation="env.fix",
    project="项目名",
    verbose=True
)

# 强制检查
novel_tool(
    operation="env.force",
    project="项目名",
    verbose=True
)

# 环境检查
novel_tool(
    operation="env.check",
    project="项目名",
    verbose=True
)
```

### 数据导出

```python
# 导出文档
novel_tool(
    operation="graph.export_docs",
    project="项目名",
    out="导出目录",
    verbose=True
)

# 导出片段
novel_tool(
    operation="graph.export_chunks",
    project="项目名",
    out="导出目录",
    verbose=True
)
```

### 结构操作

```python
# 获取单元统计
novel_tool(
    operation="graph.stats",
    project="项目名",
    verbose=True
)

# 获取修改单元
novel_tool(
    operation="graph.get_modified_units",
    project="项目名",
    since_version=1,
    verbose=True
)

# 获取最近事件
novel_tool(
    operation="graph.recent_events",
    project="项目名",
    limit=10,
    verbose=True
)

# 获取邻居
novel_tool(
    operation="graph.get_neighbors",
    project="项目名",
    id="单元 ID",
    direction="outgoing/incoming/both",
    max_depth=2,
    verbose=True
)

# 查找后代
novel_tool(
    operation="graph.find_descendants",
    project="项目名",
    id="单元 ID",
    direction="outgoing/incoming/both",
    max_depth=2,
    verbose=True
)

# 查找祖先
novel_tool(
    operation="graph.find_ancestors",
    project="项目名",
    id="单元 ID",
    direction="outgoing/incoming/both",
    max_depth=2,
    verbose=True
)

# 获取关系类型
novel_tool(
    operation="graph.list_relation_types",
    project="项目名",
    verbose=True
)

# 修改单元类型
novel_tool(
    operation="graph.change_type",
    project="项目名",
    id="单元 ID",
    new_type="新类型",
    verbose=True
)

# 迁移
novel_tool(
    operation="graph.migrate",
    project="项目名",
    since_version=1,
    verify=True,
    report=True,
    verbose=True
)

# 刷新
novel_tool(
    operation="graph.flush",
    project="项目名",
    skip_constraint_check=False,
    verbose=True
)

# 修复不对称
novel_tool(
    operation="graph.fix_asymmetry",
    project="项目名",
    verbose=True
)
```

## HARD CONSTRAINTS

1. **图操作唯一性**：所有图操作必须通过 `novel_tool` → `GraphStore` → `DeviationManager` 路径，禁止直接编辑 `nodes.jsonl` 或 `edges.jsonl`

2. **偏差持久化**：任何异常必须通过 `DeviationManager` 持久化，禁止 `except: pass`

3. **单元创建**：创建单元时必须指定 `unit_type`、`name`、`content`，禁止创建空单元

4. **关系双向性**：创建关系时 `bidirectional=True` 优先，禁止单向关系

5. **会话上下文**：所有会话操作必须关联 `session_id`，禁止孤立操作

6. **质量检查**：每次操作后必须调用 `graph.check` 验证约束

7. **错误处理**：所有操作必须捕获异常并返回 `{status: "failed", error: "错误信息"}`

8. **版本控制**：迁移操作必须指定 `since_version`，禁止无版本迁移

9. **文件引用**：禁止引用 `novel-v2` 技能名，必须使用新的子技能名

10. **参考文件**：所有参考文件必须从 `references/` 目录加载，禁止硬编码路径
