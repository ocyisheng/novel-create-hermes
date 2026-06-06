## TASK
为项目 {项目名} 执行：{任务描述}

## CONTEXT
{上下文内容}

## OUTPUT
{输出规格}

## MUST DO
- 总纲和分卷写入后确保文件存在
- YAML 写入规则：新文件用 `write`，已有文件用 `edit` 增量修改，覆盖前创建 `.bak` 备份

## HARD CONSTRAINTS

1. NO shortcut language — NEVER use "考虑到时间和复杂性", "采用简化方案"等措辞
2. NO scope reduction — Do NOT shrink the task scope
3. NO placeholder content — NEVER use "[待补充]" or similar
4. NO partial delivery — Output MUST be 100% complete
5. COMPLETENESS = SUCCESS — Incomplete output = FAILED task
6. 总纲和分卷写入后确保文件存在
7. YAML 写入规则：新文件用 `write`，已有文件用 `edit` 增量修改，覆盖前创建 `.bak` 备份
