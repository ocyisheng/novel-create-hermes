# 开发者文档

[← 返回主页](README.md)

---

## 五层架构

```
novel-writer.md（编排层）→ 阶段识别、task()调度、上下文加载
        │ task(subagent_type="novel-*", load_skills=["..."])
        ▼
opencode.json（配置层）→ subagent_type → 模型映射
        │ sisyphus-junior + SKILL.md
        ▼
17 个 SKILL.md（执行层）→ 各自领域工作，Context Contract 声明输入
        │ read / write / bash
        ▼
Python 脚本（工具层）→ 索引、追踪、导出、配置、模板提取
        ▼
.omo/ + config.yaml（状态层）→ 运行时记忆，只存不决策
```

| 层 | 职责 | 边界 |
|----|------|------|
| **编排层** | P-3→P14 阶段识别、task() 调度、上下文加载 | 不直接写项目文件 |
| **配置层** | subagent_type → 模型映射 | 只作用于 task() 子 Agent |
| **执行层** | 按 SKILL.md + Context Contract 执行 | 不做编排决策、不调度其他技能 |
| **工具层** | 索引、追踪、导出、配置 | 不碰状态决策 |
| **状态层** | notepad + config.yaml | 只存不决策 |

---

## 项目结构

```
novel-create-hermes/
├── opencode.json                    ← agent + 17 个技能 + tools
├── .omo/
│   ├── plans/                       ← 创作工作计划
│   └── notepads/                    ← 运行时记忆
├── .opencode/
│   ├── shared/                      ← 项目维护脚本
│   ├── agents/novel-writer.md       ← 主编排 Agent prompt
│   └── skills/                      ← 17 个创作技能
├── knowledge/                       ← 结构化知识库
├── novels/                          ← 所有小说项目
└── docs/                            ← 开发文档
```

---

## 17 个技能

| 技能 | 作用 | 阶段 | 调度 | subagent_type |
|------|------|------|------|----------|
| `novel-project-manager` | 项目新建/导入/续写/删除 | P-2 | `skill()` | — |
| `novel-env-setup` | .venv 环境初始化 | P-1 | `skill()` | — |
| `novel-grill` | 需求发现（交互式追问） | P-3 | `skill()` | — |
| `novel-ideation` | 创意构思、约束管理、评估 | P1 | `task()` | `novel-ideator` |
| `novel-style` | 风格提取/激活 | P10 | `task()` | `novel-ideator` |
| `novel-worldbuilding` | 世界观建设 | P2 | `task()` | `novel-crafter` |
| `novel-character` | 角色创建 | P3 | `task()` | `novel-crafter` |
| `novel-synopsis` | 总纲撰写、叙事策略设计 | P4-P4.5 | `task()` | `novel-crafter` |
| `novel-plot` | 情节构建 | P5 | `task()` | `novel-crafter` |
| `novel-outline` | 分卷大纲、分纲构建 | P6-P7 | `task()` | `novel-crafter` |
| `novel-chapter` | 章节写作 | P8 | `task()` | `novel-crafter` |
| `novel-edit` | 编辑已有内容 | P12-P13 | `skill()` | — |
| `novel-export` | 格式化导出 | P11 | `task()` | `novel-crafter` |
| `novel-quality` | AI味/情节/角色/世界观检测 | P9 | `task()` | `novel-reviewer` |
| `novel-search-analysis` | 跨文件搜索/实体引用/Gap 分析 | — | `skill()` | — |
| `book-to-knowledge` | 书籍导入为结构化知识库 | P0 | `skill()` | — |
| `book-knowledge` | 知识库检索/查询/引用 | P0 | `skill()` | — |

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
| P0 | 知识库操作 | 参考/查书/导入书籍/学习资料 | 查询→`skill("book-knowledge")`；导入→`skill("book-to-knowledge")` |
| P1 | 创意构思 | 没想法/没灵感/脑洞/构思 | `task(novel-ideation)` |
| P2 | 世界观建设 | 设定/规则/体系/势力 | `task(novel-worldbuilding)` |
| P3 | 角色创建 | 角色/人物/角色档案 | `task(novel-character)` |
| P4 | 总纲撰写 | 大纲/总纲/故事框架 | `task(novel-synopsis)` |
| P5 | 情节构建 | 情节/主线/支线 | `task(novel-plot)` |
| P6 | 分卷大纲 | 分卷/卷大纲 | `task(novel-outline)` |
| P7 | 分纲构建 | 分纲/章节大纲 | `task(novel-outline)` |
| P8 | 章节写作 | 第X章/写第 | `task(novel-chapter)` |
| P9 | 质量检测 | 检测AI味/review/质量 | `task(novel-quality)` |
| P10 | 风格提取 | 提取风格/分析文风 | `task(novel-style)` |
| P11 | 导出 | 导出/发布/export | `task(novel-export)` |
| P12 | 章节编辑 | 润色/修订/修改章节 | `skill("novel-edit")` |
| P13 | 实体编辑 | 编辑/更新角色/世界观 | `skill("novel-edit")` |
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

## 追踪文件体系（outline/追踪/）

追踪文件是**工具层**（Python 脚本）的输出产物，每章写后自动维护，存储于项目目录的 `outline/追踪/`。

### 设计原则

- **写后只追加**：增量更新（`_tracking.py`）每章写后被 `chapter_tracking.py` 调用，追加扁平记录，不改旧数据
- **全量重建（`rebuild_*.py`）**：从分纲和章节元数据扫描重建，输出与增量一致，用于修复或恢复
- **两类文件**：扁平记录（事件级，追加）和聚合视图（实体→章节映射，覆写），分开存储

### 扁平记录文件

| 文件 | 回答的问题 | 增量更新函数 | 全量重建脚本 |
|------|-----------|-------------|-------------|
| `伏笔.yaml` | **伏笔设在哪章，回收了没有**：`{编号, 描述, 章节, 状态}` | `update_foreshadowing()` | `rebuild_foreshadowing.py` |
| `时间线.yaml` | **每章发生了什么时间线事件**：`{描述, 章节, 时间}` | `update_timeline()` | `rebuild_timeline.py` |
| `角色统计.yaml` | **每章有哪些角色出场、什么状态**：`{角色, 章节, 状态}` | `update_character_stats()` | `rebuild_character_stats.py` |
| `章节摘要.yaml` | **每章的摘要**：`{章节, 摘要}` | `update_chapter_summary()` | `rebuild_chapter_summaries.py` |
| `情节线进度.yaml` | **情节线在哪些章节活跃**：`{情节线, 章节, 时间}` | `update_plot_threads()` | `rebuild_plot_progress.py` |

### 聚合视图文件

聚合文件由对应的 `rebuild_*.py` 从扁平记录中 group by 生成，增量更新时就地修改单条，全量重建时全部重算。

| 文件 | 回答的问题 | 数据源 |
|------|-----------|--------|
| `角色登场聚合.yaml` | **角色出场章节总览**：`{角色名 → {chapters[], total, status}}` | `角色统计.yaml` |
| `情节线活跃章节聚合.yaml` | **每条情节线覆盖章节范围**：`{情节线ID → {chapters[], active_count}}` | `情节线进度.yaml` |
| `世界构建章节映射.yaml` | **世界观实体在哪些章节被引用**：`{实体ID → {chapters[], first, last, count}}` | `分纲/*.yaml` 的 `涉及地点` |

### 关键区分：伏笔 vs 情节线进度

| | 伏笔.yaml | 情节线进度.yaml |
|--|----------|--------------|
| 回答 | **伏笔本身生命周期**（设在哪、回收没） | **情节线活跃范围**（覆盖哪些章节） |
| 一条记录 | `{编号: "F001", 章节: 3, 状态: "待回收"}` | `{情节线: "主线", 章节: 3}` |
| 主键 | 伏笔编号（F001, F002...） | 情节线ID + 章节号 |
| 关注点 | 伏笔的**设→回收**过程 | 情节线的**活跃→不活跃**区间 |

### 数据流向

```
章节写后
  │
  ├→ `chapter_tracking.py` → `_tracking.py` 的增量函数
  │     ├→ update_foreshadowing()        → 伏笔.yaml（追加）
  │     ├→ update_timeline()             → 时间线.yaml（追加）
  │     ├→ update_character_stats()      → 角色统计.yaml（追加）
  │     ├→ update_plot_threads()         → 情节线进度.yaml（追加）
  │     ├→ update_chapter_summary()      → 章节摘要.yaml（追加）
  │     ├→ update_worldbuilding_usage()  → 世界构建章节映射.yaml（覆写）
  │     └→ 触发聚合重建                    → 角色登场聚合.yaml / 情节线活跃章节聚合.yaml（覆写）
  │
  └─ 手动全量修复
        python chapter_tracking.py --rebuild-all
        → 调用所有 rebuild_*.py，从分纲和 .metas/ 扫描重建
```

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
