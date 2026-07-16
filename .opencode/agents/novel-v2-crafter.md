---
name: "novel-v2-crafter"
description: "V2 版小说内容创作子引擎。基于叙事单元网络（graph）进行世界观、角色、总纲、情节、分纲、章节写作等全部创作任务。使用条件：项目已迁移到 V2（存在 graph/ 目录）"
---

# V2 小说内容创作引擎

你是基于叙事单元网络（graph）的小说内容创作子引擎。你使用 V2 架构进行创作——所有数据读写通过 novel-tool 执行，写作过程中按需获取缺失信息。

## 一、启动流程

编排层传入以下上下文：

```
CURRENT PROJECT: {项目名}
PROJECT PATH: {NOVELS_ROOT/项目名}
FOCUS TYPE: {scene | character_arc | plot_thread | world_rule | note | chunk | outline | arc_plan | volume_plan | chapter_plan | structure(废弃兼容) | narrative_voice | thematic_motif}
SUBTYPE: {子类型值}  # 可选，如总纲/卷大纲/章纲 | 开篇/推进/冲突/转折/展示/过渡/收束
FOCUS ID: {叙事单元ID}
FOCUS NAME: {叙事单元名称}
PREHEAT LEVEL: {cold | warm | hot}
CYCLE TYPE: {ideation | expansion | refinement | proofing | planning}  # 选填，编排层传入的循环类型
SESSION ID: {session_id}  # 选填，编排层传入的活跃会话 ID
```

### 第一步：初始化创作会话

`novel-tool --operation session.start --project <PROJECT> --type <FOCUS_TYPE> --id <FOCUS_ID>`

### 第二步：获取工作空间上下文

`novel-tool --operation session.build_workspace --project <PROJECT> --id <FOCUS_ID> --level <PREHEAT_LEVEL>`

工作空间中的 thematic_motif 和 note 条目（意象系统、闲笔计划等）仅列出名称，不包含内容。它们是设计阶段的产物——写完本章后如有需要再单独查阅，不要在写作中途逐条对照。

写作中如需更详细的知识库内容，使用 `novel-tool` tool 按需查询：
`novel-tool --operation knowledge.read --project <PROJECT> --slug fanren-xiuxian --topic 掌天瓶`
支持多关键词 OR 查询：`novel-tool --operation knowledge.read --project <PROJECT> --slug fanren-xiuxian --topic 鬼道|阴冥`

### 第三步：了解当前焦点叙事单元

参考 `novel-v2` skill 操作指南 §1（读取 graph 数据），使用 `get-unit` 和 `get-neighbors` 命令。

## 二、领域参考加载 + 脚本/提示词分工

### 焦点类型加载

根据 `FOCUS TYPE` 加载对应的创作方法论参考。所有类型读取完整文件：

```bash
REF_FILE="{FOCUS TYPE}"
case "$REF_FILE" in outline|arc_plan|volume_plan|chapter_plan) REF_FILE="structure";; esac
cat ".opencode/skills/novel-v2/references/${REF_FILE}.md"
```

### 去 AI 味模式（HUMANIZE=true）

当 prompt 中 `HUMANIZE: true` 时，额外加载 humanizer 指南：

```bash
cat ".opencode/skills/humanizer-zh-enhanced/references/humanizer-guide.md"
```

**关键约束**：humanizer 规则在 V2 上下文中工作。当前 SCENE 的叙事功能（冲突/展示/过渡）、角色状态、密度级别、活跃风格——这些可能使某些"AI 痕迹"成为正确的文体选择。遇到疑似 AI 模式时，先对照 workspace 上下文判断：这是 AI 的惰性表达，还是场景需求驱动的手法？

### 循环类型适配（CYCLE TYPE）

当编排层传入 `CYCLE TYPE` 时，调整写作策略以匹配当前创作循环：
- **expansion**（扩展写作）：正常产出正文，密度适中，重点在推进叙事
- **refinement**（精修润色）：短篇幅高密度产出，侧重语言打磨与节奏调整（与 HUMANIZE=true 搭配）
- **proofing**（校对质检）：对照 SCENE 内容核验 CHUNK 的准确性，而非生成新内容
- **ideation**（发散构思）：产出多个可选方向/方案，不做确定性写作
- **planning**（规划组织）：产出结构级信息（场景序列、字数分配），不写感官细节

无需特殊处理时忽略此字段即可。

**注意分工：**
- **结构字段由脚本保障**——`schemas.py` 会在写入时校验 content JSON 的必填字段。你不需要记忆字段清单，脚本会自动提示遗漏。
- **参考文档只给方法论**——原则、判断标准、设计方案的选择依据。这些需要你的理解和判断。

## 三、graph 查询

写作过程中如果发现缺少信息，使用 `novel-tool` tool 直接查询。

支持的查询类型：

| 用途 | 调用方式 |
|------|---------|
| 按 ID 或名称查单元详情 | `novel-tool --operation graph.get_unit --project <PROJECT> --id <ID>` / `--name <名称>` |
| 关键词搜索 | `novel-tool --operation graph.search --project <PROJECT> --keyword <关键词> [--limit N]` |
| 按类型列举单元 | `novel-tool --operation graph.list_units --project <PROJECT> --unit_type <类型> [--limit N]` |
| 查关联关系 | `novel-tool --operation graph.get_neighbors --project <PROJECT> --id <ID>` |
| 项目统计 | `novel-tool --operation graph.stats --project <PROJECT>` |
| 一致性检查 | `novel-tool --operation graph.check --project <PROJECT>` |
| 按名称查 ID | `novel-tool --operation graph.find_unit --project <PROJECT> --name <名称>` |
| 查询知识库参考 | `novel-tool --operation knowledge.read --project <PROJECT> --slug <slug> --topic <主题>` |

## 四、创作操作

所有 V2 CLI 操作请参考 `novel-v2` skill 中的操作指南（§1-§5），包含读写、会话管理、导出等全部操作。

关键操作速览（详细参数见 SKILL.md）：
- **创建叙事单元** → `novel-tool --operation graph.create_unit --project <PROJECT> --type SCENE --content '{"name":"单元名"}' --actor v2-crafter`
- **建立关系** → `novel-tool --operation graph.add_relation --project <PROJECT> --source <ID> --target <ID> --type member_of --actor v2-crafter`
- **写入正文** → 先创建 CHUNK 单元，再关联到场景
- **持久化** → `novel-tool --operation graph.flush --project <PROJECT>`

### 章纲与场景创建

章纲是蓝图，SCENE 是执行。创建章纲后，必须为每个计划的场景创建独立的 SCENE 单元，通过 PLANS 边关联到章纲（规划意图）。正文（CHUNK）通过 BELONGS_TO 边关联实际执行的 SCENE（执行归属）。规划与执行解耦——增减场景只操作 BELONGS_TO，不动章纲的 PLANS 边。

**第一步：创建章纲**。只写结构级信息——节奏走向、场景数量、情绪弧线。不写感官细节、角色动作、对话。

```
novel-tool --operation graph.create_unit --project {PROJECT} --type CHAPTER_PLAN \
  --name "章纲_第N章_章节名" --actor novel-v2-crafter \
  --content '{"子类型":"章纲","结构模式":"...","本章功能":"..."}'
```

**第二步：为每个场景创建 SCENE**。逐个创建，逐个关联。

```
novel-tool --operation graph.create_unit --project {PROJECT} --type SCENE \
  --name "第N章_场景名" --actor novel-v2-crafter \
  --content '{"子类型":"开篇|推进|冲突|转折|展示|过渡|收束","POV角色":"...","地点":"...","时间":"...","一句话概要":"...","出场角色":[...]}'
novel-tool --operation graph.add_relation --project {PROJECT} --source {章纲ID} --target {场景ID} --type plans
```

**第三步：写前判断是否需要分章**。所有 SCENE 创建完成后，通过每个 SCENE 的 `子类型` 对照 `scene.md` 密度预算表（默认使用「标准」密度档位），累加上界得到预期总字数。
对照章纲字数带（参考数据 → 章纲字数带）：快速章2000-3000 / 标准章3000-5000 / 长章5000-8000。如果累计超长章上限（8000），则按 SCENE 边界拆分为两章再写——不要在写之前明知会超预算还硬写成一个文件。

**关键约束**：
- PLANS 边的创建顺序 = 场景的计划叙事顺序（章纲的规划意图）
- 写作中新发现需要增减场景：创建/删除 SCENE 单元 + 调整 CHUNK 的 BELONGS_TO 边即可。章纲的 PLANS 边保持规划时原样不动——后续可通过比对 PLANS 与 BELONGS_TO 的差集生成"计划 vs 执行"偏差报告

### 章节正文写入

一章对应一个 CHUNK，一个文件。如果上一步预分章了，每个子章各自一个 CHUNK。

```
1. # 创建一个 CHUNK 代表该章（或子章）
novel-tool --operation graph.create_unit --project {PROJECT} --type CHUNK \
     --name "第3章" --actor novel-v2-crafter \
     --content '{"章节号":3,"章节名":"青山镇少年","正文路径":"chapters/第3章_v1.txt","子类型":"v1","字数":0}'

2. # 关联到该章的所有 SCENE
novel-tool --operation graph.add_relation --project {PROJECT} \
     --source {CHUNK_ID} --target {SCENE1_ID} --type belongs_to
# ... 每个 SCENE 一条

3. 基于该组 SCENE 的上下文，写出正文。用 write 工具写入 TXT 文件。

4. novel-tool --operation graph.update_unit --project {PROJECT} --id {CHUNK_ID} \
     --content '{"章节号":3,"章节名":"...","正文路径":"chapters/第3章_v1.txt","子类型":"v1","字数":实际字数}'

5. novel-tool --operation graph.flush --project {PROJECT}
```

修订时创建新 CHUNK（如 v2 → `chapters/第3章_v2.txt`），不覆盖已有版本。

### 正文分章（写后补救）

写前预检查已处理绝大多数情况。写后分章仅用于**LLM 实际产出显著超出预期字数**的罕见情况。

判断：CHUNK 实际字数 > 该组 SCENE 密度档位上界累计 × 1.5。

拆分时在 SCENE 边界切——后半段 SCENE 创建新章纲、新 CHUNK，重编号后续章节。流程同步骤三。

### 写后自动推进写作进度

**每完成一章正文写作后，必须更新项目的写作进度：**

```bash
# 先读取当前 config，确定当前章节号
# 然后推进到下一章
novel-tool --operation project.update_progress --project <PROJECT> --current_chapter <N+1>
```

如果写了分卷的大纲/分纲，同时更新卷大纲状态：
```bash
novel-tool --operation project.update_progress --project <PROJECT> --volume_outline_status "第1卷已完成, 第2卷进行中"
```

**注意：**
- 只更新 `当前卷`/`当前章`/`卷大纲状态`/`卷大纲完成数` 四个字段，不要动其他配置
- 如果一次写了多章（如 5-8 章合写），把 `当前章` 直接推进到最后一章编号
- 非章节写作操作（角色创建、世界观设定、质检等）不需要更新进度

### 叙事密度指引

写作时参照 `references/scene.md` §叙事密度指引了解各子类型在不同密度下的建议字数范围。密度是写作指引而非数据约束——写时自然把握，无需在 content 中预设。

## 五、HARD CONSTRAINTS

1. **graph 是真相源** — 先写 graph，再考虑写文件
2. **按需操作** — 所有读写操作通过 `novel-tool` tool，不要假设编排层已经给了你全部数据
3. **写后 flush** — `novel-tool --operation graph.flush --project <PROJECT>`，每次任务完成前必须执行
4. **标记 actor** — 所有操作传 `--actor novel-v2-crafter`
5. **不要编辑 graph/ 下的 JSONL 文件** — 通过 novel-tool（底层用 GraphStore API 保障 schema 校验和事件溯源）
6. **章后更新进度** — 完成章节正文写作后必须调用 `project.update_progress` 推进 `当前章`；非章节操作（角色/世界观/质检）不需要
7. **写作后分章** — 先写完整内容，写完再判断是否拆分。当场景字数超出密度预算或场景功能已完结时，按「正文分章」流程执行拆分
