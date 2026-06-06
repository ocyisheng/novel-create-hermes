---
name: "novel-style"
description: "写作风格提取与应用。从参考文本中提炼结构化风格特征，指导章节写作的风格一致性。触发词：风格、文风、模仿、风格提取、style、writing style、风格分析、提炼风格"
license: "MIT"
version: "2.0.0"
compatibility: "OpenCode"
tags: ["novel", "style", "infrastructure"]
---

# novel-style — 写作风格技能

本项目**风格管理的唯一入口**。其他技能禁止自行定义风格格式或提取逻辑。

## 核心思想：prompt + 脚本分工

风格系统分为两类操作：需要 LLM 判断力的用 prompt 驱动，纯机械的用脚本自动化。

| 操作 | 驱动方式 | 工具 |
|------|---------|------|
| 参考文本 → 分析 → style.yaml | prompt | `task(category="artistry", load_skills=["novel-style"])` |
| 章节 vs style.yaml → 一致性报告 | prompt | `task(category="ultrabrain", load_skills=["novel-quality"])` |
| style.yaml 结构验证 | 脚本 | `python scripts/style_manager.py validate` |
| styles/index.yaml 条目维护 | 脚本 | `python scripts/style_manager.py register` |
| config.yaml 活跃风格 读写 | 脚本 | `python scripts/style_manager.py activate` |
| 风格清单查询 | 脚本 | `python scripts/style_manager.py list` |

编排层（novel-writer.md）通过 bash 调用脚本完成机械操作，不对项目配置文件和索引文件手动 `edit`。

## 风格格式契约

风格数据以 YAML 文件存储在项目目录 `styles/` 下。格式由 `references/style_format.md` 定义。

### 核心约束

1. **总行数 ≤ 30**：保持 prompt 注入时的 token 效率
2. **7 个维度必须齐全**：`narrative_tone` `sentence_structure` `pacing` `dialogue_style` `vocabulary_register` `rhetorical_features` `forbidden_patterns`
3. **每个维度至少一个非空字段**
4. **参考文本原文不存储**：只在提取 prompt 中分析
5. **叙事腔调适用于叙述者**，不影响角色对话的个性化声音

风格存在的唯一目的：在 P7 章节写作时由 novel-writer.md 读取并注入到写作 prompt 中。

## 使用方式

### 风格提取（文本 → style.yaml）

用户提供 2-3 段参考文本，Agent 通过 P2.5 触发提取流程。详细工作流见 `references/style_extraction.md`。

```
Step A: task(category="artistry", load_skills=["novel-style"])
        → 子 Agent 按 7 维度分析 → write styles/{名称}.yaml

Step B: bash style_manager.py validate → register → activate
        → 脚本自动维护 index.yaml 和 config.yaml
```

### 风格应用（P7 写作时）

使用 `render_style.py` 将 style.yaml 转换为写作 prompt 中的 STYLE REFERENCE 段：

```bash
python .opencode/skills/novel-style/scripts/render_style.py \
    --style styles/{active_style}.yaml --mode chapter
```

输出可直接内联到章节写作 prompt 中。详见 `novel-chapter/templates/prompt_template.md` §STYLE REFERENCE。

### 风格一致性检查（P8 质量检测时）

```bash
python .opencode/skills/novel-style/scripts/render_style.py \
    --style styles/{active_style}.yaml --mode check
```

输出为 7 维度评估表，可内联到质量检测 prompt。仅当 `active_style` 非空时运行。

## 脚本说明

| 脚本 | 功能 |
|------|------|
| `style_manager.py` | 6 子命令：register / validate / activate / deactivate / list / builtin |
| `render_style.py` | 将 style.yaml 渲染为 LLM 提示词块（chapter / check 两种模式） |

### 子命令

```
register   --project-root PATH --name NAME --file FILE
           → 注册风格到 styles/index.yaml

validate   --file FULL_PATH
           → 验证 style.yaml：7维度齐全 + ≤30行 + 合法YAML

activate   --project-root PATH --name NAME
           → 设置 config.yaml 活跃风格（支持内置风格名称，无需先 copy）

deactivate --project-root PATH
           → 清除 config.yaml 活跃风格

list       --project-root PATH [--include-builtin]
           → 列出项目风格；加 --include-builtin 同时显示内置风格

builtin    list
           → 列出 skill 包内建风格

builtin    copy --project-root PATH --name NAME
           → 将内建风格复制到项目的 styles/ 目录（通常不需要，直接 activate 即可）
```

## 内建风格

`builtin/` 目录提供 22 个开箱即用的风格定义，覆盖六大类别。**系统默认风格为「通俗网文风」**，新项目未指定风格时自动使用。

| 风格 | 文件名 | 适用场景 |
|------|--------|---------|
| **网文类** | | |
| 凡人修仙风 | `凡人修仙风.yaml` | 冷峻克制、实用主义修仙文 |
| 经典男频风 | `经典男频风.yaml` | 快节奏强爽感，升级打脸 |
| 经典女频风 | `经典女频风.yaml` | 情感细腻，关系驱动 |
| 通俗网文风 | `通俗网文风.yaml` | 轻松口语、快节奏高爽感 |
| **武侠类** | | |
| 金庸武侠风 | `金庸武侠风.yaml` | 文白夹杂、第三人称全知 |
| 古龙武侠风 | `古龙武侠风.yaml` | 极简断句，留白如刀，冷峻浪漫 |
| 新派武侠风 | `新派武侠风.yaml` | 文白兼具现代感，意境与动作并重 |
| **古典类** | | |
| 古典名著风 | `古典名著风.yaml` | 明清章回体，说书人口吻 |
| 历史演义风 | `历史演义风.yaml` | 宏大史诗，文白庄重，权谋韬略 |
| 神魔志怪风 | `神魔志怪风.yaml` | 奇诡瑰丽，亦庄亦谐，借妖魔写人 |
| 文艺古风 | `文艺古风.yaml` | 唯美抒情、古典韵味 |
| **近现代类** | | |
| 近现代名著风 | `近现代名著风.yaml` | 五四白话文学，洗练精准 |
| 鲁迅式风 | `鲁迅式风.yaml` | 冷峻犀利，刺世讥俗 |
| 老舍式风 | `老舍式风.yaml` | 京味鲜活，市井烟火 |
| 张爱玲式风 | `张爱玲式风.yaml` | 冷艳机锋，华丽苍凉 |
| **外国类** | | |
| 西方经典文学风 | `西方经典文学风.yaml` | 简洁克制，反讽含蓄 |
| 俄罗斯文学风 | `俄罗斯文学风.yaml` | 深沉厚重，灵魂拷问 |
| 日本文学风 | `日本文学风.yaml` | 极简唯美，物哀留白 |
| 拉美魔幻风 | `拉美魔幻风.yaml` | 魔幻如常，百年孤独 |
| **通用类** | | |
| 纪实白描风 | `纪实白描风.yaml` | 客观冷静、近似报告文学 |
| 悬疑推理风 | `悬疑推理风.yaml` | 线索密织，反转迭出 |
| 都市现实风 | `都市现实风.yaml` | 当下日常，关系为核心 |

使用方式：
```bash
# 直接使用内置风格（无需 copy）
python .opencode/skills/novel-style/scripts/style_manager.py activate \
  --project-root NOVELS_ROOT/项目名 --name "凡人修仙风"

# 查看所有可用风格（含内置）
python .opencode/skills/novel-style/scripts/style_manager.py list \
  --project-root NOVELS_ROOT/项目名 --include-builtin

# 需要自定义时，先复制再修改
python .opencode/skills/novel-style/scripts/style_manager.py builtin copy \
  --project-root NOVELS_ROOT/项目名 --name "凡人修仙风"
# 然后编辑 styles/凡人修仙风.yaml 按需调整
```

## 参考文件

- `references/style_format.md` — style.yaml 7维度格式契约
- `references/style_extraction.md` — 文本→style.yaml 提取工作流
- `references/style_examples.md` — 多风格示例（few-shot 参考）

## 与现有技能的边界

| 技能 | 负责 | 不负责 |
|------|------|--------|
| novel-style | 格式定义 + 提取工作流 + 脚本维护 + 应用/检查规范 | 实际写作、实际质量检测 |
| novel-chapter | 写章节时遵循 prompt 中的写作约束 | 定义 style.yaml 格式 |
| novel-quality | 执行风格一致性检查（通过 prompt） | 定义检查维度和标准 |
| novel-writer.md | 检测 活跃风格 → 加载注入 prompt → 调度检查 | 定义风格数据 |

## HARD CONSTRAINTS

1. style.yaml 总行数 ≤ 30 — 超出则 validate 报错
2. 7 个维度必须全部存在且命名精确匹配 — 缺一则 validate 报错
3. 参考文本原文不写入项目 — 仅在提取 prompt 中临时使用
4. styles/index.yaml 仅由 style_manager.py 维护 — 禁止 Agent 手动 write/edit
5. 活跃风格 字段仅由 style_manager.py activate/deactivate 修改 — 禁止 Agent 手动 edit config.yaml
6. 风格是 passive guideline — 提供写作方向参考，不是 hard quality metric

