# 交叉引用检测规则（V2）

## 检测总览

共 7 项检测，按重要性降序排列。

| 规则 | 严重级别 | 实现方式 |
|------|---------|---------|
| R1: 已故角色仍在出场 | error | SearchEngine.check_consistency() 自动 |
| R2: 角色关系不对称 | warning | SearchEngine.check_consistency() 自动 |
| R3: 孤立单元 | info | SearchEngine.check_consistency() 自动 |
| R4: 归档单元仍有活跃关系 | warning | SearchEngine.check_consistency() 自动 |
| R5: 能力边界一致性 | warning | SearchEngine 自动 + 供 LLM 角色一致性判断 |
| R6: 时间线一致性 | warning | SearchEngine 自动 + 供 LLM 情节逻辑判断 |
| R7: 情节线完成度 | info | SearchEngine 自动 + 供 LLM 情节逻辑判断 |

> 规则 1-4 已由 `SearchEngine.check_consistency()` 实现，通过 `v2_cli.py check` 调用。
> 规则 5-7 需要 LLM 做语义分析，SearchEngine 只提供原始数据。

CLI 速查：

```bash
# 快速一致性检查（规则 1-4）
python .opencode/shared/v2_cli.py check --path <PROJECT>

# 获取原始数据供 LLM 分析
python .opencode/shared/v2_cli.py search --path <PROJECT> --entity "林昭"           # 实体及邻居
python .opencode/shared/v2_cli.py search --path <PROJECT> --keyword "灵气" --scope CHUNK  # 关键词搜索
python .opencode/shared/v2_cli.py report --path <PROJECT>                          # 统计 + gap 数据
```

---

## 规则 1：已故角色仍在出场（已自动化）

**严重级别**：error

**自动化实现**：`SearchEngine.check_consistency()` → R1

**检查逻辑**：`CHARACTER_ARC.status == ARCHIVED` 的角色不应仍有 `PARTICIPATES_IN` 关系指向 `SCENE`。

**V2 数据源**：
- `CHARACTER_ARC` → `status` 字段（`ARCHIVED` = 已故/已退场）
- `Relation(type=PARTICIPATES_IN)` → `source_id=CHARACTER_ARC.id`, `target_id=SCENE.id`

**误报处理**：闪回/回忆场景中的已故角色出场不算矛盾，需要 LLM 判断是否属于闪回。

**输出示例**：
```
R1 error: 角色『无名老者』已归档(archived)，但仍在场景『后山拔剑』中出场
```

---

## 规则 2：角色关系不对称（已自动化）

**严重级别**：warning

**自动化实现**：`SearchEngine.check_consistency()` → R2

**检查逻辑**：如果角色 A 与角色 B 之间存在 `REFERENCES`/`ALLIED_WITH` 等关系，角色 B 应有对应的反向关系。

**V2 数据源**：
- `CHARACTER_ARC` 全部单元
- `Relation` 中角色之间的各类关系

**误报处理**：单相思、暗恋、单方面认识等合理不对称关系不标记为问题（由 LLM 判断）。

**输出示例**：
```
R2 warning: 『吕明理』→『韩松』(references)，但反向关系不存在
```

---

## 规则 3：孤立单元（已自动化）

**严重级别**：info

**自动化实现**：`SearchEngine.check_consistency()` → R3

**检查逻辑**：没有任何关系的单元（排除 ARCHIVED）。

**输出示例**：
```
R3 info: 有 1 个单元没有任何关系
  孤立单元:
    - 上古战场遗址 (world_rule)
```

---

## 规则 4：归档单元仍有活跃关系（已自动化）

**严重级别**：warning

**自动化实现**：`SearchEngine.check_consistency()` → R4

**检查逻辑**：`status == ARCHIVED` 的单元仍有 outgoing 关系。

**输出示例**：
```
R4 warning: 单元『无名老者』(character_arc)已归档，但仍有 2 条活跃关系
  关系: references→后山拔剑, references→魔道来袭
```

---

## 规则 5：能力边界一致性（需 LLM 分析）

**严重级别**：warning

**检查逻辑**：角色在正文中使用的技能/能力，应在 `CHARACTER_ARC.content` 中有对应定义。如果使用了未定义的能力，标记为"能力溢出"。

**V2 数据源**：
- `CHARACTER_ARC.content`（JSON 中的技能列表或自由文本）
- `CHUNK.content` → 全文语义分析（需 LLM 参与）

**获取数据**：
```bash
# 获取角色档案
python .opencode/shared/v2_cli.py search --path <PROJECT> --entity "林昭"

# 获取角色相关正文片段
python .opencode/shared/v2_cli.py search --path <PROJECT> --keyword "林昭" --scope CHUNK
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

## 规则 6：时间线一致性（需 LLM 分析）

**严重级别**：warning

**检查逻辑**：`NOTE`（tags 含"时间线"）中记录的事件顺序，应与 `CHUNK` 按 `belongs_to_chapter` 排序后的叙述顺序一致。

**V2 数据源**：
- `NOTE` → `tags` 含"时间线"的单元 → `content` 中的时间记录
- `CHUNK` → `belongs_to_chapter` 字段（隐式顺序）

**获取数据**：
```bash
# 获取时间线笔记
python .opencode/shared/v2_cli.py search --path <PROJECT> --keyword "时间线" --scope NOTE

# 获取所有正文片段
python .opencode/shared/v2_cli.py search --path <PROJECT> --keyword "" --scope CHUNK --limit 100
```

**LLM 分析**：比对时间线记录中的事件顺序 vs 按章节排序的正文内容。

**误报处理**：插叙、倒叙等叙事手法导致的顺序差异不是矛盾。

---

## 规则 7：情节线完成度（需 LLM 分析）

**严重级别**：info

**检查逻辑**：`PLOT_THREAD.content` 中的关键事件列表，对照已写 `CHUNK` 检查是否已覆盖。

**V2 数据源**：
- `PLOT_THREAD` → `content` 中的关键事件列表
- `CHUNK` + `SCENE` → 已覆盖的内容（按 `belongs_to_chapter` 排序）

**获取数据**：
```bash
# 获取所有情节线
python .opencode/shared/v2_cli.py search --path <PROJECT> --keyword "" --scope PLOT_THREAD

# 获取项目统计（含 gap 分析）
python .opencode/shared/v2_cli.py report --path <PROJECT>
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
