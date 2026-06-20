---
name: novel-chapter
description: 章节写作：根据分纲撰写具体章节正文。触发词：章节、写第、第X章、chapter、写作
version: "2.0.0"
compatibility: OpenCode
tags: ["novel", "chapter", "writing"]
---

# 章节写作技能

## 核心职责

按编排层传入的 CONTEXT 撰写章节正文。`{PROJECT_PATH}` 替换为 CONTEXT 中的 `PROJECT PATH` 值。

1. **分纲解析** → 理解情节点、角色、转折
2. **前章衔接** → 从同一场景/情绪状态自然延续（参考 `{前一章衔接}` 中的最后 100 字和悬念钩子）
3. **角色一致性** → 对话和行为符合完整档案设定，不得仅凭摘要脑补关系状态
4. **情节展开** → 按四段式结构展开情节点
5. **场景写作** → 用动作、感官细节、环境描写替代内心独白（Show, Not Tell）
6. **伏笔处理** → 检查 `{伏笔状态}`（含规划文件中的全局伏笔意图 + 追踪文件中的写后状态），回收到期伏笔，设置新伏笔；参考 `{时间线规划}` 确认当前在整体时间线中的位置
7. **悬念设置** → 在章节结尾自然设置悬念钩子
8. **文风优化** → 禁止重复句式、中英混杂、空洞内心独白

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
    --var 本章分纲内容 - --var 前章摘要 - --var 前一章衔接 - \
    --var 出场角色档案 - --var 世界观相关实体 - --var 伏笔状态 - \
    --var 时间线规划 - --var 支线状态 - --var 已知问题 - --var 活跃风格 - \
    < /tmp/context.json
```

**Step 3** — 将 extract_template.py 输出的完整 prompt 传给 Task()。

### 槽位清单

所有槽位由 chapter_context.py 一次性提供。以下为清单和文件来源参考：

| 槽位 | 内容 | 文件来源 |
|------|------|---------|
| 本章分纲 | `outline/分纲/卷{卷号}/第{N}章.yaml` | chapter_context.py |
| 前章摘要 | `outline/追踪/章节摘要.yaml` 中第{N-1}章的摘要 | chapter_context.py |
| 前一章衔接 | 最后 100 字 + 悬念钩子 | chapter_context.py 或 last_100.py |
| 出场角色档案 | 从分纲提取角色名 → 读完整档案 | chapter_context.py |
| 世界观相关实体 | 按分纲"世界观补充"字段 | chapter_context.py |
| 伏笔状态（规划+追踪） | `outline/伏笔规划.yaml`（规划设计） + `outline/追踪/伏笔.yaml`（追踪状态），合并加载 | chapter_context.py（load_foreshadowing 改造后） |
| 时间线规划 | `outline/时间线设计.yaml`（按时代分组的全局时间线设计） | chapter_context.py（load_timeline_plan 新增） |
| 相关支线 | 活跃支线当前节点 | chapter_context.py |
| 本章交汇状态 | `outline/情节线/主索引.yaml`（如存在） | chapter_context.py |
| 已知问题 | `novel-issues.md` 相关条目 | chapter_context.py |
| 活跃风格 | config.yaml `活跃风格` → 风格文件 | chapter_context.py |
| 叙事策略 | `outline/叙事策略.yaml`（P4.5 产物，含视角/手法/信息分配/展示讲述规则） | chapter_context.py |
| 技法指南 | `references/technique_guide.md`（视角/对话/自由间接引语/象征/冷热笔法） | 直接读取参考文件 |

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
