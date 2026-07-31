# 交叉引用检测规则（V2）

## 检测总览

共 7 项检测，按重要性降序排列。

| 规则 | 严重级别 | 实现方式 |
|------|---------|---------|
| R1: 已故角色仍在出场 | error | SearchEngine.check_consistency() 自动 |
| R2: 角色关系不对称 | warning | SearchEngine.check_consistency() 自动 |
| R3: 孤立单元 | info | SearchEngine.check_consistency() 自动 |
| R4: 归档单元仍有活跃关系 | warning | SearchEngine.check_consistency() 自动 |
| A5: 能力边界一致性（含修为变化） | warning | 纯 LLM 语义分析 |
| A6: 时间线一致性 | warning | 纯 LLM 语义分析 |
| A7: 情节线完成度 | info | 纯 LLM 语义分析 |

> 规则 1-4（R1-R4）为 SearchEngine 机械检查，通过 `graph.check` 调用。
> 规则 A5-A7 为 LLM 语义分析，SearchEngine 不做机械检查。
> A5 扩展：`出场角色[].状态` 中的修为/能力变化（跨越境界、离线升级判断）作为 A5 的子案例。
> 新增机械规则 R7（位置变化标记）、R9（事件顺序冲突）为 SearchEngine 新增规则，编号 R7-R9 独立于 A5-A7。

## 时间戳归因原则（所有语义规则共用）

同一设定分布在多个单元且内容不一致时，`updated_at` 决定归因方向：

- **`updated_at` 最新的单元 = 最近被修正/确认过的权威值**。修正动作会刷新
  `updated_at`（graph.update_unit 每次实际变更都会更新），因此它代表"最新的处理结果"。
- 其他持有旧值的单元归因为**"未同步"**：旧值没有被修正覆盖，是滞后副本，不是设定错误。
- 已修正的单元**不要重复报错**——它正是其他单元应该同步到的目标。
- 修正后又变回旧值（新 updated_at 但内容与权威值冲突）→ 归因为"回退/覆盖"，需要人工确认。

所有 novel-tool 读取操作（graph.search / graph.get_unit / graph.list_units /
graph.get_modified_units / graph.get_neighbors）都返回 `created_at` / `updated_at`，
比对前先读取涉及单元的这两个字段。

novel-tool 速查：

```
# 快速一致性检查（规则 1-4）
novel-tool --operation graph.check --project <PROJECT>

# 获取原始数据供 LLM 分析
novel-tool --operation graph.search --project <PROJECT> --keyword "林昭"            # 实体搜索
novel-tool --operation graph.search --project <PROJECT> --keyword "灵气" --unit_type CHUNK  # 关键词搜索
novel-tool --operation graph.stats --project <PROJECT>                              # 统计
```

---

> 规则 1-4 已由 `SearchEngine.check_consistency()` 完全自动化，通过 `graph.check` 调用即可获取结果。仅当需要区分"闪回/单相思等合理场景"时才需 LLM 做二次判断。详细的检查逻辑和 V2 数据源参考 SearchEngine 源码。

---

## 规则 A5：能力边界一致性（需 LLM 分析）

**严重级别**：warning

**检查逻辑**：角色在正文中使用的技能/能力，应在 `CHARACTER_ARC.content` 中有对应定义。如果使用了未定义的能力，标记为"能力溢出"。

**V2 数据源**：
- `CHARACTER_ARC.content`（JSON 中的技能列表或自由文本）
- `CHUNK.content` → 全文语义分析（需 LLM 参与）

**获取数据**：
```
novel-tool --operation graph.search --project <PROJECT> --keyword "林昭"
novel-tool --operation graph.search --project <PROJECT> --keyword "林昭" --unit_type CHUNK
```

**LLM 分析步骤**：
1. 从 `CHARACTER_ARC.content` 提取能力列表
2. 从 `CHUNK.content` 中分析角色使用了哪些能力
3. 比对：使用了未列出的能力 → 能力溢出

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

## 规则 A6：时间线一致性（需 LLM 分析）

**严重级别**：warning

**检查逻辑**：`NOTE`（tags 含"时间线"）中记录的事件顺序，应与 `CHUNK` 按 `belongs_to_chapter` 排序后的叙述顺序一致。

**V2 数据源**：
- `NOTE` → `tags` 含"时间线"的单元 → `content` 中的时间记录
- `CHUNK` → `belongs_to_chapter` 字段（隐式顺序）

**获取数据**：
```
novel-tool --operation graph.search --project <PROJECT> --keyword "时间线" --unit_type NOTE
novel-tool --operation graph.search --project <PROJECT> --unit_type CHUNK --limit 100
```

**LLM 分析**：比对时间线记录中的事件顺序 vs 按章节排序的正文内容。

**误报处理**：插叙、倒叙等叙事手法导致的顺序差异不是矛盾。

---

## 规则 A7：情节线完成度（需 LLM 分析）

**严重级别**：info

**检查逻辑**：`PLOT_THREAD.content` 中的关键事件列表，对照已写 `CHUNK` 检查是否已覆盖。

**V2 数据源**：
- `PLOT_THREAD` → `content` 中的关键事件列表
- `CHUNK` + `SCENE` → 已覆盖的内容（按 `belongs_to_chapter` 排序）

**获取数据**：
```
novel-tool --operation graph.list_units --project <PROJECT> --unit_type PLOT_THREAD
novel-tool --operation graph.stats --project <PROJECT>
```

**LLM 分析**：对每条情节线，提取关键事件列表，检查对应的场景或正文是否已写。

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
