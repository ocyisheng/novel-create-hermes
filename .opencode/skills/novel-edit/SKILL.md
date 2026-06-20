---
name: "novel-edit"
description: "编辑已有内容：修改角色档案、世界观设定、大纲等 YAML 实体，或润色修订章节正文。不依赖子 Agent，skill() 直接执行。触发词：改、修改、编辑、调整、润色、修订、把...改成、更新、改动"
---

# 编辑技能

## 定位

在已有内容上做精确修改。不是从零创建——不生成新实体、不写新章节。
通过 `skill("novel-edit")` 调用，指令注入主 Agent 上下文后直接执行。

## 工作流

### 第一步：判断编辑类型

看用户请求指向什么：

| 信号 | 编辑类型 | 流程 |
|------|---------|------|
| 角色名/世界观名/大纲 → 修改描述 | YAML 编辑 | 见第二步 |
| 章节号/第X章 → 润色/修订/修改描述 | TXT 编辑 | 见第三步 |

### 第二步：YAML 实体编辑

```
① read 目标实体 YAML 文件
② read 意图日志（如存在）：
     outline/追踪/intent/{实体key}.intent.yaml
③ 分析用户请求，确定要修改的字段和对应的变更操作
④ 构造变更集 JSON（格式见 references/change_set.md——读取后参考）
⑤ bash .opencode/shared/apply_changes.py
     --file {实体路径}
     --changes '{变更集 JSON}'
⑥ 如果 apply_changes 成功：
   a. 后处理链：
      bash python .opencode/shared/fix_yaml_indent.py "{实体路径}"
      bash python .opencode/shared/validate_entity_consistency.py --project-root {PROJECT_PATH}
      bash python .opencode/shared/rebuild_project_index.py --project-root {PROJECT_PATH}
   b. 日志记录：
      bash .opencode/shared/update_intent_log.py
        --project-root {PROJECT_PATH}
        --entity-path {实体相对路径}
        --user-request "{用户原始请求}"
        --change-set '{变更集 JSON}'
        --status pending
   c. 展示变更摘要给用户，询问方向确认
⑦ 如果 apply_changes 失败（路径不存在/值冲突）：
   - 阅读错误信息，修正变更集后重试
   - 或报告用户具体问题
```

### 第三步：TXT 章节编辑

```
① read 目标章节文件
② read 分纲（outline/分纲/卷{卷号}/第{N}章.yaml）
③ 根据修改范围选择方式：
   ├─ 小范围精确修改（改几段话）
   │  → 直接用 edit 工具修改目标段落
   │  → 不全局重写，不碰无关段落
   └─ 大范围重写（节奏/风格调整）
      → 运行 bash .opencode/shared/last_100.py ... 获取衔接
      → 用 edit 或 write 写入修改后文本
      → 检查衔接：确认前 100 字与上一章衔接正确
④ chapter_tracking.py 更新（如需）
```

### 第四步：方向确认（所有编辑通用）

编辑完成后，展示变更摘要并确认方向：

```
已按你的要求修改：
  ✏️ {字段1}: {旧值} → {新值}
  ...
这是你想要的方向吗？(是/继续调整/方向不对，回退)
```

- "是" → 调用 `update_intent_log.py --status confirmed_by_user`
- "继续调整" → 进入下一轮编辑
- "方向不对，回退" → 从 `.bak` 恢复，`update_intent_log.py --status rejected`

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

| 操作 | 参数 | 场景 |
|------|------|------|
| `replace` | path, old_value, new_value | 修改已有字段的值 |
| `add` | path, value | 新增字段 |
| `remove` | path | 删除字段 |
| `add_to_list` | path, value, position(可选) | 向列表追加/插入 |
| `remove_from_list` | path, index | 从列表删除指定项 |

path 使用点号分隔层级，如 `完整档案.性格.核心特质`。

## HARD CONSTRAINTS

1. **只改用户指定的内容** — 变更集只包含用户请求对应的修改，不附加"顺便优化"的修改
2. **不创建新实体** — 如果用户想创建新角色/章节，告诉编排层（P3/P8）
3. **不修改索引和元数据** — `_meta.*`、`索引信息.实体ID`、`索引信息.名称`、`project_index.yaml`、`outline/追踪/*.yaml` 等由脚本维护
4. **备份安全** — apply_changes.py 会自动创建 `.bak`，不要手动删除
5. **YAML 编辑优先使用变更集** — 不要直接 edit YAML 文件（变更集保证数据完整性）
6. **TXT 编辑优先使用 edit 工具** — 段落级精确修改，不要全局重写除非用户明确要求
7. YAML文件、验证修复使用 bash python .opencode/shared/fix_yaml_indent.py "{实体路径}"

## 参考文件

- `references/change_set.md` — 变更集格式详细规范
- `references/editing_principles.md` — 编辑原则（最小修改、风格保持、关联感知、可逆性）
- `references/common_patterns.md` — 常见编辑模式（YAML 字段替换/列表操作、TXT 段落替换/润色、跨文件联动）
