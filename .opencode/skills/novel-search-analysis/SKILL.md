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

如果用户只是问"在哪里出现过"这种简单问题，不需要 LLM 分析——直接调 novel-tool：

```
novel-tool --operation graph.search --project <PROJECT> --keyword "天道宗"
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

④ 每个偏差项生成 suggested_changeset

⑤ deviation_manager.merge() 写入偏差状态

```
> 评估维度详见 references/alignment_criteria.md

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
  方法: 检索角色档案 + 含该角色的正文片段

规则 6: 时间线一致性（需 LLM 语义分析）
  → NOTE[tags=时间线] 中的事件顺序 vs CHUNK 按章节排列的顺序
  方法: 检索时间线笔记 + 按章节排序的正文

规则 7: 情节线完成度（需 LLM 语义分析）
  → PLOT_THREAD 中的关键事件 vs 已写的 CHUNK
  方法: 检索情节线 + 正文统计

详见 references/cross_ref_rules.md 获取完整说明。

每项输出:
  - 矛盾类型: error / warning / info
  - 涉及单元: [unit_id1, unit_id2]
  - 你的归因: "角色A在角色档案中性格写的是隐忍，但在第3章的行为显示冲动——可能是在创作过程中调整了设定但没有同步更新角色档案"
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
   novel-tool --operation graph.get_modified_units --project <PROJECT> --since_version <full_scan_version>
   → 返回 version > full_scan_version 的非 ARCHIVED 单元

③ 只对变更单元运行 align + cross-ref + gap（增量分析）
   注意：如果变更单元数量很大（>20个），优先分析：
   - 角色相关变更（影响面最大）
   - 世界观规则变更（影响面次之）
   - 创建新的单元（而不是只修改内容）

④ 合并新偏差并更新扫描版本
   novel-tool --operation deviation.merge --project <PROJECT> --findings '[...]' --full_scan_version <最大unit.version>
```

---

## 工具使用指引

### 获取数据

你（LLM）通过 `novel-tool` 获取原始数据：

```
novel-tool --operation graph.search --project <PROJECT> --keyword "天道宗"
novel-tool --operation graph.search --project <PROJECT> --keyword "林昭" --limit 10
```

返回结果包含：`unit_id`、`unit_name`、`unit_type`、`content_preview`、`chapter`、`score`、`tags`、`status`、`version`、`neighbors` 等字段。

**重要**：novel-tool 只回答"数据在哪"，不回答"这意味着什么"。
后面的分析工作是你（LLM）的事。

### novel-tool 命令参考

```
# 搜索
novel-tool --operation graph.search --project <PROJECT> --keyword "天道宗"
novel-tool --operation graph.search --project <PROJECT> --keyword "林昭"
novel-tool --operation graph.search --project <PROJECT> --pattern "筑基.*期" --regex
novel-tool --operation graph.search --project <PROJECT> --keyword "剑" --scope SCENE --limit 10

# 一致性检查（输出供 LLM 分析的结构化数据）
novel-tool --operation graph.check --project <PROJECT>
# 输出：4 条规则的结构化数据

# 项目统计 + gap 数据
novel-tool --operation graph.stats --project <PROJECT>
```

### 偏差持久化

分析中发现的偏差通过 `deviation.*` 操作持久化到 `graph/deviation_state.yaml`：

```
# 合并新发现
novel-tool --operation deviation.merge --project <PROJECT> --findings '[{"dimension":"character_trait","entity":"林昭","severity":"warning","summary":"角色档案写的是'杀伐果断'，但第3章的行为偏'隐忍谨慎'"}]'

# 查看当前待处理偏差
novel-tool --operation deviation.pending --project <PROJECT>

# 标记为已解决
novel-tool --operation deviation.resolve --project <PROJECT> --id <偏差ID>

# 标记为保留（正常设计）
novel-tool --operation deviation.retain --project <PROJECT> --id <偏差ID>

# 偏差统计
novel-tool --operation deviation.stats --project <PROJECT>
```

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


