---
name: "novel-search-analysis"
description: "搜索分析：跨文件全文搜索、实体引用分析、意图对齐核验、交叉引用检测、Gap 分析。触发词：搜索、查找、分析、检查一下、找找、查一下、搜一下、核验、对齐、对比设定、看看有没有、哪里不对"
license: "MIT"
version: "1.0.0"
compatibility: "OpenCode"
tags: ["novel", "search", "analysis", "quality"]
---

# 搜索分析技能

## 核心职责

在内容生成后，提供搜索、分析、意图对齐核验能力，找出创作数据与用户意图之间的偏差。
**不生成新内容，不直接修改文件**——仅输出结构化分析报告。

**分析范围**：项目中的全部创作数据——角色、世界观、情节线、场景、分纲、总纲、创意笔记、追踪数据。章节正文可通过 QUERY 协议的 `advanced_search` 检索。

**核心定位**：本技能是"找问题"的，edit 是"改问题"的。

## 调用方式

通过 `skill()` 直接调用（如 novel-edit、novel-grill 模式）：

```
skill("novel-search-analysis", user_message="mode=search, keyword=天道宗")
skill("novel-search-analysis", user_message="mode=entity-search, entity=林昭")
skill("novel-search-analysis", user_message="mode=align, target=character:林昭")
skill("novel-search-analysis", user_message="mode=cross-ref")
skill("novel-search-analysis", user_message="mode=gap")
skill("novel-search-analysis", user_message="mode=full-diagnose")
```

编排层传入 `user_message` 参数时自动解析模式标识（`mode=xxx`）。若未提供模式，默认走引导式询问。

## 搜索范围定义

所有模式共享的搜索范围定义（按优先级排序）。
**分析域为项目 graph/ 中的全部叙事单元**，通过 `v2_cli.py` 或 GraphStore API 检索。

| 优先级 | 叙事单元类型 | V2 CLI 查询 | 内容说明 |
|--------|-------------|-------------|---------|
| 高 | `CHARACTER_ARC` | `list-units --type CHARACTER_ARC` | 角色档案 |
| 高 | `WORLD_RULE` | `list-units --type WORLD_RULE` | 世界观设定 |
| 高 | `PLOT_THREAD` | `list-units --type PLOT_THREAD` | 情节线 |
| 高 | `SCENE` | `list-units --type SCENE` | 场景/分纲 |
| 中 | `NOTE` | `list-units --type NOTE` | 创意笔记/追踪数据 |
| 中 | `CHUNK` | `list-units --type CHUNK` | 章节正文 |
| 低 | — | `config.yaml` | 项目配置 |


## 工作流程

### 入口路由

```
用户输入
  ├─ 明确模式标识（mode=search / mode=align / ...）
  │   → 按该模式执行
  ├─ 触发词匹配（搜索/查找/看看有没有/找一下/查一下/搜一下/分析/核验/对齐）
  │   → 自动判断模式
  │     ├─ 含关键词 + 无实体名 → mode=search
  │     ├─ 含实体名（角色/地名） → mode=entity-search
  │     ├─ 含"对比/检查设定/核验" → mode=align
  │     ├─ 含"完整/缺/漏/不足" → mode=gap
  │     └─ 完全模糊 → 引导式询问
  └─ 不匹配 → 返回编排层
```

### 通用执行步骤

```
Step 0: 解析 user_message 参数 → 确定 mode、target、scope
    ↓
Step 1: 确定数据来源
    ├─ mode=full-diagnose / align（未指定实体）
    │   → 使用 v2_cli.py list-units / GraphStore API 获取叙事单元列表
    │   → 通过 events.olog 比对 version/updated_at 筛选有变动的单元
    └─ mode=search / entity-search / align（指定实体）
        → 直接扫描目标文件或查询 graph 特定节点
    ↓
Step 2: 执行搜索/分析 → 按 mode 对应的策略执行
    ├─ 关键词搜索 → 使用 Grep 工具精确匹配
    ├─ 文件扫描/遍历 → 使用 Glob 工具枚举文件
    ├─ 需 LLM 推理的（意图分析、语义判断）→ AI 直接推理
    └─ 分析完成后 → 通过 deviation_manager 合并到 deviation_state
    ↓
Step 3: 结构化输出 → 格式化为 YAML 分析报告
    ├─ 每个偏差项附带 suggested_changeset（apply_changes 兼容格式）
    └─ 新/旧偏差标注（基于 deviation_state 去重）
    ↓
Step 4: 展示摘要 → 向用户展示关键发现和建议
```

## 模式详解

### 模式一：全文搜索（mode=search）

**用途**：跨项目目录进行关键词/短语搜索，找到所有出现位置及上下文。

**参数**：

| 参数 | 类型 | 必填 | 默认 | 说明 |
|------|------|------|------|------|
| `keyword` | str | 是 | — | 搜索关键词 |
| `scope` | str | 否 | `all` | 搜索范围：all / character_arc / world_rule / plot_thread / scene / note / chunk |
| `case_sensitive` | bool | 否 | `false` | 是否区分大小写 |
| `context_lines` | int | 否 | `3` | 上下文行数 |
| `max_results` | int | 否 | `50` | 最大结果数 |

**执行**：

1. 解析参数 → 确定搜索范围（scope 参数限制目录）
2. 使用 Grep 工具在指定目录中搜索关键词
3. 整理结果 → 按文件分组，标注行号和上下文
4. 输出 `quality/search/{keyword}_搜索结果.yaml`

**输出文件路径**：`quality/search/{keyword}_搜索结果.yaml`

---

### 模式二：实体搜索（mode=entity-search）

**用途**：搜索特定实体（角色/地点/势力/物品）在所有文件中的引用情况，生成完整引用链。

**参数**：

| 参数 | 类型 | 必填 | 默认 | 说明 |
|------|------|------|------|------|
| `entity` | str | 是 | — | 实体名称 |
| `type` | str | 否 | `all` | 实体类型：character / location / faction / item / all |
| `include_outlines` | bool | 否 | `true` | 是否包含分纲引用 |

**执行**：

1. 通过 `v2_cli.py find-unit --name {entity}` 查找实体
2. 通过 `v2_cli.py get-unit --id {id}` 获取详情
3. 通过 `v2_cli.py get-neighbors --id {id}` 查关联实体
4. 整理引用链：按关联类型分组
5. 统计：关联数、活跃状态
6. 输出 `quality/search/{entity}_实体引用.yaml`

**输出文件路径**：`quality/search/{entity}_实体引用.yaml`

---

### 模式三：意图对齐分析（mode=align）

**用途**：对比已生成内容 vs 用户原始意图，检查偏差。这是本技能最核心的能力。

**参数**：

| 参数 | 类型 | 必填 | 默认 | 说明 |
|------|------|------|------|------|
| `target` | str | 否 | `project` | 分析目标：project / character:角色名 / worldbuilding |
| `dimensions` | str | 否 | `all` | 分析维度：all / character / worldbuilding / plot / style / pacing |

**执行**：

1. **解析目标实体**：
   - 指定了 target（如 `character:林昭`）→ 从 graph 中查询节点信息和出边
   - 未指定 target（默认 project）→ 使用 `v2_cli.py stats` 获取单元概览，通过 events.olog 的 `updated_at` 筛选最近变动的实体
2. **读取意图来源**：
   - `quality/grill/*.yaml`（grill 需求记录）
   - `v2_cli.py list-units --type NOTE` 中 `tags` 含"创意"的单元（创意方向）
   - `v2_cli.py list-units --type NOTE` 中 `tags` 含"意图"的单元（修改意图日志）
   - `config.yaml`（项目配置）
3. **提取可对比的偏好清单**：如角色核心特质、规则约束、节奏偏好、排除项
4. **逐项对比**：每条偏好 vs 实际内容
5. **评分**：每项 1-5 分，状态标记为 ✅ ⚠️ ❌ ❓
6. **生成变更集**：每个偏差项附带 `suggested_changeset`（apply_changes 兼容格式）
7. **偏差状态合并**：调用 `deviation_manager.py merge` 写入 deviation_state
8. **输出报告**：含偏差项、变更集、偏差状态（新/已解决/用户保留）

**输出文件路径**：`quality/align/{target}_对齐报告.yaml`

**输出格式（每个偏差项）**：
```yaml
- dimension: "character_trait"
  status: "pending"            # 来自 deviation_state 的合并结果
  first_detected: "2026-07-01T12:00:00"
  detection_count: 1
  
  actual: "隐忍谨慎"
  expected: "杀伐果断"
  
  suggested_changeset:         # 可执行变更集
    changes:
      - op: "replace"
        path: "完整档案.性格.核心特质"
        old_value: "隐忍谨慎"
        new_value: "杀伐果断"
    summary: "根据grill记录修正核心特质"
  
  intent_log_ref: "NOTE(林昭意图记录, tags=[意图])"
```

---

### 模式四：交叉引用分析（mode=cross-ref）

**用途**：检查不同实体文件之间的一致性，发现矛盾点。

**参数**：无（自动扫描全部）

**检测项**（7 项）：

| # | 检测项 | V2 数据源 A | V2 数据源 B | 矛盾类型 |
|---|--------|-------------|-------------|---------|
| 1 | 角色状态一致性 | `CHARACTER_ARC.status == ARCHIVED` | `Relation(type=PARTICIPATES_IN)` → SCENE | 已故角色仍在出场 |
| 2 | 角色关系对称性 | `get_relations(A.id, outgoing)` | `get_relations(B.id, outgoing)` | 单向关系 |
| 3 | 势力归属一致性 | `CHARACTER_ARC` ↔ `WORLD_RULE` 的 BELONGS_TO 关系 | 匹配 WORLD_RULE.unit_name | 角色势力未定义 |
| 4 | 地理位置一致性 | `SCENE` 内容 → 匹配 `WORLD_RULE`（tags 含"地理"） | WORLD_RULE.unit_name | 场景地点未定义 |
| 5 | 能力边界一致性 | `CHARACTER_ARC.content` 中解析的技能列表 | `CHUNK.content` 全文（LLM 分析） | 能力溢出 |
| 6 | 时间线一致性 | `NOTE`（tags 含"时间线"）的内容 | `CHUNK` 按 belongs_to_chapter 排序 | 事件顺序矛盾 |
| 7 | 情节线完成度 | `PLOT_THREAD.content` 中的关键事件 | `CHUNK` + `SCENE` 已覆盖内容 | 关键事件未覆盖 |

**执行**：

1. 按上表逐项检查
2. 每项读取对应文件对进行对比
3. 标记矛盾点（error/warning/info）
4. 输出 `quality/align/交叉引用报告.yaml`

**输出文件路径**：`quality/align/交叉引用报告.yaml`

---

### 模式五：Gap 分析（mode=gap）

**用途**：检查已生成但未使用的内容（浪费），以及该有但缺失的内容（遗漏）。

**参数**：无（自动扫描全部）

**分析维度**：

| 维度 | 检查逻辑 | V2 数据源 | 属性 |
|------|---------|-----------|------|
| 角色使用率 | 已创建角色 vs 已有 PARTICIPATES_IN 关系的角色 | `CHARACTER_ARC` 总数 vs `get_relations(type=PARTICIPATES_IN)` 不重复角色数 | critical |
| 世界观使用率 | 已创建规则 vs 被 REFERENCES 关系引用的规则 | `WORLD_RULE` 总数 vs `get_relations(type=REFERENCES)` 不重复规则数 | info |
| 场景覆盖率 | 已有 SCENE 数 vs 预期章节数 | `list-units --type SCENE` count | info |
| 情节线完成度 | 关键事件 vs 已写 CHUNK 数 | `PLOT_THREAD.content` 中提取事件数 vs `CHUNK` 数 | info |

**输出文件路径**：`quality/align/Gap分析报告.yaml`

---

### 模式六：综合诊断（mode=full-diagnose）

**用途**：基于项目图谱的全量偏差检测。一次性检测全部实体中从上次扫描后有变动的部分，合并偏差状态，输出带变更集的聚合报告。

**参数**：无（自动扫描并对比 graph 校验和）

**执行流程**：

```
Step 1: 确认 graph 就绪
 └─ graph/ 目录存在 → 初始化 GraphStore 或 v2_cli.py stats
      → 遍历所有叙事单元，通过 version/updated_at 筛选有变动的单元

Step 2: 筛选分析目标
  ├─ 有变动的实体 → 进入 Step 3（LLM 分析）
  └─ 无变动的实体 → 跳过（但仍会检查 deviation_state 中是否有未处理的历史偏差）

Step 3: 加载偏差状态
  → 读取 deviation_state.yaml
  → filter_for_presentation() 获取待展示列表（应用 B1 频次控制）

Step 4: 执行偏差检测
  → 对有变动的实体逐项执行 align 分析（含 changeset 生成）

Step 5: 合并状态
  → deviation_manager merge（新偏差入库，重复项递增 detection_count）

Step 6: 输出聚合报告
  └─ quality/align/综合诊断_{project}.yaml
      ├─ summary: 实体总数、已扫变动数、新偏差数、历史未解决数
      ├─ deviations: [{entity, field, expected, actual, changeset, status}, ...]
      └─ filtered: {folded, skipped_resolved, skipped_retained}
```

**输出文件路径**：`quality/align/综合诊断_{project}.yaml`

**与编排层的交互**：
报告输出后，编排层读取 deviations 列表 → 按实体分组展示 → 用户确认 → 编排层批量调度 novel-edit
（具体呈现格式见编排层 novel-writer.md 路由文档）

---

## HARD CONSTRAINTS

1. **只读不写创作文件** — 不创建、修改、删除任何实体/章节/设定文件（仅向 `quality/` 输出分析报告，向 `graph/deviation_state.yaml` 写入偏差状态——偏差状态是元数据，不是创作内容）
2. **不替代 novel-grill** — 不做事前需求发现（那是 grill 的职责）
3. **不替代 novel-quality** — 不做技术质量检测（那是 quality 的职责）
4. **不替代 novel-edit** — 不直接修改内容，只输出偏差建议
5. **所有搜索限制在当前项目范围内** — 不扫描项目外文件
6. **输出路径固定** — 搜索报告写入 `quality/search/`，对齐分析写入 `quality/align/`，偏差状态写入 `graph/deviation_state.yaml`

## 项目前提

- Python 环境已初始化（先调用 `novel-env-setup`）
- 项目目录存在有效的 `config.yaml`
- 搜索分析的目标文件存在（空项目不报错，仅提示无内容）

## 参考文件

- `references/search_strategies.md` — 各类搜索策略详解
- `references/cross_ref_rules.md` — 交叉引用检测规则
- `references/alignment_criteria.md` — 意图对齐评估标准
