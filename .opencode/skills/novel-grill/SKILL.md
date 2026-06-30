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

## 模式路由

> 编排层通过 `skill("novel-grill", user_message="mode=xxx")` 传入模式标识。Grill 查下表确定决策树、读入上下文和输出变量。缺失的上下文自行 `read` 加载。

| mode | P 阶段 | 决策树 | 读入上下文（文件 → 提取内容） | 输出变量 | 说明 |
|---|---|---|---|---|---|---|
| `ideation` | P1 创意构思 | `references/D1-ideation.md` | `ideation/` 目录 → 已有创意方向摘要 | `{grill_需求}` | 供给侧推荐需求发现树 |
| `worldbuilding` | P2 世界观建设 | `references/D7-worldbuilding.md` | `ideation/最终创意方案.yaml` → 世界观概述+核心设定；`project_index.yaml` → 已有实体列表 | `{grill_世界观需求}` | 世界规模/规则体系/势力格局发现树 |
| `character` | P3 角色创建 | `references/D3-character.md` | `project_index.yaml` → 已有角色(name+one_line)；`outline/总纲.yaml` → 故事背景(核心冲突+世界观概述) | `{grill_需求}` | 上下文锚定角色设计树 |
| `outline_synopsis` | P4 总纲撰写 | `references/D6-outline.md` §D6.1 | `ideation/最终创意方案.yaml` → 故事背景摘要 | — | 大纲结构检查点 |
| `plot` | P5 情节构建 | `references/D6-outline.md` §D6.3 | `outline/总纲.yaml` → 结构配置+核心概念；`outline/分卷/*.yaml` → 卷信息 | — | 情节线规划检查点 |
| `volume` | P6 分卷大纲 | `references/D6-outline.md` §D6.2 | `outline/总纲.yaml` → 总纲概要 | — | 分卷节奏检查点 |
| `chapter_outline` | P7 分纲构建 | `references/D6-outline.md` §D6.4 | `outline/分卷/*.yaml` → 卷信息；`project_index.yaml` → 已有角色列表 | — | 分纲分配检查点 |
| `chapter` | P8 章节写作 | `references/D4-chapter.md` | `outline/分纲/卷{卷号}/第{N}章.yaml` → 分纲摘要(场景+冲突+转折+出场角色) | `{grill_需求}` | 分纲展示+覆盖调整树 |
| `entity-editor` | P13 实体编辑 | `references/D5-entity-editor.md` | 目标实体YAML → 完整内容；`outline/总纲.yaml` → 故事背景摘要 | `{grill_编辑方案}` | 现状展示→差异诊断树 |
| `quality-fuzzy` | P9 质量检测 | `references/D8-quality-fuzzy.md` | `chapters/第{N}章.txt` → 章节正文全文；`project_index.yaml` → 章节清单 | `{grill_检测焦点}` | 质量检测焦点快速选择（单问） |
| `chapter-edit-fuzzy` | P12 章节编辑 | `references/D9-chapter-edit-fuzzy.md` | `chapters/第{N}章.txt` → 章节正文；`outline/分纲/卷{卷号}/第{N}章.yaml` → 分纲摘要；`characters/` → 出场角色档案 | `{grill_编辑方案}` | 修改问题定位与方向确认树 |

## 工作流程

**目标**：在 task() 生成前收集用户需求，确认后的信息直接注入后续生成任务的 CONTEXT。

0. **解析模式与就绪上下文**：解析 `user_message` 中的 `mode=` 参数。若未提供则询问用户选择。查模式路由表，按"读入上下文"列的路径依次 `read` 加载。已有内容跳过。
1. **读决策树**：根据模式读取对应决策树文件（见模式路由表），`read references/D{N}.md`
2. **逐层追问**：向用户解释"在开始之前，我先问几个问题了解你的想法"，每问附推荐答案，用户可 `pass` 跳过分支
3. **整理需求**：将确认信息整理为清单（分支结论、关键需求、排除方向）
4. **展示成果总结**：向用户展示需求确认摘要——"根据你刚才的回答，我将在创作时遵循以下方向：[核心基调/重点关注/排除方向/其他设定]。如果没问题，我开始创作了？"——让用户看到"我说的话被用了"，提升参与感和掌控感。
5. **传递需求**：用户确认后，编排层将需求清单以对应变量名（见 §模式路由"输出变量"列）注入后续 task() 的 prompt CONTEXT。

**追问风格**：逐个提问，每问附推荐答案（基于类型常识和项目已有背景），用户确认或修正后记录结论再进下一问题，走完所有分支为止。

**进度可视化**：每轮追问前提示当前进度。快速模式下标记"只需回答 3 个核心问题"，每问标注进度（"还有 2 个问题 [2/3]：……"），降低用户的不耐烦感。

**交互前提**：仅当用户需求模糊（如"帮我想个创意""创建个角色""改一下角色"）时执行。若用户已给出详细需求（含类型、基调、核心元素、具体修改方向等），编排层跳过 grill 直接调度 task()。

**快速模式协议**：所有决策树支持快速模式（默认）和深度模式。快速模式只问每个决策树的 Top-3 核心问题，用户回答完 3 个问题后即可开始生成。用户说"再深入一下"或"多问几个"时自动展开剩余分支。用户输入含"急用""快点""简单来"等时编排层强制走快速模式。

## 参考文件

- `references/D1-ideation.md` — 创意构思需求发现树
- `references/D3-character.md` — 角色设计需求发现树
- `references/D4-chapter.md` — 章节写作需求发现树
- `references/D5-entity-editor.md` — 实体编辑需求发现树
- `references/D6-outline.md` — 大纲系列检查点（P4/P5/P6/P7）
- `references/D7-worldbuilding.md` — 世界观建设需求发现树（P2）
- `references/D8-quality-fuzzy.md` — 质量检测模糊入口引导（P9）
- `references/D9-chapter-edit-fuzzy.md` — 章节编辑模糊修改需求发现（P12）

## HARD CONSTRAINTS

1. **不替代创作决策** — 只收集需求，最终选择权在用户
2. **每个问题必须有据** — 基于类型常识或已有项目背景
3. **推荐答案必须具体且说明理由** — 有依据的选项，不泛泛而谈。每个推荐标签后附一句简短的推荐理由
4. **尊重用户中断** — `pass` 跳过当前分支，`stop` 立即终止，不追问原因


