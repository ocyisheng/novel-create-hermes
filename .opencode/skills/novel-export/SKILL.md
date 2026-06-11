---
name: "novel-export"
description: "格式化导出：收集章节正文，按格式要求导出为 EPUB/PDF/HTML/TXT/DOCX。触发词：导出、发布、publish、export、epub、pdf、html、txt、docx"
license: "MIT"
version: "1.0.0"
compatibility: "OpenCode"
tags: ["novel", "export", "publish"]
---

# 格式化导出技能

## 核心职责

收集项目章节文件，按指定格式导出为可发布的电子书/文档文件。**通过 `export.py` 脚本执行导出，不依赖子 Agent 的 AI 生成。**

## 上下文契约

编排层在调用前按以下清单加载上下文：

| 槽位 | 内容 | 加载方式 |
|------|------|---------|
| 项目名 | config.yaml | read |
| 项目路径 | 项目根目录绝对路径 | novel-context.md |
| 导出格式 | 用户指定的格式 | 编排层从用户输入提取 |
| 作者名 | 可选，用户提供的作者名 | 编排层从用户输入提取 |

## 执行方式

子 Agent 收到 task() 后，**不通过 AI 生成导出文件**，而是调用 `export.py` 脚本：

```bash
python .opencode/shared/export.py \
    --project-root {项目路径} \
    --format html txt epub   \
    --author "作者名（可选）"
```

脚本自动完成章节收集、格式化、文件写入全过程。

## 支持格式

| 格式 | 脚本能力 | 说明 |
|------|---------|------|
| HTML | ✅ 完整 | 单文件 HTML，可直接在浏览器中阅读 |
| TXT | ✅ 完整 | 纯文本，通用格式 |
| XHTML | ✅ 完整 | XHTML 单文件，可导入 Calibre 转 EPUB |
| EPUB | ⚠️ 中间格式 | 输出 XHTML → 手动导入 Calibre 完成转换 |
| PDF | ⚠️ 中间格式 | 输出 HTML → 浏览器打印为 PDF |
| DOCX | ❌ 暂不支持 | 需要 python-docx 依赖 |

## 输出

- 文件写入 `{项目路径}/output/{项目名}.{格式}`（脚本自动完成）
- 不修改任何章节正文或元数据文件

## 参考

- `references/format_specs.md` — 排版格式规范
- `references/export_examples.md` — 导出示例
- `assets/publishing.yaml` — 发布配置模板

## HARD CONSTRAINTS

1. 子 Agent **不得自行用 AI 生成导出文件内容**，必须调用 `export.py` 脚本
2. export.py 自动按文件名数字顺序排序（第1章 → 第2章 → ...）
3. 输出文件编码统一为 UTF-8
