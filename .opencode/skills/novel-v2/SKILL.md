---
name: "novel-v2"
description: "V2 创作引擎：基于叙事单元网络(graph)的下一代创作能力。用于已迁移项目的章节写作、角色管理、世界观维护、情节规划、质量检测、可视化等全部创作操作。触发词：V2、graph、叙事单元、migrate、可视化、关系图、时间线、viz"
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

## 领域参考（按焦点类型 + 横切维度）

子 Agent 根据 `FOCUS TYPE` 加载对应的创作方法论参考文档。对于横切维度（不绑定单一焦点类型），根据特定条件额外加载。

### 焦点类型 → 参考文档映射

| 焦点类型 | 参考文档 | 子类型 | 应关注什么 |
|---------|---------|-------|-----------|
| `scene` | `references/scene.md` | 开篇/推进/冲突/转折/展示/过渡/收束 | 按场域功能选择方法论：POV选择、一句话概要、核心冲突 |
| `character_arc` | `references/character_arc.md` | 主角/重要配角/反派/关键配角/群像/功能性角色 | 按角色定位选择弧线深度：扁平vs圆形、自动性空间、关系标签 |
| `plot_thread` | `references/plot_thread.md` | 主线/支线/暗线/感情线/成长线/世界观线 | 按线类型控制信息释放：伏笔四分类、复调结构、松散度 |
| `world_rule` | `references/world_rule.md` | 世界观总览/规则/力量体系/势力/地点/历史/文化/纪年事件 | 按子类型选择创建策略：自洽性标准、延迟创建 |
| `note` | `references/note.md` | 灵感/笔记 | 灵感记录、本体论核心问题 |
| `chunk` | `references/chunk.md` | 版本标签 | 完整读取，统一方法论：正文写作原则 + 章尾钩子 + 写作警觉 |
| `structure` | `references/structure.md` | 总纲/卷大纲/章纲 | 按结构层次选用方法论：总纲→七面观照；卷大纲→卷弧线；章纲→场景规划 |
| `narrative_voice` | `references/narrative_voice.md` | 第一人称/第三人称限制/第三人称全知/第二人称/多视角交替 | 按视角类型决策：腔调谱系、信息分配、笔记传统 |
| `thematic_motif` | `references/thematic_motif.md` | 贯穿性/局部性/装饰性 | 按作用范围管理意象生命周期：倒置与反向、跨章节追踪 |

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
FOCUS TYPE: scene | character_arc | plot_thread | world_rule | note | chunk | structure | narrative_voice | thematic_motif
SUBTYPE: {章节类型}  # 各类型对应的子类型值
FOCUS ID: {叙事单元ID}
FOCUS NAME: {叙事单元名称}
PREHEAT LEVEL: cold | warm | hot
```

---

## V2 操作指南（Tool 的唯一源头）

所有 V2 操作通过 `novel-tool` tool 执行。以下命令列表是唯一权威参考。

### 1. 读取 graph 数据

```
# 按名称查找叙事单元 ID
novel-tool --operation graph.find_unit --project {PROJECT} --name "{名称}"

# 获取叙事单元详情
novel-tool --operation graph.get_unit --project {PROJECT} --id {单元ID}

# 查询单元的关联关系（1-hop 邻居，可按关系类型过滤）
novel-tool --operation graph.get_neighbors --project {PROJECT} --id {单元ID}
novel-tool --operation graph.get_neighbors --project {PROJECT} --id {单元ID} --relType contains
novel-tool --operation graph.get_neighbors --project {PROJECT} --id {单元ID} --relType member_of

# 列出所有可用关系类型
novel-tool --operation graph.list_relation_types

# 按类型列出叙事单元（SCENE / CHARACTER_ARC / PLOT_THREAD / WORLD_RULE / NOTE / CHUNK / STRUCTURE / NARRATIVE_VOICE，支持--limit）
novel-tool --operation graph.list_units --project {PROJECT} --unitType SCENE
novel-tool --operation graph.list_units --project {PROJECT} --unitType WORLD_RULE --limit 10

# 项目统计
novel-tool --operation graph.stats --project {PROJECT}

# 最近事件
novel-tool --operation graph.recent_events --project {PROJECT}
```

### 2. 写入 graph 数据

```
# 创建叙事单元
novel-tool --operation graph.create_unit --project {PROJECT} --type SCENE --name "{单元名}" --content "{内容}" --tags "标签1,标签2" --chapter 3

# 更新叙事单元（内容 / 名称 / 标签）
novel-tool --operation graph.update_unit --project {PROJECT} --id {单元ID} --content "{新内容JSON}"
novel-tool --operation graph.update_unit --project {PROJECT} --id {单元ID} --name "新名称" --tags "新标签"

# 建立关系（--bidirectional 自动补反向）
novel-tool --operation graph.add_relation --project {PROJECT} --source {源ID} --target {目标ID} --type member_of
novel-tool --operation graph.add_relation --project {PROJECT} --source {源ID} --target {目标ID} --type contains
novel-tool --operation graph.add_relation --project {PROJECT} --source {源ID} --target {目标ID} --type located_at
novel-tool --operation graph.add_relation --project {PROJECT} --source {源ID} --target {目标ID} --type allied_with --bidirectional

# 补齐反向边
novel-tool --operation graph.fix_asymmetry --project {PROJECT}

# 批量推断关系（新项目迁移后必做）
novel-tool --operation graph.batch_infer --project {PROJECT}
```

### 3. 会话管理

```
# 启动创作会话
novel-tool --operation session.start --project {PROJECT} --type SCENE --id {单元ID}

# 构建工作空间上下文
novel-tool --operation session.build_workspace --project {PROJECT} --id {焦点单元ID} --level warm

# 持久化 graph
novel-tool --operation graph.flush --project {PROJECT}
```

### 4. 导出和迁移

```
# V1→V2 迁移
novel-tool --operation graph.migrate --project {PROJECT} --verify --report

# 导出结构化文档（Markdown，输出到 graph/export/）
novel-tool --operation graph.export_docs --project {PROJECT}

# 导出章节 TXT 文件
novel-tool --operation graph.export_chunks --project {PROJECT}
```

### 5. 数据格式标准

创建叙事单元时，content 字段遵循标准格式（详见 `references/数据格式标准.md`）：

**角色 (CHARACTER_ARC)**：
```json
{"角色类型": "主角", "性格": {"核心特质": "..."}, "角色弧线": {"起始状态": "...", "最终状态": "..."}, "能力设定": {"修为": "...", "功法": "...", "阵营": "..."}, "关键事件": [{"事件": "...", "时间": "..."}]}
```

**场景 (SCENE)**：
```json
{"子类型": "开篇/推进/冲突/转折/展示/过渡/收束", "POV角色": "林渊", "地点": "落云宗后山练剑坪", "时间": "午后", "一句话概要": "林渊第一次拔剑", "出场角色": ["林渊", "苏长老"], "核心冲突": "练剑被阻", "关联情节线": ["主线·剑道之争"], "字数": 1500}
```

**情节线 (PLOT_THREAD)**：
```json
{"子类型": "主线/支线/暗线/感情线/成长线/世界观线", "冲突核心": "...", "关键事件": [{"章节": 10, "事件": "..."}], "终局设计": "..."}
```

**世界观 (WORLD_RULE)**：
```json
{"子类型": "地点/势力/规则/力量体系/纪年事件", "二级类型": "大陆/宗门/家族/秘境", "描述": "...", "位置": "...", "重要场所": [...]}
```

**笔记 (NOTE)**：
```json
{"子类型": "灵感 | 笔记", "内容": "..."}
```

**结构设计 (STRUCTURE)**：
```json
{"子类型": "总纲/卷大纲/章纲", "结构模式": "沙漏/长链/螺旋/环状/多线交织", ...}
```



不再使用 `_display` 字段。所有信息直接写入 content 字段，HTML 面板按值类型自动渲染。

---

## 核心原则（HARD CONSTRAINTS）

1. **graph 是真相源** — 所有创作数据优先写入 graph，投影到文件是次要的
2. **按需查询，勿全量推送** — 使用 `novel-tool` 按需查询，不要一次性加载全部数据
3. **写后 flush** — 每次 task() 完成后执行 `novel-tool --operation graph.flush` 确保持久化
4. **记录 actor** — 所有 create/update 操作传入 `actor` 参数（如 `actor="novel-v2-crafter"`）
5. **不要手工编辑 graph/ 下的 JSONL 文件** — 通过 GraphStore API 操作
6. **通过 novel-tool 操作** — 所有数据读写通过 `novel-tool` tool 执行，不要直接调用 Python API 或编辑 JSONL 文件
