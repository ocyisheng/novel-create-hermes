---
name: "novel-search-analysis"
description: "搜索分析：跨文件全文搜索、实体引用分析、意图对齐核验、交叉引用检测、Gap 分析、风格匹配、完整性检查。触发词：搜索、查找、分析、检查一下、找找、查一下、搜一下、核验、对齐、对比设定、看看有没有、哪里不对"
license: "MIT"
version: "1.0.0"
compatibility: "OpenCode"
tags: ["novel", "search", "analysis", "quality"]
---

# 搜索分析技能

## 核心职责

在内容生成后，提供搜索、分析、意图对齐核验能力。
**不生成新内容，不直接修改文件**——仅输出结构化分析报告，作为编排层和 novel-edit 的决策参考。

## 与相关技能的边界

| 技能 | 做什么 | 不做（本技能补） |
|------|--------|----------------|
| novel-grill | 事前需求发现（用户想要什么） | 事后核验生成内容是否符合需求 |
| novel-quality | 技术质量检测（写得好不好） | 意图对齐检测（是不是用户要的） |
| novel-edit | 修改内容（修正偏差） | 发现偏差（找到要改什么） |

**核心定位**：本技能是"找问题"的，edit 是"改问题"的。

## 调用方式

通过 `skill()` 直接调用（如 novel-edit、novel-grill 模式）：

```
skill("novel-search-analysis", user_message="mode=search, keyword=天道宗")
skill("novel-search-analysis", user_message="mode=entity-search, entity=林昭")
skill("novel-search-analysis", user_message="mode=align, target=character:林昭")
skill("novel-search-analysis", user_message="mode=cross-ref")
skill("novel-search-analysis", user_message="mode=gap")
skill("novel-search-analysis", user_message="mode=style-check, chapters=1-5")
skill("novel-search-analysis", user_message="mode=completeness")
skill("novel-search-analysis", user_message="mode=full-diagnose")
```

编排层传入 `user_message` 参数时自动解析模式标识（`mode=xxx`）。若未提供模式，默认走引导式询问。

## 搜索范围定义

所有模式共享的搜索范围定义（按优先级排序）：

| 优先级 | 目录 | 文件类型 | 内容说明 |
|--------|------|---------|---------|
| P0 | `chapters/` | `*.txt` | 章节正文 |
| P1 | `characters/` | `*.yaml` | 角色档案 |
| P1 | `worldbuilding/` | `*.yaml` | 世界观设定 |
| P2 | `outline/` | `*.yaml` | 总纲/分卷/分纲/情节线/追踪 |
| P3 | `ideation/` | `*.yaml` | 创意过程文档 |
| P3 | `quality/` | `*.yaml` | 质量检测报告 |
| P4 | `project_index.yaml` | yaml | 项目索引 |
| P4 | `config.yaml` | yaml | 项目配置 |

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
  │     ├─ 含"完整/缺/漏" → mode=completeness
  │     └─ 完全模糊 → 引导式询问
  └─ 不匹配 → 返回编排层
```

### 通用执行步骤

```
Step 0: 解析 user_message 参数 → 确定 mode、target、scope
    ↓
Step 1: 确定搜索范围 → 根据 mode 确定待扫描的文件列表
    ↓
Step 2: 执行搜索/分析 → 按 mode 对应的策略执行
    ├─ 脚本可处理的（关键词搜索、文件扫描）→ bash 调用 search_content.py
    └─ 需 LLM 推理的（意图分析、语义判断）→ AI 直接推理
    ↓
Step 3: 结构化输出 → 格式化为 YAML 分析报告
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
| `scope` | str | 否 | `all` | 搜索范围：all / chapters / characters / worldbuilding / outline / ideation / quality |
| `case_sensitive` | bool | 否 | `false` | 是否区分大小写 |
| `context_lines` | int | 否 | `3` | 上下文行数 |
| `max_results` | int | 否 | `50` | 最大结果数 |

**执行**：

1. 解析参数 → 确定搜索范围
2. 调用 `search_content.py` 执行文件系统搜索
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
| `include_chapters` | bool | 否 | `true` | 是否包含章节引用 |
| `include_outlines` | bool | 否 | `true` | 是否包含分纲引用 |

**执行**：

1. 搜索实体名在所有文件中的出现
2. 读取 `project_index.yaml` 获取实体元信息
3. 读取实体档案文件获取摘要信息
4. 整理引用链：按章节/分纲/设定文件分组
5. 统计：首次出场章节、最后出场章节、活跃状态
6. 输出 `quality/search/{entity}_实体引用.yaml`

**输出文件路径**：`quality/search/{entity}_实体引用.yaml`

---

### 模式三：意图对齐分析（mode=align）

**用途**：对比已生成内容 vs 用户原始意图，检查偏差。这是本技能最核心的能力。

**参数**：

| 参数 | 类型 | 必填 | 默认 | 说明 |
|------|------|------|------|------|
| `target` | str | 否 | `project` | 分析目标：project / character:角色名 / worldbuilding / chapter:章号 |
| `dimensions` | str | 否 | `all` | 分析维度：all / character / worldbuilding / plot / style / pacing |

**执行**：

1. **读取意图来源**：
   - `quality/grill/*.yaml`（grill 需求记录）
   - `ideation/最终创意方案.yaml`（创意方向）
   - `outline/追踪/intent/*.intent.yaml`（修改意图日志）
   - `config.yaml`（项目配置）
2. **提取可对比的偏好清单**：如角色核心特质、规则约束、节奏偏好、排除项
3. **逐项对比**：每条偏好 vs 实际内容
4. **评分**：每项 1-5 分，状态标记为 ✅ ⚠️ ❌ ❓
5. **输出报告**：含偏差项和建议

**输出文件路径**：`quality/align/{target}_对齐报告.yaml`

---

### 模式四：交叉引用分析（mode=cross-ref）

**用途**：检查不同实体文件之间的一致性，发现矛盾点。

**参数**：无（自动扫描全部）

**检测项**（7 项）：

| # | 检测项 | 来源 A | 来源 B | 矛盾类型 |
|---|--------|--------|--------|---------|
| 1 | 角色状态一致性 | characters/*.yaml | outline/分纲/*.yaml | 已故角色仍在出场 |
| 2 | 角色关系对称性 | characters/A.yaml | characters/B.yaml | 单向关系 |
| 3 | 势力归属一致性 | characters/*.yaml | worldbuilding/势力*.yaml | 角色势力不存在 |
| 4 | 地理位置一致性 | outline/分纲/*.yaml | worldbuilding/地理*.yaml | 场景地点不存在 |
| 5 | 能力边界一致性 | characters/*.yaml | chapters/*.txt | 使用未设定能力 |
| 6 | 时间线一致性 | outline/追踪/时间线.yaml | chapters/*.txt | 事件顺序矛盾 |
| 7 | 情节线完成度 | plot_threads/*.yaml | chapters/*.txt | 关键事件未出现 |

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

| 维度 | 检查逻辑 | 属性 |
|------|---------|------|
| 角色使用率 | 已创建角色 vs 已在章节中出场 | critical |
| 世界观使用率 | 已创建设定 vs 章节中引用 | info |
| 伏笔回收率 | 已设置伏笔 vs 已回收 | critical |
| 情节线完成度 | 关键事件 vs 已写章节数 | info |
| 分纲覆盖率 | 分纲章节数 vs 已写章节数 | info |

**输出文件路径**：`quality/align/Gap分析报告.yaml`

---

### 模式六：风格匹配度分析（mode=style-check）

**用途**：对比实际章节文本 vs 风格定义文件，分析匹配程度。

**参数**：

| 参数 | 类型 | 必填 | 默认 | 说明 |
|------|------|------|------|------|
| `chapters` | str | 否 | `all` | 分析范围：章节号范围（如 `1-5`）或 `all` |

**执行**：

1. 读取 `config.yaml` 的 `活跃风格` 字段
2. 读取对应的风格文件（`styles/{风格名}.yaml`）
3. 读取目标章节正文
4. 逐维度对比（叙事语调/句式结构/节奏特征/对话风格/修辞密度/人称视角/细节密度）
5. 输出 `quality/style/风格匹配报告.yaml`

**输出文件路径**：`quality/style/风格匹配报告.yaml`

---

### 模式七：设定完整性分析（mode=completeness）

**用途**：根据当前创作阶段，检查必要设定文件是否存在。

**参数**：无（自动检测当前阶段）

**阶段-设定映射**：

| 当前阶段 | 必须存在 | 建议存在 |
|---------|---------|---------|
| P1 创意构思 | 创意方案 | — |
| P2 世界观 | 世界观文件 | — |
| P3 角色 | 角色档案 | — |
| P4 总纲 | 总纲.yaml | — |
| P5 情节 | 情节线文件 | — |
| P6 分卷 | 分卷文件 | — |
| P7 分纲 | 分纲文件 | 追踪文件 |
| P8 章节 | 章节正文 | 全部追踪文件 |

**输出文件路径**：`quality/align/完整性报告.yaml`

---

### 模式八：综合诊断（mode=full-diagnose）

**用途**：合并各模式分析结果，按严重程度排序，给出优先处理建议。

**参数**：无（依次执行 cross-ref → gap → completeness → style-check）

**输出文件路径**：`quality/align/综合诊断_{project}.yaml`

---

## HARD CONSTRAINTS

1. **只读不写** — 不创建、修改、删除任何项目文件（仅向 `quality/` 输出分析报告）
2. **不替代 novel-grill** — 不做事前需求发现（那是 grill 的职责）
3. **不替代 novel-quality** — 不做技术质量检测（那是 quality 的职责）
4. **不替代 novel-edit** — 不直接修改内容，只输出偏差建议
5. **所有搜索限制在当前项目范围内** — 不扫描项目外文件
6. **输出路径固定** — 搜索报告写入 `quality/search/`，对齐分析写入 `quality/align/`，风格分析写入 `quality/style/`
7. **搜索脚本调用** — 关键词搜索使用 `bash python .opencode/skills/novel-search-analysis/scripts/search_content.py` 执行

## 项目前提

- Python 环境已初始化（先调用 `novel-env-setup`）
- 项目目录存在有效的 `config.yaml`
- 搜索分析的目标文件存在（空项目不报错，仅提示无内容）

## 参考文件

- `references/search_strategies.md` — 各类搜索策略详解
- `references/cross_ref_rules.md` — 交叉引用检测规则
- `references/alignment_criteria.md` — 意图对齐评估标准
