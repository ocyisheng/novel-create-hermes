---
name: "novel-grill"
description: "创作前需求发现：在创意构思、角色创建、章节写作前，通过结构化追问发现用户需求（预生成模式）。触发词：grill"
license: "MIT"
version: "2.1.0"
compatibility: "OpenCode"
tags: ["novel", "grill"]
---

# 创作需求发现技能

## 核心职责

在 task() 生成内容前，主动追问用户需求偏好，将确认后的信息作为生成输入。流程：**追问→确认→生成**。

## 上下文契约

> 编排层通过 `user_message` 参数显式传入 `mode=` 标识。Grill 根据模式匹配决策树和必需上下文。具体映射见下方 §模式调度。

| 槽位 | 文件路径 | 提取内容 | 适用模式 |
|------|---------|---------|---------|
| `{项目名}` | `config.yaml`（notepad 注入） | 项目名称 | 全部 |
| `{已有角色列表}` | `project_index.yaml` | `characters` 段：name + one_line | character, chapter_outline |
| `{故事背景摘要}` | `outline/总纲.yaml` 或 `ideation/最终创意方案.yaml` | 核心冲突 + 世界观概述 | character, entity-editor, outline_synopsis |
| `{分纲摘要}` | `outline/分纲/卷{卷号}/第{N}章.yaml` | 场景 + 冲突 + 转折 + 出场角色 | chapter |
| `{已有创意方向}` | `ideation/` 目录 | 已有创意方案核心摘要 | ideation |
| `{实体文件内容}` | 目标实体文件（角色/世界观/大纲等 YAML） | 完整 YAML 内容 | entity-editor |
| `{总纲概要}` | `outline/总纲.yaml` | 结构配置 + 核心概念 | volume, plot |
| `{分卷概要}` | `outline/分卷/*.yaml` | 卷信息.核心冲突 + 章节范围 | plot, chapter_outline |

## 模式调度

> 编排层通过 `skill("novel-grill", user_message="mode=xxx")` 显式传入模式。Grill 据此确定决策树和必需上下文。`{测试阶段}` 槽位已废弃，不再从 `read` 文件推断。

| 模式标识 | 对应阶段 | 决策树文件 | 必需上下文（缺失时主动 read） |
|---------|---------|-----------|---------------------------|
| `ideation` | P1 创意构思 | `references/D1-ideation.md` | `ideation/` 目录下的已有创意方向（如存在） |
| `outline_synopsis` | P2 总纲撰写 | `references/D6-outline.md` §D6.1 | `ideation/最终创意方案.yaml`（→故事背景摘要） |
| `volume` | P3 分卷大纲 | `references/D6-outline.md` §D6.2 | `outline/总纲.yaml`（→总纲概要） |
| `plot` | P4 情节构建 | `references/D6-outline.md` §D6.3 | `outline/总纲.yaml` + `outline/分卷/*.yaml` |
| `character` | P6 角色创建 | `references/D3-character.md` | `project_index.yaml`（→已有角色列表） + `outline/总纲.yaml`（→故事背景摘要） |
| `chapter_outline` | P7 分纲构建 | `references/D6-outline.md` §D6.4 | `outline/分卷/*.yaml` + `project_index.yaml` |
| `chapter` | P8 章节写作 | `references/D4-chapter.md` | `outline/分纲/卷{卷号}/第{N}章.yaml`（→分纲摘要） |
| `entity-editor` | P13 实体编辑 | `references/D5-entity-editor.md` | 目标实体文件（→当前实体内容） + `outline/总纲.yaml`（→故事背景摘要） |

### 上下文就绪流程

执行追问前，Grill 自行确保所需上下文已加载：

1. 解析 `user_message` 中的 `mode=` 参数
   - 若未提供 → 询问用户"你想在哪个方面做需求发现？"并列出上表中的 8 个模式
2. 查表获取该模式的必需上下文文件列表
3. 检查当前对话中是否已有对应文件内容
4. 缺失的文件 → 主动 `read` 加载到对话上下文
5. 继续执行追问流程

## 决策树引用

> 决策树定义在独立参考文件中。执行时先读取对应文件再逐层追问。

| 模式 | 文件 | 说明 |
|------|------|------|
| 创意构思 | `references/D1-ideation.md` | 供给侧推荐需求发现树 |
| 角色设计 | `references/D3-character.md` | 上下文锚定角色设计树 |
| 章节写作 | `references/D4-chapter.md` | 分纲展示+覆盖调整树 |
| 实体编辑 | `references/D5-entity-editor.md` | 现状展示→差异诊断树 |
| 总纲撰写 | `references/D6-outline.md` | D6.1 大纲结构检查点 |
| 分卷大纲 | `references/D6-outline.md` | D6.2 分卷节奏检查点 |
| 情节构建 | `references/D6-outline.md` | D6.3 情节线规划检查点 |
| 分纲构建 | `references/D6-outline.md` | D6.4 分纲分配检查点 |

## 工作流程

**目标**：在 task() 生成前收集用户需求，确认后的信息直接注入后续生成任务的 CONTEXT。

0. **解析模式与就绪上下文**：根据 `user_message` 中的 `mode=` 参数确定模式，按 §模式调度.上下文就绪流程 加载必需文件
1. **读决策树**：根据模式读取对应决策树文件（见模式调度表），`read references/D{N}.md`
2. **逐层追问**：向用户解释"在开始之前，我先问几个问题了解你的想法"，每问附推荐答案，用户可 `pass` 跳过分支
3. **整理需求**：将确认信息整理为清单（分支结论、关键需求、排除方向）
4. **传递需求**：Grill 在主 Agent 上下文执行完毕，确认信息已在对话上下文中。编排层将需求清单直接注入后续 task() 的 prompt CONTEXT
- `ideation` / `character` / `chapter` 模式 → 注入 task() 的 `{grill_需求}` 槽位
- `entity-editor` 模式 → 注入 novel-entity-editor 的 CONTEXT `{grill_编辑方案}` 槽位

**追问风格**：逐个提问，每问附推荐答案（基于类型常识和项目已有背景），用户确认或修正后记录结论再进下一问题，走完所有分支为止。

**交互前提**：仅当用户需求模糊（如"帮我想个创意""创建个角色""改一下角色"）时执行。若用户已给出详细需求（含类型、基调、核心元素、具体修改方向等），编排层跳过 grill 直接调度 task()。

## HARD CONSTRAINTS

1. **不替代创作决策** — 只收集需求，最终选择权在用户
2. **每个问题必须有据** — 基于类型常识或已有项目背景
3. **推荐答案必须具体** — 有依据的选项，不泛泛而谈
4. **尊重用户中断** — `pass` 跳过当前分支，`stop` 立即终止，不追问原因

## 参考文件

- `references/D1-ideation.md` — 创意构思需求发现树
- `references/D3-character.md` — 角色设计需求发现树
- `references/D4-chapter.md` — 章节写作需求发现树
- `references/D5-entity-editor.md` — 实体编辑需求发现树
- `references/D6-outline.md` — 大纲系列检查点（P2/P3/P4/P7）
