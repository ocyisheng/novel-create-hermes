# 关系类型选用速查（26 种）

> 与 `graph_schema.py` 的 `RelationType` 枚举严格一致。关系方向由 `source`/`target` 表达（无独立 direction 字段）；`bidirectional=true` 或 `graph.fix_asymmetry` 会**物化**反向边（物理写入，非虚拟推导）。

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
  例：`rel_type="relates_to", label="同盟", bidirectional=true`
- **通用角色关系** → `RELATES_TO` + `label`。
- **非枚举输入自动降级**：代码层 `_resolve_rel_type` 会把未知字符串（如 `"师徒"`）降级为 `REFERENCES` + `label`，不会报错；查询时可用 `graph.get_relations(label="师徒")` 按语义找回（P2-6 新增 label 过滤，支持 `label_substring=true` 包含匹配）。

## 自反 vs 配对（决定 bidirectional 行为）

- **自反类型**（`inverse == 自身`）：RELATES_TO、CAUSES、CONTRADICTS、REFERENCES、IMPLIES、PARALLEL、INSPIRES、REFINES、PRECEDES、PARTICIPATES_IN、INVOLVES、PLANS 等 → 反向边为同类型，`add_relation` 自动去重。
- **配对类型**（有独立逆类型）：CONTAINS↔BELONGS_TO、POSSESSES↔POSSESSED_BY、CONTROLS↔CONTROLLED_BY、MEMBER_OF↔HAS_MEMBER、LOCATED_AT↔LOCATION_OF、HAS_EVENT↔EVENT_OF、PLANS↔PLANNED_BY → `bidirectional=true` 会物理写入逆类型边。
- **无环配对**（CONTAINS/BELONGS_TO）：`add_relation` 会做环检测拒绝成环；`fix_asymmetry` 跳过此类，避免自动制造环（由 R2 检查提示）。

## 常用操作

```
# 建边（含双向物化）
novel-tool(operation="graph.add_relation", project="{P}", source="{A}", target="{B}", rel_type="relates_to", label="同盟", bidirectional=true, weight=0.8)

# 按语义标签查边（P2-6 新增）
novel-tool(operation="graph.get_relations", project="{P}", label="师徒", label_substring=true)

# 补齐反向边（跳过无环配对类型）
novel-tool(operation="graph.fix_asymmetry", project="{P}")

# 批量推断（新项目迁移后必做）
novel-tool(operation="graph.batch_infer", project="{P}")

# 更新单条边
novel-tool(operation="graph.update_relation", project="{P}", id="{关系ID}", label="新标签", weight=0.9, payload='{"status":"敌对"}')
```
