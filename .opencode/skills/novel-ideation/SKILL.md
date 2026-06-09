---
name: "novel-ideation"
description: "创意构思：为小说创作提供创意生成、约束管理、类型分析、模板生成、创意评估。触发词：创意、构思、脑洞、灵感、没想法、没灵感、ideation、约束、模板、评估、类型"
license: "MIT"
version: "2.0.0"
compatibility: "OpenCode"
tags: ["novel", "ideation"]
---

# 创意构思技能

## 核心职责

按编排 Agent 传入的 CONTEXT 执行创意构思任务。覆盖约束管理、类型分析、模板生成、创意发散、评估筛选。

## PROMPT_TEMPLATE

> 模板定义在 `templates/prompt_template.md`。编排层使用 `extract_template.py` 加载并填充变量。

## 上下文契约

> 参见 `templates/prompt_template.md` 的变量列表和 SKILL.md 正文中的工作流程。

## 约束管理

参考 `references/constraints_library.md`（30+ 约束，6 大类），应用以下约束方向激发创意：
- **结构约束**：叙事结构、时间结构、视角结构
- **内容约束**：题材限制、基调限制、主题方向
- **角色约束**：主角特质、角色数量、关系限制
- **设定约束**：世界观规则、力量体系、科技水平
- **形式约束**：篇幅限制、章节结构、叙事方式
- **主题约束**：核心主题、价值取向、情感基调

每次生成 3-5 个约束组合，每个约束包含类型、描述、创作指导。输出 YAML 格式。

## 类型专家指南

支持的小说类型及核心要素：
1. **玄幻/修仙** — 东方幻想，修炼体系，力量升级
2. **科幻/星际** — 科技幻想，宇宙文明，未来世界
3. **都市/异能** — 现代都市，超能力，现实与幻想交织
4. **悬疑/推理** — 推理谜题，反转悬念，心理探索
5. **历史/穿越** — 历史背景，穿越元素，现实与想象

每种类型提供：核心元素、典型情节模式、世界观构建指南、角色设定建议、创作禁忌、创新方向。

参考: `references/genres_compendium.md`

## 模板生成指南

将创意概念转化为可执行的结构化故事框架。支持 5 种叙事结构：
- **三幕结构**（起因→发展→高潮）：适合大多数长篇
- **五幕结构**（引入→上升→中点→下降→解决）：适合中篇
- **英雄之旅**（12阶段）：适合成长型故事
- **侦探结构**（案件→调查→推理→揭露）：适合悬疑类
- **多线叙事**（多条故事线交织）：适合群像剧

参考: `references/template_principles.md`

## 创意生成方法

基于"约束激发创意"的核心方法，在给定约束条件下生成原创故事概念。

### 阶段一：创意发散
应用以下创意生成技术，生成 3-5 个创意方向（每方向包含一句话概述、核心冲突、主角设定、亮点卖点）：

1. **约束组合矩阵**：从 6 大类中各选 1 个约束组合
2. **类型融合**：两种类型交叉产生新概念
3. **反转预期**：打破类型常规套路
4. **极端假设**：如果某个设定推到极致
5. **限制激发**：在严格限制下寻找突破口

### 阶段二：创意深化（用户选定后）
对选定创意进行深度开发：世界观设定、角色档案、情节大纲、主题方向。

参考: `references/ideation_techniques.md`

## 评估标准

基于 4 维度评估矩阵对创意进行系统化评分和筛选：

| 维度 | 评分标准（0-5分） | 权重 |
|------|-----------------|------|
| **原创性** | 概念的新颖程度 | 30% |
| **可行性** | 在目标篇幅内能否完整呈现 | 25% |
| **吸引力** | 对目标读者的吸引力 | 25% |
| **独特性** | 与同类作品的差异化程度 | 20% |

阈值：总分 ≥16/20，原创性≥4，吸引力≥4 为通过。输出 YAML 评估报告，含改进建议。

参考: `references/evaluation_criteria.md`

## 工作流程

### 当在已有项目中运行时
- 先读取 project_index.yaml 了解现有实体概况
- 先读取 ideation/最终创意方案.yaml 了解已有创意方向
- 避免生成与已有实体冲突的创意
- 新创意应填补已有设定中的空白

### 流程步骤
0. 接收编排 Agent 传入的 CONTEXT（项目路径、项目类型、已有实体、已有创意方向）
   输入：编排层 task() prompt 中的 TASK + CONTEXT 字段
   ↓
1. 约束应用 → 应用约束库，生成约束集
    输入：需求分析结果
    输出：ideation/需求分析.yaml → 填入类型/基调/元素等
          ideation/约束集.yaml → 写入 6 大类约束
    ↓
2. 类型分析（可选）→ 如用户未明确类型，提供类型指南
    输出：类型特征指南
    ↓
3. 模板生成 → 提供故事框架
    输入：约束集 + 类型指南
    输出：故事模板（三幕/五幕结构）
    ↓
4. 创意发散 → 生成 3-5 个创意方向
    输入：约束集 + 模板 + 类型指南
    输出：ideation/创意简报.yaml（write 写入全部方向）
    ↓
5. 创意评估 → 打分筛选
    输入：ideation/创意简报.yaml
    输出：ideation/评估报告.yaml → 4 维度评分 + 推荐方向
    ↓
6. 整合输出 → 完整创意方案
    输入：选定的创意方向
    输出：ideation/最终创意方案.yaml（主角/冲突/世界观/情节主线）
    展示摘要给用户，等待确认

### 写入规范

- 5 个文件独立写入 `ideation/` 目录：
  - `需求分析.yaml` — write（首次）
  - `约束集.yaml` — write（首次）
  - `创意简报.yaml` — write（生成全部方向时覆盖）
  - `评估报告.yaml` — write
  - `最终创意方案.yaml` — write（选定后一次写入）
- 创意简报中 `选定: true` 标记被选中的方向
- novel-outline 读取 `ideation/最终创意方案.yaml` 作为创作起点

## 参考文件

### 核心指南
- `references/genres_compendium.md` — 五大类型概览（玄幻/科幻/都市/悬疑/历史）
- `references/constraints_library.md` — 30+ 约束模板（6 大类）
- `references/template_principles.md` — 模板生成原则
- `references/ideation_techniques.md` — 创意生成方法
- `references/evaluation_criteria.md` — 4 维度评估矩阵
- `references/ideation_philosophy.md` — 创意构思哲学
- `references/thresholds.md` — 评估阈值设定

### 类型深入（详细版，genres_compendium.md 的精缩对照）
- `references/genre_fantasy.md` — 玄幻/修仙类型深入
- `references/genre_scifi.md` — 科幻/星际类型深入
- `references/genre_urban.md` — 都市/异能类型深入
- `references/genre_mystery.md` — 悬疑/推理类型深入
- `references/genre_history.md` — 历史/穿越类型深入
- `references/genres_quick_reference.md` — 类型快速诊断清单
- `references/genre_innovation.md` — 类型创新方向

### 约束与组合
- `references/constraint_types_overview.md` — 约束类型概览
- `references/combination_strategy.md` — 约束组合策略
- `references/combination_examples.md` — 约束组合示例

### 模板与示例
- `references/template_examples.md` — 模板生成示例
- `references/output_examples.md` — 输出格式示例

### 评估与场景
- `references/evaluation_scenarios.md` — 评估场景
- `references/evaluation_examples.md` — 评估实例

### 模式参考
- `references/ideation_tools.md` — 创意工具
- `references/ideation_mode.md` — 创意模式
- `references/writing_mode.md` — 写作模式

## HARD CONSTRAINTS

> 约束已移入 `templates/prompt_template.md`。编排层通过 `extract_template.py` 加载模板时一并注入 LLM prompt。
