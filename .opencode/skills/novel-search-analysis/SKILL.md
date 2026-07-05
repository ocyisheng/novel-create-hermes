---
name: "novel-search-analysis"
description: "搜索分析：跨文件全文搜索、实体引用分析、意图对齐核验、交叉引用检测、Gap 分析。触发词：搜索、查找、分析、检查一下、找找、查一下、搜一下、核验、对齐、对比设定、看看有没有、哪里不对"
license: "MIT"
version: "2.0.0"
compatibility: "OpenCode"
tags: ["novel", "search", "analysis", "quality", "v2"]
---

# 搜索分析技能 (V2)

## 核心职责

在创作过程中（不限于"之后"），提供搜索、分析、意图对齐核验能力，找出创作数据与用户意图之间的偏差。
**不生成新内容，不直接修改 graph**——仅输出结构化分析报告。

**定位变化**：V1 版本是"文件搜索工具"，V2 版本是 **LLM 分析推理框架**。

| V1 方式（废弃） | V2 方式 |
|----------------|---------|
| Python 脚本做全文搜索 + 模式匹配 | **SearchEngine 做机械搜索**，LLM 做语义分析 |
| 固定 mode 参数调用 | **LLM 按需选择分析维度** |
| 输出到 `quality/search/` 目录 | **分析结果注入 agent 上下文**，驱动下一步创作决策 |
| 依赖 events.olog 做增量 | **基于 unit.version**，与 VizIncrementalEngine 同一模式 |

## 架构

```
你（LLM） ← skill 指令指导你的分析思路
  │
  ├── 调 SearchEngine / v2_cli.py → 拿原始数据
  ├── 自己读 deviation_state.yaml → 历史上下文
  ├── 自己做语义分析、对比、归因
  └── 用 DeviationManager 记录发现的偏差
```

## 调用方式

通过 `skill()` 调用：

```
skill("novel-search-analysis", user_message="mode=search, keyword=天道宗")
skill("novel-search-analysis", user_message="mode=align, target=character:林昭")
skill("novel-search-analysis", user_message="mode=cross-ref")
skill("novel-search-analysis", user_message="mode=gap")
skill("novel-search-analysis", user_message="mode=full-diagnose")
```

编排层传入 `user_message` 参数时自动解析模式标识（`mode=xxx`）。
若未提供模式，默认走引导式询问。

### 直接搜索（不需要 skill）

如果用户只是问"在哪里出现过"这种简单问题，不需要 LLM 分析——直接调 CLI：

```
bash: python .opencode/shared/v2_cli.py search --path <PROJECT> --keyword "天道宗"
```

### 分析类任务（需要 skill）

如果用户要求"分析一致性"、"帮我看看哪里不对"、"检查一下设定矛盾"——切换到 skill 路径，LLM 做推理。

---

## 分析模式（LLM 做的事）

以下每种模式，你（LLM）都要按推理框架执行。

### 一、mode=search

在 SearchEngine 的机械搜索结果上做语义分析。

```
① 拿到原始数据：
   调 SearchEngine(v2_cli.py) 搜索关键词/正则/实体
   
② 语义分析：
   ├─ 关键词在 content 中是什么语境（设定描述/角色对话/叙事旁白）？
   ├─ 这些出现位置之间有关联吗（重复引用/剧情推进/矛盾）？
   └─ 覆盖了所有应该出现的场景吗（有无遗漏）？

③ 输出：结构化分析 + 发现
```

### 二、mode=align — 意图对齐

对比"用户想写的" vs "实际写了什么"。

```
① 获取用户意图来源：
   ├─ NOTE 类型 + tags=["意图"] → 修改意图日志
   ├─ NOTE 类型 + tags=["创意"] → 创意方向
   ├─ config.yaml → 项目配置
   └─ grill 记录（如果有）

② 提取可对比的偏好清单：
   ├─ 角色特质要求（如"杀伐果断"）
   ├─ 规则约束（如"筑基期不能使用元神出窍"）
   ├─ 节奏偏好（如"前三章要有第一个高潮"）
   └─ 排除项（如"不要系统流设定"）

③ 逐项对比：
   ├─ 用 SearchEngine 搜索目标实体的所有引用
   ├─ 对比实际内容 vs 期望
   └─ 每项打分 1-5，标注状态 ✅ / ⚠️ / ❌ / ❓

④ 每个偏差项生成 suggested_changeset

⑤ deviation_manager.merge() 写入偏差状态

> 评估维度详见 references/alignment_criteria.md
```

### 三、mode=cross-ref — 交叉引用检测

检测 graph 中 7 条一致性规则。

```
规则 1: 已故角色仍在出场？
  → 查 CHARACTER_ARC[status=ARCHIVED] ↔ PARTICIPATES_IN → SCENE
  方法: SearchEngine.check_consistency() 已有此规则

规则 2: 角色关系不对称？
  → A 列出了 B 但 B 没列出 A
  方法: SearchEngine.check_consistency() 已有此规则

规则 3: 孤立单元（没有任何关系）
  → SearchEngine.check_consistency() 已有此规则

规则 4: 归档单元仍有活跃关系
  → SearchEngine.check_consistency() 已有此规则

规则 5: 能力边界一致性（需 LLM 语义分析）
  → CHARACTER_ARC 中记录的能力 vs CHUNK 中实际使用的能力
  方法: SearchEngine.search(entity="林昭") 获取角色档案，search(keyword="林昭", scope=[CHUNK]) 获取正文

规则 6: 时间线一致性（需 LLM 语义分析）
  → NOTE[tags=时间线] 中的事件顺序 vs CHUNK 按章节排列的顺序
  方法: SearchEngine.search(keyword="时间线", scope=[NOTE]) 获取时间线记录

规则 7: 情节线完成度（需 LLM 语义分析）
  → PLOT_THREAD 中的关键事件 vs 已写的 CHUNK
  方法: SearchEngine.search(scope=[PLOT_THREAD]) 获取情节线

详见 references/cross_ref_rules.md 获取完整说明。

每项输出:
  - 矛盾类型: error / warning / info
  - 涉及单元: [unit_id1, unit_id2]
  - 你的归因: "角色A在角色档案中性格写的是隐忍，但在第3章的行为显示冲动——可能是在创作过程中调整了设定但没有同步更新角色档案"
```

### 四、mode=gap — 使用率分析

```
① 从 SearchEngine / GraphStore 获取统计数据：
  - 角色总数 vs 有 PARTICIPATES_IN 关系的角色数
  - 世界观规则总数 vs 被 REFERENCES 引用的规则数
  - 情节线关键事件数 vs 已写 CHUNK 数
  - 所有单元的关联率（多少单元至少有一条关系）

② 分析：
  - 哪些角色创建了但一直没出场？（CHARACTER_ARC 无 PARTICIPATES_IN）
  - 哪些设定写了但正文里从未体现？（WORLD_RULE 无 REFERENCES）
  - 哪些伏笔埋了但还没收？（NOTE 无 PARALLEL/IMPLEMENTS 关系）
  - 情节线进度：关键事件 vs 已写章节（详见 references/cross_ref_rules.md R7）
  - 全局故事资产的利用率 -> 给出具体的"可以删除的"或"可以激活的"建议
```

### 五、mode=full-diagnose — 增量综合诊断

```
① 读 deviation_state.yaml
   ├─ scan.full_scan_version（全局已分析的版本）
   └─ scan.last_scan_at（上次分析时间）

② 调 SearchEngine.get_modified_units(full_scan_version)
   ├─ 遍历所有非 ARCHIVED 单元
   └─ 返回 unit.version > full_scan_version 的变更单元

③ 只对变更单元运行 align + cross-ref + gap（增量分析）
   注意：如果变更单元数量很大（>20个），优先分析：
   - 角色相关变更（影响面最大）
   - 世界观规则变更（影响面次之）
   - 创建新的单元（而不是只修改内容）

④ deviation_manager.merge() 合并新旧偏差

⑤ 写回 deviation_state.yaml：
   ├─ full_scan_version = 当前全局最大 version
   └─ 更新已扫描单元的 version
```

> **为什么不基于 events.olog？** events.olog 是操作日志，按操作数增长而非内容数增长。
> 正确做法是 **unit.version 对比**——与 VizIncrementalEngine 同一模式（见 `v2_graph_viz.py:942`），
> O(n_units) 而非 O(n_events)。

---

## 工具使用指引

### SearchEngine（纯数据检索，不做分析）

你（LLM）通过以下方式获取原始数据：

```python
# 方式一：直接 import（在编排层可用 Python 的环境中）
from search_engine import SearchEngine
engine = SearchEngine(store)
result = engine.search(keyword="天道宗", max_results=20)

# 方式二：通过 CLI（在 bash 中执行）
python .opencode/shared/v2_cli.py search --path <PROJECT> --keyword "天道宗"
python .opencode/shared/v2_cli.py search --path <PROJECT> --entity "林昭" --limit 10
```

SearchEngine 的输出是 `SearchResultSet`，包含：
- `results`: `List[SearchResult]`（每个含 unit_id/name/type/content_preview/version/neighbors）
- `total`: 总数
- `time_ms`: 耗时

**重要**：SearchEngine 只回答"数据在哪"，不回答"这意味着什么"。
后面的分析工作是你（LLM）的事。

### CLI 命令参考

```bash
# 搜索
v2_cli.py search --path <PROJECT> --keyword "天道宗"
v2_cli.py search --path <PROJECT> --entity "林昭"
v2_cli.py search --path <PROJECT> --pattern "筑基.*期" --regex
v2_cli.py search --path <PROJECT> --keyword "剑" --scope SCENE --limit 10

# 一致性检查（输出供 LLM 分析的结构化数据）
v2_cli.py check --path <PROJECT>
# 输出：7 条规则的结构化数据

# 项目报告
v2_cli.py report --path <PROJECT>
v2_cli.py report --path <PROJECT> --with-deviations
```

### DeviationManager（状态存储）

分析中发现的偏差通过 DeviationManager 持久化：

```python
from deviation_manager import DeviationManager, DeviationItem

mgr = DeviationManager(project_root)
mgr.merge([DeviationItem(
    dimension="character_trait",
    entity="林昭",
    scanned_version=15,
    summary="角色档案写的是'杀伐果断'，但第3章的行为偏'隐忍谨慎'",
    suggested_changeset={"changes": [
        {"op": "replace", "path": "性格.核心特质", "old_value": "隐忍果断", "new_value": "杀伐果断"}
    ]},
)])
mgr.save()
```

偏差状态文件存储在 `graph/deviation_state.yaml`。

---

## LLM 通用推理链条

所有分析模式共享以下推理步骤：

```
Step 1: 确定分析范围
  ├─ 用户指定了实体/目标 → 缩小范围（SearchEngine.search(entity=...)）
  └─ 未指定 → 读 scan.full_scan_version，分析 version 有变动的
       单元（SearchEngine.get_modified_units(version)）

Step 2: 获取原始数据
  ├─ 调 SearchEngine / v2_cli.py → 结构化数据
  └─ 读 deviation_state.yaml → 历史状态

Step 3: LLM 逐项分析
  ├─ 对比（实际 vs 期望，或统计 vs 预期）
  ├─ 归因（差异的原因是什么）
  └─ 评级（严重程度、影响范围）

Step 4: 结果持久化
  ├─ deviation_manager.merge() → 写入新偏差/更新旧偏差
  └─ 输出 YAML 报告

Step 5: 生成可执行动作
  └─ 每个偏差项附带 suggested_changeset
```

---

## 分析完成后输出格式

你的最终输出应为结构化文本，包含以下部分：

```
【分析报告】

## 概要
- 分析模式: align/cross-ref/gap/full-diagnose
- 分析范围: {具体实体或范围}
- 发现总数: N

## 发现列表

### 1. {简要标题}
- 类型: error/warning/info
- 涉及: 单元名 (类型)
- 描述: {你的分析结论}
- 归因: {你认为的原因}
- 建议:
  ```yaml
  changes:
    - op: replace
      path: "性格.核心特质"
      old_value: "隐忍果断"
      new_value: "杀伐果断"
  ```

### 2. ...

## 偏差状态
- 本次新增/更新: N 条
- 历史待解决: N 条
```

---

## 与 V2 设计哲学

| 原则 | 本技能如何遵守 |
|------|--------------|
| **Graph 是单一真相源** | 只查 GraphStore，不走文件系统 |
| **无阶段概念** | 搜索分析不是"写完后才能做的事"，任何时候都可以 |
| **焦点驱动** | 分析范围由焦点实体确定，不是整个项目 |
| **冷/温/热预热** | full-diagnose 只分析 version 有变动的单元 |
| **QUERY 协议** | 子 agent 通过 QUERY 获取搜索数据 |
| **事件溯源** | events.olog 用于调试；增量分析用 unit.version |
| **创作循环** | 偏差状态可以被后续写作引用和解决 |
