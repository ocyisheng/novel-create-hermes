## TASK

为项目 {项目名} 执行章节编辑：{修改指令}

编辑模式：{编辑模式}

## CONTEXT

### 章节正文

{章节正文}

### 本章分纲

{本章分纲}

### 出场角色档案

{出场角色档案}

### 前章衔接

{前章衔接}

### 活跃风格

{活跃风格}

## OUTPUT

编辑后的 `chapters/第{章节号}章.txt`，用 `edit` 工具写入。

## MUST DO

- 文笔优化：保持原意不变，只提升表达
- 反馈修订：只修复反馈指出的问题
- 内容修改：精确执行修改指令，不波及无关段落
- 修改后重新确认与前后章的衔接

> 以下上下文由编排层通过 extract_template.py 注入。如果出现未填充的 `{变量名}`，说明编排层未提供该数据，请自行 read 获取。不要自己调用 extract_template.py。

## HARD CONSTRAINTS

1. NO shortcut language
2. NO scope reduction
3. NO placeholder content
4. 角色行为须符合档案设定
5. 修改后运行衔接检查
