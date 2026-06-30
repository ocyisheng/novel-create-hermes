---
name: "novel-character"
description: "角色创建：创建角色档案，包含性格、背景、能力、成长弧线等。触发词：角色、人物、创建角色、主角、配角"
license: "MIT"
version: "1.0.0"
compatibility: "OpenCode"
tags: ["novel", "character", "entity"]
---

# 角色创建技能

## 核心职责

按编排 Agent 传入的 CONTEXT 执行角色创建任务（P3）。创建角色档案的 YAML 实体文件。

> **路径说明**：下文所有 `{PROJECT_PATH}` 替换为编排层 CONTEXT 中传入的 `PROJECT PATH` 值。

## 上下文契约

编排层在调用本技能前按以下清单加载上下文：

|槽位|文件路径|提取字段|加载方式|
|------|---------|---------|---------|
|创意方案|`ideation/最终创意方案.yaml`|`最终方案.主角设定` `最终方案.核心冲突`|`read` 全文件|
|总纲|`outline/总纲.yaml`|`关键角色` `关系网`|`read` 全文件|
|已有角色|`project_index.yaml`|`characters` 段（已有角色名 + `type` `status`）|`read` 避免重复创建|

## 角色创建

创建角色前先完成两个理论决策，再将结果填入模板。

### 决策一：扁平还是圆形

创建每个角色前先判断其类型：

**扁平人物（flat character）**：基于单一观念或品质塑造，可用一句话概括。狄更斯是使用扁平人物的大师——"密考伯太太说'我永远不会抛弃密考伯先生'"——易辨识、易记忆、从不跑掉。功能：幽默感、适度心、类型化配角。

**圆形人物（round character）**：能以令人信服的方式让读者感到意外。检验标准："能否以令人信服的方式让我们感到意外？"。奥斯丁的人物看似扁平实则高度有机，在情节需要时能扩展为圆形（如伯特伦夫人的道德觉醒）。陀思妥耶夫斯基的人物全属圆形。

**决策规则**：主角和关键配角必为圆形；功能性配角可用扁平。但扁平人物注入作者的浩瀚活力后也可获得深度人性效果（狄更斯证明了这一点）。复杂的小说同时需要两者。

### 决策二：为"自动性"预留空间

《老残游记》中妓女翠环揭示了一种"自动装置"——角色一旦被请进小说便有自身意志，作者无法随意驱遣。

> "一部作品中确有由不得作者操控的自动装置。"

刘鹗之子刘大绅评翠环："此则本从无意，因文势所逼，写成有意。"角色弧线设计时不应过度控制角色的每一步发展，应留下"文势所逼"的空间。如果角色在设计中开始"反抗"你的安排、表现出预料之外的言行——"请神容易送神难"——这通常是角色成功的标志。

**注意事项**：角色不必讨好读者或符合道德典范。世事一无可知（契诃夫），艺术家不做裁判官，做公平的证人。好的角色往往"由不得作者操控"。如果角色开始反抗你的安排——那是活过来的标志。

### 输出

`characters/{角色名}.yaml` — 按 `assets/character.yaml` 模板。角色弧线（起始→变化→最终）为必填字段。弧线设计中自动纳入上述两个决策的结果。

## 参考

- `references/character_types.md` — 角色类型与设计原则
- `references/character_profile_example.md` — 角色档案示例
- `assets/character.yaml` — 角色模板

## 写后处理（chain: `entity-base`）

输出写入后编排层自动执行以下脚本：

```bash
# 1. YAML 格式修正
python .opencode/shared/fix_yaml_indent.py "characters/{新文件名}.yaml"

# 2. 实体格式校验
python .opencode/shared/validate_entity_format.py --project-root {PROJECT_PATH}

# 3. 项目索引重建
python .opencode/shared/rebuild_project_index.py --project-root {PROJECT_PATH}

# 4. 阶段切换（P3→P4 角色创建→总纲撰写）
python .opencode/shared/config_manager.py set 当前阶段 "总纲撰写" --project-root {PROJECT_PATH}
```

> **禁止**：不要用 `edit`/`write` 手工修正 YAML 缩进或格式——交给 fix_yaml_indent.py 统一处理。你写完文件、标记好内容即可，脚本会自动格式化。

## HARD CONSTRAINTS

1. 每次创建 1 个 `characters/` 下的角色 YAML 文件
2. 严格遵循 `assets/character.yaml` 模板的三层结构
3. 角色弧线（起始→变化→最终）为必填字段
4. YAML 格式约束见 `templates/prompt_template.md`
5. 不修改 `project_index.yaml`（写后处理脚本自动更新）
