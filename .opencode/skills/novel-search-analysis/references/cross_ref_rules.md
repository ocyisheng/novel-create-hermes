# 交叉引用检测规则（V2 版）

## 检测总览

共 7 项检测，按重要性降序排列。所有数据通过 GraphStore API 读取，不依赖旧 YAML 文件。

V2 CLI 速查：

```bash
# 列出所有角色
v2_cli.py list-units --path <PROJECT> --type CHARACTER_ARC

# 查角色详情
v2_cli.py get-unit --path <PROJECT> --id <ID>

# 查关系网络
v2_cli.py get-neighbors --path <PROJECT> --id <ID>

# 列出所有场景
v2_cli.py list-units --path <PROJECT> --type SCENE

# 列出所有情节线
v2_cli.py list-units --path <PROJECT> --type PLOT_THREAD

# 列出所有世界观规则
v2_cli.py list-units --path <PROJECT> --type WORLD_RULE

# 列出所有正文片段
v2_cli.py list-units --path <PROJECT> --type CHUNK

# 项目统计
v2_cli.py stats --path <PROJECT>
```

---

## 规则 1：角色状态一致性

**严重级别**：critical

**检查逻辑**：`CHARACTER_ARC.status == ARCHIVED` 的角色不应仍有 `PARTICIPATES_IN` 关系指向 `SCENE`。

**V2 数据源**：
- `CHARACTER_ARC` → `status` 字段（`ARCHIVED` = 已故/已退场）
- `Relation(type=PARTICIPATES_IN)` → `source_id=CHARACTER_ARC.id`, `target_id=SCENE.id`

**实现方式**：
```python
for ca in store.find_units(type=CHARACTER_ARC):
    if ca.status != UnitStatus.ARCHIVED:
        continue
    for rel in store.get_relations(ca.id, direction="outgoing"):
        if rel.relation_type == RelationType.PARTICIPATES_IN:
            scene = store.get_unit(rel.target_id)
            if scene:
                mark_warning(f"{ca.unit_name} 已归档，仍参与场景 {scene.unit_name}")
```

**误报处理**：闪回/回忆场景中的已故角色出场不算矛盾，需要 AI 判断是否属于闪回。

**输出示例**：
```yaml
- rule: "角色状态一致性"
  status: "warning"
  detail:
    character: "林昭"
    status: "archived"
    appearing_in_scene: "第15章·天机城之战"
    note: "角色已归档（已故），但仍有 PARTICIPATES_IN 关系指向场景"
```

---

## 规则 2：角色关系对称性

**严重级别**：warning

**检查逻辑**：如果角色 A 与角色 B 之间存在 `REFERENCES` 关系，角色 B 应有对应的反向关系。

**V2 数据源**：
- `CHARACTER_ARC` 全部单元
- `Relation(type=REFERENCES)` 且 `source.type == CHARACTER_ARC` 且 `target.type == CHARACTER_ARC`

**实现方式**：
```python
chars = store.find_units(type=CHARACTER_ARC)
for a in chars:
    for rel in store.get_relations(a.id, direction="outgoing", relation_type=REFERENCES):
        b = store.get_unit(rel.target_id)
        if not b or b.type != CHARACTER_ARC:
            continue
        # 检查 B → A 的反向关系
        has_reverse = any(
            r.target_id == a.id
            for r in store.get_relations(b.id, direction="outgoing", relation_type=REFERENCES)
        )
        if not has_reverse:
            mark_info(f"单向关系: {a.unit_name} ↔ {b.unit_name}")
```

**误报处理**：单相思、暗恋、单方面认识等合理不对称关系不标记为问题。

**输出示例**：
```yaml
- rule: "角色关系对称性"
  status: "info"
  detail:
    character_a: "林昭"
    character_b: "苏晴"
    a_mentions_b: true
    b_mentions_a: false
    note: "苏晴未建立指向林昭的 REFERENCES 关系"
```

---

## 规则 3：势力归属一致性

**严重级别**：warning

**检查逻辑**：角色关联的势力（通过 `BELONGS_TO` 关系指向 `WORLD_RULE`），对应的 `WORLD_RULE.unit_name` 应存在。

**V2 数据源**：
- `Relation(type=BELONGS_TO)` 且 `source.type == CHARACTER_ARC`, `target.type == WORLD_RULE`
- `WORLD_RULE` 全部单元

**实现方式**：
```python
chars = store.find_units(type=CHARACTER_ARC)
rules = {r.unit_name for r in store.find_units(type=WORLD_RULE)}
for ca in chars:
    for rel in store.get_relations(ca.id, direction="outgoing", relation_type=BELONGS_TO):
        wr = store.get_unit(rel.target_id)
        if wr and wr.type == WORLD_RULE:
            # wr.unit_name 就是势力名，已存在
            pass
        elif wr is None:
            mark_warning(f"{ca.unit_name} 的 BELONGS_TO 关系指向不存在的 WORLD_RULE")
```

**误报处理**：不要求精确匹配名称，子势力/别名也算通过。

**输出示例**：
```yaml
- rule: "势力归属一致性"
  status: "warning"
  detail:
    character: "林昭"
    faction: "天机阁"
    exists_in_world_rules: false
    note: "林昭有指向'天机阁'的 BELONGS_TO 关系，但 WORLD_RULE 中无此名称"
```

---

## 规则 4：地理位置一致性

**严重级别**：warning

**检查逻辑**：`SCENE.unit_name` 或 `SCENE.content` 中解析出的地点名，应在 `WORLD_RULE`（tags 含"地理"）中有对应定义。

**V2 数据源**：
- `SCENE` 全部单元（`unit_name` + `content`）
- `WORLD_RULE` 中 `tags` 含"地理"的单元

**实现方式**：
```python
geo_rules = [r for r in store.find_units(type=WORLD_RULE) if "地理" in r.tags]
geo_names = {r.unit_name for r in geo_rules}

scenes = store.find_units(type=SCENE)
for s in scenes:
    # 从 scene.unit_name 或 content 中提取地点名（需 LLM）
    locations = extract_locations(s.unit_name, s.content)
    for loc in locations:
        if loc not in geo_names:
            mark_info(f"场景 {s.unit_name} 中的地点 '{loc}' 未在 WORLD_RULE 中定义")
```

**误报处理**：路过型地点（如"森林中""路边茶馆"）不需要在设定文件中显式定义。

**输出示例**：
```yaml
- rule: "地理位置一致性"
  status: "info"
  detail:
    location: "天机城"
    appears_in_scene: "第15章·天机城之战"
    in_world_rules: false
    note: "天机城是重要场景，但 WORLD_RULE 中未找到对应地理规则"
```

---

## 规则 5：能力边界一致性

**严重级别**：critical

**检查逻辑**：角色在正文中使用的技能/能力，应在 `CHARACTER_ARC.content` 中有对应定义。如果使用了未定义的能力，标记为"能力溢出"。

**V2 数据源**：
- `CHARACTER_ARC.content`（JSON 中的技能列表或自由文本）
- `CHUNK.content` → 全文语义分析（需 LLM 参与）

**实现方式**：
```python
# 此规则必须由 LLM 执行语义分析
# 1. 从 CHARACTER_ARC.content 提取能力列表
# 2. 从 CHUNK.content 中分析角色使用了哪些能力
# 3. 比对：使用了未列出的能力 → 能力溢出
```

**误报处理**：通用能力（如"跑步""跳跃""基本拳脚"）不需要在技能专长中列出。

**输出示例**：
```yaml
- rule: "能力边界一致性"
  status: "warning"
  detail:
    character: "林昭"
    ability_used: "灵气屏蔽阵法"
    chapter: 8
    in_profile: false
    note: "林昭在第8章使用了'灵气屏蔽阵法'，但角色能力设定中未包含此技能"
```

---

## 规则 6：时间线一致性

**严重级别**：warning

**检查逻辑**：`NOTE`（tags 含"时间线"）中记录的事件顺序，应与 `CHUNK` 按 `belongs_to_chapter` 排序后的叙述顺序一致。

**V2 数据源**：
- `NOTE` → `tags` 含"时间线"的单元 → `content` 中的时间记录
- `CHUNK` → `belongs_to_chapter` 字段（隐式顺序）

**实现方式**：
```python
timeline_notes = [n for n in store.find_units(type=NOTE) if "时间线" in n.tags]
chunks = store.find_units(type=CHUNK)
chunks.sort(key=lambda c: c.belongs_to_chapter or 0)
# LLM 比对：时间线记录中的事件顺序 vs 章节顺序
```

**误报处理**：插叙、倒叙等叙事手法导致的顺序差异不是矛盾。

**输出示例**：
```yaml
- rule: "时间线一致性"
  status: "info"
  detail:
    event: "秘境试炼"
    expected_chapter: 15
    actual_chapter: 18
    note: "时间线记录秘境试炼发生在第15章前后，但第18章尚未写到"
```

---

## 规则 7：情节线完成度

**严重级别**：info

**检查逻辑**：`PLOT_THREAD.content` 中的关键事件列表，对照已写 `CHUNK` 检查是否已覆盖。

**V2 数据源**：
- `PLOT_THREAD` → `content` 中的关键事件列表
- `CHUNK` + `SCENE` → 已覆盖的内容（按 `belongs_to_chapter` 排序）

**实现方式**：
```python
plots = store.find_units(type=PLOT_THREAD)
chunks = store.find_units(type=CHUNK)
written_chapters = {c.belongs_to_chapter for c in chunks if c.belongs_to_chapter}

for pt in plots:
    key_events = extract_key_events(pt.content)  # 需 LLM
    uncovered = [e for e in key_events if not is_covered(e, written_chapters)]
    if uncovered:
        mark_info(f"情节线 {pt.unit_name}: {len(uncovered)}/{len(key_events)} 未覆盖")
```

**输出示例**：
```yaml
- rule: "情节线完成度"
  status: "info"
  detail:
    plot_thread: "主线·末法觉醒"
    total_key_events: 11
    covered_in_chapters: 2
    uncovered:
      - event: "秘境试炼"
        note: "尚未写到"
    note: "当前只写到第3章，大部分关键事件尚未到达"
```
