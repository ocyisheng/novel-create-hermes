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
**只读 graph 单元（不 create/update/archive/关系）；`deviation.merge` 为偏差库写入通道，多方可调用，按 `dimension+entity` 键控合并**——仅输出结构化分析报告。

**不做什么/边界**：不写优化线索/分析清单（不写 `.engine/analysis/`），分析结果只持久化到 `deviation_state.yaml`。

## 调用方式

通过 `skill()` 调用：

```
skill("novel-search-analysis", user_message="mode=search, keyword=天道宗")
skill("novel-search-analysis", user_message="mode=align, target=character:林昭")
skill("novel-search-analysis", user_message="mode=cross-ref")
skill("novel-search-analysis", user_message="mode=gap")
skill("novel-search-analysis", user_message="mode=full-diagnose")
```

深度诊断 subagent（novel-diagnose）传入 `user_message` 参数时自动解析模式标识（`mode=xxx`）。
若未提供模式，默认走引导式询问。

简单检索（"在哪里出现过"）由 orchestrator 经 novel-tool 自执行，无需本 skill；分析类任务（"分析一致性"、"哪里不对"）才走本 skill 的 LLM 推理路径。

---

## 分析模式（LLM 做的事）

以下每种模式，执行者都应按推理框架执行。通用分析方法详见 `references/quality_methodology.md`。

### 一、mode=search

在 SearchEngine 的机械搜索结果上做语义分析。

```
① 拿到原始数据：
   调 novel-tool (graph.search) 搜索关键词/正则/实体
   
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
    ├─ 用 novel-tool (graph.search) 搜索目标实体的所有引用
   ├─ 对比实际内容 vs 期望
   └─ 每项打分 1-5，标注状态 ✅ / ⚠️ / ❌ / ❓

③.5 多单元不一致归因（关键）：
   ├─ 当同一设定分布在多个 unit 且内容不一致时，先比较各 unit 的 updated_at
   ├─ updated_at 最新的 unit = 最近被修正/确认过 → 以它为准（权威值）
   ├─ 其他 unit 的旧值 = 未同步（不是设定错误）
   └─ 归因写法："unit B 的旧值未随 unit A 的修正同步更新"，
      而非"unit A 的设定有误"——避免把已修正的单元重复报为偏差

④ 每个偏差项生成 suggested_changeset

⑤ 偏差去重/计数由 deviation.merge 自动处理（按 dimension+entity 键控），无需手动过滤

⑥ deviation.merge 写入新偏差

```
> 评估维度详见 references/alignment_criteria.md

### 三、mode=cross-ref — 交叉引用检测

检测 graph 中的一致性规则。

```
① 获取机械检查结果：
   novel-tool(operation="graph.quality_check", project="{PROJECT}", layers="mechanical")

   返回 mechanical_results 列表，每条包含：
   - rule_id: R1/R3/R4/R5a/R5/R6/R9
   - rule_name: 规则名称
   - severity: error/warning/info
   - description: 问题描述
   - units_involved: 涉及单元ID列表

② 获取统计信号：
   novel-tool(operation="graph.quality_check", project="{PROJECT}", layers="statistical")

   返回 statistical_signals 列表，每条包含：
   - rule_id: R7/R10/R11/R12
   - signal_type: 信号类型
   - raw_value: 原始值
   - threshold: 阈值

③ 语义分析（需 LLM）：
   规则 5: 能力边界一致性
     → CHARACTER_ARC 中记录的能力 vs CHUNK 中实际使用的能力
     方法: 检索角色档案 + 含该角色的正文片段

   规则 6: 时间线一致性
     → NOTE[tags=时间线] 中的事件顺序 vs CHUNK 按章节排列的顺序
     方法: 检索时间线笔记 + 按章节排序的正文

   规则 7: 情节线完成度
     → PLOT_THREAD 中的关键事件 vs 已写的 CHUNK
     方法: 检索情节线 + 正文统计

④ 统计信号裁决（需 LLM）：
   R7 位置变化：判断是否合理剧情推进
   R10 节奏单调：判断是否有意的叙事节奏
   R11 密度偏离：判断是否高潮/过渡章节
   R12 主角能动性：判断是否角色性格设定

每项输出:
  - 矛盾类型: error / warning / info
  - 涉及单元: [unit_id1, unit_id2]
  - 归因: "角色A在角色档案中性格写的是隐忍，但在第3章的行为显示冲动——可能是在创作过程中调整了设定但没有同步更新角色档案"

时间戳辅助归因：当同一设定在多个单元间不一致时，先比较各单元
updated_at 判断"哪个是被修正过的最新值"：
  - 最新 updated_at 的单元 → 权威值（已修正/确认）
  - 其他单元 → 旧值未同步，归因为"未同步"，不重复报错
  - 若发现已修正单元之后又变回旧值 → 归因为"回退/覆盖"，需要人工确认
```

### 四、mode=gap — 使用率分析

```
① 从 novel-tool (graph.stats / graph.list_units) 获取统计数据：
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
① 确定当前扫描版本
   deviation.stats → full_scan_version

② 获取自该版本以来的变更单元
   novel-tool(operation="graph.get_modified_units", project="{PROJECT}", since_version="{full_scan_version}")
   → 返回 version > full_scan_version 的非 ARCHIVED 单元

③ 只对变更单元运行质量检查（增量分析）
   novel-tool(operation="graph.quality_check", project="{PROJECT}", layers="mechanical,statistical")

   注意：如果变更单元数量很大（>20个），优先分析：
   - 角色相关变更（影响面最大）
   - 世界观规则变更（影响面次之）
   - 创建新的单元（而不是只修改内容）

④ 偏差去重/计数由 deviation.merge 自动处理（按 dimension+entity 键控），无需手动过滤

⑤ deviation.merge 合并新偏差并更新扫描版本
   novel-tool(operation="deviation.merge", project="{PROJECT}", findings='[...]', full_scan_version="{最大unit.version}")
```

---

## 工具使用指引

### 获取数据

执行者通过 `novel-tool` 获取原始数据：

```
novel-tool(operation="graph.search", project="<PROJECT>", keyword="天道宗")
novel-tool(operation="graph.search", project="<PROJECT>", keyword="林昭", limit=10)
```

返回结果包含：`unit_id`、`unit_name`、`unit_type`、`content_preview`、`chapter`、`score`、`tags`、`status`、`version`、`neighbors` 等字段。

**重要**：novel-tool 只回答"数据在哪"，不回答"这意味着什么"。
后面的分析工作由执行者完成。

### novel-tool 参数契约

参数契约见 novel-tool.ts schema；操作语义见 novel-v2-core。

---

## LLM 通用推理链条

所有分析模式共享以下推理步骤：

```
Step 1: 确定分析范围
  ├─ 用户指定了实体/目标 → 缩小范围（graph.search 按关键词/名称检索）
  └─ 未指定 → 读 scan.full_scan_version，分析 version 有变动的
       单元（通过 graph.stats 确定完整扫描版本）

Step 2: 获取原始数据
  ├─ 调 novel-tool (graph.search / graph.stats / graph.check) → 结构化数据
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

执行者的最终输出应为结构化文本，包含以下部分：

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
- 描述: {分析结论}
- 归因: {判断的原因}
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


