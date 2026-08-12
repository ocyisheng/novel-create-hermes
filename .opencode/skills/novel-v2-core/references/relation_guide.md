# 关系类型选用速查（26 种）

> 与 `graph_schema.py` 的 `RelationType` 枚举严格一致。关系方向由 `source`/`target` 表达（无独立 direction 字段）；反向边的物化由 **auto_reverse 三态** 决定（见下），`bidirectional=true` 或 `graph.fix_asymmetry` 仅对 `always`/`optional` 类型物理写入反向边（never 类不建反向）。每条边可带 `source_role`/`target_role`（端点角色，跟随端点不跟随边）与 `payload`（证据锚点 `source: auto|llm|manual` + 时态约定键）。

## 结构类（骨架：层级 / 归属）

| 类型 | 场景 | 示例 |
|------|------|------|
| CONTAINS / BELONGS_TO | 层级包含（卷→章→场景）；互为逆类型 | 黄枫谷卷 CONTAINS 第3章；第3章 BELONGS_TO 黄枫谷卷 |
| PLANS / PLANNED_BY | 章纲规划场景（规划意图，非结构归属） | 第3章纲 PLANS 后山对决 |
| IMPLEMENTS | 场景实现了哪条情节线 | 第3章场景 IMPLEMENTS 主线·末法觉醒 |
| REFINES | 对已有设定做精细化修订 | 新版力量体系 REFINES 旧版 |
| INSPIRES | 启发了创作 | 参考书 INSPIRES 世界观 |

## 叙事类（血肉：因果 / 时间 / 关联）

| 类型 | 场景 | 示例 |
|------|------|------|
| CAUSES | 因果关系 | 坠崖 CAUSES 得传承 |
| PRECEDES | 时间线先后 | 初遇 PRECEDES 结盟 |
| CONTRADICTS | 设定/情节矛盾（需解决） | 旧设定 CONTRADICTS 新设定 |
| IMPLIES | 弱隐含关联 | 废灵根 IMPLIES 修炼缓慢 |
| PARALLEL | 并列发生 | 主线与支线 PARALLEL |

## 角色 / 势力 / 事件

| 类型 | 场景 | 示例 |
|------|------|------|
| PARTICIPATES_IN | 角色出场场景 | 韩致 PARTICIPATES_IN 第3章 |
| POSSESSES / POSSESSED_BY | 角色持有物（物品/能力/法宝） | 韩致 POSSESSES 血晶 |
| CONTROLS / CONTROLLED_BY | 势力控制地域/组织 | 鬼雾谷 CONTROLS 黄枫谷 |
| MEMBER_OF / HAS_MEMBER | 角色属于势力/组织 | 林渊 MEMBER_OF 落云宗 |
| LOCATED_AT / LOCATION_OF | 场景/角色所在地点 | 后山对决 LOCATED_AT 黄枫谷 |
| HAS_EVENT / EVENT_OF | 实体挂载时间事件 | 林渊 HAS_EVENT 结丹日 |
| INVOLVES | 事件涉及角色 | 大典事件 INVOLVES 林昭 |

## 开放标签规则（重要）

- **具体语义**（师徒/母子/欠人情/同盟）→ 类型选最接近枚举 + `label` 字段承载语义。
  例：`rel_type="relates_to", label="同盟", source_role="盟主", target_role="盟友", bidirectional=true`
- **通用角色关系** → `RELATES_TO` + `label`。
- **非枚举输入自动降级**：代码层 `_resolve_rel_type` 会把未知字符串（如 `"师徒"`）降级为 `RELATES_TO` + `label`（**P0 起由原 REFERENCES 改为 RELATES_TO**），不会报错；查询时可用 `graph.get_relations(label="师徒")` 按语义找回（支持 `label_substring=true` 包含匹配）。

## auto_reverse 三态（决定反向边物化）

每条关系类型有 `auto_reverse` 属性，决定 `bidirectional=true` 与 `graph.fix_asymmetry` 的行为：

| 状态 | 含义 | 类型 |
|------|------|------|
| `always` | 对称/配对语义，双向成立 → 物化反向边 | 自反对称：RELATES_TO、CONTRADICTS、PARALLEL、PARTICIPATES_IN、INVOLVES；配对：POSSESSES↔POSSESSED_BY、CONTROLS↔CONTROLLED_BY、MEMBER_OF↔HAS_MEMBER、LOCATED_AT↔LOCATION_OF、HAS_EVENT↔EVENT_OF、PLANS↔PLANNED_BY |
| `optional` | 层级包含，一条边足够 → 默认不补，显式 `bidirectional=true` 才物化 | CONTAINS↔BELONGS_TO |
| `never` | 单向断言，A→B 不蕴含 B→A → 永不建反向（`bidirectional=true` 返回 warning） | CAUSES、PRECEDES、IMPLEMENTS、REFERENCES、IMPLIES、INSPIRES、REFINES |

**反向边翻转规则**（always/optional 物化时）：交换端点 + 类型取 `inverse`（自反类型不变）+ **role 跟随端点**（反向边 `source_role`=原 `target_role`，`target_role`=原 `source_role`）+ label/weight 保持。

- **自反类型**（`inverse == 自身`）：RELATES_TO、CAUSES、CONTRADICTS、REFERENCES、IMPLIES、PARALLEL、INSPIRES、REFINES、PRECEDES、PARTICIPATES_IN、INVOLVES、PLANS 等 → 反向边为同类型，`add_relation` 自动去重。
- **配对类型**（有独立逆类型）：CONTAINS↔BELONGS_TO、POSSESSES↔POSSESSED_BY、CONTROLS↔CONTROLLED_BY、MEMBER_OF↔HAS_MEMBER、LOCATED_AT↔LOCATION_OF、HAS_EVENT↔EVENT_OF、PLANS↔PLANNED_BY → `bidirectional=true` 会物理写入逆类型边。
- **无环配对**（CONTAINS/BELONGS_TO，optional）：`add_relation` 会做环检测拒绝成环；`fix_asymmetry` 跳过此类，避免自动制造环（由 R2 检查提示）。

## 证据锚点与时态（payload 约定键，P2 起）

- **证据锚点**：自动边（relation_inferrer / fix_asymmetry）写入 `payload.source="auto"` + 出处 `chapter`；`handle_add_relation` 按 actor 判定 `source="llm"`（novel-writer）或 `"manual"`（script/web-ui）。可用 `graph.get_relations` 读回 `payload` 溯源。
- **时态约定**（约定而非新字段）：`payload.start_chapter` / `end_chapter` / `resolve_chapter` 表达关系生效/结束/伏笔回收章节。`Relation.set_temporal_scope()` / `get_temporal_scope()` 为读写入口。

## 常用操作

```
# 建边（含双向物化 + 角色 + 证据通道自动标记）
novel-tool(operation="graph.add_relation", project="{P}", source="{A}", target="{B}", rel_type="relates_to", label="同盟", source_role="盟主", target_role="盟友", bidirectional=true, weight=0.8)

# 按语义标签查边
novel-tool(operation="graph.get_relations", project="{P}", label="师徒", label_substring=true)

# 按强度过滤查边（P2 新增）
novel-tool(operation="graph.get_relations", project="{P}", id="{A}", min_weight=0.5, max_weight=0.9)

# 补齐反向边（仅 always 类型；never/optional 跳过）
novel-tool(operation="graph.fix_asymmetry", project="{P}")

# 批量推断（新项目迁移后必做）
novel-tool(operation="graph.batch_infer", project="{P}")

# 更新单条边（label/weight/role/payload）
novel-tool(operation="graph.update_relation", project="{P}", id="{关系ID}", label="新标签", weight=0.9, payload='{"start_chapter":1,"resolve_chapter":50}')
```
