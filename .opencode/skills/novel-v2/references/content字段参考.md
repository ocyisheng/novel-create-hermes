# V2 叙事单元 content 字段参考

## 统一结构

所有叙事单元的 `content` 字段遵循两层结构：

```json
{
  "普适字段": "...",          // YAML schema 定义的必填/可选字段（英文 field name），所有类型共有
  "流派适配字段": "...",      // LLM 按小说流派自由生成的字段，自动按值类型渲染
}
```

**渲染规则**（所有类型统一）：
1. `描述` → 文本块（按名称匹配，强制 textblock）
2. `核心特质` → 标签云（按名称匹配，强制 tagcloud，即使是 string 也按逗号分割）
3. `key_events` → 时间线（按名称匹配，强制 timeline）
4. 其余所有字段 → 按值类型自动渲染（string<50→键值对、string[]→标签云、{目标,关系}[]→关系列表、dict→群组展开）
5. `_display` 不再使用。如有旧数据，其字段被当作普通 dict 字段渲染。

**不需要为每个类型定义专用字段**。LLM 创作时自然生成的字段（如势力的`首领`、地点的`位置`、角色的`修为`）都会自动按值类型推断渲染。

---

## 一、角色（CHARACTER_ARC）

### 标准 schema

```json
{
  "subtype": "主角 | 重要配角 | 反派 | 关键配角 | 群像 | 功能性角色",
  "性格": {
    "核心特质": "以医入道，坚韧不拔",
    "优点": ["隐忍", "聪慧"],
    "缺点": ["固执", "多疑"]
  },
  "背景": {
    "出身": "韩家医馆学徒",
    "描述": "韩门少年，天生绝灵根..."
  },
  "goals_conflicts": {
    "目标": "探索灵界，补全五行回路",
    "冲突": "绝灵根限制与修行之路的矛盾"
  },
  "能力设定": {
    "修为": "化神期",
    "功法": "五行轮转经",
    "阵营": "正道",
    "身份": "韩门门主"
  },
  "character_arc_detail": {
    "volume_start_state": "凡人，绝灵根",
    "最终状态": "化神飞升"
  },
  "key_events": [
    {"事件": "离家学医", "time_text": "8岁"},
    {"事件": "筑基成功", "time_text": "30岁"}
  ]
}
```

### 渲染规则

| content 值类型 | 渲染方式 | 示例字段 |
|----------------|---------|---------|
| `string` < 50字 | 键值对标签 | 身份, 修为, 阵营 |
| `string` > 50字 | 文本块 | 描述 |
| `string[]` | 标签云 | 核心特质, 优点 |
| `{event, chapter_number?}[]` | 时间线 | key_events |
| `{target, relation}[]` | 关系列表 | 人物关系 |
| `dict` | 群组展开 | 能力设定, 性格 |

---

## 二、场景（SCENE）

### 定位

SCENE 是单个场域（时间×地点×POV 叙事切片）的结构设计单元。每章由多个 SCENE 构成（通常 3-5 个）。

### 标准 schema

```json
{
  "subtype": "开篇 | 推进 | 冲突 | 转折 | 展示 | 过渡 | 收束",
  "pov_character": "林渊",
  "location": "落云宗后山练剑坪",
  "time_text": "午后",
  "one_line_summary": "林渊在练剑坪第一次拔剑",
  "cast": [{"name": "林渊"}, {"name": "苏长老"}],
  "related_plotlines": ["主线·剑道之争"]
}
```

`出场角色` 支持两种格式：
- **简洁格式**（推荐）：字符串数组 `[{"name": "林渊"}, {"name": "苏长老"}]`，工作空间自动填充状态和描述为空
- **详细格式**：对象数组 `[{"name": "林渊", "role_status": "冷静", "role_in_scene": "首次拔剑尝试"}]`，工作空间可提取角色状态和场景作用

### 子类型说明

| 子类型 | 功能 | 适用 |
|-------|------|------|
| 开篇 | 章首场景，定情绪基调，衔接上章 | 推进章、过渡章 |
| 推进 | 推进情节，释放信息 | 推进章、高潮章 |
| 冲突 | 正面对抗，制造张力 | 高潮章、推进章 |
| 转折 | 反转/揭示，改变叙事方向 | 高潮章、收束章 |
| 展示 | 世界观/角色展示，不急于推进 | 过渡章、引入章 |
| 过渡 | 节奏缓冲，衔接两个重点场景 | 过渡章 |
| 收束 | 章尾场景，留悬念或余韵 | 推进章、收束章 |

---

## 三、情节线（PLOT_THREAD）

### 标准 schema

```json
{
  "subtype": "主线 | 支线 | 暗线 | 感情线 | 成长线 | 世界观线",
  "core_conflict": "人界灵气污染背后的阴冥势力渗透",
  "key_events": [
    {"chapter_number": 10, "event": "鬼道屠城"},
    {"chapter_number": 25, "event": "韩致发现污染真相"}
  ],
  "ending_design": "鬼主被击败，人界灵气恢复平衡",
  "角色参与": ["韩致", "鬼主"]
}
```

---

## 四、世界观（WORLD_RULE）

### 标准 schema

```json
{
  "subtype": "地点 | 势力 | 规则 | 力量体系 | 世界观总览 | 历史 | 文化 | 经济体系 | 政治体系 | 社会阶层 | 纪年事件",
  "sub_type_detail": "大陆 | 宗门 | 家族 | 秘境 | 海域 | 组织 | ...",
  "描述": "天南大陆修仙界的核心区域..."
}
```

`子类型` 和 `二级类型` 是标准分类器。其余字段按子类型自由添加，HTML 面板自动渲染所有非 schema 字段为键值对。

### 子类型常用字段（LLM 自然生成，非强制）

**地点类** — 二级分类：大陆、国家、城市、海域、秘境、地域、沿海、内陆

```json
{
  "subtype": "location",
  "sub_type_detail": "海域",
  "描述": "人界最北端的极寒海域，北极元光可淬炼法宝至人界巅峰品质...",
  "位置": "人界最北端",
  "归属": "无主之地",
  "重要场所": ["冰凤遗迹", "海眼"],
  "物产": ["北极元光", "玄冥水脉"]
}
```

**势力类** — 二级分类：宗门、家族、商行、组织、阵营、联盟、族群

```json
{
  "subtype": "势力",
  "sub_type_detail": "宗门",
  "描述": "正道七大宗门之一，以剑修和丹修闻名...",
  "首领": "程知节（元婴中期）",
  "主要成员": ["韩松", "吕明理"],
  "势力范围": "越国",
  "立场": "正道"
}
```

**规则/力量体系类**

```json
{
  "subtype": "力量体系",
  "描述": "修仙境界分为炼气→筑基→结丹→元婴→化神五个大境界...",
  "等级划分": [
    {"名称": "炼气期", "说明": "引气入体，淬炼经脉"},
    {"名称": "筑基期", "说明": "易经洗髓，凝结道基"}
  ],
  "灵根体系": "金木水火土五行灵根"
}
```

**纪年事件类**

```json
{
  "subtype": "纪年事件",
  "sub_type_detail": "战争 | 天灾 | 政治变革 | 人物生平 | 传说",
  "summary": "韩致飞升灵界",
  "time_text": "凡人历2047年",
  "描述": "韩致以化神期修为飞升灵界，人界灵气平衡被打破...",
  "关联角色": ["韩致", "苏长老"],
  "关联地点": "天南大陆"
}
```

### 渲染规则

1. `子类型` → 决定二级标签（地点/势力/纪年事件等带有颜色区分）
2. `二级类型` → 显示为键值对
3. `描述` → 显示为文本块（按名称匹配，强制 textblock）
4. 其余所有字段 → 自动按值类型渲染（string→键值对/文本块、string[]→标签云、dict→群组展开）

---

## 五、笔记（NOTE）

### 标准 schema

```json
{
  "subtype": "灵感 | 笔记",
  "内容": "想到了一个有趣的设定..."
}
```

---

## 六、正文片段（CHUNK）

### 定位

CHUNK 是章节正文的**元数据单元**，不包含实际文本。正文写入 `正文路径` 指定的 TXT 文件。

### 标准 schema

```json
{
  "subtype": "v1",
  "chapter_number": 3,
  "chapter_title": "青山镇少年",
  "file_path": "chapters/第3章_v1.txt",
  "word_count": 3200
}
```

### 正文文件约定

- `正文路径` 为空时默认：`chapters/第{章节号}章_{子类型}.txt`
  - v1（初稿） → `chapters/第3章_v1.txt`
  - v2（修订稿） → `chapters/第3章_v2.txt`
  - v3（定稿） → `chapters/第3章_v3.txt`
- 格式：纯文本 UTF-8
- 不同版本互不覆盖，可同时保留多个版本

---

## 七、主题意象（THEMATIC_MOTIF）

### 标准 schema

```json
{
  "subtype": "贯穿性 | 局部性 | 装饰性",
  "motif_symbol": "剑",
  "symbolic_meaning": "从武器到身份的象征",
  "variation_method": "在不同情境中改变剑的描摹——童年初见敬畏，中年断裂，晚年重铸",
  "occurrence_chapters": [1, 8, 15, 30, 50],
  "related_characters": [{"name": "林渊"}, {"name": "苏长老"}]
}
```

---

## 八、结构设计（OUTLINE / ARC_PLAN / VOLUME_PLAN / CHAPTER_PLAN）

每种结构类型有独立的 content Schema，不再使用统一的 `子类型`+`结构模式` 模型。

### 总纲（OUTLINE）

```json
{
  "mode": "沙漏/长链/螺旋/环状/多线交织",
  "ontology": "故事的本质是什么？为什么这个故事只能以这种方式存在？",
  "aesthetic_promise": "向读者承诺的美学体验——爽快/沉思/悬疑/悲壮……",
  "seven_facets": {
    "叙事起点": "...",
    "叙事终点": "...",
    "核心冲突": "...",
    "主题表达": "..."
  },
  "notes": ""
}
```

### 部篇大纲（ARC_PLAN）

```json
{
  "naming_convention": "部/篇",
  "序列": 1,
  "core_theme": "部/篇的核心主题",
  "coverage": "覆盖哪些卷，如'第1-3卷'",
  "arc_start_state": "本部的起始状态",
  "arc_end_state": "本部的终点状态",
  "mood_curve_overview": [],
  "cross_volume_foreshadowing": [],
  "notes": ""
}
```

### 卷大纲（VOLUME_PLAN）

```json
{
  "卷号": 1,
  "volume_title": "volume_title",
  "核心冲突": "本卷的核心矛盾（一句话）",
  "volume_start_state": "卷起始时的叙事状态",
  "arc_end_state": "卷结束时的叙事状态",
  "emotional_tone": "压抑/紧张/明快/悲壮/悬疑/热血/沉稳/诙谐",
  "节奏类型配比": {},
  "word_count_target": 0,
  "foreshadowing_list": [],
  "notes": ""
}
```

### 章纲（CHAPTER_PLAN）

```json
{
  "chapter_number": 1,
  "chapter_title": "",
  "chapter_function": "开篇/推进/冲突/转折/展示/过渡/收束",
  "scene_sequence": [
    {"场景名": "场景1", "定位": "...", "字数预计": 0}
  ],
  "情绪弧线": [],
  "info_release_plan": [],
  "word_count_allocation": {},
  "transition_note": "如何衔接上一章",
  "notes": ""
}
```

> 场景的规划归属由 PLANS 边承载（章纲→SCENE），场景的执行归属由 CHUNK 的 BELONGS_TO 边承载。规划与执行解耦。

---

## 九、叙述腔调（NARRATIVE_VOICE）

### 标准 schema

```json
{
  "subtype": "第一人称 | 第三人称限制 | 第三人称全知 | 第二人称 | 多视角交替",
  "voice_lineage": "踩谁的影子",
  "function_role": "催眠 | 警醒 | 复调",
  "narrative_perspective": "全知 | 部分全知 | 戏剧性手法 | 多视角",
  "pov_switch_rules": "切换条件及注意事项",
  "info_distribution_strategy": "常规 | 抵抗 | 挑衅",
  "notes_tradition_enabled": false
}
```

`voice_lineage`、`function_role`、`narrative_perspective` 为必填字段。详见 `references/narrative_voice.md` 创作方法论。

---

## 十、时间事件（TEMPORAL_EVENT）

### 标准 schema

```json
{
  "event_type": "scene_event|cultivation|battle|plot_event|item_event|chronicle|relationship|note",
  "ordinal": 4500,
  "precision": "exact|approximate|chapter|same|volume|vague",
  "time_label": "第三日黄昏",
  "summary": "吕明理突破至结丹中期",
  "details": {
    "old_realm": "结丹初期",
    "new_realm": "结丹中期"
  },
  "location": "后山密室",
  "characters": [{"name": "吕明理", "role": "当事人"}]
}
```

### 使用方式

时间事件是独立 graph 节点，通过边关联到实体：

```
角色/地点/物品 ──HAS_EVENT──→ [事件节点] ──LOCATED_AT──→ 地点
                                  ├─INVOLVES──→ 角色
                                  └─CAUSED_BY──→ [另一事件]
```

创建、编辑、删除均通过标准的 `graph.create_unit` / `graph.update_unit` / `graph.archive_unit` 操作，不新增 API。

### 存量数据兼容

已有 CHARACTER_ARC 的 `key_events`、PLOT_THREAD 的 `key_events`、SCENE 的 `time_text`/`location` 自动被 `TemporalEventIndex` 提取到统一时间线，无需迁移。

---

## 展示层值类型渲染对照表

| content 值类型 | 判断条件 | 渲染方式 | 示例 |
|----------------|---------|---------|------|
| `string` 短文本 | `typeof val === 'string' && val.length < 50` | 键值对标签 | `身份: 韩门门主` |
| `string` 长文本 | `typeof val === 'string' && val.length >= 50` | 文本块 | `描述: 韩门少年...` |
| `string[]` | `Array.isArray(val) && typeof val[0] === 'string'` | 标签云 | `[隐忍, 坚韧]` |
| `{target, relation}[]` | `Array.isArray(val) && val[0]?.target` | 关系列表 | `韩松 (族叔)` |
| `{target, relation}[]` | `Array.isArray(val) && val[0]?.target` | 关系列表 | `韩松 (族叔)` |
| `{event, chapter_number?}[]` | `Array.isArray(val) && (val[0]?.事件 \|\| val[0]?.event)` | 时间线 | `8岁 离家学医` |
| `dict` | 非数组对象 | 群组展开 | `能力设定: {修为, 功法, ...}` |

**字段名特殊规则**（优先级高于值类型推断）：

| 字段名 | 强制渲染方式 |
|--------|-------------|
| `描述` | 文本块（textblock），无论长度 |
| `核心特质` | 标签云（tagcloud），即使 LLM 写了 string 也按逗号分割 |
| `key_events` | 时间线（timeline） |
| `角色弧线` | 群组展开（group） |

---

## 筛选层级

```
全部
├── 角色         → CHARACTER_ARC
├── 场景         → SCENE
├── 情节线       → PLOT_THREAD
├── 世界观       → WORLD_RULE
│   ├── ↳ 地点   → WORLD_RULE + sub_type=地点
│   ├── ↳ 势力   → WORLD_RULE + sub_type=势力
│   └── ↳ 纪年事件 → WORLD_RULE + sub_type=纪年事件
├── 笔记         → NOTE
├── 正文         → CHUNK
├── 结构设计     → OUTLINE / ARC_PLAN / VOLUME_PLAN / CHAPTER_PLAN
├── 叙述腔调     → NARRATIVE_VOICE
└── 主体意象     → THEMATIC_MOTIF
```

---

## 设计原则

1. **单一数据源**——不再有 `_display`，所有信息直接写入 content 字段
2. **HTML 面板不关心字段名**——只根据值类型自动渲染，新字段自动适配
3. **标准 schema 只约束普适字段**——流派适配字段由值类型推断自动处理
4. **类型无关的内容自动适配**——仙侠小说显示"修为/功法"，都市小说显示"职业/社会关系"，无需改代码
