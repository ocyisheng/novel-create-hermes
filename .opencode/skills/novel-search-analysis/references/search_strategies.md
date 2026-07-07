# 搜索策略参考（V2）

## SearchEngine 用法

搜索由 `SearchEngine` 类提供，纯机械搜索，不做语义理解。

### 统一搜索入口

通过 novel-tool 搜索：

```
novel-tool --operation graph.search --project <PROJECT> --keyword "天道宗"
novel-tool --operation graph.search --project <PROJECT> --keyword "林昭"
novel-tool --operation graph.search --project <PROJECT> --pattern "筑基.*期" --regex
novel-tool --operation graph.search --project <PROJECT> --keyword "剑" --unitType SCENE --limit 10
```

搜索逻辑（供理解，不直接使用）：
- 关键词搜索：子串匹配 name/content/tags
- 正则搜索：re.search 遍历 content
- 实体搜索：按名称查找 + 1 度邻居展开

也可以通过 Python 直接调用 SearchEngine：

```
novel-tool --operation graph.search --project <PROJECT> --keyword "天道宗"
novel-tool --operation graph.search --project <PROJECT> --keyword "林昭"
novel-tool --operation graph.search --project <PROJECT> --pattern "筑基.*期" --regex
novel-tool --operation graph.search --project <PROJECT> --keyword "剑" --unitType SCENE --limit 10
```

### 增量分析

```python
# 只获取 version 大于指定版本的变更单元（与 VizIncrementalEngine 同模式）
changed = engine.get_modified_units(since_version=42)
```

### 一致性检查

```python
results = engine.check_consistency()
# 返回 CheckResult 列表，含 4 条规则：
# R1: 已故角色仍在出场（error）
# R2: 角色关系不对称（warning）
# R3: 孤立单元（info）
# R4: 归档单元仍有活跃关系（warning）
```

novel-tool：

```
novel-tool --operation graph.check --project <PROJECT>
```

---

## 搜索结果排序

`SearchEngine.search()` 按 `score` 降序排列：
- 关键词在 `unit_name` 中匹配 → +3 分
- 关键词在 `content` 中匹配 → +2 分
- 关键词在 `tags` 中匹配 → +1 分
- 正则匹配 → +1 分
- 实体搜索主单元 → +5 分，邻居 → +3 分

---

## 搜索结果结构

```python
@dataclass
class SearchResult:
    unit_id: str
    unit_name: str
    unit_type: UnitType
    content_preview: str    # 前 200 字
    content_length: int
    chapter: Optional[int]
    score: float
    tags: List[str]
    version: int
    neighbors: List[str]    # 邻居名列表（供 LLM 分析）

@dataclass
class SearchResultSet:
    query: str
    total: int
    results: List[SearchResult]
    time_ms: float
```

---

## 搜索模式组合

| 用户意图 | novel-tool 操作 | 说明 |
|---------|---------|------|
| "找所有提到天道宗的地方" | `graph.search --keyword "天道宗"` | 全范围搜索 |
| "查查第5章写了什么" | `graph.search` + find_units(chapter=5) | 按章节查场景 |
| "林昭在第3章说了什么" | `graph.search --keyword "林昭" --unitType CHUNK --limit 20` | 关键词+类型过滤 |
| "有哪些角色还没出场" | `graph.stats` + `graph.list_units --unitType CHARACTER_ARC` | 统计 |
| "检查设定有没有冲突" | `graph.check` | 一致性检查 |

---

## 中文搜索注意事项

- Python 的 `in` 操作符对中文子串搜索已经足够（如 `"天" in "天道宗"` → True）
- 不需要分词，中文关键词直接按字符子串匹配
- 正则搜索时注意中文的 Unicode 编码（`\w` 不匹配中文，用 `.*` 或显式字符类）
- 默认不区分大小写（中文无大小写问题）

---

## 搜索性能

- 小项目（<100 单元）：全量扫描，无性能顾虑
- 中等项目（100-500 单元）：用 `scope` 缩小搜索范围
- 大项目（>500 单元）：优先搜 `CHARACTER_ARC` + `CHUNK`，其他类型按需搜
- 结果截断：`max_results` 参数，默认 50 条
