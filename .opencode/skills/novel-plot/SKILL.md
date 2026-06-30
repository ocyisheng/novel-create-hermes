---
name: "novel-plot"
description: "情节构建：设计主线与支线情节、伏笔规划。触发词：情节、主线、支线、故事线、伏笔"
license: "MIT"
version: "1.0.0"
compatibility: "OpenCode"
tags: ["novel", "plot", "thread"]
---

# 情节构建技能

## 核心职责

按编排 Agent 传入的 CONTEXT 执行情节构建任务（P5）。设计主线+支线，并生成全局伏笔规划。

> **路径说明**：下文所有 `{PROJECT_PATH}` 替换为编排层 CONTEXT 中传入的 `PROJECT PATH` 值。

## 上下文契约

编排层在调用本技能前按以下清单加载上下文：

|槽位|文件路径|提取字段|加载方式|
|------|---------|---------|---------|
|总纲|`outline/总纲.yaml`|`幕结构` `分卷` `关键事件` `节奏安排`|`read` 全文件|
|叙事策略|`outline/叙事策略.yaml`|`信息分配.戏剧反讽` `信息分配.悬念管理` `叙事手法`|`read` 全文件|
|已有情节线|`outline/情节线/*.yaml`|每条线的 `索引信息.实体ID`|`glob` + `read` 摘要段|
|情节线进度|`outline/追踪/情节线进度.yaml`|进度列表|`read` 筛选活跃线|
|时间线设计|`outline/时间线设计.yaml`|`时间线设计` 段（如存在，作为伏笔设置的时序参考）|`read` 全文件|

输出：
- `outline/情节线/主线.yaml` + `outline/情节线/支线_{名称}.yaml`，参见 `assets/plot_thread.yaml` 模板
- `outline/伏笔规划.yaml`，参见 `assets/foreshadowing_plan.yaml` 模板
- `outline/情节线/主索引.yaml`（可选），参见 `assets/plot_index.yaml` 模板

## 情节线设计

### 设计决策一：底层驱动力

每条情节线设计时先判断它的底层驱动方式——这决定伏笔规划的密度和回收策略：

|驱动方式|内核|适用场景|伏笔策略|
|---------|------|---------|---------|
|**故事驱动**（"然后呢"）|悬念驱动|冒险型支线、悬疑主线|伏笔密度高，按时回收|
|**情节驱动**（"为什么"）|因果驱动|社会派、心理向主线|伏笔可以有落空/误解型回收|

注意：因果律超出界限时人物沦为牺牲品。精密情节可能成为"盲目崇拜"——人物有自己的"秘密生活"，会抗拒情节的逻辑约束。

### 设计决策二：复调结构

在情节线上层叠两重意义——表面情节（读者以为这是A）与反讽潜流（实际指向B）：
- **主线**：高大叙事/卑微现实并置形成反讽对照
- **支线**：作为主线的反讽镜像——同一事件的不同视角彼此拆解
- **伏笔**：对应"反讽型伏笔"——回收时揭示真相与表面认知的落差

## 伏笔规划

伏笔不必全部"兑现"。以下4种回收类型，在 `伏笔规划.yaml` 的每个条目中标记：

|类型|回收方式|效果|来源|
|------|---------|------|------|
|精准型|如约兑现，因果清晰|满足期待|—|
|落空型|预示但未发生|荒谬/讽刺|预言术降格|
|误解型|读者/角色理解偏差|意外的真实||
|悬置型|开放式不回收|保持开放||

**松散与巧合的正当性**：情节中的偶然性不是缺陷。巧合是传奇的识别证，伏笔是巧合的掩护——"假'前'为因，假'后'为果"。在情节线主索引中标记每章的"松散度"许可区间。

## 输出文件一览

|文件|模板|写入方式|
|------|------|---------|
|`outline/情节线/主线.yaml`|`assets/plot_thread.yaml`|`write` / `edit`|
|`outline/情节线/支线_{名称}.yaml`|`assets/plot_thread.yaml`|`write` / `edit`|
|`outline/伏笔规划.yaml`|`assets/foreshadowing_plan.yaml`|`write`|
|`outline/情节线/主索引.yaml`（可选）|`assets/plot_index.yaml`|`write`|

## 写后处理（chain: `entity-plot`）

输出写入后编排层自动执行以下脚本：

```bash
# 1. YAML 格式修正
python .opencode/shared/fix_yaml_indent.py "outline/{新文件路径}"

# 2. 实体格式校验
python .opencode/shared/validate_entity_format.py --project-root {PROJECT_PATH}

# 3. 项目索引重建
python .opencode/shared/rebuild_project_index.py --project-root {PROJECT_PATH}

# 4. 情节线进度重建
python .opencode/shared/rebuild_plot_progress.py --project-root {PROJECT_PATH}

# 5. 阶段切换（P5→P6 情节→分卷）
python .opencode/shared/config_manager.py set 当前阶段 "分卷大纲生成" --project-root {PROJECT_PATH}
```

> **禁止**：不要用 `edit`/`write` 手工修正 YAML 缩进或格式——交给 fix_yaml_indent.py 统一处理。你写完文件、标记好内容即可，脚本会自动格式化。

## 参考文件

- `references/plot_examples.md` — 情节设计示例
- `references/foreshadowing.md` — 伏笔设计参考
- `assets/plot_thread.yaml` — 情节线模板
- `assets/foreshadowing_plan.yaml` — 伏笔规划模板
- `assets/plot_index.yaml` — 主索引模板

## HARD CONSTRAINTS

> 约束已移入 `templates/prompt_template.md`。编排层通过 `extract_template.py` 加载模板时一并注入。
