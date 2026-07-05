## TASK

为用户提供的参考文本提取写作风格特征，输出完整的风格定义文件 (`styles/{风格名称}.yaml`)。

## CONTEXT

### 参考文本

{参考文本}

## OUTPUT

1. 按 `references/style_format.md` 定义的 7 维度契约分析参考文本
2. 写入 `styles/{风格名称}.yaml`（相对于项目根目录）
3. 总行数 ≤ 32 行（不含注释行）

## ANALYSIS METHOD

通读全部参考文本后，逐维度分析：

| 维度 | 分析要点 |
|------|---------|
| `narrative_tone` | 叙述角度（第三人称/第一人称）、情感距离（冷峻/亲密）、作者评论频率 |
| `sentence_structure` | 平均句长、从句深度、长短句交替模式、节奏特征 |
| `pacing` | 详写对象（动作/心理/环境/对话）、略写对象（过渡/时间跳跃） |
| `dialogue_style` | 对话标签频率、对话间距、潜台词密度、个性化声音 |
| `vocabulary_register` | 语域（口语/书面/文白）、高频词、特色用词、禁区词 |
| `rhetorical_features` | 修辞手法清单及出现频率（比喻/排比/设问/白描等） |
| `forbidden_patterns` | 该风格不会出现的写法，列出 3-5 条具体模式 |

每个维度必须：
- 有 `description` 概括特征
- 有 `evidence` 引用参考文本中的具体句子（原文引用）

## HARD CONSTRAINTS

1. 总行数 ≤ 32 — 超出则 `style_manager.py validate` 会报错
2. 7 个维度必须全部存在且命名精确匹配 — 缺一则 validate 报错
3. 每个维度至少一个非空字段
4. `forbidden_patterns` 必须列出 3-5 条具体模式（用 natural language 描述，不要编码）
5. 参考文本原文不写入项目文件 — 仅在 prompt 中分析使用
6. 不创建 `excerpts/` 目录或任何临时文件
7. 不要凭空编造证据 — 每个声明必须有参考文本引用支撑
8. NO shortcut language — 不使用"考虑到时间和复杂性"等措辞
9. NO placeholder content — 不使用"[待补充]"或类似占位符
10. COMPLETENESS = SUCCESS — 不完整的输出 = 失败的任务

> 以下上下文由编排层通过 `extract_template.py` 注入。如果出现未填充的 `{变量名}`，说明编排层未提供该数据，请自行 read 获取。不要自己调用 extract_template.py。
