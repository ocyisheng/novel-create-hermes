---
name: book-knowledge
description: "知识库管理：检索、查询、引用 book-to-knowledge 生成的结构化知识库。支持按书名/模式/tag 检索，加载章节摘要和叙事模式。独立于任何项目，可在任意 OpenCode/Amp/Claude 中使用。触发词：查书、参考、知识库、knowledge、找XX模式"
---

# book-knowledge — 知识库管理

管理和查询 `knowledge/` 目录下的结构化知识库。每个知识库由 book-to-knowledge 生成，包含核心框架、章节索引、术语表、模式库和决策速查。

**不依赖任何项目实体**，只依赖 `knowledge/` 目录的文件约定。可复制到任意项目中使用。

---

## 核心职责

### 1. 检索知识库

| 操作 | 实现方式 |
|------|---------|
| 列举所有书籍 | 读 `knowledge/index.yaml` 或扫描 `knowledge/*/source.yaml` |
| 按 slug 加载 | 读 `knowledge/<slug>/knowledge.md` |
| 按模式搜索 | `grep knowledge/*/patterns.md` |
| 按标签过滤 | 在 `index.yaml`/`source.yaml` 中按 `tags` 字段筛选 |

### 2. 查询具体内容

- **"盘龙的力量体系是什么"** → 读 `knowledge/panlong/knowledge.md` 提取力量体系相关段
- **"找逆袭弧线的例子"** → grep `knowledge/*/patterns.md` 返回所有相关模式
- **"星辰变的 cheatsheet"** → 读 `knowledge/xingchen-bian/cheatsheet.md`

### 3. 格式化输出

所有查询返回统一 markdown 片段格式：

```
## 参考：<slug>
### 来源
<title> — <author>（<chapter_count> 章）

### 相关内容
<从 knowledge/ 中检索到的相关片段>
```

---

## 上下文契约

### 入参格式

```
参考书籍: <slug>[, <slug2>, ...]
查询内容: <力量体系|叙事模式|角色原型|节奏控制|章节摘要|全部>
```

### 工作流程

1. 解析 slug 列表和查询类型
2. 读取 `knowledge/<slug>/source.yaml` 验证存在
3. 按查询类型读取对应文件：
   - **力量体系** → `knowledge.md` 的 Core Frameworks 段过滤出体系相关
   - **叙事模式** → `patterns.md`
   - **角色原型** → `chapters/` 中主角/反派章节的摘要
   - **节奏控制** → `cheatsheet.md`
   - **章节摘要** → `chapters/ch<NN>-<slug>.md`
   - **全部** → `knowledge.md` + `patterns.md` + `cheatsheet.md`
4. 组装为标准 markdown 参考片段返回

### 行为约束

- 不修改 `knowledge/` 下的任何文件（只读）
- 索引维护由 `book-to-knowledge` 的导入流程负责（`rebuild_knowledge_index.py`）
- 当 slug 不存在时，返回清晰错误并建议可用书籍列表

---

## 知识库位置

默认读取项目根目录下的 `knowledge/`。通过 `KNOWLEDGE_ROOT` 环境变量覆盖：

```bash
export KNOWLEDGE_ROOT="/path/to/shared/knowledge"
```
