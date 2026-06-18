# style.yaml 格式契约

所有风格定义文件必须遵循以下 7 维度结构，总行数 ≤ 32。

## 契约

```yaml
# novels/{项目名}/styles/{名称}.yaml
style_name: ""           # 必填，人类可读名称
description: ""           # 必填，一句话描述 ≤ 30 字
category: ""              # 推荐，大类标签：网文/武侠/古典/近现代/外国/通用

dimensions:               # 必填，全部 7 个维度
  narrative_tone:         # 叙事基调
    description: ""       # 必填
    keywords: []          # 必填，3-5 个关键词
    example: ""           # 推荐，具体示例（1-2句话）

  sentence_structure:     # 句子结构
    description: ""       # 必填
    avg_sentence_length: "short|medium|long|mixed"  # 必填
    characteristics: []   # 必填
    example: ""           # 推荐，具体句式示例

  pacing:                 # 节奏
    description: ""       # 必填
    pattern: ""           # 必填
    example: ""           # 推荐，节奏模式示例

  dialogue_style:         # 对话风格
    description: ""       # 必填
    attribution_pattern: ""  # 必填
    speech_patterns: []   # 必填
    example: ""           # 推荐，典型对话示例

  vocabulary_register:    # 词汇选择
    description: ""       # 必填
    register_level: "literary|colloquial|mixed"  # 必填
    distinctive_vocab: [] # 必填
    forbidden_vocab: []   # 必填

  rhetorical_features:    # 修辞特征
    description: ""       # 必填
    devices: []           # 必填

  forbidden_patterns:     # 禁止模式
    patterns: []          # 必填，至少 3 条
    example: ""           # 推荐，违反示例
```

## 约束

1. 总行数 ≤ 32（包括注释和空行）
2. 每个维度至少有一个非空字段
3. 7 个维度必须全部存在且命名精确匹配
4. 参考文本原文不存储在 style.yaml 中（仅在提取 prompt 中分析）
5. 风格定义的叙事腔调适用于叙述者，不影响角色对话的个性化声音

## 示例字段说明

`example` 字段为推荐字段，用于提供该维度的具体写作示例，帮助 LLM 更准确地执行风格要求。

**示例格式要求**：
- `sentence_structure.example`：具体句式，如"他抬手。灵力涌出。法器碎裂。"
- `dialogue_style.example`：典型对话，如"灵石不够。够了。不够。"
- `pacing.example`：节奏模式，如"【修炼】详细描写炼丹过程（3-5句）→【战斗】3句内结束"
- `forbidden_patterns.example`：违反示例，如"避免：过长心理独白（超过2句）、情感渲染"
- `narrative_tone.example`：典型段落，如"他站在山顶，望着远方。风起。云涌。"
