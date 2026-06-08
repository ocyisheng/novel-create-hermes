# 风格提取工作流

从用户提供的参考文本中提取写作风格特征，输出 style.yaml。

## 流程

### Step A — prompt 驱动（子 Agent 分析）

```
task(category="artistry", load_skills=["novel-style"],
     prompt="
## TASK
为用户提供的参考文本提取写作风格特征。

## INPUT
用户提供的 2-3 段参考文本（内联在 prompt 中）。

## OUTPUT
按 style_format.md 7 维度契约分析，输出完整的 style.yaml。写入 styles/{用户命名}.yaml。

## ANALYSIS METHOD
1. 通读全部参考文本，建立整体风格感觉
2. 逐维度分析：
   - narrative_tone：从叙述角度、情感距离、作者评论频率判断
   - sentence_structure：随机取 5 句，统计平均长度、从句深度、节奏模式
   - pacing：观察哪些内容详写（动作/心理/环境？），哪些略写（过渡/时间跳跃？）
   - dialogue_style：统计对话标签频率、回复间距、潜台词密度
   - vocabulary_register：提取高频词和禁区词，判断语域
   - rhetorical_features：统计比喻/排比/设问/白描等手法的出现频率
   - forbidden_patterns：反向分析——这种风格不会出现的写法
3. 每个维度输出 description + 证据（引用文本具体句子）作为注释

## CONSTRAINTS
- 总行数 ≤ 30
- 每个维度必须有 evidence 支撑
- forbidden_patterns 必须列出 3-5 条
- 参考文本原文不写入项目（仅在 prompt 中分析）
- 不创建 excerpts/ 目录

## MUST NOT
- 不存储原始参考文本到项目
- 不凭空编造证据（每个声明必须有文本引用）
")
```

### Step B — 脚本驱动（编排层自动维护）

```
# 验证结构
python .opencode/skills/novel-style/scripts/style_manager.py validate \
  --file styles/{用户命名}.yaml

# 若验证失败 → 提示子 Agent 修正
# 若验证通过 → 注册 + 激活
python .opencode/skills/novel-style/scripts/style_manager.py register \
  --project-root {项目路径} --name "{用户命名}" --file styles/{用户命名}.yaml

python .opencode/skills/novel-style/scripts/style_manager.py activate \
  --project-root {项目路径} --name "{用户命名}"
```

## 注意事项

- 编排层不再手动 edit config.yaml / write index.yaml——全部由脚本完成
- 风格提取是一次性操作，由编排层直接调度
- 提取后用户可随时重新提取覆写现有风格
