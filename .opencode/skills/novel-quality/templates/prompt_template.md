## TASK
为项目 {项目名} 执行 {检测类型}。

> 以下上下文由编排层通过 extract_template.py 注入。如果出现未填充的 `{变量名}`，说明编排层未提供该数据，请自行 read 获取。不要自己调用 extract_template.py。

## CONTEXT
### 目标章节正文
{章节正文}

### 相关素材
{相关素材}

## OUTPUT
{输出规格}

## MUST DO
- 仅执行 {检测类型}，不跨检测类型
- 先读 SKILL.md 正文中对应检测维度的详细指引
- 输出 YAML 格式报告到指定路径

## HARD CONSTRAINTS

1. NO shortcut language — NEVER use "考虑到时间和复杂性", "采用简化方案"等措辞
2. NO scope reduction — Do NOT shrink the task scope
3. NO placeholder content — NEVER use "[待补充]" or similar
4. NO partial delivery — Output MUST be 100% complete
5. COMPLETENESS = SUCCESS — Incomplete output = FAILED task
6. 先检测再修复，不跳过检测直接修改
7. 仅提供修正建议，不直接修改原文（修复由 novel-chapter-editor 处理）
8. 问题按严重程度（致命/重要/轻微）分级
