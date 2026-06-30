---
name: "novel-edit"
description: "编辑已有内容：修改角色档案、世界观设定、大纲等 YAML 实体，或润色修订章节正文。通过 Task() 子 Agent 调用。触发词：改、修改、编辑、调整、润色、修订、把...改成、更新、改动"
---

# 编辑技能

## 定位

在已有内容上做精确修改。不是从零创建——不生成新实体、不写新章节。
通过 `Task(subagent_type="novel-crafter", load_skills=["novel-edit"])` 调用。
编排层负责在 Task() prompt 中注入：编辑目标、文件路径、修改说明、grill 输出（如有）。

### 编辑前判断：要不要改

每次修改前先判断目标段落的性质——不是所有"问题"都需要修复：

|类型|判断依据|编辑行动|
|------|---------|---------|
|**硬伤**|事实矛盾、逻辑断裂、格式错误|必须修复|
|**修正痕**|叙述者的自我纠正、记忆的不确定性、视角的有限性|**保留**，这是叙事深度来源|
|**起居注细节**|看起来"不推进情节"的生活细节|三级判断：发现级(可删)→设计级(谨慎)→发明级(保护)|
|**扁平化风险**|修改后角色变得更可预测、不再让读者意外|如是圆形人物→退步信号；如是扁平人物→正常|

**核心原则**：修正痕暴露了叙述者的存在（是深度），无意败笔暴露了作者的存在（是失误）。当修改导致角色"变乖"、情节"变顺"，反而可能是退步。

> 编辑需求模糊时，编排层会先走 `skill("novel-grill")` 澄清需求，然后将 grill 输出注入 Task() prompt 的 `{grill_编辑方案}` 变量。本技能不需要再自行问询用户。

## 工作流

### 第一步：判断编辑类型

看用户请求指向什么：

|信号|编辑类型|流程|
|------|---------|------|
|角色名/世界观名/大纲 → 修改描述|YAML 编辑|见第二步|
|章节号/第X章 → 润色/修订/修改描述|TXT 编辑|见第三步|

### 第二步：YAML 实体编辑

```
① read 目标实体 YAML 文件
② read 意图日志（如存在）：
 outline/追踪/intent/{实体key}.intent.yaml
③ 分析用户请求，确定要修改的字段和对应的变更操作
④ 构造变更集 JSON（格式见 references/change_set.md——读取后参考）
⑤ python .opencode/shared/apply_changes.py
 --file {实体路径}
 --changes '{变更集 JSON}'
⑥ 如果 apply_changes 成功：
 a. **后处理链**（chain: `entity-edit`）：
 python .opencode/shared/fix_yaml_indent.py "{实体路径}"
 python .opencode/shared/validate_entity_format.py --project-root {PROJECT_PATH}
 python .opencode/shared/validate_entity_consistency.py --project-root {PROJECT_PATH}
 python .opencode/shared/rebuild_project_index.py --project-root {PROJECT_PATH}
 b. 【可选】级联影响分析（建议对角色/世界观重大修改时运行）：
 python .opencode/shared/cascade_impact.py
 --project-root {PROJECT_PATH}
 --changed-file {实体相对路径}
 → 阅读输出 → 如果发现高置信度影响章节，询问是否检查
 c. 日志记录：
 python .opencode/shared/update_intent_log.py
 --project-root {PROJECT_PATH}
 --entity-path {实体相对路径}
 --user-request "{用户原始请求}"
 --change-set '{变更集 JSON}'
 --status pending
 d. 在回复中输出变更摘要（含 `diff` 或新旧值对照），供编排层呈现给用户确认方向
⑦ 如果 apply_changes 失败（路径不存在/值冲突）：
 - 阅读错误信息，修正变更集后重试
 - 或报告用户具体问题
```

> 不要用 `edit`/`write` 手工修正 YAML 缩进或格式——上面的后处理链中 `fix_yaml_indent.py` 会自动处理。

### 第三步：TXT 章节编辑

```
① read 目标章节文件
② read 分纲（outline/分纲/卷{卷号}/第{N}章.yaml）
③ 根据修改范围选择方式：
 ├─ 小范围精确修改（改几段话）
 │ → 直接用 edit 工具修改目标段落
 │ → 不全局重写，不碰无关段落
 └─ 大范围重写（节奏/风格调整）
 → 运行 python .opencode/shared/last_100.py ... 获取衔接
 → 用 edit 或 write 写入修改后文本
 → 检查衔接：确认前 100 字与上一章衔接正确
④ chapter_tracking.py 更新（如需）
```

### 第四步：返回结果（所有编辑通用）

编辑完成后，在回复中输出变更摘要，格式如下：

```
变更摘要：
 ✏️ {字段1}: {旧值} → {新值}
 ...
是否需要级联影响分析：{YAML 编辑建议运行 cascade_impact.py / TXT 编辑无需}
```

编排层收到结果后负责：
- 向用户展示摘要并确认方向
- 用户确认后 → 编排层运行 `update_intent_log.py --status confirmed_by_user`
- 用户要求回退 → 编排层从 `.bak` 恢复，运行 `update_intent_log.py --status rejected`

## 变更集格式（YAML 编辑）

变更集是 JSON 格式的操作列表，精确描述要修改的字段：

```json
{
 "changes": [
 {
 "op": "replace",
 "path": "完整档案.性格.核心特质",
 "old_value": "隐忍谨慎",
 "new_value": "杀伐果断"
 }
 ],
 "summary": "将核心特质从'隐忍谨慎'改为'杀伐果断'",
 "related_impacts": ["检查 目标与冲突 是否需要同步更新"]
}
```

### 操作类型速查

|操作|参数|场景|
|------|------|------|
|`replace`|path, old_value, new_value|修改已有字段的值|
|`add`|path, value|新增字段|
|`remove`|path|删除字段|
|`add_to_list`|path, value, position(可选)|向列表追加/插入|
|`remove_from_list`|path, index|从列表删除指定项|

path 使用点号分隔层级，如 `完整档案.性格.核心特质`。

## HARD CONSTRAINTS

1. **只改用户指定的内容** — 变更集只包含用户请求对应的修改，不附加"顺便优化"的修改
2. **不创建新实体** — 如果用户想创建新角色/章节，告诉编排层（P3/P8）
3. **不修改索引和元数据** — `_meta.*`、`索引信息.实体ID`、`索引信息.名称`、`project_index.yaml`、`outline/追踪/*.yaml` 等由脚本维护
4. **备份安全** — apply_changes.py 会自动创建 `.bak`，不要手动删除
5. **YAML 编辑优先使用变更集** — 不要直接 edit YAML 文件（变更集保证数据完整性）
6. **TXT 编辑优先使用 edit 工具** — 段落级精确修改，不要全局重写除非用户明确要求
7. YAML文件、验证修复使用 python .opencode/shared/fix_yaml_indent.py "{实体路径}"

## 参考文件

- `references/change_set.md` — 变更集格式详细规范
- `references/editing_principles.md` — 编辑原则（最小修改、风格保持、关联感知、可逆性）
- `references/common_patterns.md` — 常见编辑模式（YAML 字段替换/列表操作、TXT 段落替换/润色、跨文件联动）
