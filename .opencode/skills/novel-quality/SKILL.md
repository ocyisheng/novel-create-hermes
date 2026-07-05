---
name: "novel-quality"
description: "质量把控：提供 AI 味道检测、情节逻辑检测、角色一致性检查、世界观漏洞检测、节奏分析、读者体验评估、风格一致性委托共 7 路检测。全部基于 V2 graph 数据源。触发词：质量、检测、AI味、太AI、没有灵魂、情节逻辑、角色一致、世界观冲突、节奏、风格一致、review、评估、quality"
license: "MIT"
version: "3.0.0"
compatibility: "OpenCode"
tags: ["novel", "quality", "v2"]
---

# 质量把控技能（V2）

## 核心职责

按编排层传入的 CONTEXT 执行质量检测任务。覆盖 AI 味道检测、情节逻辑、角色一致性、世界观漏洞、节奏分析、读者体验评估、风格一致性委托共 7 路检测。所有数据通过 GraphStore API 和 SearchEngine 从 graph 获取。

> 全模糊质量检测请求（"看看写得怎么样"）由编排层先调用 `skill("novel-grill", mode=quality)` 收集焦点，检测结果写入 NOTE 单元。

## 上下文契约

编排层在调用本技能前将以下上下文传入 prompt。所有数据由编排层通过 GraphStore API / SearchEngine 预先获取。

| 检测类型 | 必需上下文 | V2 获取方式 |
|---------|-----------|------------|
| AI 味道检测 | 正文内容 | `search_engine.search(scope=[CHUNK], chapter={N})` → content |
| 情节逻辑检测 | 正文内容 + 情节线 + 伏笔 | CHUNK + `store.find_units(type=PLOT_THREAD)` + `search_engine.search(keyword="伏笔", scope=[NOTE])` + `search_engine.check_consistency()` |
| 角色一致性检测 | 正文内容 + 出场角色 | CHUNK 的关联 CHARACTER_ARC + `search_engine.search(entity="{角色名}")` |
| 世界观漏洞检测 | 正文内容 + 世界观设定 | CHUNK + `store.find_units(type=WORLD_RULE)` |
| 节奏分析 | 正文内容 + 相邻章节 | CHUNK 按 chapter 排序 + SCENE 的结构数据 |
| 读者体验评估 | 全部正文 | 所有 CHUNK + SCENE |
| 风格一致性 | 正文内容 + 活跃风格 | CHUNK + `config.yaml` 的 `活跃风格` 字段（委托 novel-search-analysis align mode） |

### 总则：编排层负责数据准备

编排层在调用 quality 前准备数据，不要指望 quality 自己去读文件。

```python
# 编排层准备上下文的示例
ctx = {
    "project_name": config["项目名称"],
    "chapter_number": N,
    "chunk_content": [c.content for c in store.find_units(type=CHUNK, chapter=N)],
    "chapter_scenes": [s.unit_name for s in store.find_units(type=SCENE, chapter=N)],
    "active_style": config.get("活跃风格", "通俗网文风"),
    "all_plot_threads": [p.unit_name for p in store.find_units(type=PLOT_THREAD)],
    "world_rules": [w.unit_name for w in store.find_units(type=WORLD_RULE)],
}
# 注入 quality prompt 的 CONTEXT 段
```

## AI 味道检测

检测 8 类 AI 生成特征，按严重程度分级，输出检测报告和修正建议。

### 8 类 AI 特征
| 特征 | 严重程度 | 说明 |
|------|---------|------|
| 角色不一致 | 高 | 角色言行与设定不符 |
| 情节逻辑空隙 | 高 | 因果关系断裂 |
| 旁白叙述过多 | 高 | Show not tell 缺失 |
| 情感空洞 | 中 | 情感描写模板化 |
| 缺乏细节 | 中 | 场景描写模糊 |
| 重复套路 | 中 | 情节模式单一 |
| 风格过于正式 | 低 | 对话不够口语化 |
| 句式单调 | 低 | 句子结构单一 |

参考: `references/ai_flavor_rules.md`

### 处理流程
问题识别（8 类特征全文扫描） → 问题分类（高中低优先级） → 输出检测报告（含修正建议）

> 仅提供修正建议，不直接修改原文。优化由编排层调度修改任务。

## 情节逻辑检测

验证情节发展的因果合理性、转折动机充分性、伏笔设置与回收逻辑。

### 整合 SearchEngine 一致性检查

本检测与 `SearchEngine.check_consistency()` 的 R5-R7 深度整合。建议执行顺序：

```
Step 1: 运行 SearchEngine.check_consistency()
        → 获取 R5（能力边界）/ R6（时间线）/ R7（情节线完成度）结果
        → R5/R6/R7 的 findings 自动成为情节逻辑检测的输入线索

Step 2: 在检测报告中明确标注：
        - 哪些问题是 SearchEngine 自动发现的（R# 编号）
        - 哪些需要 LLM 额外语义分析的
```

**映射关系**：

| 检测维度 | SearchEngine 自动发现 | LLM 额外语义分析 |
|---------|---------------------|-----------------|
| 因果合理性 | R6（时间线事件顺序矛盾） | 动机是否充分、因果关系是否成立 |
| 转折动机检测 | — | 完全依赖 LLM 判断 |
| 伏笔逻辑检测 | R7（情节线关键事件未覆盖） | 伏笔设置质量、回收节奏 |
| 节奏逻辑检测 | — | 完全依赖 LLM 判断 |
| 结局逻辑检测 | — | 完全依赖 LLM 判断 |

### 5 个检测维度
1. **因果合理性**：事件之间的因果关系是否成立。结合 `SearchEngine.check_consistency()` R6 时间线一致性结果
2. **转折动机检测**：情节转折是否有足够铺垫和动机
3. **伏笔逻辑检测**：伏笔设置和回收是否合理。结合 R7 情节线完成度
4. **节奏逻辑检测**：情节推进节奏是否合理
5. **结局逻辑检测**：结局是否具有必然性和说服力。结合 R7 情节线完整度

**V2 数据获取**：
- `SearchEngine.check_consistency()` R5 / R6 / R7 — 一致性引擎自动扫描结果
- PLOT_THREAD 单元的 content → 关键事件列表
- NOTE(tags=伏笔) → 伏笔状态
- CHUNK 按 chapter 排序 → 推进顺序

### 注意事项
区分"艺术性留白"与"逻辑漏洞"；优先处理影响理解的致命问题

参考: `references/logic_criteria.md`

## 角色一致性检测

检测角色性格、行为、语言、能力边界的前后一致性。

### 整合 SearchEngine 一致性检查

`SearchEngine.check_consistency()` R5（能力边界一致性）直接对应该检测的第 4 维度。

```
Step 1: 运行 SearchEngine.check_consistency()
        → 过滤出 R5（能力边界）类型的结果
        → 能力检测的发现自动成为第 4 维度的检测线索

Step 2: 结合 SearchEngine 发现 + LLM 语义分析输出完整报告
```

### 6 个检测维度
1. **性格一致性**：角色性格是否前后矛盾
2. **行为一致性**：角色行为是否符合性格设定
3. **语言风格**：对话是否符合角色身份
4. **能力边界**：角色能力是否超出设定（结合 `SearchEngine.check_consistency()` R5）
5. **关系动态**：角色关系变化是否合理（可参考 `SearchEngine.check_consistency()` R2 关系不对称）
6. **状态连续性**：角色状态是否与上一次出场时连续

**V2 数据获取**：
```python
# 编排层准备
chunk_content = [c.content for c in store.find_units(type=CHUNK, chapter=N)]
# 从 CHUNK 的相邻 CHARACTER_ARC 找出场角色
for chunk in chunks:
    neighbors = store.get_neighbors(chunk.id, max_depth=1)
    for nid in neighbors.get(1, set()):
        n = store.get_unit(nid)
        if n.type == CHARACTER_ARC:
            roles_in_chapter.add(n)
# 对每个角色：search_engine.search(entity=角色名) 获取完整档案

# 一致性引擎自动扫描
consistency_results = engine.check_consistency()
# R5 过滤出能力边界相关的问题
ability_issues = [r for r in consistency_results if r.rule_id == "R5"]
```

### 注意事项
区分"角色成长"与"性格突变"；尊重角色多面性；关注关键角色和重要场景

参考: `references/check_criteria.md`

## 世界观漏洞检测

检测世界观设定中的逻辑漏洞、规则冲突、物理法则矛盾。

### 5 个检测维度
1. **规则一致性**：魔法/科技/能力规则是否自洽
2. **物理法则**：重力、能量、时间等物理法则是否一致
3. **势力逻辑**：势力分布和范围是否合理
4. **时间线**：历史事件设定是否矛盾
5. **文化自洽**：文化、信仰、习俗设定是否统一

**V2 数据获取**：
```python
world_rules = store.find_units(type=WORLD_RULE)
# 每条规则的 content 包含规则定义
# CHUNK content 中检测规则是否被违反
```

### 注意事项
区分"创新设定"与"逻辑漏洞"；聚焦与情节相关的核心设定

参考: `references/bug_criteria.md`

## 节奏分析

通过量化分析章节节奏、高潮分布、情感曲线，评估小说节奏是否合适。

### 4 维度评估
1. **节奏扫描**：逐章分析（快/中/慢）
2. **高潮分布**：评估高潮点数量和分布
3. **情感曲线**：愉悦度/紧张度/好奇度
4. **疲劳点检测**：连续慢节奏/信息疲劳/情感疲劳

**V2 数据获取**：
```python
chapters = defaultdict(list)
for chunk in store.find_units(type=CHUNK):
    chapters[chunk.belongs_to_chapter].append(chunk.content)
# 按 chapter 排序分析
```

### 注意事项
节奏判断需结合目标读者群体；不同类型对节奏要求不同；节奏服务于情感传递

参考: `references/pacing_guide.md`

## 读者体验评估

从读者视角评估章节的综合阅读体验，覆盖可读性、情感节奏、悬念管理、信息密度四个维度。

### 4 个评估维度
1. **可读性评估**：段落长度（50-120 字理想）、句子长度（20-30 字理想）、信息密度（每段≥1 核心信息点）
2. **情感节奏**：情感强度曲线（1-10 级）、高潮分布（每章≥1 个小高潮）、情感对比（相邻场景强度差≤5）
3. **悬念管理**：章节钩子（每章结尾必须有）、悬念密度（每卷≥3 个主要悬念）、读者期待管理
4. **信息密度**：每章新信息点（2-3 个）、重复信息间隔（≤10 章）、信息遗忘检测

**V2 数据获取**：CHUNK content（按 chapter 排序）+ SCENE 结构数据

### 评分标准
- 优秀：90-100 分
- 良好：75-89 分
- 中等：60-74 分
- 较差：<60 分

参考: `references/reader_experience.md`

## 读者反馈

本技能**不模拟读者反馈**（LLM 无法替代真实读者）。真实反馈由用户通过 `.omo/notepads/novel-feedback.md` 提供。

### 反馈的作用
- 用户在阅读章节后粘贴真实读者反馈到 `.omo/notepads/novel-feedback.md`
- novel-writer 在修订时读取 novel-feedback.md 中与该章相关的反馈
- 反馈作为修订 prompt 的 CONTEXT 注入

### feedback 格式
```markdown
## 第5章 反馈
- [读者A 2026-06-01] 陈霆的转变太快了
- [读者B 2026-06-02] 奏章那段信息密度太高
```

参见 novel-writer.md 了解完整接入流程。

## 风格一致性检测

在 V2 中，风格一致性检测委托给 `novel-search-analysis` 完成：

```markdown
skill("novel-search-analysis")
→ mode=align
→ 自动读取活跃风格进行对齐分析
```

详见 `.opencode/skills/novel-search-analysis/`

## 工作流程

输出写入 NOTE 单元后，由 ProjectionEngine 自动投影到 `quality/` 目录。

```
S1. 编排层通过 graph API 获取数据 → 注入 quality prompt CONTEXT
   ↓
S2. AI 味道检测
   输入：CHUNK content
   输出：NOTE(tags=["质量报告","AI味道"])
   ↓
S3. 情节逻辑检测
   输入：CHUNK + PLOT_THREAD + NOTE(伏笔) + SearchEngine.consistency()
   输出：NOTE(tags=["质量报告","情节逻辑"])
   ↓
S4. 角色一致性检测
   输入：CHUNK + CHARACTER_ARC + SearchEngine.search(entity=角色)
   输出：NOTE(tags=["质量报告","角色一致性"])
   ↓
S5. 世界观漏洞检测
   输入：CHUNK + WORLD_RULE
   输出：NOTE(tags=["质量报告","世界观漏洞"])
   ↓
S6. 节奏分析
   输入：CHUNK 按 chapter 排序
   输出：NOTE(tags=["质量报告","节奏分析"])
   ↓
S7. 读者体验评估
   输入：全部 CHUNK + SCENE
   输出：NOTE(tags=["质量报告","读者体验"])
   ↓
S8. 风格一致性委托
   委托 skill("novel-search-analysis") → mode=align
   ↓
S9. 问题整合 → 完整质量报告 NOTE 单元
   输出：NOTE(tags=["质量报告","综合"])
```

> 所有质量报告写入 graph 中的 NOTE 单元。`ProjectionEngine.rebuild_all()` 会自动将 NOTE 单元投影到 `quality/` 目录，保持与 V1 用户习惯的文件结构兼容。

## 参考文件

> 参考文件中的 V1 路径（如 chapters/ characters/ outline/）不会影响 LLM 的判断逻辑——它提供的是检测维度和评分示例，LLM 理解的是概念而非路径。仅 `bug_examples.md` 有 4 处示例路径标注，已更新为 V2 graph 表述。

- `references/ai_flavor_rules.md`
- `references/logic_criteria.md`
- `references/check_criteria.md`
- `references/bug_criteria.md`
- `references/pacing_guide.md`
- `references/reader_experience.md`
- `references/feedback_metrics.md`
- `references/problem_examples.md`
- `references/check_examples.md`
- `references/bug_examples.md`
- `references/pacing_examples.md`
- `references/drop-off_indicators.md`
- `references/quality_mode.md`
- `references/reader_personas.md`
