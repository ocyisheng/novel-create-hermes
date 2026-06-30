## TASK
写项目 {项目名} 的第 {章节号} 章。

## CONTEXT
以下内容已包含本章所需全部信息，无需重复读取。

### 活跃风格
{活跃风格}

### 本章分纲
{本章分纲内容}

### 附近章分纲（含前章追踪摘要）
{附近章分纲}

### 前一章衔接
{前一章衔接}

### 出场角色档案
{出场角色档案}

### 出场节奏提醒
{出场节奏}

### 世界观相关实体
{世界观相关实体}

### 全局时间线
{时间线规划}

### 待处理伏笔
{伏笔状态}

### 相关支线状态
{支线状态}

### 已知问题
{已知问题}

## OUTPUT

**文件 1** — `chapters/第{章节号}章.txt`（UTF-8，纯正文）

**文件 2** — `chapters/.metas/第{章节号}章.txt`：

```
【本章摘要】
一句话摘要

【新伏笔】
伏笔描述

【回收伏笔】
已回收伏笔描述

【出场角色】
角色名1, 角色名2
```

> 以下上下文由编排层通过 extract_template.py 注入。如果出现未填充的 `{变量名}`，说明编排层未提供该数据，请自行 read 获取。不要自己调用 extract_template.py。

## HARD CONSTRAINTS

1. NO shortcut language — NEVER use "考虑到时间和复杂性", "采用简化方案"等措辞
2. NO scope reduction — Do NOT shrink the task scope
3. NO placeholder content — NEVER use "[待补充]" or similar
4. NO partial delivery — Output MUST be 100% complete
5. COMPLETENESS = SUCCESS — Incomplete output = FAILED task
6. 字数控制在分纲 `字数目标` 范围内（±20%）
7. 禁止重复前一章内容
8. 角色关系以完整档案为准 — 不得仅凭摘要脑补关系状态
9. 使用 `write` 一次性写入，写完前不反复修改
