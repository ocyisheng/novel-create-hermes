## TASK
为项目 {项目名} 执行：{任务描述}

## CONTEXT
### 创意方案
{创意方案}

### 总纲
{总纲内容}

### 已有实体参考
{已有实体列表}

## OUTPUT
按对应模板创建实体文件。

## MUST DO
- 按 `assets/character.yaml` 或 `assets/worldview.yaml` 模板格式创建实体文件
- YAML 缩进统一 2 空格，字符串用双引号包裹

## HARD CONSTRAINTS

1. NO shortcut language — NEVER use "考虑到时间和复杂性", "采用简化方案"等措辞
2. NO scope reduction — Do NOT shrink the task scope
3. NO placeholder content — NEVER use "[待补充]" or similar
4. NO partial delivery — Output MUST be 100% complete
5. COMPLETENESS = SUCCESS — Incomplete output = FAILED task
6. YAML 缩进统一 2 空格，字符串用双引号包裹
7. 多段落文本使用 `|` literal block scalar
