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

按编排 Agent 传入的 CONTEXT 执行质量检测任务。覆盖 AI 味道检测、情节逻辑、角色一致性、世界观漏洞、节奏分析、风格一致性检查、读者体验评估共 7 路检测。如需修正，由编排层调度 novel-chapter-editor 执行文笔优化或内容修改。


## 上下文契约

编排层（或手工操作者）在调用本技能前按检测类型准备上下文。

| 检测类型 | 槽位 | 文件路径 | 加载方式 |
|---------|------|---------|---------|
| AI 味道检测 | 章节正文 | `chapters/第{N}章.txt` | `read` 全文 |
| 情节逻辑检测 | 章节正文 | `chapters/第{N}章.txt` | `read` 全文 |
| | 伏笔追踪 | `outline/追踪/伏笔.yaml` | `read` 筛选进行中/需回收 |
| | 时间线 | `outline/追踪/时间线.yaml` | `read` |
| | 情节线 | `outline/情节线/*.yaml` | `glob` + `read` |
| | 主索引 | `outline/情节线/主索引.yaml`（如存在） | `read` 全文件 |
| | 章节分纲 | `outline/分纲/卷*/第{N}章.yaml` | `read` |
| 角色一致性检查 | 章节正文 | `chapters/第{N}章.txt` | `read` 全文 |
| | 出场角色档案 | `characters/{角色ID}.yaml`（摘要段优先） | `project_index.yaml` → 找路径 → `read` |
| | 角色统计 | `outline/追踪/角色统计.yaml` | `read` 筛选本章出场角色的历史状态 |
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

参考: `references/ai_flavor_rules.md`（8 大类检测模式整合为体系化规则库）

### 处理流程
问题识别（8类特征全文扫描） → 问题分类（高中低优先级） → 输出检测报告（含修正建议）

**注意**：仅提供修正建议，不直接修改原文。文笔优化由 novel-chapter-editor 技能处理。风格一致性由编排层 §6.3 条件追加第 6 路检测。

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

参考: `references/logic_criteria.md`

## 角色一致性检查

检测角色性格、行为、语言、能力边界的前后一致性。

### 6 个检测维度
1. **性格一致性**：角色性格是否前后矛盾
2. **行为一致性**：角色行为是否符合性格设定
3. **语言风格**：对话是否符合角色身份
4. **能力边界**：角色能力是否超出设定
5. **关系动态**：角色关系变化是否合理
6. **状态连续性**：角色状态是否与上一次出场时的状态连续（读取 `角色统计.yaml` 检测状态跳跃）

### 状态连续性检测规则

读取 `outline/追踪/角色统计.yaml`，获取本章出场角色的上一次记录：
- 若上一次记录有 `状态` 字段，检查本章中该角色的状态是否与之连续
- **连续示例**：上一次"重伤" → 本章"康复"（合理过渡）
- **跳跃示例**：上一次"重伤" → 本章"正常战斗"（警告：状态跳跃）
- **无记录**：首次出场或无状态记录 → 跳过检测

### 加载策略
先读 project_index.yaml 确定本章涉及角色，再读 characters/{角色ID}.yaml 的 `摘要` 段获取当前境况（~30行/角色），仅在需要深度检查时读取完整 `完整档案` 段

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

### 注意事项
节奏判断需结合目标读者群体；不同类型对节奏要求不同；节奏服务于情感传递

参考: `references/pacing_guide.md`

## 读者体验评估

从读者视角评估章节的综合阅读体验，覆盖可读性、情感节奏、悬念管理、信息密度四个维度。

### 4 个评估维度
1. **可读性评估**：段落长度（50-120字理想）、句子长度（20-30字理想）、信息密度（每段≥1核心信息点）
2. **情感节奏**：情感强度曲线（1-10级）、高潮分布（每章≥1个小高潮）、情感对比（相邻场景强度差≤5）
3. **悬念管理**：章节钩子（每章结尾必须有）、悬念密度（每卷≥3个主要悬念）、读者期待管理
4. **信息密度**：每章新信息点（2-3个）、重复信息间隔（≤10章）、信息遗忘检测

### 输入素材
- 章节正文：`chapters/第{N}章.txt`
- 章节分纲：`outline/分纲/卷*/第{N}章.yaml`
- 叙事策略：`outline/叙事策略.yaml`（如存在）

### 评分标准
- 优秀：90-100分
- 良好：75-89分
- 中等：60-74分
- 较差：<60分

参考: `references/reader_experience.md`

## 读者反馈

本技能**不模拟读者反馈**（LLM 无法替代真实读者）。真实反馈由用户通过 `novel-feedback.md` 提供。

### 反馈的作用
- 用户在阅读章节后粘贴真实读者反馈到 `.omo/notepads/novel-feedback.md`
- novel-writer 在修订/重写章节时，读取 novel-feedback.md 中与该章相关的反馈
- 反馈作为修订 prompt 的 CONTEXT 注入，指导 novel-chapter-editor 精准修正

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
     输入：章节正文 + project_index.yaml + characters/{角色ID}.yaml（摘要段优先）+ outline/追踪/角色统计.yaml
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
   6. 读者体验评估
      输入：章节正文 + 分纲 + 叙事策略（如存在）
      输出：quality/第{N}章_读者体验评估.yaml
      ↓
   7. 风格一致性检查（若 config.yaml 设了 活跃风格）
      输入：章节正文 + styles/{active_style}.yaml
      输出：quality/第{N}章_风格一致性检查.yaml
      ↓
   8. 问题整合 → 完整质量报告（YAML，含问题清单/优先级/修复建议）
    输出：quality/第{N}章_综合质量报告.yaml
   ↓
9. 修复执行 → 调度 novel-chapter-editor 执行文笔优化或内容修改
   ↓
 10. 完成质量报告
```

## 写后处理

输出写入后执行以下脚本：

```bash
# 阶段切换（P9→完成）
python .opencode/shared/config_manager.py set 当前阶段 "已完成" --project-root {PROJECT_PATH}
```

> `{PROJECT_PATH}` 由编排层在 Task() prompt CONTEXT 中传入。

## 参考文件

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


