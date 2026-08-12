---
name: "novel-v2-core"
description: "V2 共享核心子技能：角色路由、上下文契约、novel-tool 操作指南、HARD CONSTRAINTS。必须与角色技能（novel-v2-writing / novel-v2-planning / novel-v2-analysis）一起加载。触发词：V2 操作、graph 操作、novel-tool、角色路由、共享规范"
license: "MIT"
version: "2.0.0"
compatibility: "OpenCode"
tags: ["novel", "v2", "core", "shared"]
---

# novel-v2-core — V2 共享核心

## 定位

novel-v2-core 是 V2 创作体系的**共享操作层**：角色路由、上下文契约、novel-tool 操作指南、HARD CONSTRAINTS 全部集中于此。

**加载方式**：主 agent / subagent 通过 `load_skills=["novel-v2-core", "<角色技能>"]` 同时加载；方法论技能（`novel-six-dimensions` / `novel-grill` / `novel-ideation` / `novel-search-analysis`）按需叠加。

角色技能只保留角色定位与专属参考，不再重复操作指南：

| 角色技能 | 供谁使用 |
|----------|----------|
| `novel-v2-writing` | `novel-writer`（写作物化） |
| `novel-v2-planning` | `novel-planner`（设计讨论） |
| `novel-v2-analysis` | `novel-analyzer` / `novel-diagnose`（诊断） |

## 角色路由

| 角色 | 触发词 | 行为 |
|------|--------|------|
| **planner** | `novel-planner`, `规划`, `planning` | 设计讨论：grill 需求发现 → 创意方案 → 六维冲突设计 → 写入 NOTE 单元（唯一写类型） |
| **writer** | `novel-writer`, `写作`, `writing`, `写` | 写作物化：单元内容创作/优化、关系构建、质量检查、写后处理（actor 门禁白名单） |
| **analyzer** | `novel-analyzer`, `分析`, `analysis`, `质检` | 诊断编排：快检自执行（novel-search-analysis 方法论）、深度诊断调度 novel-diagnose |
| **diagnose** | `novel-diagnose` | 深度诊断 subagent：align/cross-ref/gap/full-diagnose（只读 + deviation.merge 写通道） |
| **lore-search** | `novel-lore-search` | 跨库检索 subagent：graph + knowledge/ + 文件系统全文检索（只读） |
| **book-importer** | `novel-book-importer` | 书籍导入 subagent：book-to-knowledge 全管道（写 knowledge/） |

> **不存在** `novel-v2-crafter` / `novel-ideation` / `novel-search-analysis` / `novel-v2-analyzer` 等 subagent —— 均为幽灵，调度即失败。创意方案用 `skill("novel-ideation")` 自执行加载；深度诊断用 `task(subagent_type="novel-diagnose", ...)`。

## 脚本 vs 提示词分工

| 层级 | 负责内容 | 示例 |
|------|----------|------|
| **脚本层** | 图操作、数据持久化、约束检查 | `novel-tool` → `run_operation` → `GraphStore` / `DeviationManager` |
| **提示词层** | 业务逻辑、领域知识、创作指导 | `novel-v2-core`（操作层）→ 角色技能（业务定位）→ 方法论技能（领域知识） |

## 上下文契约

### 输入契约

```python
{
    "project": "项目名",
    "focus_name": "焦点名称（单元名，如 第53章 / 韩致）",
    "focus_type": "会话焦点类型 (scene/character_arc 等)",
    "session_id": "关联的创作 session ID（如 ses_xxx）",
    "user_intent": "用户原始输入摘要（summary.save record_type=subagent 用）",
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

## 操作指南

> **调用约定**：`novel-tool` 是 MCP 工具，以 JSON 调用约定传参（`operation` + 参数），非 Python 函数调用。以下示例用 Python 字面量展示参数结构。

### 1. 单元操作

```python
# 单元查询（详情）
novel_tool(
    operation="graph.get_unit",
    id="单元 ID",
    verbose=True
)

# 结构化查询
novel_tool(
    operation="graph.find_unit",
    name="单元名",
    unit_type="SCENE",
    limit=30
)

# 关键词/正则搜索
novel_tool(
    operation="graph.search",
    keyword="关键词",
    scope="SCENE,CHARACTER_ARC",
    regex=False,
    case_sensitive=False,
    limit=20
)

# 列出单元
novel_tool(
    operation="graph.list_units",
    project="项目名",
    unit_type="SCENE",
    chapter=1,
    volume=1,
    status="mature",
    limit=50,
    offset=0
)

# 创建单元
novel_tool(
    operation="graph.create_unit",
    unit_type="SCENE",
    name="场景名",
    content='{"subtype":"推进","pov_character":"...","location":"...","time_label":"...","one_line_summary":"..."}',
    actor="novel-writer",
    chapter=3,
    volume=1,
    parent_id="父级单元 ID",
    tags="标签（逗号分隔）",
    if_exists="error",
    verbose=True
)

# 更新单元
novel_tool(
    operation="graph.update_unit",
    id="单元 ID",
    content='{"subtype":"推进",...}',
    status="mature",
    tags="新标签（逗号分隔）",
    actor="novel-writer"
)

# 归档单元
novel_tool(
    operation="graph.archive_unit",
    id="单元 ID",
    verbose=True
)

# 彻底删除（已归档）
novel_tool(
    operation="graph.purge_archived",
    ids="ID 列表（逗号分隔）",
    limit=100,
    verbose=True
)
```

### 2. 关系操作

```python
# 建立关系
novel_tool(
    operation="graph.add_relation",
    source="源单元 ID",
    target="目标单元 ID",
    rel_type="member_of",
    bidirectional=True,
    label="关系标签",
    source_role="源角色",
    target_role="目标角色",
    weight=0.9,
    description="关系描述",
    tags="标签（逗号分隔）",
    actor="novel-writer",
)

# 删除关系
novel_tool(
    operation="graph.remove_relation",
    source="源单元 ID",
    target="目标单元 ID",
    rel_type="member_of",
    actor="novel-writer"
)

# 查询关系（按单元）
novel_tool(
    operation="graph.get_relations",
    id="单元 ID",
    direction="outgoing/incoming/both",
    label="关系语义标签",
    label_substring=False,
    role="端点角色",
    rel_type="CONTAINS",
    limit=50
)

# 更新关系
novel_tool(
    operation="graph.update_relation",
    id="关系 ID",
    label="新标签",
    description="新描述",
    payload="附加数据（JSON 字符串）",
    weight=0.5
)
```

### 3. 约束检查

```python
# 增量约束检查（flush 后自动触发）
novel_tool(
    operation="graph.check",
    project="项目名",
    full=False,
    verbose=True
)

# 全量语义约束检查
novel_tool(
    operation="constraint.check",
    project="项目名",
    full=True,
    verbose=True
)

# 统一质量检查（多层）
novel_tool(
    operation="graph.quality_check",
    project="项目名",
    layers="mechanical,statistical,semantic",
    full=True,
    verbose=True
)
```

### 4. 偏差管理

```python
# 合并偏差（发现兼容偏差时归并）
novel_tool(
    operation="deviation.merge",
    id="兼容偏差 ID",
    conflict_decision="merge/ignore/reject",
    note="修复说明",
    severity="warning",
    dimension="character",
    scan_version=1
)

# 列出偏差
novel_tool(
    operation="deviation.list",
    project="项目名",
    severity="warning",
    dimension="character",
    limit=10
)

# 待处理偏差
novel_tool(
    operation="deviation.pending",
    project="项目名",
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

# 保留偏差
novel_tool(
    operation="deviation.retain",
    project="项目名",
    id="偏差 ID"
)

# 删除偏差
novel_tool(
    operation="deviation.delete",
    project="项目名",
    id="偏差 ID"
)
```

### 5. 会话管理

```python
# 启动会话
novel_tool(
    operation="session.start",
    project="项目名",
    id="ses_xxx",
    focus_type="scene"
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

# 构建工作区（焦点预热）
novel_tool(
    operation="session.build_workspace",
    project="项目名",
    id="ses_xxx",
    preheat_level="warm"
)

# 会话信息
novel_tool(
    operation="session.info",
    project="项目名"
)
```

### 6. 项目管理

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
    project="项目名",
    force=True
)
```

### 7. 知识库操作

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

### 8. 分析与统计

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

# 解决分析（标记修复）
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

### 9. Web 服务

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

### 10. 结构操作

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

# 关系批量推断
novel_tool(
    operation="graph.batch_infer",
    project="项目名",
    verbose=True
)

# 迁移（版本升级）
novel_tool(
    operation="graph.migrate",
    project="项目名",
    since_version=1,
    verify=True,
    report=True,
    verbose=True
)

# 刷新（落盘 + 约束检查）
novel_tool(
    operation="graph.flush",
    project="项目名",
    skip_constraint_check=False,
    verbose=True
)

# 修复不对称关系
novel_tool(
    operation="graph.fix_asymmetry",
    project="项目名",
    verbose=True
)

# 重建结构路径
novel_tool(
    operation="graph.rebuild_structure_path",
    project="项目名",
    verbose=True
)

# 结构到边迁移
novel_tool(
    operation="graph.migrate_structure_to_edges",
    project="项目名",
    verify=True,
    report=True,
    verbose=True
)

# 模式信息
novel_tool(
    operation="graph.schema_info",
    project="项目名",
    verbose=True
)

# 导出文档 / 片段
novel_tool(
    operation="graph.export_docs",
    project="项目名",
    out="导出目录",
    verbose=True
)
novel_tool(
    operation="graph.export_chunks",
    project="项目名",
    out="导出目录",
    verbose=True
)
```

## 参考文件

| 文件 | 内容 |
|:----|:-----|
| `references/relation_guide.md` | 关系操作指南 |
| `references/planning/structure.md` | 结构化规划参考 |
| `references/planning/plot_thread.md` | 情节线规划参考 |
| `references/planning/note.md` | NOTE 单元规范 |

## HARD CONSTRAINTS

1. **图操作唯一性**：所有图操作必须通过 `novel-tool` → `run_operation` → `GraphStore` / `DeviationManager` 路径，禁止直接编辑 `nodes.jsonl` 或 `edges.jsonl`

2. **偏差持久化**：任何异常必须通过 `DeviationManager` 持久化，禁止 `except: pass`

3. **单元创建**：创建单元时必须指定 `unit_type`、`name`、`content`，禁止创建空单元

4. **关系双向性**：创建关系时 `bidirectional=True` 优先，禁止无意识地创建单向关系

5. **会话上下文**：会话操作必须关联 `session_id`（`session.start` 返回），禁止孤立操作

6. **质量检查**：写操作后调用 `graph.check` / `graph.quality_check` 验证约束

7. **错误处理**：所有操作必须捕获异常并返回 `{status: "failed", error: "错误信息"}`，禁止吞错

8. **版本控制**：增量扫描操作（`graph.get_modified_units`）必须指定 `since_version`，禁止无版本增量扫描

9. **技能加载**：V2 技能必须 `["novel-v2-core", "<角色技能>"]` 成对加载；禁止单独加载角色技能（缺少操作层）或引用幽灵技能名（`novel-v2` / `novel-v2-crafter`）

10. **参考文件**：所有参考文件必须从 `references/` 目录加载，禁止硬编码路径

## DEVIATION_MERGE_POLICY

偏差合并策略（`deviation.merge` 的行为契约）：

1. **合并键**：`dimension + entity` 组合为唯一键（`entity_id` 为辅助，不参与键判定）
2. **新偏差**：键不存在于状态 → 直接添加，`detection_count=1`，记录 `first_detected` 与 `last_detected`
3. **已有偏差**：键命中 → `detection_count += 1`，`last_detected` 更新为当前时间，`summary`/`detail` 取最新值（last-write-wins）
4. **已解决/保留状态保护**：`status == "resolved"` 或 `"retained"` 的偏差，合并时**不重置状态**，仅更新计数与时间戳、summary/detail
5. **多入口写入**：`novel-writer`（写后自检）、`novel-search-analysis`（align/full-diagnose）、`novel-diagnose` 均可调用 `deviation.merge`，按 `dimension+entity` 键控合并，**无需显式优先级**（last-write-wins 自然消解冲突）
6. **写入通道声明**：`deviation.merge` 是偏差库的写入通道，多方可调用，按 `dimension+entity` 键控合并
