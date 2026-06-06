# 导入迁移指南

本文档定义旧项目导入到标准目录结构的完整迁移流程。

---

## 概述

`novel-project-manager` 的 `import` 子命令执行两阶段迁移：

1. **脚本阶段**（`init.py`）：机械搬运 + 粗分类 → 生成 `migration_report.yaml`
2. **Agent 阶段**（技能调度）：内容理解 + 精细分类 + 格式转换 → 完成迁移

---

## 阶段一：脚本自动分类

### 文件识别规则

脚本通过两层判断识别文件类型：

#### 层1：基于文件名关键词（快速猜测）

| 关键词 | 猜测类型 | 目标目录 |
|--------|---------|---------|
| 角色、character、人物、档案 | `likely_character` | `characters/` |
| 大纲、outline、总纲、分纲、情节、伏笔、时间线 | `likely_outline` | `outline/` |
| 世界观、world、设定、规则、力量体系、势力、地理、历史、文化 | `likely_worldbuilding` | `worldbuilding/` |
| 章节、chapter、正文、场景 | `likely_chapter` | `chapters/` |
| `.txt` 扩展名 | 自动归类 | `chapters/` |

#### 层2：基于 YAML 顶层 key（内容识别）

脚本读取 YAML 文件的顶层 key，匹配特征集：

| 特征 key | 识别类型 |
|---------|---------|
| `大纲`, `三幕结构`, `故事结构`, `核心概念`, `结构` | `outline` |
| `角色`, `姓名`, `年龄`, `性格`, `外貌`, `背景故事` | `character` |
| `世界名称`, `力量体系`, `势力格局`, `核心规则`, `地理位置` | `worldbuilding` |
| `章节号`, `正文`, `场景`, `情节点` | `chapter_outline` |

### 大纲版本检测

对识别为 outline 的文件，脚本判断旧大纲格式：

| 检测条件 | 判断结果 | 处理方式 |
|---------|---------|---------|
| `大纲.版本` 存在且为固定 6 文件结构 | 标准格式 | 无需迁移，仅校验 |
| `大纲.模块` 存在索引 | 旧索引格式 | 加载各模块后重新分发到标准 6 文件 |
| 顶层 key > 5 个，无 `大纲` 根 key | 单文件大 YAML | 按关键词映射拆分到标准 6 文件 |

### migration_report.yaml 结构

```yaml
migration_report:
  source_path: "C:/旧项目路径"
  imported_at: "2026-05-19 14:30"
  status: "pending_agent_review"
  auto_classified:
    - path: "_migration_staging/角色-林默.yaml"
      name_guess: "likely_character"
      content_type: "character"
      final_classification: "character"
      needs_review: false
  needs_agent_review:
    - path: "_migration_staging/笔记.yaml"
      name_guess: "unknown"
      content_type: "unknown"
      final_classification: "unknown"
      needs_review: true
  outline_files:
    - path: "_migration_staging/旧大纲.yaml"
      name_guess: "likely_outline"
      content_type: "outline"
      final_classification: "outline"
      outline_version: "single_file"
      needs_review: false
  summary:
    total_files: 15
    auto_classified_count: 10
    needs_review_count: 5
```

---

## 阶段二：Agent 迁移流程

### 步骤 1：读取迁移报告

```
读取 migration_report.yaml
→ 获取 auto_classified 列表（需验证）
→ 获取 needs_agent_review 列表（需分类）
→ 获取 outline_files 列表（需格式迁移）
```

### 步骤 2：验证自动分类

对 `auto_classified` 中的每个文件：
- 读取文件内容
- 确认脚本分类是否正确
- 如错误，移动到正确目录

### 步骤 3：分类未知文件

对 `needs_agent_review` 中的每个文件：
- 读取文件内容，理解语义
- 判断归属：
  - 角色档案 → `characters/{角色名}.yaml`
  - 世界观 → `worldbuilding/{对应文件}.yaml`
  - 章节正文 → `chapters/chapter_{序号}.txt`
  - 其他 → 根据内容决定或标记删除

### 步骤 4：大纲格式迁移

对 `outline_files` 中非标准格式的文件（单文件大 YAML / 索引格式）：
- 调用 `novel-writing-outline` 技能的旧大纲迁移流程
- 按内容分类映射拆分到 6 个固定文件
- 处理 $ref 规范化

### 步骤 5：构建项目索引

运行 rebuild_project_index.py --project-root {项目路径} 构建项目索引

### 步骤 6：清理暂存区

```bash
# 确认所有文件已处理后，删除暂存区
rm -rf {project}/_migration_staging/
```

### 步骤 7：更新迁移状态

```yaml
# 更新 migration_report.yaml
migration_report:
  status: "completed"
```

---

## 内容分类映射表（大纲迁移用）

| 源内容关键词 | 目标文件 |
|-------------|---------|
| 基本信息、核心概念、故事结构（幕列表）、分卷、结局、节奏 | `outline/总纲.yaml`（旧格式 `故事结构.yaml` → `总纲.yaml`） |
| 主线、支线、事件链条、单元案件、案件设计 | `outline/情节线/主线.yaml`（旧格式 `情节线.yaml` → 拆分） |
| 伏笔管理、伏笔、悬念、铺垫 | `outline/追踪/伏笔.yaml` |
| 时间线、时间、事件 | `outline/时间线.yaml` |
| 角色出场、角色统计 | `characters/角色统计.yaml` |

---

## 错误处理

| 场景 | 处理方式 |
|------|---------|
| 文件无法识别 | 保留在暂存区，标记为 `manual_review` |
| 大纲格式完全非标 | Agent 理解内容后手动迁移 |
| $ref 循环引用 | 报错并记录到迁移报告 |
| 文件编码非 UTF-8 | 尝试转换，失败则保留原编码并标记 |

---

## 迁移完成检查清单

- [ ] `_migration_staging/` 已清空
- [ ] `migration_report.yaml` 状态为 `completed`
- [ ] `outline/` 下必需文件均已存在（总纲、情节线、分纲、追踪）
- [ ] `characters/` 下角色档案格式标准（含 角色统计.yaml）
- [ ] `worldbuilding/` 下 7 个文件均已存在
- [ ] `chapters/` 下章节文件按 `chapter_XX.txt` 命名
- [ ] 所有 `$ref` 引用路径有效
