## TASK
为项目 {项目名} 执行：{任务描述}

## CONTEXT
{上下文内容}

## OUTPUT
{输出规格}

## YAML 格式约束

以下规则适用于所有输出的实体 YAML 文件（`outline/情节线/*.yaml`、`outline/分纲/*.yaml`）：

1. **缩进**：统一 2 空格，禁止使用 tab
2. **引号**：所有字符串值必须用双引号 `""` 包裹
3. **多段落文本**（标注 `|` 的字段）：使用 YAML literal block scalar，正文比字段名多缩进 2 空格，段落间空行保持同等缩进
4. **列表项**：`-` 比父级键多缩进 2 空格
5. **顶层键间空行**：`_meta:`、`索引信息:`、`摘要:`、`完整档案:` 之间保留空行分割

> 总纲（`outline.yaml`）和分卷（`volume.yaml`）为文档型模板，不参与三层索引，不强制要求规则 5。

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
