# 搜索策略参考

## 关键词搜索策略

### 基础关键词匹配
- 精确匹配：搜索完整关键词（如"天道宗"）
- 模糊匹配：对中文字词自动支持子串匹配
- 大小写：默认不区分，可配置

### 文件类型感知
- **`graph/` 目录**（V2 数据）：通过 GraphStore API 检索，按单元类型筛选
- **`graph/nodes.jsonl`**：搜索 `unit_name` 和 `content` 字段
- **`config.yaml`**：搜索项目配置字段

### 排序策略
搜索结果按以下优先级排序：
1. `CHUNK` 优先——章节正文最常被搜索
2. 按 `belongs_to_chapter` 升序——按章节顺序排列
3. 同一类型内按 `unit_name` 字典序

### 中文搜索注意事项
- Python 的 `in` 操作符对中文子串搜索已经足够（如"天" in "天道宗" → True）
- 不需要分词，中文关键词直接按字符子串匹配
- YAML 文件中的注释行（`#` 开头）应包含在搜索范围内

## 实体引用分析策略

### 实体类型识别
- **角色**：`v2_cli.py list-units --type CHARACTER_ARC`
- **世界观规则**：`v2_cli.py list-units --type WORLD_RULE`
- **情节线**：`v2_cli.py list-units --type PLOT_THREAD`
- **场景**：`v2_cli.py list-units --type SCENE`

### 引用链构建
1. **通过 `get-neighbors` 获取实体的关系网络**
2. **按关系类型区分引用上下文**：
   - `PARTICIPATES_IN` → "参演"
   - `IMPLEMENTS` → "计划出场"
   - `REFERENCES` → "关联引用"
   - `BELONGS_TO` → "从属"
3. **统计引用频率**：按关联类型统计

### 实体状态推断
- 首次出场章节：引用链中最早的章节
- 最近出场章节：引用链中最晚的章节
- 活跃状态：最近 5 章内有过出场

## 搜索模式与参数组合

| 用户意图 | mode | keyword | scope | 说明 |
|---------|------|---------|-------|------|
| "找一下所有提到天道宗的地方" | search | 天道宗 | all | 全范围搜索 |
| "查查第5章写了什么" | search | — | chapters | 关键词为空时返回章节概览 |
| "林昭在第3章说了什么" | entity-search | 林昭 | chapters | 指定实体+范围 |
| "有哪些角色还没出场" | gap | — | — | 角色使用率分析 |
| "检查设定有没有冲突" | cross-ref | — | — | 交叉引用检测 |

## 搜索性能优化

- 对小项目（<100 叙事单元）：GraphStore 全量扫描，无性能顾虑
- 对中等项目（100-500 单元）：按 `type` 缩小范围
- 对大项目（>500 单元）：优先搜索 `CHARACTER_ARC` + `CHUNK`，其他类型按需搜索
- 结果截断：默认最多返回 50 条匹配（可通过 max_results 调整）
