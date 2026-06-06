# 风格示例

以下提供不同文学流派的 style.yaml 示例，供 style_extraction 参考。

## 示例 1：金庸武侠风

```yaml
style_name: "金庸武侠风"
description: "金庸式叙事，文白夹杂，第三人称全知"

dimensions:
  narrative_tone:
    description: "第三人称全知，时有作者跳出点评，庄谐并重"
    keywords: ["全知视角", "庄谐并重", "偶尔评点"]

  sentence_structure:
    description: "长短交错，四字短语密集，对仗工整"
    avg_sentence_length: "mixed"
    characteristics: ["四字短语密集", "对仗", "文白夹杂"]

  pacing:
    description: "比武/惊险处极细（一招一式），过渡段极简"
    pattern: "武打慢镜头 + 叙事快进交替"

  dialogue_style:
    description: "话中有话，少修饰语，多用语气词和称谓"
    attribution_pattern: "极少标签，靠语气词区分说话人"
    speech_patterns: ["语气词丰富", "称谓密集"]

  vocabulary_register:
    description: "文白夹杂，大量成语典故，历史专有名词"
    register_level: "literary"
    distinctive_vocab: ["但见", "当下", "喝道", "心道"]
    forbidden_vocab: ["现代科技术语", "西式长句"]

  rhetorical_features:
    description: "比喻多（武功/自然景物），排比用于武打场面"
    devices: ["明喻", "排比", "设问"]

  forbidden_patterns:
    patterns: ["现代口语网络梗", "西式长从句嵌套", "抽象心理独白"]
```

## 示例 2：凡人流修仙风

```yaml
style_name: "凡人修仙风"
description: "冷峻克制，实用主义修仙，第三人称有限视角"

dimensions:
  narrative_tone:
    description: "冷峻克制，极少修辞，贴着主角视线走"
    keywords: ["克制", "实用主义", "有限视角"]

  sentence_structure:
    description: "短句为主，少用复合句，句间靠动作推进"
    avg_sentence_length: "short"
    characteristics: ["短句密集", "少关联词", "动作链驱动"]

  pacing:
    description: "修炼过程极详（灵药炼制、突破瓶颈），战斗快节奏"
    pattern: "修炼慢镜头 + 战斗快切"

  dialogue_style:
    description: "直白简练，少修饰语，对话自带信息量"
    attribution_pattern: "极少标签，仅'说''道'"
    speech_patterns: ["信息密集型", "少有废话"]

  vocabulary_register:
    description: "朴素口语，力量体系术语精准，少成语"
    register_level: "colloquial"
    distinctive_vocab: ["灵力", "瓶颈", "法器", "灵根"]
    forbidden_vocab: ["文艺腔渲染", "现代网络用语"]

  rhetorical_features:
    description: "几乎不用修辞，以白描和动作推进叙事"
    devices: ["白描"]

  forbidden_patterns:
    patterns: ["过长心理独白", "情感渲染", "环境抒情"]
```

## 示例 3：简练白描风（个人写作）

```yaml
style_name: "简练白描风"
description: "干净利落，每句承载信息，极少修饰"

dimensions:
  narrative_tone:
    description: "客观冷静，极少作者介入，贴着事实走"
    keywords: ["客观", "冷静", "事实驱动"]

  sentence_structure:
    description: "极端短句，一段一句居多，无从句嵌套"
    avg_sentence_length: "short"
    characteristics: ["一段一句", "无从句", "动词密集"]

  pacing:
    description: "均衡推进，无明显详略差异，每段一个信息点"
    pattern: "匀速推进"

  dialogue_style:
    description: "最简标签，对话与行动交替"
    attribution_pattern: "\"说\"\"问\"\"道\"三字标签"
    speech_patterns: ["简短回复", "无大段独白"]

  vocabulary_register:
    description: "日常口语，精确具体，拒绝抽象"
    register_level: "colloquial"
    distinctive_vocab: ["具体名词和动词"]
    forbidden_vocab: ["抽象情感词", "评价性形容词"]

  rhetorical_features:
    description: "不用修辞，纯事实叙述"
    devices: []

  forbidden_patterns:
    patterns: ["修辞性比喻", "情绪渲染", "长定语修饰", "从句嵌套"]
```

## 使用说明

这些示例展示了 7 维度在不同风格中的典型填法。style_extraction 在分析用户文本时，
应参考这些示例的维度和深度来输出 style.yaml。

同一项目可以有多个风格定义文件（如"战斗场面风""日常叙述风"），
但同一时间只有 active_style 指定的那一个生效。
