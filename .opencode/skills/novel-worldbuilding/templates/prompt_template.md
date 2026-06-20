## TASK
为项目 {项目名} 创建世界观设定：{任务描述}

## CONTEXT
### 创意方案
{创意方案}

### 总纲
{总纲内容}

### 已有实体参考
{已有实体列表}

## OUTPUT
按 `assets/worldview.yaml` 模板创建世界观实体文件，写入 `worldbuilding/{文件名}.yaml`。

## YAML 格式约束

1. **缩进**：统一 2 空格，禁止使用 tab
2. **引号**：所有字符串值必须用双引号 `""` 包裹
3. **多段落文本**：使用 YAML literal block scalar（`|`），正文比字段名多缩进 2 空格，段落间空行保持同等缩进
4. **列表项**：`-` 比父级键多缩进 2 空格
5. **顶层键间空行**：`_meta:`、`索引信息:`、`摘要:`、`完整档案:` 之间保留空行分割

## HARD CONSTRAINTS

1. NO shortcut language — NEVER use "考虑到时间和复杂性", "采用简化方案"等措辞
2. NO scope reduction — Do NOT shrink the task scope
3. NO placeholder content — NEVER use "[待补充]" or similar
4. NO partial delivery — Output MUST be 100% complete
5. COMPLETENESS = SUCCESS — Incomplete output = FAILED task
6. YAML文件由写后处理脚本统一维护，不需要手动校验

> 以下上下文由编排层通过 extract_template.py 注入。如果出现未填充的 `{变量名}`，说明编排层未提供该数据，请自行 read 获取。不要自己调用 extract_template.py。
