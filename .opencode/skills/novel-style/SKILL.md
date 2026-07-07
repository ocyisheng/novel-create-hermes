---
name: "novel-style"
description: "写作风格提取与应用。从参考文本中提炼结构化风格特征，指导章节写作的风格一致性。触发词：风格、文风、模仿、风格提取、style、writing style、风格分析、提炼风格"
license: "MIT"
version: "2.2.0"
compatibility: "OpenCode"
tags: ["novel", "style", "infrastructure"]
---

# novel-style — 写作风格技能

本项目**风格管理的唯一入口**。其他技能禁止自行定义风格格式或提取逻辑。

## 架构

风格系统分为两个模式，均不依赖固定阶段，可在创作流程中随时按需调用。

| 模式 | 调用时机 | 产出 |
|------|---------|------|
| **提取模式** | 用户提供参考文本时（"模仿这个文风"、"用这个风格写"） | `styles/{名称}.yaml` + 写入 `config.yaml.活跃风格` |
| **验证模式** | 章节写作完成后需要检查风格一致性时 | 风格偏差报告 |

### 提取模式

用户提供 2-3 段参考文本，按 7 维度分析生成新风格定义。

工作流：
1. 接收参考文本后，调用 `task(subagent_type="general", load_skills=["novel-style"])` 让子 Agent 按 7 维度分析
2. 子 Agent 将分析结果写为 `styles/{名称}.yaml`
3. 编排层（novel-writer.md）通过 `edit` 修改 `config.yaml` 的 `活跃风格` 字段，指向新风格名称

如果没有参考文本，跳过提取，使用内置风格（默认"通俗网文风"）。

### 验证模式

章节写作完成后，检查已写章节与已激活风格的一致性。不生成新风格，只输出偏差报告。

工作流：
1. 调用 `task(category="ultrabrain", load_skills=["novel-v2"])` 让子 Agent 对比章节正文 vs 活跃风格
2. 输出 7 维度一致性评估报告
3. 报告可内联到质量检测结果中

仅在 `活跃风格` 非空时运行。

## 核心思想：prompt + 脚本分工

风格系统分为两类操作：需要 LLM 判断力的用 prompt 驱动，纯机械的用 novel-tool 自动化。

| 操作 | 驱动方式 |
|------|---------|
| 参考文本 → 分析 → style.yaml（提取模式） | `task(subagent_type="general", load_skills=["novel-style"])` |
| 章节 vs style.yaml → 一致性报告（验证模式） | `task(subagent_type="general", load_skills=["novel-v2"])` |
| 活跃风格读取 | `novel-tool --operation project.status`（返回 config 中的活跃风格） |
| 活跃风格设置 | 由编排层通过 `edit` 修改 `config.yaml` 的 `活跃风格` 字段 |

## 风格格式契约

风格数据以 YAML 文件存储在项目目录 `styles/` 下。格式由 `references/style_format.md` 定义。

### 核心约束

1. **总行数 ≤ 32**：保持 prompt 注入时的 token 效率
2. **7 个维度必须齐全**：`narrative_tone` `sentence_structure` `pacing` `dialogue_style` `vocabulary_register` `rhetorical_features` `forbidden_patterns`
3. **每个维度至少一个非空字段**
4. **参考文本原文不存储**：只在提取 prompt 中分析
5. **叙事腔调适用于叙述者**，不影响角色对话的个性化声音

风格存在的唯一目的：在章节写作时由 novel-v2-crafter 读取并注入到写作 prompt 中。

## 使用方式

### 提取模式：文本 → style.yaml（可选）

用户提供 2-3 段参考文本时触发。详细工作流见 `references/style_extraction.md`。

```
Step 1: task(subagent_type="general", load_skills=["novel-style"])
        → 子 Agent 按 7 维度分析参考文本 → write styles/{名称}.yaml

Step 2: 编排层通过 edit 修改 config.yaml 的 活跃风格 字段
        → 指向 styles/{名称}.yaml
```

> 此步骤可选。如果用户没有提供参考文本，跳过提取，使用内置风格（默认"通俗网文风"）。

### 验证模式：章节 vs style.yaml → 一致性报告

章节写作完成后触发。检查已写章节与已激活风格的一致性。

```
Step 1: task(subagent_type="general", load_skills=["novel-v2"])
        → 子 Agent 对比章节正文 vs 活跃风格 → 输出一致性报告

Step 2: 报告可内联到质量检测结果
        → 仅当 活跃风格 非空时运行
```

### 风格应用（章节写作时）

novel-v2-crafter 在写作时会自动从 `config.yaml` 读取 `活跃风格`，并从 `styles/` 或内置风格目录加载对应的 YAML 文件，将其 7 维度定义注入到写作 prompt 的 `### 活跃风格` 段。

### 风格切换

由编排层（novel-writer.md）通过 `edit` 修改 `config.yaml` 的 `活跃风格` 字段实现。

## 内建风格

`builtin/` 目录提供 22 个开箱即用的风格定义。**系统默认风格为「通俗网文风」**，新项目未指定风格时自动使用。

| 风格 | 文件名 | 适用场景 |
|------|--------|---------|
| **网文类** | | |
| 凡人修仙风 | `凡人修仙风.yaml` | 冷峻克制、实用主义修仙文 |
| 经典男频风 | `经典男频风.yaml` | 升级突破、装逼打脸、碾压对手 |
| 经典女频风 | `经典女频风.yaml` | 情感细腻，关系驱动 |
| 通俗网文风 | `通俗网文风.yaml` | 轻松口语、快节奏强爽感、通用娱乐（默认） |
| **武侠类** | | |
| 金庸武侠风 | `金庸武侠风.yaml` | 文白夹杂、第三人称全知 |
| 古龙武侠风 | `古龙武侠风.yaml` | 极简断句，留白如刀，冷峻浪漫 |
| 新派武侠风 | `新派武侠风.yaml` | 复合风格：融合金庸典雅与古龙锋利 |
| **古典类** | | |
| 古典名著风 | `古典名著风.yaml` | 世情冷暖，闲笔判词，日常见深意 |
| 历史演义风 | `历史演义风.yaml` | 庙堂权谋，沙场征伐，忠义韬略并重 |
| 神魔志怪风 | `神魔志怪风.yaml` | 奇诡瑰丽，亦庄亦谐，借妖魔写人 |
| 文艺古风 | `文艺古风.yaml` | 唯美抒情、古典韵味 |
| **近现代类** | | |
| 近现代名著风 | `近现代名著风.yaml` | 五四白话文学，洗练精准 |
| 鲁迅式风 | `鲁迅式风.yaml` | 冷峻犀利，刺世讥俗 |
| 老舍式风 | `老舍式风.yaml` | 京味鲜活，市井烟火 |
| 张爱玲式风 | `张爱玲式风.yaml` | 冷艳机锋，华丽苍凉 |
| **外国类** | | |
| 西方经典文学风 | `西方经典文学风.yaml` | 20世纪现代主义，冰山留白，反讽含蓄 |
| 俄罗斯文学风 | `俄罗斯文学风.yaml` | 深沉厚重，灵魂拷问 |
| 日本文学风 | `日本文学风.yaml` | 极简唯美，物哀留白 |
| 拉美魔幻风 | `拉美魔幻风.yaml` | 魔幻如常，百年孤独 |
| **通用类** | | |
| 纪实白描风 | `纪实白描风.yaml` | 客观冷静、近似报告文学 |
| 悬疑推理风 | `悬疑推理风.yaml` | 线索密织，反转迭出 |
| 都市现实风 | `都市现实风.yaml` | 当下日常，关系为核心 |

### 使用内置风格

内置风格按名称引用即可。novel-v2-crafter 在写作时会自动从 `builtin/` 目录加载对应的 YAML 文件。

## 参考文件

- `references/style_format.md` — style.yaml 7维度格式契约
- `references/style_extraction.md` — 文本→style.yaml 提取工作流
- `references/style_examples.md` — 多风格示例（few-shot 参考）


## HARD CONSTRAINTS

1. style.yaml 总行数 ≤ 32 — 超出则校验不通过
2. 7 个维度必须全部存在且命名精确匹配 — 缺一则校验不通过
3. 参考文本原文不写入项目 — 仅在提取 prompt 中临时使用
4. 风格是 passive guideline — 提供写作方向参考，不是 hard quality metric
