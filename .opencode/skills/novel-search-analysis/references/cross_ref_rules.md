# 交叉引用检测规则

## 检测总览

共 7 项检测，按重要性降序排列。

---

## 规则 1：角色状态一致性

**严重级别**：critical

**检查逻辑**：分纲中标记为"出场角色"的角色，其角色档案的 `索引信息.状态` 不应为 `deceased`/`inactive`/`已故`/`已退场`。

**数据来源**：
- `characters/*.yaml` → `索引信息.状态`
- `outline/分纲/卷*/*.yaml` → `出场角色` 列表

**误报处理**：闪回/回忆场景中的已故角色出场不算矛盾，需要 AI 判断是否属于闪回。

**输出示例**：
```yaml
- rule: "角色状态一致性"
  status: "warning"
  detail:
    character: "林昭"
    status_in_profile: "deceased"
    appearing_in_chapter: 15
    chapter_file: "outline/分纲/卷2/第15章.yaml"
    note: "角色档案标记为'已故'，但在第15章分纲中仍列为出场角色"
```

---

## 规则 2：角色关系对称性

**严重级别**：warning

**检查逻辑**：角色 A 的档案中提及与角色 B 的关系，角色 B 的档案中应对称提及与角色 A 的关系（非强制，但单向关系值得标记）。

**数据来源**：`characters/*.yaml` → `完整档案.关系网络`

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
    a_context: "第一个追随者/革新派盟友"
    note: "苏晴档案中未提及林昭，如果苏晴是主要角色建议补充"
```

---

## 规则 3：势力归属一致性

**严重级别**：warning

**检查逻辑**：角色档案中 `索引信息.势力` 或 `完整档案.基本信息.身份` 中提到的势力，应在 `worldbuilding/势力*.yaml` 中有对应定义。

**数据来源**：
- `characters/*.yaml` → `索引信息.势力` 或 `完整档案.基本信息.身份`
- `worldbuilding/*.yaml` → `索引信息.名称`

**误报处理**：不要求精确匹配名称，子势力/别名也算通过。

**输出示例**：
```yaml
- rule: "势力归属一致性"
  status: "warning"
  detail:
    character: "林昭"
    faction_mentioned: "天机阁"
    in_worldbuilding_files: false
    note: "角色档案中提到了'天机阁'，但 worldbuilding/ 下未找到该势力的设定文件"
```

---

## 规则 4：地理位置一致性

**严重级别**：warning

**检查逻辑**：分纲文件中出现的场景地点，应在 `worldbuilding/地理*.yaml` 或 `worldbuilding/基本信息.yaml` 中有对应定义。

**数据来源**：
- `outline/分纲/卷*/*.yaml` → `场景列表` 中的场景名
- `worldbuilding/*.yaml` → `索引信息.名称` 或 `完整档案` 中的地点名

**误报处理**：路过型地点（如"森林中""路边茶馆"）不需要在设定文件中显式定义。

**输出示例**：
```yaml
- rule: "地理位置一致性"
  status: "info"
  detail:
    location: "天机城"
    appears_in_chapter: 15
    chapter_file: "outline/分纲/卷2/第15章.yaml"
    in_worldbuilding_files: false
    note: "天机城是重要场景，但 worldbuilding/ 下未找到设置文件"
```

---

## 规则 5：能力边界一致性

**严重级别**：critical

**检查逻辑**：角色在章节中使用的技能/能力，应在角色档案的 `完整档案.能力设定.技能专长` 中有对应定义。如果角色使用了档案中未列出的能力，标记为"能力溢出"。

**数据来源**：
- `characters/*.yaml` → `完整档案.能力设定.技能专长`
- `chapters/*.txt` → 全文语义分析（需 LLM 参与）

**误报处理**：通用能力（如"跑步""跳跃""基本拳脚"）不需要在技能专长中列出。

**输出示例**：
```yaml
- rule: "能力边界一致性"
  status: "warning"
  detail:
    character: "林昭"
    ability_used: "灵气屏蔽阵法"
    chapter: 8
    chapter_file: "chapters/第8章.txt"
    in_profile: false
    note: "林昭在第8章使用了'灵气屏蔽阵法'，但角色档案的能力设定中未包含此技能"
```

---

## 规则 6：时间线一致性

**严重级别**：warning

**检查逻辑**：`outline/追踪/时间线.yaml` 中记录的关键事件的时间顺序，应与章节正文中的叙述顺序一致。

**数据来源**：
- `outline/追踪/时间线.yaml` → 事件时间记录
- `chapters/*.txt` → 事件叙述顺序

**误报处理**：插叙、倒叙等叙事手法导致的顺序差异不是矛盾。

---

## 规则 7：情节线完成度

**严重级别**：info

**检查逻辑**：`outline/情节线/*.yaml` 中 `关键事件` 列表的事件，对照已写章节检查是否已覆盖。

**数据来源**：
- `outline/情节线/*.yaml` → `关键事件`
- `chapters/*.txt` → 已有章节内容

**输出示例**：
```yaml
- rule: "情节线完成度"
  status: "info"
  detail:
    plot_thread: "主线_末法觉醒"
    total_key_events: 11
    covered_in_chapters: 2
    uncovered:
      - event: "秘境试炼"
        target_chapter: 15
        status: "未到达"
      - event: "宗门大比"
        target_chapter: 28
        status: "未到达"
    note: "当前只写到第3章，大部分关键事件尚未到达"
```
