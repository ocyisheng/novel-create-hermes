---
name: "novel-ideation"
description: "创意构思：为小说创作提供灵感发散、约束管理、类型分析、创意评估。写作全程可呼叫。触发词：创意、构思、脑洞、灵感、没想法、没灵感、ideation、约束、模板、评估、类型"
license: "MIT"
version: "3.0.0"
compatibility: "OpenCode"
tags: ["novel", "ideation", "v2"]
---

# 创意构思技能（V2）

## 定位

本技能是 V2 架构下的创意构思方法论参考，供 `novel-ideation` subagent 在创作全程按需调用。不同于一次性的"初始创意生成"，本技能覆盖写作全过程中可能出现的创意卡点。

> 本技能**不处理** graph 写入或项目管理——那是 subagent prompt 和编排层的职责。本技能只提供方法论文档。

---

## 创意模式方法论

subagent 根据 `CREATIVE MODE` 参数选择对应的方法论：

### 1. divergent — 发散新方向

**场景**：完全没想法/需要全新故事概念

**流程**：
1. 约束应用（从 `constraints_library.md` 选取 3-5 个约束）
2. 类型定位（参考 `genres_compendium.md`）
3. 创意发散（参考 `ideation_techniques.md` 5 种技术）
4. 评估筛选（参考 `evaluation_criteria.md` 4 维度矩阵）

**输出**：3-5 个 NOTE 单元（`note_type=灵感`, `tag=creative_direction`）+ 评估报告 NOTE

### 2. constrained — 在已有框架内找突破

**场景**：有明确项目/设定，但需要新角度

**额外输入**：当前项目的已建单元列表（编排层通过 graph 查询传入）

**方法**：
1. 读取当前焦点单元 1 度邻居（已有角色/设定/情节线）
2. 识别"空白区域"（未被覆盖的约束或类型组合）
3. 在已有框架内生成 3 个不冲突的变体

**输出**：3 个 NOTE 单元（`tag=constrained_idea`），与焦点单元建立 `INSPIRES` 关系

### 3. enrich — 丰富现有单元

**场景**：角色太扁平/场景太单薄/世界观缺细节

**方法**：针对当前焦点类型应用特定丰富技术：

| 焦点类型 | 丰富方向 | 参考 |
|---------|---------|------|
| `character_arc` | 加秘密/加矛盾/加关系 | `genres_compendium.md` 角色建议 |
| `scene` | 加冲突层/加感官细节/加伏笔 | `ideation_techniques.md` 组合技术 |
| `world_rule` | 加二级子类/加历史/加文化细节 | `constraints_library.md` 设定约束 |
| `plot_thread` | 加子情节/加反转/加伏笔 | 交叉引用技术 |

**输出**：3 条具体改进建议 + 可选的 NOTE 单元

### 4. unblock — 写作卡点解锁

**场景**：写到一半写不下去

**诊断流程**：
1. 分析阻塞类型（不知道该写什么 / 有选择但不知道该选哪个 / 当前方向感觉不对）
2. 根据类型选择解锁策略：

| 阻塞类型 | 策略 |
|---------|------|
| 不知道该写什么 | 用 `constraints_library.md` 的反转密度/时间限定约束强制生成 |
| 有选择但犹豫 | 用 `evaluation_criteria.md` 快速评估各选项 |
| 方向感觉不对 | `ideation_philosophy.md` 的"约束即催化剂"重新定位 |

**输出**：阻塞分析 + 3 条解锁路径

### 5. cross_pollinate — 跨类型/知识库灵感

**场景**：当前方向写到瓶颈，需要外部刺激

**方法**：
1. 跨类型借概念（`genres_compendium.md` 附录A 融合方向）
2. 从知识库借元素（编排层注入知识库内容）
3. 应用约束组合的"化学反应测试"

**输出**：3 个跨域灵感方向

---

## 输出到 graph

subagent 在生成创意内容后，通过编排层提供的 API 写入 graph：

| 数据类型 | NOTE 字段 | 关系 |
|---------|----------|------|
| 创意方向 | `note_type=灵感`, `tag=creative_direction` | 与焦点单元 `INSPIRES` |
| 约束集 | `note_type=灵感`, `tag=constraint_set` | — |
| 评估报告 | `note_type=灵感`, `tag=evaluation` | 与创意方向 `REFERENCES` |
| 丰富建议 | `note_type=灵感`, `tag=enrichment` | 与目标单元 `INSPIRES` |
| 解锁路径 | `note_type=灵感`, `tag=unblock_plan` | 与阻塞单元 `INSPIRES` |

---

## 参考文件清单

### 核心方法论
- `references/constraints_library.md` — 30 个约束模板 + 类型概览 + 组合策略 + 模板原则
- `references/genres_compendium.md` — 5 大类型总览 + 融合指南 + 创新方向 + 故事结构
- `references/genres_quick_reference.md` — 类型快速诊断清单
- `references/evaluation_criteria.md` — 4 维评分矩阵 + 阈值配置 + 评估场景 + 输出示例
- `references/ideation_techniques.md` — 5 种创意生成技术
- `references/ideation_philosophy.md` — 创意构思哲学

### 类型深入（写作全程可用）
- `references/genre_fantasy.md` — 玄幻/修仙类型深入
- `references/genre_scifi.md` — 科幻/星际类型深入
- `references/genre_urban.md` — 都市/异能类型深入
- `references/genre_mystery.md` — 悬疑/推理类型深入
- `references/genre_history.md` — 历史/穿越类型深入

### 流程与示例
- `references/ideation_mode.md` — 创意需求分析流程 + 输出格式
- `references/combination_examples.md` — 约束组合示例
- `references/writing_mode.md` — 写作模式参考
