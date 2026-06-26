# novel-create-hermes — 项目上下文指引

## 项目性质

这是一个基于 OhMyOpenCode Skills 的小说创作工具。当前项目**不是被创作的小说本身**，
而是一个"创作引擎"——提供 17 个技能帮助用户完成从环境安装、创意构思、写作执行、风格管理、知识库到质量把控的全流程。

## 目录结构

```
novel-create-hermes/              ← 工具项目根目录
├── AGENTS.md                      ← 本文件 — Sisyphus 上下文指引
├── DEVELOPER.md                   ← 开发者文档（五层架构、技能表、工作流）
├── opencode.json                  ← 项目级配置（已注册 17 个 skill）
├── README.md                      ← 用户入门指南
├── knowledge/                     ← 结构化知识库（由 book-to-knowledge 生成）
├── .opencode/
│   ├── agents/
│   │   └── novel-writer.md        ← 主调度 Agent prompt
│   └── skills/                    ← 17 个创作技能（详见下文）
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
| `novel-project-manager` | 新建/导入/查看状态/续写/删除项目 | `skill("novel-project-manager")` |
| `novel-env-setup` | 环境初始化 / .venv 故障修复 |  `skill("novel-env-setup")` |
| `novel-ideation` | 无创意 / 需要脑洞/灵感/构思 | `Task(subagent_type="novel-ideator", load_skills=["novel-ideation"], ...)` |
| `novel-style` | 风格提取/切换/查看内置风格 | `Task(subagent_type="novel-ideator", load_skills=["novel-style"], ...)` |
| `novel-worldbuilding` | 世界观建设/设定/规则/力量体系 | `Task(subagent_type="novel-crafter", load_skills=["novel-worldbuilding"], ...)` |
| `novel-character` | 角色档案/人物创建 | `Task(subagent_type="novel-crafter", load_skills=["novel-character"], ...)` |
| `novel-synopsis` | 总纲撰写/故事框架/叙事策略 | `Task(subagent_type="novel-crafter", load_skills=["novel-synopsis"], ...)` |
| `novel-plot` | 情节/主线/支线/故事线 | `Task(subagent_type="novel-crafter", load_skills=["novel-plot"], ...)` |
| `novel-outline` | 分卷大纲/分纲/章节大纲 | `Task(subagent_type="novel-crafter", load_skills=["novel-outline"], ...)` |
| `novel-chapter` | 章节写作 | `Task(subagent_type="novel-crafter", load_skills=["novel-chapter"], ...)` |
| `novel-edit` | 编辑已有内容：角色/世界观/大纲/章节修改 | `skill("novel-edit")` |
| `novel-export` | 格式化导出 EPUB/PDF/HTML/TXT/DOCX | `Task(subagent_type="novel-crafter", load_skills=["novel-export"], ...)` |
| `novel-grill` | 需求发现：创作前交互式追问收敛需求 | `skill("novel-grill")` |
| `novel-quality` | AI味/情节/角色/世界观/节奏/风格/反馈 | `Task(subagent_type="novel-reviewer", load_skills=["novel-quality"], ...)` |
| `novel-search-analysis` | 搜索分析：跨文件全文搜索、实体引用分析、Gap 分析 | `skill("novel-search-analysis")` |
| `book-to-knowledge` | 将书籍（PDF/EPUB/TXT/HTML/MOBI）导入为结构化知识库 | `skill("book-to-knowledge")` |
| `book-knowledge` | 知识库管理：检索、查询、引用已导入的知识 | `skill("book-knowledge")` |


