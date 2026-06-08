---
name: "novel-polish"
description: "文笔优化与导出：文笔增强、反馈修订、格式化导出。触发词：文笔、润色、修订、反馈、导出、发布、publish、export"
license: "MIT"
version: "2.0.0"
compatibility: "OpenCode"
tags: ["novel", "polish", "export"]
---

# 文笔优化与导出技能

## PROMPT_TEMPLATE

> 模板定义在 `templates/prompt_template.md`。编排层使用 `extract_template.py` 加载并填充变量。

## 核心职责

按编排 Agent 传入的 CONTEXT 执行文笔优化、反馈修订和格式化导出任务。

## 上下文契约

编排层（或手工操作者）在调用本技能前准备以下上下文：

| 槽位 | 文件路径 | 提取内容 | 加载方式 |
|------|---------|---------|---------|
| 章节正文 | `chapters/第{N}章.txt` | 全文 | `read` |
| 读者反馈 | `.omo/notepads/novel-feedback.md` | 筛选 `## 第{N}章 反馈` 段落 | `read` → 按章节号过滤 |
| 活跃风格 | `styles/{active_style}.yaml` | 全文件（≤30行） | `config.yaml` → `活跃风格` → `read` 风格文件 |
| 前章衔接参考 | `chapters/第{N-1}章.txt` 最后 100 字 | 末尾段落 | `last_100.py` |

## 文笔优化

文笔增强技巧 → `enhancement_tips.md`，润色示例 → `enhancement_tips.md` §润色示例

### 核心原则

**Show Not Tell** — 用动作、神态、感官细节代替抽象描述

### 注意事项

保持原意、风格一致、适度原则、保留角色独特声音

## 反馈修订

当编排层传入 `## 读者反馈（本次修订需关注）` 时，说明本次章节写作是基于真实读者反馈的修订版。

### 处理原则

1. **精准修正**：只修改反馈指出的具体问题，不重写无关段落
2. **理解意图**：从反馈中提取读者感受到的"不适点"，找到文本层面的根因
   - "转变太快" → 缺少过渡描写，需要补写内心挣扎或转折事件
   - "信息密度太高" → 拆分段落，增加喘息点，或分章展开
   - "角色行为不合理" → 对照角色档案检查动机链，补写铺垫
3. **保留原素材**：不要丢弃已有的好段落，在原文基础上插入/改写最小必要内容
4. **衔接前后章**：修订后必须重新确认与前章的衔接和悬念钩子

### MUST NOT

- ❌ 不要因一个反馈而"推倒重写"整章
- ❌ 不要忽略反馈中提到的具体细节
- ❌ 不要在修正时引入新的角色不一致

## 格式化与导出

格式化、导出 EPUB/PDF/HTML/TXT/DOCX。

### 支持格式

| 格式 | 用途 | 平台 |
|------|------|------|
| EPUB | 电子书 | 微信读书/Kindle |
| PDF | 打印 | 通用 |
| HTML | 网页 | Web |
| TXT | 纯文本 | 通用 |
| DOCX | 排版 | Word |

### 处理流程

收集章节 → 格式化（标题/段落/对话） → 生成元数据（封面/目录/作者/简介） → 生成目录 → 导出

## 参考

- `references/enhancement_tips.md` — 文笔提升技巧（含润色示例）
- `references/format_specs.md` — 排版格式规范
- `references/checklist_example.md` — 写作检查清单
- `references/export_examples.md` — 导出示例
- `assets/publishing.yaml` — 发布配置

## HARD CONSTRAINTS

> 约束已移入 `templates/prompt_template.md`。编排层通过 `extract_template.py` 加载模板时一并注入 LLM prompt。
