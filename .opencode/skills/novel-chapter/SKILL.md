---
name: novel-chapter
description: 章节写作：根据分纲撰写具体章节正文。触发词：章节、写第、第X章、chapter、写作
version: "2.0.0"
compatibility: OpenCode
tags: ["novel", "chapter", "writing"]
---

# 章节写作技能

## PROMPT_TEMPLATE

> 模板定义在 `templates/prompt_template.md`。编排层使用 `extract_template.py` 加载并填充变量。

## 核心职责

按编排层传入的 CONTEXT 撰写章节正文。`{PROJECT_PATH}` 替换为 CONTEXT 中的 `PROJECT PATH` 值。

1. **分纲解析** → 理解情节点、角色、转折
2. **前章衔接** → 从同一场景/情绪状态自然延续（参考 `{前一章衔接}` 中的最后 100 字和悬念钩子）
3. **角色一致性** → 对话和行为符合完整档案设定，不得仅凭摘要脑补关系状态
4. **情节展开** → 按四段式结构展开情节点
5. **场景写作** → 用动作、感官细节、环境描写替代内心独白（Show, Not Tell）
6. **伏笔处理** → 检查 `{伏笔状态}`，回收到期伏笔，设置新伏笔
7. **悬念设置** → 在章节结尾自然设置悬念钩子
8. **文风优化** → 禁止重复句式、中英混杂、空洞内心独白

## 上下文契约

编排层在调用前按以下清单加载，`extract_template.py` 填充到模板变量中。

| 槽位 | 内容 | 加载方式 |
|------|------|---------|
| 本章分纲 | `outline/分纲/卷{卷号}/第{N}章.yaml` | read 关键字段（场景、出场角色、冲突、转折、收尾） |
| 前章摘要 | 第{N-1}章分纲 `摘要.本章摘要` | read 字段值 |
| 前一章衔接 | 最后 100 字 + 悬念钩子 | `last_100.py` + 分纲.下章铺垫 |
| 出场角色档案 | 从分纲提取角色名 → 读完整档案 | project_index.yaml → read |
| 世界观相关实体 | 按分纲"世界观补充"字段 | read worldbuilding/ 对应文件 |
| 待处理伏笔 | `outline/追踪/伏笔.yaml` | read 筛选进行中/需回收 |
| 时间线上下文 | `outline/追踪/时间线.yaml` | read 筛选本章附近章节的事件（±5章），提供故事当前时间锚点 |
| 相关支线 | 活跃支线当前节点 | project_index.yaml → read 支线 YAML |
| 本章交汇状态 | `outline/情节线/主索引.yaml`（如存在）→ 多线交织总图中匹配本章的条目 | read 筛选。注明涉及哪些线、优先级、交汇内容 |
| 已知问题 | `novel-issues.md` 相关条目 | read 筛选注入 |
| 活跃风格 | config.yaml `活跃风格` → 风格文件 | read 全文件（≤30行） |

## 输出

- `chapters/第X章.txt` — 纯正文（UTF-8）
- `chapters/.metas/第X章.txt` — 元数据标记（保留不删，格式见 `templates/prompt_template.md` §OUTPUT）

## 维护

> 由编排层执行，子 Agent 无需调用。

```bash
python .opencode/shared/auto_update.py \
    --project-root {PROJECT_PATH} --chapter chapters/第X章.txt
```

一个脚本完成全部：伏笔追踪、时间线、角色统计、config 进度、章节摘要、项目索引重建。省略 `--chapter` 则自动扫描所有待处理章节。

## 写作效率

- 使用 `write` 一次性写入完整正文，不逐段写入后反复修改
- 仅在修复特定段落时使用 `edit`
- 先一次性写完，再整体审查修订

## 参考

- `references/writing_principles.md` — 核心写作原则
- `references/scene-guide.md` — 场景写作指南
- `references/foreshadowing.md` — 伏笔设计

## HARD CONSTRAINTS

> 约束已移入 `templates/prompt_template.md`。编排层通过 `extract_template.py` 加载模板时一并注入 LLM prompt。
