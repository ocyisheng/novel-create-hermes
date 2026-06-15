---
name: "novel-entity-editor"
description: "实体编辑器：精准修改大纲/角色/世界观/情节线等 YAML 实体。触发词：修改、调整、把...改成、改一下、编辑、更新、改动、变更"
license: "MIT"
version: "1.0.0"
compatibility: "OpenCode"
tags: ["novel", "entity", "editor", "modification"]
---

# 实体编辑器技能

## 核心职责

对已创建的 YAML 实体（大纲/角色/世界观/情节线/分纲等）进行**精准字段级修改**。

**与创建技能的关系**：创建技能负责"从零生成"，本技能负责"微调已有内容"。
不替代创建技能，不重新生成整个文件。

### 工作流

```
编排层传入 CONTEXT（项目路径 + 实体路径 + 修改请求）
  ↓
① 读取目标实体文件 → 获得当前完整 YAML
  ↓
② 用 extract_template.py 加载 prompt_template.md，
   注入 {当前实体内容}、{修改请求描述}、{实体类型} 等变量
  ↓
③ task(category="novel-write", load_skills=["novel-entity-editor"])
   → 子 Agent 执行编辑（AI 判断改什么 + 怎么改）
   ↓
④ 子 Agent 输出修改后的完整 YAML + 变更摘要
  ↓
⑤ 编排层用 edit 工具写回文件
  ↓
⑥ 后处理链（pipeline）：
   ┌─ python fix_yaml_indent.py       → YAML 格式修正
   ├─ python validate_entity_consistency.py → 一致性校验（角色状态/出场）
   └─ python rebuild_project_index.py → 索引更新
  ↓
⑦ 用 entity_diff.py 展示变更摘要给用户
```

## 上下文契约

编排层在调用前按以下清单准备上下文：

| 槽位 | 内容 | 加载方式 |
|------|------|---------|
| 实体类型 | 自动检测（character/worldbuilding/plot_thread/outline_synopsis/volume/chapter_outline） | `entity_schema.py detect --file {路径}` |
| 实体文件路径 | 目标文件的绝对路径 | 从用户请求解析 |
| 当前实体内容 | 目标文件的完整 YAML 内容 | `read` 全文件 |
| 修改请求描述 | 用户说的具体修改内容 | 用户原始输入 |
| 实体编辑指南 | 对应实体类型的编辑指南 | `references/{类型}_fields.md` |
| 项目名 | 当前项目名 | config.yaml |
| 项目路径 | 项目根目录 | novel-context.md |
| grill_编辑方案（可选） | 编辑前需求发现的用户确认结果 | `quality/grill/entity-editor_需求_*.yaml`（仅模糊请求触发） |

## 实体类型支持

| 实体类型 | schema 名称 | 文件路径模式 | 可编辑字段数 |
|---------|------------|-------------|-------------|
| 角色档案 | character | `characters/{角色名}.yaml` | ~50 |
| 世界观实体 | worldbuilding | `worldbuilding/{实体ID}.yaml` | ~32 |
| 情节线 | plot_thread | `outline/情节线/{主线|支线}.yaml` | ~24 |
| 总纲 | outline_synopsis | `outline/总纲.yaml` | ~25 |
| 分卷大纲 | volume | `outline/分卷/卷{N}_{名称}.yaml` | ~17 |
| 分纲 | chapter_outline | `outline/分纲/卷{卷号}/第{N}章.yaml` | ~32 |

> 完整字段列表见 `scripts/entity_schema.py`。

## 触发方式

编排层（novel-writer.md）按以下规则识别修改请求：

```
用户说"改一下/调整/修改/把...改成/编辑/更新/改动/变更"

  ├─ 涉及章节正文（.txt）→ 调度 novel-chapter-editor
  ├─ 涉及 YAML 实体（.yaml）→ 调度 novel-entity-editor
  │   ├─ 检测实体类型 → entity_schema.py detect --file {路径}
  │   └─ 传入 CONTEXT → task(category="novel-write", load_skills=["novel-entity-editor"])
  └─ 无法判断 → 询问用户"你是想改章节正文还是改设定文件？"
```

### 触发词示例

| 用户说 | 推断 | 调度 |
|--------|------|------|
| "把主角的性格改成更果断" | 修改角色档案 | novel-entity-editor |
| "第3卷中间加一个过渡事件" | 修改分卷大纲 | novel-entity-editor |
| "力量体系加一条心魔试炼的规则" | 修改世界观 | novel-entity-editor |
| "支线B的结局不要这么悲剧" | 修改情节线 | novel-entity-editor |
| "第5章的开头改一下，不要直接打斗" | 修改分纲 | novel-entity-editor |
| "故事的底层世界观调整一下" | 修改总纲 | novel-entity-editor |

## 脚本说明

| 脚本 | 功能 | 调用时机 |
|------|------|---------|
| `entity_schema.py` | 检测实体类型、列出可编辑字段 | 编辑前（检测类型）、编辑后（验证） |
| `entity_diff.py` | 比较编辑前后的 YAML 语义化 diff | 编辑后（展示变更摘要） |

## 写后处理

输出写入后执行以下脚本：

```bash
# 1. YAML 格式修正
python .opencode/shared/fix_yaml_indent.py "{实体文件路径}"

# 2. 实体一致性校验（仅角色和分纲变更时需要）
python .opencode/shared/validate_entity_consistency.py --project-root {PROJECT_PATH}

# 3. 项目索引重建
python .opencode/shared/rebuild_project_index.py --project-root {PROJECT_PATH}
```

## 参考文件

- `references/character_fields.md` — 角色档案编辑指南
- `references/outline_fields.md` — 大纲类实体编辑指南（总纲/分卷/情节线/分纲）
- `references/worldbuilding_fields.md` — 世界观实体编辑指南
- `scripts/entity_schema.py` — 实体类型 schema 定义（CLI 查询入口）
- `scripts/entity_diff.py` — YAML 语义化 diff 工具

## 与校验系统的关系

```
novel-entity-editor（编辑者）
  └─ 修改完成后 →
       └─ 编排层调用 validate_entity_consistency.py（脚本）→
            └─ 检出不一致 →
                 └─ novel-entity-validator（技能，如已注册）
                      └─ AI 判断：这是可接受的改变还是真正的逻辑漏洞？
```

编辑器的后处理链包含脚本级校验（`validate_entity_consistency.py`）。
只有当脚本检出不一致时，才升级到技能级 AI 判断（`novel-entity-validator`）。

## HARD CONSTRAINTS

1. **不重新生成** — 不调用创建技能（novel-outline/novel-entity）来"重做"实体
2. **字段级修改** — 只改用户指定的字段，其他字段原样保留
3. **不变路径** — 不修改文件名和目录结构（`opencode.json` 和 `novel-writer.md` 不受影响）
4. **不变审计** — 总是输出变更摘要（改了什么字段、before/after）
5. **后处理必须** — 修改后必须运行 YAML 格式化 + 校验 + 索引重建
6. **不做创建** — 用户说"新建一个角色"不在此技能范围内，走 novel-entity
