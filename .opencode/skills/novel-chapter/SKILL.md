---
name: novel-chapter
description: 章节写作：根据分纲撰写具体章节正文。触发词：章节、写第、第X章、chapter、写作
version: "2.0.0"
compatibility: OpenCode
tags: ["novel", "chapter", "writing"]
---

# 章节写作技能

## 核心职责

按编排层传入的 CONTEXT 撰写章节正文。以下10个步骤融入了理论技法。

### 步骤一：解析分纲与动作书写

使用 `{场域规划}` 的结构化场景蓝图（POV/感官锚点/节奏/进入退出），非扁平情节点。动作书写只保留影像无法掠夺的意义——以"把/用/将"等助动词支撑连续动作（施耐庵法），或以音韵节奏辅助动作（吴承恩法），或以升格仿讽形成张力。

### 步骤二：前章衔接

从同一场景/情绪自然延续（参考 `{前一章衔接}` 最后100字）。审视衔接段中有没有一件"只是生活细节"的事让读者停留——曹雪芹的发明在于让无意义的日常与内心暗合。

### 步骤三：角色一致性

对话和行为符合完整档案，参考 `{出场角色档案}` 和 `{出场节奏}`。注意：角色可能产生"自动性"——如果角色开始做你没想到的事，不要强行压回轨道，区分"角色成长"（文势所逼）与"性格突变"（粗暴干预）。

### 步骤四：张力控制

严格遵循 `{张力曲线}` 量化节奏指标。张力升降不是外力强加的节奏表——真正的速度感是角色意志碰撞的自然结果，渗透到角色内部和意义内部。

### 步骤五：场景写作

按 `{场域规划}` 使用指定POV、感官锚点、进入/退出方式。细节是调整节奏的枢纽——越进入细节，时钟越趋近静止。不要过度经营细节的意义。POV自由切换但需让读者信以为真。

### 步骤六：对话

参考 `{对话规划}` 的节拍/声线/潜台词。注意角色声线差异以及叙述者腔调与角色对话之间的张力——腔调决定意义。

### 步骤七：伏笔处理

检查 `{伏笔状态}`，回收/设置伏笔。伏笔不必全部"兑现"——落空、误解、悬置都是现代叙事的深度来源。

### 步骤八：悬念设置

在章尾自然设置悬念钩子。钩子不限于因果驱动——可以是一个意象/词语的回落。

### 步骤九：风格一致性

严格遵循 `{活跃风格}` 的7维度约束。7维度是腔调谱系的结构化表达——写作时要意识到自己"踩在谁的影子上"。

### 步骤十：文风优化

逐句检查语言尸体——这个描述是真切的观察还是通行修辞模板？"暮色从四面八方袭来"是尸体，"光线从窗帘边缘挤进来"可能是观察。描述程序即观察程序。

## 上下文契约

编排层在调用前按以下流程加载上下文，`extract_template.py` 填充到模板变量中。

### 上下文加载流程（强制性）

编排层在 Task() 前必须执行以下脚本：

**Step 1** — 使用 `chapter_context.py` 一次性收集全部上下文：

```bash
python .opencode/shared/chapter_context.py \
 --project-root {PROJECT_PATH} --chapter {章节号} --output /tmp/context.json
```

**Step 2** — 用 `extract_template.py` 填充 prompt 模板：

```bash
python .opencode/shared/extract_template.py \
 --skill novel-chapter \
  --var 项目名 "{项目名}" --var 章节号 "{章节号}" \
  --var 本章分纲内容 - --var 前一章衔接 - \
  --var 出场角色档案 - --var 世界观相关实体 - --var 伏笔状态 - \
  --var 时间线规划 - --var 支线状态 - --var 已知问题 - --var 活跃风格 - \
  --var 叙事策略 - --var 出场节奏 - --var 场域规划 - --var 张力曲线 - --var 对话规划 - \
  --var 附近章分纲 - \
  < /tmp/context.json
```

**Step 3** — 将 extract_template.py 输出的完整 prompt 传给 Task()。

### 槽位清单

所有槽位由 chapter_context.py 一次性提供。以下为清单和文件来源参考：

|槽位|内容|文件来源|
|------|------|---------|
|本章分纲|`outline/分纲/卷{卷号}/第{N}章.yaml`|chapter_context.py|
|附近章分纲|第 N-1 章：`outline/追踪/章节摘要.yaml`（写后记录）; 其他章：`outline/分纲/卷*/*.yaml` Layer 2 摘要|chapter_context.py（load_nearby_outlines 合并 load_previous_summary）|
|前一章衔接|最后 100 字 + 悬念钩子|chapter_context.py 或 last_100.py|
|出场角色档案|从分纲提取角色名 → 读完整档案|chapter_context.py|
|世界观相关实体|按分纲"世界观补充"字段|chapter_context.py|
|伏笔状态（规划+追踪）|`outline/伏笔规划.yaml`（规划设计） + `outline/追踪/伏笔.yaml`（追踪状态），合并加载|chapter_context.py|
|时间线规划|`outline/时间线设计.yaml`（按时代分组的全局时间线设计）|chapter_context.py|
|相关支线|活跃支线当前节点|chapter_context.py|
|本章交汇状态|`outline/情节线/主索引.yaml`（如存在）|chapter_context.py|
|已知问题|`novel-issues.md` 相关条目|chapter_context.py|
|活跃风格|config.yaml `活跃风格` → 风格文件|chapter_context.py|
|叙事策略|`outline/叙事策略.yaml`（P4.5 产物）|chapter_context.py|
|出场节奏|从情节线 `完整档案.角色参与.出场节奏` 聚合：本章应出场/不应出场的角色提醒|chapter_context.py（load_appearance_rhythm 新增）|
|场域规划|从分纲 `完整档案.场域规划` 提取（含 POV/氛围/节奏/感官锚点）|chapter_context.py（load_scene_beat_plan 新增）|
|张力曲线|从分纲 `完整档案.张力曲线` 提取（量化 1-10 节奏指标）|chapter_context.py（load_tension_curve 新增）|
|对话规划|从分纲 `完整档案.对话规划` 提取（可选，对话节拍/声线/潜台词）|chapter_context.py（load_dialogue_plan 新增）|
|上下文完整性|综合评分 + 缺口列表|chapter_context.py（assess_context_completeness 新增）|

## 输出

- `chapters/第X章.txt` — 纯正文（UTF-8）
- `chapters/.metas/第X章.txt` — 元数据标记（保留不删，格式见 `templates/prompt_template.md` §OUTPUT）

## 写后处理

输出写入后执行以下脚本：

```bash
# 追踪数据 — 增量更新伏笔/时间线/角色统计/情节线进度/章节摘要
python .opencode/shared/chapter_tracking.py \
 --project-root {PROJECT_PATH} --chapter chapters/第X章.txt

# 创作进度 — 更新当前章节号和最后编辑时间
python .opencode/shared/config_manager.py set 创作进度.当前章节 {N} --project-root {PROJECT_PATH}
python .opencode/shared/config_manager.py set 最后编辑 "{now}" --project-root {PROJECT_PATH}
```

> 项目索引不在此维护；字数通过 word_count.py 按需查询。

## 写作效率

- 使用 `write` 一次性写入完整正文，不逐段写入后反复修改
- 仅在修复特定段落时使用 `edit`
- 先一次性写完，再整体审查修订

## 参考

- `references/writing_principles.md` — 核心写作原则
- `references/scene-guide.md` — 场景写作指南
- `references/foreshadowing.md` — 伏笔设计
- `references/technique_guide.md` — 写作技法指南（视角/对话/自由间接引语/象征/冷热笔法）
