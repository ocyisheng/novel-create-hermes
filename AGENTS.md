# novel-create-hermes — 项目上下文指引

## 项目性质

这是一个基于 OhMyOpenCode Skills 的小说创作工具。当前项目**不是被创作的小说本身**，
而是一个"创作引擎"——提供 8 个技能帮助用户完成从创意构思、写作执行、风格管理到质量把控的全流程。

## 目录结构

```
novel-create-hermes/              ← 工具项目根目录
├── AGENTS.md                      ← 本文件 — Sisyphus 上下文指引
├── opencode.json                  ← 项目级配置（已注册 8 个 skill）
├── .opencode/
│   ├── agents/
│   │   └── novel-writer.md        ← 主调度 Agent prompt
│   └── skills/                    ← 8 个创作技能（详见下文）
├── .omo/
│   ├── plans/                     ← 小说创作工作计划（非本项目开发计划）
│   └── notepads/                  ← 创作上下文持久化
└── docs/                          ← 历史开发文档（不代表当前规范）

NOVELS_ROOT/                       ← 小说项目根目录（novel-create-hermes/novels/）
├── .venv/                         ← 共享 Python 虚拟环境（自动发现上一级或 novels/ 下）
└── {小说名}/                       ← 单个小说项目
    ├── config.yaml                ← 项目配置（阶段等）
    ├── chapters/
    ├── characters/
    ├── ideation/
    ├── outline/
    ├── quality/
    ├── styles/                    ← 写作风格定义（可选，默认"通俗网文风"）
    └── worldbuilding/
```

## 技能一览

| 技能 | 场景 | 调用方式 |
|------|------|---------|
| `novel-project-manager` | 新建/导入/查看状态/续写/删除项目 | `task(category="novel-pm", load_skills=["novel-project-manager"], ...)` |
| `novel-env-setup` | 环境初始化 / .venv 故障修复 | `task(category="novel-pm", load_skills=["novel-env-setup"], ...)` 或 `skill("novel-env-setup")` |
| `novel-ideation` | 无创意 / 需要脑洞/灵感/构思 | `task(category="novel-ideate", load_skills=["novel-ideation"], ...)` |
| `novel-style` | 风格提取/切换/查看内置风格 | `task(category="novel-ideate", load_skills=["novel-style"], ...)` |
| `novel-outline` | 大纲/总纲/分卷/分纲/情节主线支线 | `task(category="novel-write", load_skills=["novel-outline"], ...)` |
| `novel-entity` | 角色档案/世界观建设 | `task(category="novel-write", load_skills=["novel-entity"], ...)` |
| `novel-chapter` | 章节写作 | `task(category="novel-write", load_skills=["novel-chapter"], ...)` |
| `novel-polish` | 文笔优化/反馈修订/导出 | `task(category="novel-write", load_skills=["novel-polish"], ...)` |
| `novel-quality` | AI味/情节/角色/世界观/节奏/风格/反馈 | `task(category="novel-review", load_skills=["novel-quality"], ...)` |

## 关键规则

1. **所有技能调用必须传递 `PROJECT PATH`**，路径须是 `NOVELS_ROOT/{项目名}` 的格式
2. **Python 环境依赖**：如果 `.venv/` 不存在，先走 `novel-env-setup` 初始化
3. **项目选择** → novel-writer.md §1.2
4. **不直接写项目文件**：agent 自己不写 YAML/TXT，通过 `task()` 调用技能来执行

### 阶段识别 → novel-writer.md §6.2

**状态查询**（"当前项目""查看状态""进度""在哪一步""写了几章"）→ 快速状态查询：读 config.yaml，直接报告。

### 连续创作（ultrawork）→ novel-writer.md §6.4
