---
name: "novel-grill"
description: "创作前需求发现：在创意构思、角色创建、章节写作前，通过结构化追问发现用户需求（预生成模式）。触发词：grill、压力测试、拷问、推敲、质疑、挑战"
license: "MIT"
version: "2.1.0"
compatibility: "OpenCode"
tags: ["novel", "grill"]
---

# 创作需求发现技能

## 核心职责

在 task() 生成内容前，主动追问用户需求偏好，将确认后的信息作为生成输入。流程：**追问→确认→生成**。

## 上下文契约

> `skill()` 在主 Agent 上下文执行，编排层调用前需通过 `read` 加载对应阶段文件到上下文，技能据此判断当前阶段。

| 槽位 | 来源 | 说明 |
|------|------|------|
| `{项目名}` | config.yaml | 当前项目名称（编排层注入 notepad） |
| `{测试阶段}` | 编排层调用前 read 的文件 | `ideation` / `character` / `chapter` / `entity-editor` / `outline_synopsis` / `volume` / `plot` / `chapter_outline` |
| `{测试对象概要}` | 对应阶段文件摘要 | 描述要生成什么 |
| `{实体文件路径}` | 编排层传入（仅 entity-editor 模式） | 目标实体文件的绝对路径 |
| `{当前实体内容}` | `read` 实体文件（仅 entity-editor 模式） | 编辑前的完整 YAML 内容 |
| `{已有角色列表}` | project_index.yaml | 角色名 + 一句话描述（D3/D6.4 模式） |
| `{故事背景摘要}` | 总纲.yaml / 创意方案 | 当前故事背景设定概要（D3/D5/D6.1 模式） |
| `{已有实体摘要}` | read 实体文件 | 当前实体核心内容摘要（D5 模式） |
| `{分纲摘要}` | 目标分纲文件 | 当前章节分纲概要（D4 模式） |
| `{已有创意方向}` | ideation/ 目录 | 已存在的创意方向摘要（D1 模式） |

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

1. **读决策树**：根据 `{测试阶段}` 读取对应文件（见决策树引用表），`read references/D{阶段}.md`
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
