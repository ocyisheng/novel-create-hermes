---
name: "novel-checkpoint-service"
description: "检查点暂停决策引擎。查询 pause/continue 决策，支持项目级规则覆盖。触发词：检查点、暂停决策、干预等级、pause、checkpoint、intervention"
license: "MIT"
version: "2.0.0"
compatibility: "OpenCode"
tags: ["novel", "infrastructure", "checkpoint-service"]
---

# 检查点暂停决策引擎

## 操作方式

从项目根目录通过 `bash` 调用：

```bash
# 查询某个检查点的决策
python .opencode/skills/novel-checkpoint-service/scripts/checkpoint_service.py check <检查点名> <high|medium|low>

# 列出所有已注册检查点
python .opencode/skills/novel-checkpoint-service/scripts/checkpoint_service.py list

# 重载规则（修改规则后）
python .opencode/skills/novel-checkpoint-service/scripts/checkpoint_service.py reload

# 环境自检
python .opencode/skills/novel-checkpoint-service/scripts/checkpoint_service.py self-check
```

## 检查点列表

| 检查点 | 触发时机 | low | medium | high |
|--------|---------|-----|--------|------|
| `writing_after_outline` | 大纲完成（强制暂停，不可覆盖） | ⏸ pause | ⏸ pause | ⏸ pause |
| `ideation_after_concept` | 创意方向选定 | ▶ continue | ⏸ pause | ⏸ pause |
| `ideation_after_template` | 约束集 + 模板生成完成 | ▶ continue | ⏸ pause | ⏸ pause |
| `writing_after_character` | 角色创建完成 | ▶ continue | ▶ continue | ⏸ pause |
| `writing_after_worldview` | 世界观建设完成 | ▶ continue | ▶ continue | ⏸ pause |
| `writing_after_plot` | 情节线设计完成 | ▶ continue | ▶ continue | ⏸ pause |
| `writing_after_chapters` | 每章写作完成 | ▶ continue | ▶ continue | ⏸ pause |
| `quality_after_plot_check` | 情节逻辑检测 | ▶ continue | ▶ continue | ⏸ pause |
| `quality_after_character_check` | 角色一致性检测 | ▶ continue | ▶ continue | ⏸ pause |
| `quality_after_worldview_check` | 世界观漏洞检测 | ▶ continue | ▶ continue | ⏸ pause |
| `quality_after_pacing` | 节奏分析 | ▶ continue | ▶ continue | ⏸ pause |
| `quality_after_full_evaluation` | 完整质量评估 | ▶ continue | ⏸ pause | ⏸ pause |
| `quality_after_feedback` | 读者反馈 | ▶ continue | 🔧 auto_fix | ⏸ pause |
| `project_after_new` | 项目新建 | ▶ continue | ▶ continue | ⏸ pause |
| `project_after_import` | 项目导入 | ▶ continue | ▶ continue | ⏸ pause |

## 项目级覆盖

在项目 `config.yaml` 中加 `checkpoint_rules` 字段可覆盖默认决策。
**注意：`writing_after_outline` 为硬编码强制暂停，不可通过项目规则覆盖。**

## HARD CONSTRAINTS

1. 必须通过 `checkpoint_service.py` 查询，不自行判断
2. `writing_after_outline` 所有等级强制 pause（不可覆盖）

## 参考文件

- `references/rules_format.md` — 检查点规则文件格式说明
