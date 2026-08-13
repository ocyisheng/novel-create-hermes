# 质量检查方法论（创作流程内嵌）

> 本文件承载质量检查的完整方法论：设计原则、各场景校验关注点、统计信号裁决提示词。
> 机械调用指引（何时调用 `graph.quality_check`）见 SKILL.md「质量检查」章节。

## 设计原则

- **轻量**：不打断创作流，快速检查
- **嵌入式**：集成到现有写作步骤中
- **可选**：用户可跳过质检直接继续

## 1. 章节写作后自动质检

写完章节（`graph.create_unit` 创建 CHUNK）后，顺手执行：

```
# 获取质量检查结果
novel-tool(operation="graph.quality_check", project="{PROJECT}", layers="mechanical,statistical")
```

**输出格式**：
```
✅ 章节已写入
📋 质量摘要：
  - 机械检查：{N} 个问题（{error} 个错误，{warning} 个警告）
  - 统计信号：{M} 个信号需关注
```

**处理逻辑**：
- 如果有 `error` 级别问题：提示用户，但不阻塞
- 如果有 `warning` 级别问题：简要列出，建议用户关注
- 如果只有 `info` 或无问题：简单告知"质量检查通过"

## 2. 角色创建后校验

创建角色（`graph.create_unit` 创建 CHARACTER_ARC）后，检查关系完整性：

```
# 检查角色关系
novel-tool(operation="graph.quality_check", project="{PROJECT}", layers="mechanical")
```

**关注点**：
- R2: 关系不对称（角色 A→B 但 B→A 缺失）
- R3: 孤立单元（新角色没有任何关系）

## 3. 世界观规则创建后校验

创建世界观规则（`graph.create_unit` 创建 WORLD_RULE）后，检查自洽性：

```
# 检查世界观一致性
novel-tool(operation="graph.quality_check", project="{PROJECT}", layers="mechanical")
```

**关注点**：
- 规则之间的逻辑矛盾
- 规则与已有设定的冲突

## 4. 统计信号裁决

当统计检测返回信号时，按以下提示词裁决：

**R7 位置变化信号**：
```
检测到角色位置变化：{from_location} → {to_location}
请判断：这是合理的剧情推进，还是可能的设定矛盾？
```

**R10 节奏单调信号**：
```
检测到节奏可能过于均匀（标准差: {std}）
请判断：这是有意的叙事节奏，还是需要调整？
```

**R11 密度偏离信号**：
```
检测到第{chapter}章场景数偏离均值（{count} vs 均值{mean}）
请判断：这是高潮/过渡章节的正常安排，还是结构问题？
```

**R12 主角能动性信号**：
```
检测到主角可能过于被动（主动比例: {ratio}）
请判断：这是角色性格设定，还是需要增强主角行动？
```