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

## 领域参考（按角色路由）

子 Agent 根据自身角色（planner / writer / crafter / analyzer）加载对应的创作方法论参考文档。横切维度（关系操作）对所有角色通用，按需额外加载。

### 角色 → 参考文档路由

**IF YOU ARE planner**（规划：总纲/部篇/卷/章纲、情节线、笔记）→ 读取 `references/planning/`：

| 焦点类型 | 参考文档 | 子类型 | 应关注什么 |
|---------|---------|-------|-----------|
| `outline` | `references/planning/structure.md` | 总纲 | 七面观照+模式节奏+本体论 |
| `arc_plan` | `references/planning/structure.md` | 部大纲/篇大纲 | 部篇弧线+跨卷节奏+层级过渡 |
| `volume_plan` | `references/planning/structure.md` | 卷大纲 | 卷弧线+节奏密度+过渡 |
| `chapter_plan` | `references/planning/structure.md` | 章纲 | 章纲→场景规划+字数分配+密度预算 |
| `plot_thread` | `references/planning/plot_thread.md` | 主线/支线/暗线/感情线/成长线/世界观线 | 按线类型控制信息释放：伏笔四分类、复调结构、松散度 |
| `note` | `references/planning/note.md` | 灵感/笔记 | 灵感记录、本体论核心问题 |

**IF YOU ARE writer/crafter**（写作：场景/角色/世界观/正文/腔调/意象）→ 读取 `references/writing/` + `references/planning/`（全量物化需要结构方法论）：

| 焦点类型 | 参考文档 | 子类型 | 应关注什么 |
|---------|---------|-------|-----------|
| `scene` | `references/writing/scene.md` | 开篇/推进/冲突/转折/展示/过渡/收束 | 按场域功能选择方法论：POV选择、一句话概要 |
| `character_arc` | `references/writing/character_arc.md` | 主角/重要配角/反派/关键配角/群像/功能性角色 | 按角色定位选择弧线深度：扁平vs圆形、自动性空间、关系标签 |
| `world_rule` | `references/writing/world_rule.md` | 世界观总览/规则/力量体系/势力/地点/历史/文化/经济体系/政治体系/社会阶层/纪年事件 | 按子类型选择创建策略：自洽性标准、延迟创建 |
| `chunk` | `references/writing/chunk.md` | v1/v2/v3 | 完整读取，统一方法论：正文写作原则 + 章尾钩子 + 写作警觉 |
| `narrative_voice` | `references/writing/narrative_voice.md` | 第一人称/第三人称限制/第三人称全知/第二人称/多视角交替 | 按视角类型决策：腔调谱系、信息分配、笔记传统 |
| `thematic_motif` | `references/writing/thematic_motif.md` | 贯穿性/局部性/装饰性 | 按作用范围管理意象生命周期：倒置与反向、跨章节追踪 |
| `content 字段` | `references/writing/content字段参考.md` | 全部单元类型 | 创建/更新单元时按类型查字段标准 |

**IF YOU ARE analyzer**（质检/诊断）→ 读取 `references/analysis/`：

| 场景 | 参考文档 | 应关注什么 |
|------|---------|-----------|
| 质量检查 | `references/analysis/quality_methodology.md` | 设计原则、各场景校验关注点、统计信号裁决提示词（R7/R10/R11/R12） |

**（横切）关系操作**（所有角色通用）→ `references/relation_guide.md`：

| 焦点类型 | 参考文档 | 子类型 | 应关注什么 |
|---------|---------|-------|-----------|
| `（横切）关系操作` | `references/relation_guide.md` | 全部 26 种关系类型 + 开放标签规则 | 建边前必查：结构类/叙事类/角色势力事件类 + 自反vs配对决定 bidirectional 行为 |

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

### 焦点启动（主 agent 负责）

主 agent（planner / writer / crafter）在调用 `task(subagent_type="novel-v2-crafter", load_skills=["novel-v2"])` 时，在 prompt 中注入以下 V2 上下文：

```
CURRENT PROJECT: {项目名}
PROJECT PATH: {NOVELS_ROOT/项目名}
FOCUS TYPE: scene | character_arc | plot_thread | world_rule | note | chunk | outline | arc_plan | volume_plan | chapter_plan | structure(废弃兼容) | narrative_voice | thematic_motif
SUBTYPE: {章节类型}  # 各类型对应的子类型值
FOCUS ID: {叙事单元ID}
FOCUS NAME: {叙事单元名称}
PREHEAT LEVEL: cold | warm | hot
CYCLE TYPE: ideation | expansion | refinement | proofing | planning  # 活跃会话的循环类型（可空）
SESSION ID: {session_id}  # 活跃会话 ID（可空）。已注入则 crafter 不得重复 session.start（会话归主 agent 自持）
```

---

## V2 操作指南（Tool 的唯一源头）

所有 V2 操作通过 `novel-tool` tool 执行。以下命令列表是唯一权威参考。

### 1. 读取 graph 数据

```
# 按名称查找叙事单元 ID
novel-tool(operation="graph.find_unit", project="{PROJECT}", name="{名称}")

# 获取叙事单元详情
novel-tool(operation="graph.get_unit", project="{PROJECT}", id="{单元ID}")

# 查询单元的关联关系（1-hop 邻居，可按关系类型过滤）
novel-tool(operation="graph.get_neighbors", project="{PROJECT}", id="{单元ID}")
novel-tool(operation="graph.get_neighbors", project="{PROJECT}", id="{单元ID}", rel_type="contains")
novel-tool(operation="graph.get_neighbors", project="{PROJECT}", id="{单元ID}", rel_type="member_of")

# 列出所有可用关系类型
novel-tool(operation="graph.list_relation_types")

# 按类型列出叙事单元（SCENE / CHARACTER_ARC / PLOT_THREAD / WORLD_RULE / NOTE / CHUNK / OUTLINE / ARC_PLAN / VOLUME_PLAN / CHAPTER_PLAN / NARRATIVE_VOICE，支持 limit 参数）
novel-tool(operation="graph.list_units", project="{PROJECT}", unit_type="SCENE")
novel-tool(operation="graph.list_units", project="{PROJECT}", unit_type="WORLD_RULE", limit=10)

# 项目统计
novel-tool(operation="graph.stats", project="{PROJECT}")

# 最近事件
novel-tool(operation="graph.recent_events", project="{PROJECT}")

# 查询单元间的具体关系（比 get_neighbors 更精确——按类型和方向过滤）
novel-tool(operation="graph.get_relations", project="{PROJECT}", id="{单元ID}")
novel-tool(operation="graph.get_relations", project="{PROJECT}", id="{单元ID}", rel_type="contains", direction="outgoing")

# 层级结构遍历：子单元
novel-tool(operation="graph.find_descendants", project="{PROJECT}", id="{单元ID}") [max_depth=5]

# 层级结构遍历：父单元
novel-tool(operation="graph.find_ancestors", project="{PROJECT}", id="{单元ID}")

# 可视化（Web 交互式）
启动 Web 服务后打开浏览器查看交互式关系图：
```bash
novel-tool(operation="web.start", project="{PROJECT}")
# 打开 http://localhost:8766
```

### 2. 写入 graph 数据

**会话归因**：prompt 注入了 `SESSION ID`（活跃会话中）时，所有写操作（create_unit/update_unit/add_relation）必须携带 `session_id="{SESSION_ID}"`，确保事件溯源归因到会话（供遥测/偏差分析）。会话由主 agent 自持（规划=planning / 写作=expansion），执行者不 `session.start`/`session.end`。

```
# 创建叙事单元
novel-tool(operation="graph.create_unit", project="{PROJECT}", unit_type="SCENE", name="{单元名}", content="{内容}", tags="标签1,标签2", chapter=3, session_id="{SESSION_ID}")

# 更新叙事单元（内容 / 名称 / 标签）
novel-tool(operation="graph.update_unit", project="{PROJECT}", id="{单元ID}", content="{新内容JSON}")
novel-tool(operation="graph.update_unit", project="{PROJECT}", id="{单元ID}", name="新名称", tags="新标签")

# ── 建立关系（关系走 edge，content 只存可读名称） ──
# 场景 → 情节线：场景实现了哪条情节线
novel-tool(operation="graph.add_relation", project="{PROJECT}", source="{场景ID}", target="{情节线ID}", rel_type="implements")
# 章纲 → 场景：章纲规划哪些场景（规划意图，非结构归属）
novel-tool(operation="graph.add_relation", project="{PROJECT}", source="{章纲ID}", target="{场景ID}", rel_type="plans")
# 角色 → 场景：角色参与哪些场景
novel-tool(operation="graph.add_relation", project="{PROJECT}", source="{角色ID}", target="{场景ID}", rel_type="participates_in")
# 成员/位置/同盟（bidirectional=true 自动补反向）
novel-tool(operation="graph.add_relation", project="{PROJECT}", source="{源ID}", target="{目标ID}", rel_type="member_of")
novel-tool(operation="graph.add_relation", project="{PROJECT}", source="{源ID}", target="{目标ID}", rel_type="located_at")
# 角色通用关系（师徒/同盟等具体语义放 label；26 种类型速查见 references/relation_guide.md）
novel-tool(operation="graph.add_relation", project="{PROJECT}", source="{源ID}", target="{目标ID}", rel_type="relates_to", label="同盟", bidirectional=true)

# 补齐反向边
novel-tool(operation="graph.fix_asymmetry", project="{PROJECT}")

# 批量推断关系（新项目迁移后必做）
novel-tool(operation="graph.batch_infer", project="{PROJECT}")

# ── 删除关系 ──
novel-tool(operation="graph.remove_relation", project="{PROJECT}", id="{关系ID}")
novel-tool(operation="graph.remove_relation", project="{PROJECT}", source="{源ID}", target="{目标ID}", rel_type="implements")

# ── 归档单元（软删除，单元移出活跃状态但保留数据） ──
novel-tool(operation="graph.archive_unit", project="{PROJECT}", id="{单元ID}")
```

### 3. 会话管理

**会话由主 agent 自持**：planner 自持 planning 会话，writer/crafter 自持 expansion 会话，analyzer 不开会话（只读诊断）。主 agent 调度 crafter 时通过 `SESSION ID` 注入活跃会话，执行者直接消费，不得重复 `session.start`。

```
# 查询当前会话状态（返回 preheat/cycle_type/session_id/updated_at/focus 等）
novel-tool(operation="session.info", project="{PROJECT}")

# 启动创作会话（主 agent 自持会话时使用，或 SESSION ID 为空时兜底）
novel-tool(operation="session.start", project="{PROJECT}", focus_type="SCENE", id="{单元ID}")

# 设置循环类型（主 agent 写后回写：规划=planning / 写作=expansion / 其他 refinement/proofing/ideation）
novel-tool(operation="session.set_cycle", project="{PROJECT}", cycle_type="expansion")

# 设置会话阶段（ASSESS/EXECUTE/REVIEW/SETTLE）
novel-tool(operation="session.set_phase", project="{PROJECT}", phase="EXECUTE")

# 构建工作空间上下文
novel-tool(operation="session.build_workspace", project="{PROJECT}", id="{焦点单元ID}", preheat_level="warm")

# 持久化 graph
novel-tool(operation="graph.flush", project="{PROJECT}")
```

### 4. 导出和迁移

```
# V1→V2 迁移
novel-tool(operation="graph.migrate", project="{PROJECT}", verify=true, report=true)

# 导出结构化文档（Markdown，输出到 graph/export/）
novel-tool(operation="graph.export_docs", project="{PROJECT}")

# 导出章节 TXT 文件
novel-tool(operation="graph.export_chunks", project="{PROJECT}")
```

### 4. 时间事件（TEMPORAL_EVENT）

时间事件是挂载到任意实体上的时间轴节点，可独立 CRUD、可关联地点/参与者/因果。

**创建事件并关联到角色/地点/物品**：
```
# 创建事件节点
novel-tool(operation="graph.create_unit", project="{PROJECT}", unit_type="temporal_event", name="结丹突破", content='{"event_type":"cultivation","ordinal":4500,"precision":"exact","time_label":"第三日黄昏","summary":"吕明理突破至结丹中期","details":{"old_realm":"结丹初期","new_realm":"结丹中期"}}')

→ 返回 event_id: te_abc123

# 关联到实体
novel-tool(operation="graph.add_relation", project="{PROJECT}", source="{角色ID}", target="te_abc123", rel_type="has_event")

# 关联到地点
novel-tool(operation="graph.add_relation", project="{PROJECT}", source="te_abc123", target="{地点ID}", rel_type="located_at")
```

**查询统一时间线（跨类型）**：
```
Workspace 构建后，entity_timeline 自动包含该实体的所有事件类型：
  scene_event（场景参与）
  cultivation（修炼/突破）
  plot_event（情节节点）
  chronicle（纪年事件）
  item_event（物品转移）
  
在 prompt 中显示为：
  实体时间线（N 个事件）
  #ordinal time_label 📍location  [event_type] summary
```

> 存量数据（CHARACTER_ARC 的 `events[]`、PLOT_THREAD 的 `key_events[]`、SCENE 的 `time_text`）自动提取到时间线，无需迁移。

### 5. content 字段参考

创建叙事单元时，content 字段遵循标准格式（详见 `references/writing/content字段参考.md`）。

字段名统一为英文（ASCII），中文展示走 schema 的 `description`。以下为速查：

**角色 (CHARACTER_ARC)**：
```json
{"subtype": "主角|重要配角|反派|关键配角|群像|功能性角色", "性格": {"核心特质": "..."}, "character_arc_detail": {"arc_start_state": "...", "arc_end_state": "..."}, "能力设定": {"修为": "...", "功法": "...", "阵营": "..."}, "events": [{"event": "...", "ordinal": 1000}]}
```

**场景 (SCENE)**：
```json
{"synopsis": "场景概要", "subtype": "开篇|推进|冲突|转折|展示|过渡|收束", "pov_character": "林渊", "location": "落云宗后山练剑坪", "time_text": "午后", "one_line_summary": "林渊第一次拔剑", "cast": [{"name": "林渊", "role_status": "登场"}], "related_plotlines": ["主线·剑道之争"]}
```

> `related_plotlines` 和 `cast` 存可读名称（非内部 ID），真实关系走 edge。详见 §2。

**情节线 (PLOT_THREAD)**：
```json
{"subtype": "主线|支线|暗线|感情线|成长线|世界观线", "core_conflict": "...", "key_events": [{"chapter_number": 10, "event": "..."}], "ending_design": "..."}
```

**世界观 (WORLD_RULE)**：
```json
{"sub_type": "世界观总览|规则|力量体系|势力|地点|历史|文化|经济体系|政治体系|社会阶层|纪年事件", "sub_type_detail": "大陆|宗门|家族|秘境", "description": "...", "event_location": "...", "event_volume": 1}
```

**笔记 (NOTE)**：
```json
{"subtype": "灵感|笔记", "note": "..."}
```

**总纲 (OUTLINE)**：
```json
{"title": "作品名", "genre": "类型", "mode": "沙漏|长链|螺旋|环状|多线交织", "ontology": "故事的本质", "aesthetic_promise": "美学承诺", "seven_facets": {"叙事起点": "...", "核心冲突": "...", "主题表达": "..."}, "notes": ""}
```

**部篇大纲 (ARC_PLAN)**：
```json
{"arc_number": 1, "naming_convention": "部|篇", "core_theme": "核心主题", "coverage": "第1-3卷", "arc_start_state": "...", "arc_end_state": "...", "mood_curve_overview": [], "cross_volume_foreshadowing": [], "notes": ""}
```

**卷大纲 (VOLUME_PLAN)**：
```json
{"volume_number": 1, "volume_title": "卷名称", "core_conflict": "核心矛盾", "volume_start_state": "...", "volume_end_state": "...", "emotional_tone": "压抑|紧张|明快|悲壮|悬疑|热血|沉稳|诙谐", "word_count_target": 0, "foreshadowing_list": [], "notes": ""}
```

**章纲 (CHAPTER_PLAN)**：
```json
{"chapter_number": 1, "chapter_title": "", "chapter_function": "开篇|推进|冲突|转折|展示|过渡|收束", "scene_sequence": [{"场景名": "场景1"}], "info_release_plan": [], "word_count_allocation": {}, "transition_note": "如何衔接上一章", "notes": ""}
```

---

## 质量检查（创作流程内嵌）

写完章节 / 创建角色 / 创建世界观规则后，顺手执行机械自检（轻量、嵌入式、可选，不打断创作流）：

```
# 章节写作后：机械 + 统计双层检查
novel-tool(operation="graph.quality_check", project="{PROJECT}", layers="mechanical,statistical")

# 角色创建后 / 世界观规则创建后：机械检查
novel-tool(operation="graph.quality_check", project="{PROJECT}", layers="mechanical")
```

**处理逻辑**：
- 如果有 `error` 级别问题：提示用户，但不阻塞
- 如果有 `warning` 级别问题：简要列出，建议用户关注
- 如果只有 `info` 或无问题：简单告知"质量检查通过"

**深度诊断**：设计原则、各场景校验关注点（R2/R3 等）、统计信号裁决提示词（R7/R10/R11/R12）见 `references/analysis/quality_methodology.md`。统计检测返回信号时，按该文档的裁决提示词判断。

---

## 核心原则（HARD CONSTRAINTS）

1. **graph 是真相源** — 所有创作数据优先写入 graph，投影到文件是次要的
2. **关系走 edge，content 存可读名称** — content 里不写内部 ID（`sc_xxx` / `pt_xxx` 等）。`related_plotlines` 和 `cast[].name` 存的是可读名称用于快速查阅，真实关系通过 `novel-tool(operation="graph.add_relation")` 写入 edge。
3. **按需查询，勿全量推送** — 使用 `novel-tool` 按需查询，不要一次性加载全部数据
4. **写后 flush** — 每次 task() 完成后执行 `novel-tool(operation="graph.flush")` 确保持久化
5. **记录 actor** — 所有 create/update 操作传入 `actor` 参数（如 `actor="novel-v2-crafter"`）
6. **不要手工编辑 graph/ 下的 JSONL 文件** — 通过 GraphStore API 操作
7. **通过 novel-tool 操作** — 所有数据读写通过 `novel-tool` tool 执行，不要直接调用 Python API 或编辑 JSONL 文件
