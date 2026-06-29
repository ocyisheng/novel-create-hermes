# Cross-Skill Contract：Grill 输出变量接口定义

此为 grill 输出变量的**唯一真实源**。所有技能通过变量名引用时以本文档为准。
修改变量名或语义时须同步更新本文档及所有引用方。

---

## 1. 变量清单

| 变量名 | 生产者 | 消费者 | 注入模式 | 类型 | 语义 |
|--------|--------|--------|---------|------|------|
| `{grill_需求}` | novel-grill | novel-ideation / novel-character / novel-chapter | `ideation` / `character` / `chapter` | 文本（用户确认的需求清单） | 创意方向、角色设定、写作方案 |
| `{grill_编辑方案}` | novel-grill | novel-edit | `entity-editor` / `chapter-edit-fuzzy` | 文本（编辑方案描述） | 用户确认的具体修改方向和范围 |
| `{grill_世界观需求}` | novel-grill | novel-worldbuilding | `worldbuilding` | 文本（世界观构建需求） | 用户对世界观规模、规则类型、势力格局的偏好 |
| `{grill_检测焦点}` | novel-grill | novel-quality | `quality-fuzzy` | 文本（检测重点描述） | 用户关心的检测维度（AI味/情节/角色/世界观等） |
| `{grill_写作方案}` | novel-grill | novel-chapter | `chapter`（编排层 §四 P8） | 文本（写作方案描述） | 用户对本章写作的具体要求 |

---

## 2. 引用说明

- **生产者**（novel-grill）：定义输出变量名，写入时决定将需求注入哪个槽位。
- **编排层**（novel-writer.md）：在 Task() prompt 中将变量内容注入对应 `{variable}` 槽位。
- **消费者**（各技能）：在 SKILL.md 或 prompt_template.md 中声明引用变量名。

---

## 3. 变更规则

1. **添加新变量** → 在本表新增一行，更新 producer SKILL.md（grill 模式映射）和 consumer SKILL.md（变量引用）
2. **修改变量名** → 必须同步更新：① 本文档 ② novel-grill/SKILL.md ③ 各 consumer SKILL.md ④ novel-writer.md
3. **删除变量** → 确认无 consumer 引用后移除，清理编排层脚本中的注入逻辑
