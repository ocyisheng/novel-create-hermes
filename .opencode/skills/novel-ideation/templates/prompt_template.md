## TASK
为项目 {项目名} 生成创意构思方案。

## CONTEXT
### 项目类型
{项目类型}

### 已有实体
{已有实体概览}

### 已有创意方向
{已有创意方向}

## OUTPUT
按 ideation/ 目录模板输出：需求分析 → 约束集 → 创意简报 → 评估 → 最终方案

## YAML 格式约束

1. **缩进**：统一 2 空格，禁止使用 tab
2. **引号**：所有字符串值必须用双引号 `""` 包裹
3. **列表项**：`-` 比父级键多缩进 2 空格
> 以下上下文由编排层通过 extract_template.py 注入。如果出现未填充的 `{变量名}`，说明编排层未提供该数据，请自行 read 获取。不要自己调用 extract_template.py。

## HARD CONSTRAINTS

1. NO shortcut language — NEVER use "考虑到时间和复杂性", "采用简化方案"等措辞
2. NO scope reduction — Do NOT shrink the task scope
3. NO placeholder content — NEVER use "[待补充]" or similar
4. NO partial delivery — Output MUST be 100% complete
5. COMPLETENESS = SUCCESS — Incomplete output = FAILED task
6. 不要生成与已有实体冲突的创意
7. YAML文件由写后处理脚本统一维护，不需要手动校验
