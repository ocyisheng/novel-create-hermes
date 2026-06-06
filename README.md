# novel-create-hermes

从创意构思、写作执行、质量把控、风格管理到检查点控制的完整小说创作引擎。10 个技能 + OhMyOpenAgent 插件多模型编排。

## 架构

五层 + 插件模型路由层：

```
novel-writer.md（编排层）→ 阶段识别、task()调度、上下文加载、检查点
        │ task(category="novel-*", load_skills=["..."])
        ▼
oh-my-openagent.json（插件层）→ category → 模型路由 + fallback 链
        │ sisyphus-junior + SKILL.md
        ▼
10 个 SKILL.md（执行层）→ 各自领域工作，Context Contract 声明输入
        │ read / write / bash
        ▼
Python 脚本（工具层）→ 索引、追踪、导出、配置、模板提取（extract_template.py，框架无关）
        ▼
.omo/ + config.yaml（状态层）→ 运行时记忆，只存不决策
```

| 层 | 职责 | 边界 |
|----|------|------|
| **编排层** | P-1→P10 阶段识别、task() 调度、上下文加载、检查点 | 不直接写项目文件 |
| **插件层** | category → 模型路由、fallback 链 | 只作用于 task() 子 Agent |
| **执行层** | 按 SKILL.md + Context Contract 执行 | 不做编排决策、不调度其他技能 |
| **工具层** | 索引、追踪、导出、配置 | 不碰状态决策 |
| **状态层** | notepad + config.yaml | 只存不决策 |

## 项目结构

```
novel-create-hermes/
├── opencode.json                    ← agent + 10 个技能 + tools
├── .omo/
│   ├── plans/novel-creation.md      ← 工作流计划
│   └── notepads/
│       ├── templates/               ← notepad 模板
│       ├── projects/                ← 项目切换快照
│       ├── novel-context.md         ← 项目状态快照
│       ├── novel-issues.md          ← 矛盾追踪
│       └── novel-learnings.md       ← 跨项目技巧
├── .opencode/
│   ├── shared/                      ← 项目维护脚本
│   │   ├── _utils.py                   ← 公共工具（YAML读写、路径解析）
│   │   ├── _tracking.py                ← 追踪数据维护（伏笔/时间线/角色/config）
│   │   ├── _summary.py                 ← 标记提取 + 摘要内联
│   │   ├── auto_update.py              ← 章节写后元数据维护（CLI编排）
│   │   ├── rebuild_project_index.py    ← 项目索引重建
│   │   ├── config_manager.py           ← config 字段读写（dot notation）
│   │   ├── phase_detect.py             ← 文件证据阶段推导
│   │   ├── export.py                   ← 格式化导出（EPUB/PDF/TXT/DOCX）
│   │   ├── validate_entity_consistency.py ← 实体一致性校验
│   │   ├── extract_template.py         ← prompt 模板填充（框架无关）
│   │   └── migrate_from_ref.py         ← 项目迁移
│   ├── agents/novel-writer.md       ← 主编排 Agent prompt
│   └── skills/                      ← 10 个创作技能（见下表）
├── novels/                          ← 所有小说项目父目录
└── docs/                            ← 开发文档
```

## 技能一览

### 10 个技能

| 技能 | 作用 | 阶段 | category |
|------|------|------|----------|
| `novel-project-manager` | 项目新建/导入/续写/删除 | P0 | `novel-pm` |
| `novel-env-setup` | .venv 环境初始化 | P-1 | `novel-pm` |
| `novel-ideation` | 创意构思、约束管理、评估 | P1 | `novel-ideate` |
| `novel-outline` | 大纲规划、情节构建、分纲撰写 | P2/P3/P6 | `novel-write` |
| `novel-entity` | 角色创建、世界观建设 | P4/P5 | `novel-write` |
| `novel-chapter` | 章节写作 | P7 | `novel-write` |
| `novel-polish` | 文笔优化、反馈修订、导出 | 按需 | `novel-write` |
| `novel-style` | 风格提取/激活（22 个内置） | P9 | `novel-ideate` |
| `novel-quality` | AI 味/情节/角色/世界观/节奏 | P8 | `novel-review` |
| `novel-checkpoint-service` | 检查点 pause/continue 决策 | — | — |

### 技能打包结构

每个技能自包含模板、资产和引用：

```
novel-chapter/
├── SKILL.md              ← 技能指令 + Context Contract
├── templates/            ← prompt 模板
│   └── prompt_template.md
├── assets/               ← 自有模板
│   └── chapter.yaml
└── references/           ← 自有参考文件
    ├── writing_principles.md
    ├── scene-guide.md
    └── foreshadowing.md
```

### Context Contract

执行技能在 SKILL.md 中声明上下文契约，编排层按契约加载后传入：

| 技能 | 声明的上下文输入 |
|------|----------------|
| novel-outline | 创意方案 / 总纲 / 情节线 + 角色列表 |
| novel-entity | 创意方案 + 总纲 |
| novel-chapter | 分纲 / 前章摘要 / 衔接 / 角色 / 世界观 / 伏笔 / 支线 / 问题 / 风格（9 槽位） |

## OhMyOpenAgent 插件

本项目依赖 OhMyOpenAgent 插件（`oh-my-openagent@4.x`），按 **category 路由子 Agent 到不同模型**。

### Category 路由

| category | 阶段 | 主模型 | fallback 链 |
|----------|------|--------|------------|
| `novel-write` | P2-P7 | deepseek-v4-flash-free | big-pickle → nemotron → v4-flash → v4-pro |
| `novel-review` | P8 | deepseek-v4-flash-free | nemotron → big-pickle → v4-flash → v4-pro |
| `novel-ideate` | P1/P9 | big-pickle | deepseek-v4-flash-free → mimo → v4-flash |
| `novel-pm` | P0 | nemotron-3-super-free | big-pickle → v4-flash |

> category 路由只作用于 task() 子 Agent，主 novel-writer Agent 使用会话模型。

### 插件配置

`~/.config/opencode/oh-my-openagent.json`：

```json
{
  "categories": {
    "novel-write": {
      "model": "opencode/deepseek-v4-flash-free",
      "fallback_models": ["opencode/big-pickle", "opencode/nemotron-3-super-free", "deepseek/deepseek-v4-flash", "deepseek/deepseek-v4-pro"]
    },
    "novel-review": {
      "model": "opencode/deepseek-v4-flash-free",
      "fallback_models": ["opencode/nemotron-3-super-free", "opencode/big-pickle", "deepseek/deepseek-v4-flash", "deepseek/deepseek-v4-pro"]
    },
    "novel-ideate": {
      "model": "opencode/big-pickle",
      "fallback_models": ["opencode/deepseek-v4-flash-free", "opencode/mimo-v2.5-free", "deepseek/deepseek-v4-flash"]
    },
    "novel-pm": {
      "model": "opencode/nemotron-3-super-free",
      "fallback_models": ["opencode/big-pickle", "deepseek/deepseek-v4-flash"]
    },
  }
}
```

### .omo/ 目录约定

`.omo/` 是 OhMyOpenAgent 插件标准工作目录：

| 路径 | 插件功能 | 本项目用途 |
|------|---------|-----------|
| `.omo/plans/` | Prometheus 读取 | `novel-creation.md` |
| `.omo/notepads/` | Momus/Boulder | novel-context/issues/learnings |
| `.omo/run-continuation` | Ralph Loop 续接 | 默认启用 |

## 工作流（P-1 → P10）

```
P-1  环境初始化
P0   项目管理
P1   创意构思 → ideation_after_concept
P2   大纲规划
P3   情节构建
P4   世界观建设
P5   角色创建
P6   分纲构建 → writing_after_outline（安全门）
P7   章节写作 → writing_after_chapters（仅 high）
P8   深度检查 → quality_after_*
P9   风格提取
P10  意图澄清
```

### 检查点等级

| 等级 | 语义 | 暂停点 |
|------|------|--------|
| `low` | 安全门 | 仅 writing_after_outline |
| `medium` | 关键决策 | + 创意方向、大纲、质量总评 |
| `high` | 逐步审核 | + 角色/世界观/每章/每检测 |

### Ultrawork

`ulw 写第3-5章` — 连续写作不打断，唯一例外：入口查 writing_after_outline 安全门。

## 实体信息存储

| 层级 | 存储 | 大小 | 加载时机 |
|------|------|------|---------|
| Layer 1 项目索引 | `project_index.yaml` | ~200B/实体 | 始终 |
| Layer 2 摘要 | 实体文件的 `摘要` 段 | ~200B/实体 | 写章/质检 |
| Layer 3 完整档案 | 实体文件 `完整档案` 段 | 数KB | 深度描写 |

## 快速开始

- Python 3.8+ / OpenCode / OhMyOpenAgent 插件

```bash
# 创建项目
python .opencode/skills/novel-project-manager/scripts/init.py new "我的小说" "玄幻"

# 风格管理
python .opencode/skills/novel-style/scripts/style_manager.py builtin list
python .opencode/skills/novel-style/scripts/style_manager.py activate --project-root NOVELS_ROOT/项目名 --name "凡人修仙风"

# 导出
python .opencode/shared/export.py --project-root NOVELS_ROOT/项目名 --format txt html

# 维护
python .opencode/shared/auto_update.py --project-root NOVELS_ROOT/项目名
python .opencode/shared/rebuild_project_index.py --project-root NOVELS_ROOT/项目名
```

## 内置风格（22 个，六大类）

| 类别 | 风格 |
|------|------|
| 网文 | 凡人修仙风、经典男频风、经典女频风、通俗网文风（默认） |
| 武侠 | 金庸武侠风、古龙武侠风、新派武侠风 |
| 古典 | 古典名著风、历史演义风、神魔志怪风、文艺古风 |
| 近现代 | 近现代名著风、鲁迅式风、老舍式风、张爱玲式风 |
| 外国 | 西方经典文学风、俄罗斯文学风、日本文学风、拉美魔幻风 |
| 通用 | 纪实白描风、悬疑推理风、都市现实风 |

## License

MIT
