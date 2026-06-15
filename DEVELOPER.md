# 开发者文档

[← 返回主页](README.md)

---

## 五层架构

```
novel-writer.md（编排层）→ 阶段识别、task()调度、上下文加载
        │ task(category="novel-*", load_skills=["..."])
        ▼
oh-my-openagent.json（插件层）→ category → 模型路由 + fallback 链
        │ sisyphus-junior + SKILL.md
        ▼
12 个 SKILL.md（执行层）→ 各自领域工作，Context Contract 声明输入
        │ read / write / bash
        ▼
Python 脚本（工具层）→ 索引、追踪、导出、配置、模板提取
        ▼
.omo/ + config.yaml（状态层）→ 运行时记忆，只存不决策
```

| 层 | 职责 | 边界 |
|----|------|------|
| **编排层** | P-1→P14 阶段识别、task() 调度、上下文加载 | 不直接写项目文件 |
| **插件层** | category → 模型路由、fallback 链 | 只作用于 task() 子 Agent |
| **执行层** | 按 SKILL.md + Context Contract 执行 | 不做编排决策、不调度其他技能 |
| **工具层** | 索引、追踪、导出、配置 | 不碰状态决策 |
| **状态层** | notepad + config.yaml | 只存不决策 |

---

## 项目结构

```
novel-create-hermes/
├── opencode.json                    ← agent + 12 个技能 + tools
├── .omo/
│   ├── plans/novel-creation.md      ← 工作流计划
│   └── notepads/                    ← 运行时记忆
├── .opencode/
│   ├── shared/                      ← 项目维护脚本
│   ├── agents/novel-writer.md       ← 主编排 Agent prompt
│   └── skills/                      ← 12 个创作技能
├── novels/                          ← 所有小说项目
└── docs/                            ← 开发文档
```

---

## 12 个技能

| 技能 | 作用 | 阶段 | 调度 | category |
|------|------|------|------|----------|
| `novel-project-manager` | 项目新建/导入/续写/删除 | P-2 | `skill()` | — |
| `novel-env-setup` | .venv 环境初始化 | P-1 | `skill()` | — |
| `novel-grill` | 需求发现（交互式追问） | P-3 | `skill()` | — |
| `novel-ideation` | 创意构思、约束管理、评估 | P1 | `task()` | `novel-ideate` |
| `novel-style` | 风格提取/激活 | P10 | `task()` | `novel-ideate` |
| `novel-outline` | 总纲/分卷大纲/情节/分纲 | P2-P4,P7 | `task()` | `novel-write` |
| `novel-entity` | 角色创建、世界观建设 | P5-P6 | `task()` | `novel-write` |
| `novel-chapter` | 章节写作 | P8 | `task()` | `novel-write` |
| `novel-chapter-editor` | 章节编辑 | P12 | `task()` | `novel-write` |
| `novel-entity-editor` | 实体编辑 | P13 | `task()` | `novel-write` |
| `novel-export` | 格式化导出 | P11 | `task()` | `novel-write` |
| `novel-quality` | AI味/情节/角色/世界观检测 | P9 | `task()` | `novel-review` |

**调度方式**：
- `skill()` — 主 Agent 上下文执行，支持交互
- `task()` — 子 Agent 执行，不可交互

---

## 创作工作流（P-3 → P14）

| 优先级 | 阶段 | 触发词 | 调度 |
|--------|------|--------|------|
| P-3 | 需求发现 | 嵌入模糊分支，或 `grill` | `skill("novel-grill")` |
| P-2 | 项目管理 | 新建/导入/切换/续写/删除 | `skill("novel-project-manager")` |
| P-1 | 环境初始化 | 环境检测/安装依赖 | `skill("novel-env-setup")` |
| P1 | 创意构思 | 没想法/没灵感/脑洞/构思 | `task(novel-ideation)` |
| P2 | 总纲撰写 | 大纲/总纲/故事框架 | `task(novel-outline)` |
| P3 | 分卷大纲 | 分卷/卷大纲 | `task(novel-outline)` |
| P4 | 情节构建 | 情节/主线/支线 | `task(novel-outline)` |
| P5 | 世界观建设 | 设定/规则/体系/势力 | `task(novel-entity)` |
| P6 | 角色创建 | 角色/人物/角色档案 | `task(novel-entity)` |
| P7 | 分纲构建 | 分纲/章节大纲 | `task(novel-outline)` |
| P8 | 章节写作 | 第X章/写第 | `task(novel-chapter)` |
| P9 | 质量检测 | 检测AI味/review/质量 | `task(novel-quality)` |
| P10 | 风格提取 | 提取风格/分析文风 | `task(novel-style)` |
| P11 | 导出 | 导出/发布/export | `task(novel-export)` |
| P12 | 章节编辑 | 润色/修订/修改章节 | `task(novel-chapter-editor)` |
| P13 | 实体编辑 | 编辑/更新角色/世界观 | `task(novel-entity-editor)` |
| P14 | 意图澄清 | 以上均不匹配 | 询问用户 |

**连续创作**：`ulw 写第3-5章` — 批量生成章节，完成后自动质检。

---

## 关键脚本

| 脚本 | 用途 |
|------|------|
| `chapter_tracking.py` | 章节写后元数据维护 |
| `chapter_context.py` | 章节写作上下文收集 |
| `rebuild_project_index.py` | 项目索引重建 |
| `rebuild_character_stats.py` | 角色统计重建 |
| `rebuild_foreshadowing.py` | 伏笔重建 |
| `rebuild_timeline.py` | 时间线重建 |
| `rebuild_plot_progress.py` | 情节线进度重建 |
| `rebuild_chapter_summaries.py` | 章节摘要重建 |
| `config_manager.py` | config.yaml 字段读写 |
| `export.py` | 格式化导出（HTML/TXT/XHTML） |
| `validate_entity_consistency.py` | 实体一致性校验 |
| `extract_template.py` | prompt 模板填充 |

---

## 命令行用法

```bash
# 创建项目
python .opencode/skills/novel-project-manager/scripts/init.py new "我的小说" "玄幻"

# 风格管理
python .opencode/skills/novel-style/scripts/style_manager.py builtin list
python .opencode/skills/novel-style/scripts/style_manager.py activate --project-root NOVELS_ROOT/项目名 --name "凡人修仙风"

# 章节写作上下文
python .opencode/shared/chapter_context.py --project-root NOVELS_ROOT/项目名 --chapter 5

# 导出
python .opencode/shared/export.py --project-root NOVELS_ROOT/项目名 --format txt html

# 维护
python .opencode/shared/chapter_tracking.py --project-root NOVELS_ROOT/项目名
python .opencode/shared/rebuild_project_index.py --project-root NOVELS_ROOT/项目名

# 重建追踪
python .opencode/shared/chapter_tracking.py --project-root NOVELS_ROOT/项目名 --rebuild-all
```
