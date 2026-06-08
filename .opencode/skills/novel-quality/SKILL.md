---
name: "novel-quality"
description: "质量把控：提供AI味道检测、情节逻辑检测、角色一致性检查、世界观漏洞检测、节奏分析、风格一致性检查。触发词：质量、检测、AI味、太AI、没有灵魂、情节逻辑、角色一致、世界观冲突、节奏、风格一致、review、评估、quality"
license: "MIT"
version: "2.0.0"
compatibility: "OpenCode"
tags: ["novel", "quality"]
---

# 质量把控技能

## 核心职责

按编排 Agent 传入的 CONTEXT 执行质量检测任务。覆盖 AI 味道检测、情节逻辑、角色一致性、世界观漏洞、节奏分析。如需修正，由编排层调度 novel-polish 执行文笔优化。

## PROMPT_TEMPLATE

> 模板定义在 `templates/prompt_template.md`。编排层使用 `extract_template.py` 加载并填充变量。

## 上下文契约

编排层（或手工操作者）在调用本技能前按检测类型准备上下文。

| 检测类型 | 槽位 | 文件路径 | 加载方式 |
|---------|------|---------|---------|
| AI 味道检测 | 章节正文 | `chapters/第{N}章.txt` | `read` 全文 |
| 情节逻辑检测 | 章节正文 | `chapters/第{N}章.txt` | `read` 全文 |
| | 伏笔追踪 | `outline/追踪/伏笔.yaml` | `read` 筛选进行中/需回收 |
| | 时间线 | `outline/追踪/时间线.yaml` | `read` |
| | 情节线 | `outline/情节线/*.yaml` | `glob` + `read` |
| | 章节分纲 | `outline/分纲/卷*/第{N}章.yaml` | `read` |
| 角色一致性检查 | 章节正文 | `chapters/第{N}章.txt` | `read` 全文 |
| | 出场角色档案 | `characters/{角色ID}.yaml`（摘要段优先） | `project_index.yaml` → 找路径 → `read` |
| 世界观漏洞检测 | 章节正文 | `chapters/第{N}章.txt` | `read` 全文 |
| | 世界观实体 | `worldbuilding/*.yaml` | `glob` + `read` |
| 节奏分析 | 章节正文 | `chapters/第{N}章.txt` + 相邻章节 | `read` |
| | 分纲 | `outline/分纲/卷*/第{N}章.yaml` | `read` |
| 风格一致性检查 | 章节正文 | `chapters/第{N}章.txt` | `read` 全文 |
| | 活跃风格 | `styles/{active_style}.yaml`（config.yaml `活跃风格` 字段） | `read` 全文件 |

## AI 味道检测

检测 8 类 AI 生成特征，按严重程度分级，输出检测报告和修正建议。

### 8 类 AI 特征
| 特征 | 严重程度 | 说明 |
|------|---------|------|
| 角色不一致 | 高 | 角色言行与设定不符（表层不一致，区别于深度角色一致性检查 §角色一致性检查） |
| 情节逻辑空隙 | 高 | 因果关系断裂 |
| 旁白叙述过多 | 高 | Show not tell 缺失 |
| 情感空洞 | 中 | 情感描写模板化 |
| 缺乏细节 | 中 | 场景描写模糊 |
| 重复套路 | 中 | 情节模式单一 |
| 风格过于正式 | 低 | 对话不够口语化 |
| 句式单调 | 低 | 句子结构单一 |

参考: `novel-quality/references/ai_flavor_rules.md`（8 大类检测模式整合为体系化规则库）

### 处理流程
问题识别（8类特征全文扫描） → 问题分类（高中低优先级） → 输出检测报告（含修正建议）

**注意**：仅提供修正建议，不直接修改原文。文笔优化由 novel-polish 技能处理。风格一致性由编排层 §6.3 条件追加第 6 路检测。

## 情节逻辑检测

验证情节发展的因果合理性、转折动机充分性、伏笔设置与回收逻辑。

### 5 个检测维度
1. **因果合理性**：事件之间的因果关系是否成立
2. **转折动机检测**：情节转折是否有足够铺垫和动机
3. **伏笔逻辑检测**：伏笔设置和回收是否合理
4. **节奏逻辑检测**：情节推进节奏是否合理
5. **结局逻辑检测**：结局是否具有必然性和说服力

### 输入素材
- 待检测文本（章节/全文）
- project_index.yaml（章节角色清单、章节序列、伏笔索引）
- outline/总纲.yaml、outline/分纲/卷1/第N章.yaml
- outline/情节线/主线.yaml + 支线_*.yaml
- outline/追踪/伏笔.yaml、outline/追踪/时间线.yaml

### 注意事项
区分"艺术性留白"与"逻辑漏洞"；优先处理影响理解的致命问题

参考: `novel-quality/references/logic_criteria.md`

## 角色一致性检查

检测角色性格、行为、语言、能力边界的前后一致性。

### 5 个检测维度
1. **性格一致性**：角色性格是否前后矛盾
2. **行为一致性**：角色行为是否符合性格设定
3. **语言风格**：对话是否符合角色身份
4. **能力边界**：角色能力是否超出设定
5. **关系动态**：角色关系变化是否合理

### 加载策略
先读 project_index.yaml 确定本章涉及角色，再读 characters/.summary/{角色ID}.yaml 获取当前境况（~30行/角色），仅在需要深度检查时读取完整 characters/{角色}.yaml

### 注意事项
区分"角色成长"与"性格突变"；尊重角色多面性；关注关键角色和重要场景

参考: `novel-quality/references/check_criteria.md`

## 世界观漏洞检测

检测世界观设定中的逻辑漏洞、规则冲突、物理法则矛盾。

### 5 个检测维度
1. **规则一致性**：魔法/科技/能力规则是否自洽
2. **物理法则**：重力、能量、时间等物理法则是否一致
3. **势力逻辑**：势力分布和范围是否合理
4. **时间线**：历史事件设定是否矛盾
5. **文化自洽**：文化、信仰、习俗设定是否统一

### 注意事项
区分"创新设定"与"逻辑漏洞"；聚焦与情节相关的核心设定

参考: `novel-quality/references/bug_criteria.md`

## 节奏分析

通过量化分析章节节奏、高潮分布、情感曲线，评估小说节奏是否合适。

### 4 维度评估
1. **节奏扫描**：逐章分析（快/中/慢）
2. **高潮分布**：评估高潮点数量和分布
3. **情感曲线**：愉悦度/紧张度/好奇度
4. **疲劳点检测**：连续慢节奏/信息疲劳/情感疲劳

### 注意事项
节奏判断需结合目标读者群体；不同类型对节奏要求不同；节奏服务于情感传递

参考: `novel-quality/references/pacing_guide.md`

## 读者反馈

本技能**不模拟读者反馈**（LLM 无法替代真实读者）。真实反馈由用户通过 `novel-feedback.md` 提供。

### 反馈的作用
- 用户在阅读章节后粘贴真实读者反馈到 `.omo/notepads/novel-feedback.md`
- novel-writer 在修订/重写章节时，读取 novel-feedback.md 中与该章相关的反馈
- 反馈作为修订 prompt 的 CONTEXT 注入，指导 novel-polish 精准修正

### feedback 格式
```markdown
## 第5章 反馈
- [读者A 2026-06-01] 陈霆的转变太快了，第4章还在"不跪"，第5章直接行动
- [读者B 2026-06-02] 奏章那段信息密度太高，读了两次才理清7份奏章的关系
- [作者自评] 赵广军报被压8天需要在前文有伏笔
```

参见 novel-writer.md「读者反馈协议」了解完整接入流程。

## 工作流程

```
0. 接收需求分析结果（由 Agent 传递）
   输入：质量检测需求报告（检测类型/维度/优先级/范围）
   ↓
 1. AI 味道检测
    输入：章节正文
    输出：quality/第{N}章_AI味道检测.yaml
    ↓
 2. 情节逻辑检测
    输入：章节正文 + outline/追踪/伏笔.yaml + outline/追踪/时间线.yaml
    输出：quality/第{N}章_情节逻辑检测.yaml
    ↓
 3. 角色一致性检查
     输入：章节正文 + project_index.yaml + characters/.summary/*.yaml（摘要层优先）
     输出：quality/第{N}章_角色一致性检查.yaml
    ↓
 4. 世界观漏洞检测
    输入：章节正文 + worldbuilding/*.yaml
    输出：quality/第{N}章_世界观漏洞检测.yaml
    ↓
 5. 节奏分析
     输入：章节正文 + 分纲
     输出：quality/第{N}章_节奏分析报告.yaml
     ↓
   6. 风格一致性检查（若 config.yaml 设了 活跃风格）
      输入：章节正文 + styles/{active_style}.yaml
      输出：quality/第{N}章_风格一致性检查.yaml
      ↓
   7. 问题整合 → 完整质量报告（YAML，含问题清单/优先级/修复建议）
    输出：quality/第{N}章_综合质量报告.yaml
   ↓
8. 修复执行 → 调度 novel-polish 执行文笔优化
   ↓
 9. 完成质量报告
```

## 参考文件

- `novel-quality/references/ai_flavor_rules.md`
- `novel-quality/references/logic_criteria.md`
- `novel-quality/references/check_criteria.md`
- `novel-quality/references/bug_criteria.md`
- `novel-quality/references/pacing_guide.md`
- `novel-quality/references/feedback_metrics.md`
- `novel-quality/references/problem_examples.md`
- `novel-quality/references/check_examples.md`
- `novel-quality/references/bug_examples.md`
- `novel-quality/references/pacing_examples.md`
- `novel-quality/references/drop-off_indicators.md`
- `novel-quality/references/quality_mode.md`

---

## HARD CONSTRAINTS

> 约束已移入 `templates/prompt_template.md`。编排层通过 `extract_template.py` 加载模板时一并注入 LLM prompt。
