---
name: "novel-v2-core"
description: "V2 共享核心子技能：操作语义、输出契约、HARD CONSTRAINTS。必须与角色技能（novel-v2-writing）一起加载。触发词：V2 操作、graph 操作、novel-tool、共享规范"
license: "MIT"
version: "2.0.0"
compatibility: "OpenCode"
tags: ["novel", "v2", "core", "shared"]
---

# novel-v2-core — V2 共享核心

## 定位

novel-v2-core 是 V2 创作体系的**共享操作层**：操作语义、输出契约、HARD CONSTRAINTS 全部集中于此。

**加载方式**：主 agent / subagent 通过 `load_skills=["novel-v2-core", "<角色技能>"]` 同时加载；方法论技能（`novel-six-dimensions` / `novel-grill` / `novel-ideation` / `novel-search-analysis`）按需叠加。

角色技能只保留角色定位与专属参考，不再重复操作指南：

| 角色技能 | 供谁使用 |
|----------|----------|
| `novel-v2-writing` | `novel-writer`（写作物化） |

> **不存在** `novel-v2-crafter` / `novel-ideation` / `novel-search-analysis` / `novel-v2-analyzer` / `novel-analyzer` 等 subagent —— 均为幽灵，调度即失败。创意方案用 `skill("novel-ideation")` 自执行加载；深度诊断用 `task(subagent_type="novel-diagnose", ...)`。

## 脚本 vs 提示词分工

| 层级 | 负责内容 | 示例 |
|------|----------|------|
| **脚本层** | 图操作、数据持久化、约束检查 | `novel-tool` → `run_operation` → `GraphStore` / `DeviationManager` |
| **提示词层** | 业务逻辑、领域知识、创作指导 | `novel-v2-core`（操作层）→ 角色技能（业务定位）→ 方法论技能（领域知识） |

## 操作语义

> **调用约定**：`novel-tool` 是 MCP 工具，以 JSON 传参（`operation` + 参数），非 Python 函数调用。**参数契约见 `novel-tool.ts` schema（`.opencode/tools/novel-tool.ts`）；类型特定 content 形状见 `unit_types/*.yaml`（`.opencode/shared/v2/unit_types/`）**——本节省略参数清单，只记录 schema 无法表达的语义。

### 单元操作

- `graph.get_unit`：按 ID 取单元详情（含完整 content）
- `graph.find_unit`：按名称/类型结构化查询（精确名匹配）
- `graph.search`：关键词/正则全文搜索，带评分排序
- `graph.list_units`：按类型/章节/卷/状态批量列出，分页
- `graph.create_unit`：创建单元（必须指定 `unit_type` / `name` / `content`）
- `graph.update_unit`：更新 content/status/tags
- `graph.archive_unit`：软删除（archived）；`graph.purge_archived` 彻底删除已归档单元

### 关系操作

- `graph.add_relation`：建立关系；`graph.remove_relation` / `graph.update_relation`：删除 / 更新关系
- `graph.get_relations`：按端点/标签/角色/类型过滤查询
- `graph.fix_asymmetry`：修复不对称关系；`graph.batch_infer`：关系批量推断

### 约束与质量

- `graph.flush`：**落盘 + 自动触发约束检查**（`skip_constraint_check=True` 可跳过）
- `graph.check`：增量约束检查（flush 后自动触发）；`constraint.check`：全量语义检查（`full=True`）
- `graph.quality_check`：统一质量检查，分层 `mechanical/statistical/semantic`

### 偏差管理

- `deviation.merge`：合并偏差（唯一写入通道，多入口）；`list` / `pending` / `resolve` / `retain` / `delete` / `stats` / `summary`：查询与状态流转
- 合并行为见下方 DEVIATION_MERGE_POLICY

### 会话管理

- `session.start`：生成 `session_id`，后续操作必须关联
- `session.build_workspace`：焦点预热（cold/warm/hot）；`session.set_cycle` / `set_phase`：循环与阶段推进；`session.info`：会话信息

### 项目 / 知识库 / Web / 分析

- 项目生命周期：`project.new` / `import` / `status` / `resume` / `switch` / `delete`；环境：`env.check` / `fix` / `force`
- 知识库：`knowledge.list_books` / `read`（按 slug + topic）
- Web 服务：`web.start` / `stop` / `restart`
- 会话摘要与分析：`summary.save/list/read`、`analysis.save/list/read/resolve`、`analyze.usage` / `analyze.telemetry`

### 结构操作

- `graph.stats`：单元统计；`graph.get_modified_units`：增量扫描（**必须带 `since_version`**）；`graph.recent_events`：最近事件
- `graph.get_neighbors` / `find_descendants` / `find_ancestors`：图遍历（`direction` + `max_depth`）
- `graph.list_relation_types`：关系类型清单；`graph.change_type`：修改单元类型；`graph.schema_info`：模式信息
- `graph.rebuild_structure_path` / `migrate_structure_to_edges`：结构路径重建 / 迁移；`graph.migrate`：版本升级（`since_version` + `verify`/`report`）
- `graph.export_docs` / `export_chunks`：导出文档 / 片段（`out` 指定目录）

### 关键语义

1. **检索路径选择**：有 ID → `get_unit`；知道确定名称 → `find_unit`；需模糊/跨类型/正则匹配 → `search`；批量遍历 → `list_units`
2. **flush 自动触发约束检查**：写操作完成后 `graph.flush` 落盘即触发增量约束检查，无需手动 `graph.check`；全量语义检查才需 `constraint.check`
3. **bidirectional 三态**：`always`（总是建反向边）/ `optional`（物化，视语义而定）/ `never`（不建反向，返回 warning）——`bidirectional=True` 优先，禁止无意识单向关系
4. **if_exists 策略**：同名单元已存在时 `error`（默认，报错）/ `skip`（跳过）/ `create`（强行新建）
5. **actor 门禁**：`actor` 参数标识操作者并限定写权限——`novel-planner` 只能写 NOTE 单元；`novel-writer` 走白名单（单元内容创作/关系构建/质量检查）；`novel-analyzer` / `novel-diagnose` / `novel-lore-search` 只读（仅 `deviation.merge` 例外）
6. **操作顺序规则**：先 `graph.create_unit` 再 `graph.add_relation`（关系必须指向已存在单元）；`flush` 前完成本批全部 `add_relation`，否则约束检查会报孤立边/缺失关系
7. **增量扫描**：`graph.get_modified_units` 必须指定 `since_version`，禁止无版本增量扫描

### DEVIATION_MERGE_POLICY

偏差合并策略（`deviation.merge` 的行为契约）：

1. **合并键**：`dimension + entity` 组合为唯一键（`entity_id` 为辅助，不参与键判定）
2. **新偏差**：键不存在于状态 → 直接添加，`detection_count=1`，记录 `first_detected` 与 `last_detected`
3. **已有偏差**：键命中 → `detection_count += 1`，`last_detected` 更新为当前时间，`summary`/`detail` 取最新值（last-write-wins）
4. **已解决/保留状态保护**：`status == "resolved"` 或 `"retained"` 的偏差，合并时**不重置状态**，仅更新计数与时间戳、summary/detail
5. **多入口写入**：`novel-writer`（写后自检）、`novel-search-analysis`（align/full-diagnose）、`novel-diagnose` 均可调用 `deviation.merge`，按 `dimension+entity` 键控合并，**无需显式优先级**（last-write-wins 自然消解冲突）
6. **写入通道声明**：`deviation.merge` 是偏差库的写入通道，多方可调用，按 `dimension+entity` 键控合并

## 输出契约

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
