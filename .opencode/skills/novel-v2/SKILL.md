---
name: "novel-v2"
description: "V2 创作引擎：基于叙事单元网络(graph)的下一代创作能力。用于已迁移项目的章节写作、角色管理、世界观维护、情节规划、质量检测、可视化等全部创作操作。触发词：V2、graph、叙事单元、QUERY、migrate、可视化、关系图、时间线、viz"
license: "MIT"
version: "1.0.0"
compatibility: "OpenCode"
tags: ["novel", "v2", "graph"]
---

# novel-v2 — V2 创作引擎

## 定位

本技能是 V2 架构的操作指引。不替代现有技能，而是在项目已迁移到 V2（存在 `graph/` 目录）时，提供基于叙事单元网络的创作能力。

**使用条件**：项目根目录下存在 `graph/nodes.jsonl` 文件（已执行过 `migrate.py`）。

---

## 领域参考（按焦点类型）

子 Agent 根据 `FOCUS TYPE` 加载对应的创作方法论参考文档：

| 焦点类型 | 参考文档 | 应关注什么 |
|---------|---------|-----------|
| `scene` | `references/scene.md` | 场域设计、张力曲线、角色自动性、语言尸体 |
| `character_arc` | `references/character_arc.md` | 扁平vs圆形、自动性空间、关系标签 |
| `plot_thread` | `references/plot_thread.md` | 伏笔四分类、复调结构、松散度 |
| `world_rule` | `references/world_rule.md` | 方法论选择、自洽性标准、延迟创建 |
| `note` | `references/note.md` | 总纲核心决策、叙事策略、灵感记录 |
| `chunk` | `references/chunk.md` | AI味检测、意志速度检验、主题曲检验 |
| `style` | `references/styles/style_format.md` + `references/styles/style_extraction.md` | 7 维度格式契约、提取工作流、22 内置风格 |

### 脚本 vs 提示词的分工

**脚本（schemas.py + graph_store.py）自动处理：**
- content JSON 的必填字段校验（字段名、类型、枚举值）
- 创建/更新时自动检查字段完整性，遗漏时报 warning
- 结构规范不需要 LLM 记忆——脚本会提示

**提示词（本参考文档）负责：**
- 创作方法论（哪些设计原则适用、什么情况选什么方案）
- 质量判断标准（什么是语言尸体、什么是意志速度）
- 这些需要 LLM 的理解和判断，不适合硬编码

## 上下文契约

### 焦点启动（编排层负责）

编排层在调用 `task(subagent_type="novel-v2-crafter", load_skills=["novel-v2"])` 时，在 prompt 中注入以下 V2 上下文：

```
CURRENT PROJECT: {项目名}
PROJECT PATH: {NOVELS_ROOT/项目名}
FOCUS TYPE: scene | character_arc | plot_thread | world_rule | note | chunk | style
FOCUS ID: {叙事单元ID}
FOCUS NAME: {叙事单元名称}
PREHEAT LEVEL: cold | warm | hot
WRITING MODE: draft | polish | rewrite
```

---

## V2 操作指南（CLI 命令的唯一源头）

所有 V2 操作通过 `v2_cli.py` 执行。以下命令列表是唯一权威参考——Agent 和子 Agent 的 prompt 不应重复这些命令，应引用本指南。

### 1. 读取 graph 数据

```bash
# 按名称查找叙事单元 ID
python .opencode/shared/v2/v2_cli.py find-unit --path {PROJECT_PATH} --name "{名称}"

# 获取叙事单元详情
python .opencode/shared/v2/v2_cli.py get-unit --path {PROJECT_PATH} --id {单元ID}

# 查询单元的关联关系（1-hop 邻居，可按关系类型过滤）
python .opencode/shared/v2/v2_cli.py get-neighbors --path {PROJECT_PATH} --id {单元ID}
python .opencode/shared/v2/v2_cli.py get-neighbors --path {PROJECT_PATH} --id {单元ID} --rel-type contains
python .opencode/shared/v2/v2_cli.py get-neighbors --path {PROJECT_PATH} --id {单元ID} --rel-type member_of

# 列出所有可用关系类型
python .opencode/shared/v2/v2_cli.py list-relation-types

# 按类型列出叙事单元（SCENE / CHARACTER_ARC / PLOT_THREAD / WORLD_RULE / NOTE / CHUNK，支持--limit）
python .opencode/shared/v2/v2_cli.py list-units --path {PROJECT_PATH} --type SCENE
python .opencode/shared/v2/v2_cli.py list-units --path {PROJECT_PATH} --type WORLD_RULE --limit 10

# 项目统计
python .opencode/shared/v2/v2_cli.py stats --path {PROJECT_PATH}

# 最近事件
python .opencode/shared/v2/v2_cli.py recent-events --path {PROJECT_PATH}
```

### 2. 写入 graph 数据

```bash
# 创建叙事单元（SCENE / CHARACTER_ARC / PLOT_THREAD / WORLD_RULE / NOTE / CHUNK）
python .opencode/shared/v2/v2_cli.py create-unit --path {PROJECT_PATH} --type SCENE --name "{单元名}" --content "{内容}" --tags "标签1,标签2" --chapter 3

# 更新叙事单元（内容 / 名称 / 标签，推荐用 --file 避免引号编码问题）
python .opencode/shared/v2/v2_cli.py update-unit --path {PROJECT_PATH} --id {单元ID} --file content.json
python .opencode/shared/v2/v2_cli.py update-unit --path {PROJECT_PATH} --id {单元ID} --name "新名称" --tags "新标签"

# 建立关系（--type 见下方"关系类型速查表"，加 --bidirectional 自动补反向）
python .opencode/shared/v2/v2_cli.py add-relation --path {PROJECT_PATH} --source {源ID} --target {目标ID} --type member_of
python .opencode/shared/v2/v2_cli.py add-relation --path {PROJECT_PATH} --source {源ID} --target {目标ID} --type contains
python .opencode/shared/v2/v2_cli.py add-relation --path {PROJECT_PATH} --source {源ID} --target {目标ID} --type located_at
python .opencode/shared/v2/v2_cli.py add-relation --path {PROJECT_PATH} --source {源ID} --target {目标ID} --type allied_with --bidirectional

# 补齐反向边：扫描所有关系，自动补齐对称类型缺失的反向边
python .opencode/shared/v2/v2_cli.py fix-asymmetry --path {PROJECT_PATH}

# 批量推断关系（新项目迁移后必做）
python .opencode/shared/v2/v2_cli.py batch-infer --path {PROJECT_PATH}
```

### 3. 会话管理

```bash
# 启动创作会话
python .opencode/shared/v2/v2_cli.py start-session --path {PROJECT_PATH} --type SCENE --id {单元ID}

# 构建工作空间上下文
python .opencode/shared/v2/v2_cli.py build-workspace --path {PROJECT_PATH} --id {焦点单元ID} --level warm

# 持久化 graph
python .opencode/shared/v2/v2_cli.py flush --path {PROJECT_PATH}
```

### 4. 通过 QUERY 协议获取上下文

写作过程中如果缺少信息，在回复中包含 QUERY 指令：

```
QUERY: character_background(name="角色名")
QUERY: scene_detail(scene_id="场景ID")  
QUERY: scene_detail(name="场景名")
QUERY: world_rule(name="规则名")
QUERY: plot_thread_summary(name="情节线名")
QUERY: plot_thread_summary()
QUERY: foreshadowing_status(id="伏笔编号")
QUERY: foreshadowing_status()
QUERY: advanced_search(keywords=["关键词1","关键词2"], limit=5)
QUERY: chapter_status(number=章节号)
QUERY: recent_context(chapter=章节号, limit=5)
```

编排层会拦截 QUERY，从 graph 查询，将结果注入 session 上下文。
**QUERY 指令不会出现在最终输出中。**

### 5. 导出和迁移

```bash
# V1→V2 迁移
python .opencode/shared/v2/migrate.py --project-root {PROJECT_PATH} --verify --report

# 导出结构化文档（Markdown，输出到 graph/export/）
python .opencode/shared/v2/v2_cli.py export-docs --path {PROJECT_PATH}

# 导出章节 TXT 文件
python .opencode/shared/v2/v2_cli.py export --path {PROJECT_PATH}
```

### 6. 数据格式标准

创建叙事单元时，content 字段遵循标准格式（详见 `references/数据格式标准.md`）：

**角色 (CHARACTER_ARC)**：
```json
{"角色类型": "主角", "性格": {"核心特质": "..."}, "角色弧线": {"起始状态": "...", "最终状态": "..."}, "能力设定": {"修为": "...", "功法": "...", "阵营": "..."}, "关键事件": [{"事件": "...", "时间": "..."}]}
```

**场景 (SCENE)**：
```json
{"章节类型": "推进/高潮/过渡", "结构规划": {"开篇": {...}, "发展": {...}, "转折": {...}, "收尾": {...}}, "出场角色": [...], "地点": "...", "核心冲突": "...", "一句话概要": "..."}
```

**情节线 (PLOT_THREAD)**：
```json
{"类型": "主线/支线", "冲突核心": "...", "关键事件": [{"章节": 10, "事件": "..."}], "终局设计": "..."}
```

**世界观 (WORLD_RULE)**：
```json
{"实体子类型": "location/faction/rule/power_system", "二级类型": "大陆/宗门/家族/秘境", "描述": "...", "位置": "...", "重要场所": [...]}
```

**笔记 (NOTE)**：
```json
{"note_type": "总纲/纪年事件/灵感", "事件": "...", "时间": "...", "备注": "..."}
```

**风格文件**：`references/styles/` 下有 22 个内置风格 YAML 文件（通俗网文风、凡人修仙风、金庸武侠风等）。当 FOCUS TYPE=style 时，可直接 `read` 这些文件获取参考模板。

不再使用 `_display` 字段。所有信息直接写入 content 字段，HTML 面板按值类型自动渲染。

---

## 核心原则（HARD CONSTRAINTS）

1. **graph 是真相源** — 所有创作数据优先写入 graph，投影到文件是次要的
2. **按需查询，勿全量推送** — 使用 QUERY 协议获取缺失信息，不要一次性加载全部数据
3. **写后 flush** — 每次 task() 完成后执行 `store.flush()` 确保持久化
4. **记录 actor** — 所有 create/update 操作传入 `actor` 参数（如 `actor="novel-v2-crafter"`）
5. **不要手工编辑 graph/ 下的 JSONL 文件** — 通过 GraphStore API 操作
6. **不要在回复中包含 QUERY 指令原文** — QUERY 是编排层协议，不会自动剥离
