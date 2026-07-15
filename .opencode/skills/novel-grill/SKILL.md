---
name: "novel-grill"
description: "创作前需求发现：在创作任务前，通过结构化追问发现用户需求偏好，供编排层注入创作任务。触发词：grill"
license: "MIT"
version: "4.0.0"
compatibility: "OpenCode"
tags: ["novel", "grill", "v2"]
---

# 创作需求发现技能（V2）

## 核心职责

在 task() 或 skill() 生成内容前，主动追问用户需求偏好，将确认后的结论整理为需求清单，供编排层注入后续创作任务的 TASK prompt。
流程：**追问 → 确认 → 整理需求 → 编排层注入 crafter TASK**。

Grill **不做持久化存储**。确认的需求清单通过编排层直接传入 crafter prompt，由 crafter 写入对应叙事单元的 content 字段或作为一次性创作指引使用。

## 上下文契约

> 编排层通过 `user_message` 字符串传入焦点元信息，格式：`{FOCUS TYPE}:{FOCUS NAME}`。
> 例如 `user_message="scene:第一章 觉醒"` 或 `character_arc:林渊`。
> 编排层**不**预先查询 graph——grill 在追问过程中按需使用 novel-tool 自查询。

| 编排层提供 | 说明 |
|-----------|------|
| `CURRENT PROJECT` | 小说项目名称 |
| `PROJECT PATH` | 项目绝对路径 |
| `FOCUS TYPE` | 8 个聚焦类型之一：scene / character_arc / plot_thread / world_rule / note / structure / narrative_voice / thematic_motif |
| `FOCUS NAME` | 目标叙事单元名称（可选，为空表示新建） |

Grill 在追问过程中自行通过 novel-tool 查询需要的 graph 数据：
- `novel-tool --operation graph.search --project <PROJECT> --keyword <关键词>` — 搜索已有设定
- `novel-tool --operation graph.list_units --project <PROJECT> --unit_type <TYPE>` — 按类型列举
- `novel-tool --operation graph.get_unit --project <PROJECT> --name <名称>` — 查单个单元
- `novel-tool --operation graph.stats --project <PROJECT>` — 项目统计概览

## 模式调度

> 模式 = 聚焦类型。编排层通过 `skill("novel-grill", user_message="{FOCUS TYPE}:{FOCUS NAME}")` 调用。
> 8 种聚焦类型即 8 种模式，与 V2 叙事单元类型对齐。chunk 类型不进入 grill（正文写作无需需求发现，直接由编排层根据场景上下文执行）。

| 聚焦类型（模式） | 适用场景 | 决策树文件 |
|-----------------|---------|-----------|
| `scene` | 场景/章节写作前 | `references/D1-scene.md` |
| `character_arc` | 角色创建/编辑前 | `references/D2-character_arc.md` |
| `plot_thread` | 情节线设计/调整前 | `references/D3-plot_thread.md` |
| `world_rule` | 世界观设定/规则建设前 | `references/D4-world_rule.md` |
| `note` | 创意/备忘前 | `references/D5-note.md` |
| `structure` | 分卷/分纲/结构规划前 | `references/D6-structure.md` |
| `narrative_voice` | 叙事风格/视角/语调确认前 | `references/D7-narrative_voice.md` |
| `thematic_motif` | 主题/母题/伏笔规划前 | `references/D8-thematic_motif.md` |

注：edit 和 entity-editor 功能不作为独立模式，而是分布到各聚焦类型的决策树中（每个决策树的最后一个分支「编辑/调整」）。

## 工作流程

**目标**：在 task() 生成前收集用户需求，确认后的结论通过编排层注入 crafter 的 TASK prompt。

1. **接收焦点**：编排层传入 `{FOCUS TYPE}:{FOCUS NAME}`，Grill 识别聚焦类型
2. **读决策树**：根据聚焦类型读取对应决策树文件，`read references/D{N}-{type}.md`
3. **按需查询**：追问中如需已有数据（如已有角色、已有设定），通过 novel-tool 自行搜索
4. **逐层追问**：向用户解释"在开始之前，我先问几个问题了解你的想法"，每问附推荐答案，用户可 `pass` 跳过分支
   - 快速模式（默认）：只问 Top-3 核心问题
   - 深度模式：用户说"多问几个"或"再深入一下"时展开剩余分支
   - 用户输入含"急用""快点""简单来"等时编排层强制走快速模式
5. **整理需求**：将确认信息整理为清单（分支结论、关键需求、排除方向）
6. **展示成果总结**：向用户展示需求确认摘要——"根据你刚才的回答，我将在创作时遵循以下方向：[核心基调/重点关注/排除方向/其他设定]。如果没问题，我开始创作了？"
7. **交付编排层**：用户确认后，编排层将需求清单组织为 `### 创作需求` 段落，注入 crafter 的 TASK prompt：

```markdown
Task(
  subagent_type="novel-v2-crafter",
  load_skills=["novel-v2"],
  prompt="...
TASK: {用户原始请求}

### 创作需求（经需求确认）
- 性格：果断坚定，杀伐决断
- 身份：寒门出身的剑修
- 人物定位：主线核心，推动剧情
- 排除：不写系统流"
)
```

编排层注入规则：
- **实体级属性**（性格、背景、定位等）→ 注入 TASK，crafter 写入 unit content，后续通过 graph 自动加载
- **任务级指令**（节奏、侧重、排除项）→ 注入 TASK，一次性消费
- **项目级偏好**（罕见，如"整体基调灰暗"）→ 注入 TASK，每次创作时编排层自行判断是否需要重复注入

## 追问风格

- 逐个提问，每问附推荐答案（基于类型常识和项目已有背景）
- 用户确认或修正后记录结论再进下一问题
- 每轮追问前提示当前进度："还有 2 个问题 [2/3]：……"
- 用户 `pass` 跳过当前分支，`stop` 立即终止，不追问原因

**交互前提**：仅当用户需求模糊（"写个角色""加个设定"）时执行。若用户已给出详细需求，编排层跳过 grill 直接调度。

## HARD CONSTRAINTS

1. **不替代创作决策** — 只收集需求，最终选择权在用户
2. **每个问题必须有据** — 基于聚焦类型类型常识或已有项目背景
3. **推荐答案必须具体** — 有依据的选项，不泛泛而谈
4. **尊重用户中断** — `pass` 跳过，`stop` 终止
5. **不直接 read 项目文件** — 使用 novel-tool tool 查询 graph，不做文件级操作
6. **chunk 不经过 grill** — 正文写作不进入需求发现流程，编排层直接调度 crafter

## 参考文件

- `references/D1-scene.md` — 场景/章节写作需求发现树
- `references/D2-character_arc.md` — 角色创建/编辑需求发现树
- `references/D3-plot_thread.md` — 情节线设计需求发现树
- `references/D4-world_rule.md` — 世界观设定需求发现树
- `references/D5-note.md` — 创意/备忘需求发现树
- `references/D6-structure.md` — 分卷/分纲/结构需求发现树
- `references/D7-narrative_voice.md` — 叙事风格/视角需求发现树
- `references/D8-thematic_motif.md` — 主题/母题/伏笔需求发现树
