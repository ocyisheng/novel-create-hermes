---
name: "novel-grill"
description: "创作前需求发现：在创作任务前，通过结构化追问发现用户需求偏好，并将确认结果写入 DeviationManager 供后续任务消费。触发词：grill"
license: "MIT"
version: "3.0.0"
compatibility: "OpenCode"
tags: ["novel", "grill", "v2"]
---

# 创作需求发现技能（V2）

## 核心职责

在 task() 或 skill() 生成内容前，主动追问用户需求偏好，将确认后的信息通过 DeviationManager 持久化。
流程：**追问 → 确认 → 写入偏差状态 → 被后续任务消费**。

V2 中 grill 不直接读取文件。编排层负责从 graph 查询上下文后传入，grill 只做追问。

## 上下文契约

> 编排层通过 `user_message` 参数传入 `mode=` + `context=`（JSON）。Grill 不再自行 read 文件。
> context 由编排层从 GraphStore API 查询后组装。

| 槽位 | V2 数据源（编排层负责获取） | 来源 API | 适用模式 |
|------|---------------------------|---------|---------|
| `{项目名}` | `config.yaml`（编排层读取） | `read config.yaml` | 全部 |
| `{已有角色列表}` | `store.find_units(type=CHARACTER_ARC)` → name + tags | GraphStore | character, chapter |
| `{故事背景摘要}` | `store.find_units(type=NOTE)` → tags 含"总纲"或"创意" | GraphStore | character, worldbuilding, plot |
| `{已有场景列表}` | `store.find_units(type=SCENE)` → name + belongs_to_chapter | GraphStore | chapter, outline |
| `{已有正文摘要}` | `search_engine.search(scope=[CHUNK], chapter={N})` | SearchEngine | quality, edit |
| `{已有情节线}` | `store.find_units(type=PLOT_THREAD)` → name + status | GraphStore | plot |
| `{活跃风格}` | `config.yaml` 的 `活跃风格` 字段 | `read config.yaml` | chapter, style |
| `{一致性状态}` | `deviation_manager.filter_for_presentation()` | DeviationManager | edit, quality |
| `{世界观设定}` | `store.find_units(type=WORLD_RULE)` → content 摘要 | GraphStore | worldbuilding |

## 模式调度

> 编排层通过 `skill("novel-grill", user_message="mode=xxx")` 传入模式。
> 编排层在调用前已通过 graph API 获取 context，通过 `user_message` 传入。

| 模式标识 | 场景 | 决策树文件 | 必需上下文 |
|---------|------|-----------|-----------|
| `ideation` | 创意构思前 | `references/D1-ideation.md` | 已有创意方向（或空） |
| `worldbuilding` | 世界观建设前 | `references/D7-worldbuilding.md` | 已有世界观设定、项目类型 |
| `character` | 角色创建前 | `references/D3-character.md` | 已有角色列表、故事背景 |
| `outline_synopsis` | 总纲撰写前 | `references/D6-outline.md` §D6.1 | 故事背景、项目类型 |
| `plot` | 情节规划前 | `references/D6-outline.md` §D6.3 | 总纲、已有情节线 |
| `volume` | 分卷大纲前 | `references/D6-outline.md` §D6.2 | 总纲概要 |
| `chapter_outline` | 分纲构建前 | `references/D6-outline.md` §D6.4 | 已有场景列表、角色列表 |
| `chapter` | 章节写作前 | `references/D4-chapter.md` | 已有正文摘要、活跃风格、出场角色 |
| `entity-editor` | 编辑角色/设定前 | `references/D5-entity-editor.md` | 目标实体当前内容、故事背景 |
| `quality` | 质量检测前 | — | 一致性状态、检测焦点 |
| `edit` | 修改章节前 | `references/D9-chapter-edit-fuzzy.md` | 正文内容、分纲摘要、出场角色 |

> 与 V1 区别：V2 无固定阶段（P1-P13），任何模式可随时调用。编排层根据用户意图选择模式，不依赖阶段状态。

## 工作流程

**目标**：在 task() 生成前收集用户需求，确认后的信息通过 DeviationManager 持久化，供后续创作/分析任务消费。

1. **接收上下文**：编排层已通过 graph API 获取并传入 `context=JSON`，Grill 直接使用
2. **读决策树**：根据模式读取对应决策树文件，`read references/D{N}.md`
3. **逐层追问**：向用户解释"在开始之前，我先问几个问题了解你的想法"，每问附推荐答案，用户可 `pass` 跳过分支
   - 快速模式（默认）：只问 Top-3 核心问题
   - 深度模式：用户说"多问几个"或"再深入一下"时展开剩余分支
   - 用户输入含"急用""快点""简单来"等时编排层强制走快速模式
4. **整理需求**：将确认信息整理为清单（分支结论、关键需求、排除方向）
5. **展示成果总结**：向用户展示需求确认摘要——"根据你刚才的回答，我将在创作时遵循以下方向：[核心基调/重点关注/排除方向/其他设定]。如果没问题，我开始创作了？"
6. **持久化**：用户确认后，调用 DeviationManager 写入需求状态：

```python
deviation_manager.merge(
    source="grill:{模式标识}",
    findings=[
        {"field": "核心基调", "expected": "冷峻实用主义", "severity": "info"},
        {"field": "排除方向", "expected": "不写系统流", "severity": "critical"},
        {"field": "重点关注", "expected": "力量体系合理性", "severity": "info"},
    ],
    scan_version=current_version,
)
```

> Drill 的输出不再通过 `{grill_需求}` 变量注入 prompt，而是写入 DeviationManager。
> 后续创作任务会自动检查 DeviationManager 中 `source="grill:*"` 的记录，作为意图基准。
> align/full-diagnose 分析时也会自动加载这些记录进行偏差对比。

## 追问风格

- 逐个提问，每问附推荐答案（基于类型常识和项目已有背景）
- 用户确认或修正后记录结论再进下一问题
- 每轮追问前提示当前进度："还有 2 个问题 [2/3]：……"
- 用户 `pass` 跳过当前分支，`stop` 立即终止，不追问原因

**交互前提**：仅当用户需求模糊（"帮我想个创意""创建个角色""改一下角色"）时执行。若用户已给出详细需求，编排层跳过 grill 直接调度。

## HARD CONSTRAINTS

1. **不替代创作决策** — 只收集需求，最终选择权在用户
2. **每个问题必须有据** — 基于类型常识或已有项目背景
3. **推荐答案必须具体** — 有依据的选项，不泛泛而谈
4. **尊重用户中断** — `pass` 跳过，`stop` 终止
5. **不直接 read 项目文件** — 所有上下文由编排层通过 graph API 获取后传入

## 参考文件

- `references/D1-ideation.md` — 创意构思需求发现树
- `references/D3-character.md` — 角色设计需求发现树
- `references/D4-chapter.md` — 章节写作需求发现树
- `references/D5-entity-editor.md` — 实体编辑需求发现树
- `references/D6-outline.md` — 大纲系列检查点（总纲/分卷/情节/分纲）
- `references/D7-worldbuilding.md` — 世界观建设需求发现树
- `references/D8-quality-fuzzy.md` — 质量检测焦点快速选择
- `references/D9-chapter-edit-fuzzy.md` — 章节编辑需求发现树
