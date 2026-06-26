<p align="center">
  <img src="https://img.shields.io/badge/status-稳定-22c55e?style=flat-square" alt="Status">
  <img src="https://img.shields.io/badge/小说项目-可移植-3b82f6?style=flat-square" alt="Portable">
  <img src="https://img.shields.io/badge/技能包-17个-8b5cf6?style=flat-square" alt="Skills">
  <img src="https://img.shields.io/badge/导出格式-5种-ec4899?style=flat-square" alt="Export Formats">
  <img src="https://img.shields.io/badge/内置风格-20+-f59e0b?style=flat-square" alt="Styles">
  <img src="https://img.shields.io/badge/license-MIT-64748b?style=flat-square" alt="License">
</p>

<h1 align="center">📖 novel-create-hermes</h1>
<p align="center"><strong>跟 AI 聊着天，就把小说写了。</strong></p>
<p align="center">像发微信一样说出你的想法，Hermes 自动完成从创意构思到章节写作再到格式导出的全部流程。<br>
不用学工具、不用记命令、不用纠结先做什么后做什么——开口说话就行。</p>

<br>

---

## 🚀 为什么用这个？

写小说最大的障碍从来不是"不会写"，而是**打开空白文档时的茫然**。

Hermes 把这个过程变成了对话——你说"新建项目'龙渊'，类型玄幻"，它自动创建好目录结构和配置文件；你说"帮我建个力量体系"，它理解你的世界观风格生成设定；你说"写第3章"，它把分纲、角色档案、前文摘要、活跃风格全部准备好，直接产出一章正文。

整个过程不需要离开聊天界面。不需要在多个工具之间切换，不需要记住复杂的软件操作。**你说想法，它干活。**

---

## ✨ 核心能力一览

| 能力 | 做什么 | 怎么说 |
|------|--------|--------|
| **🤯 创意构思** | 没灵感时帮你发散、收束、评估创意 | `帮我想个创意` |
| **🌍 世界观建设** | 力量体系、势力格局、地理历史 | `搭个世界观` / `建个力量体系` |
| **👤 角色创建** | 角色档案、性格弧线、成长轨迹 | `创建主角林渊` |
| **📋 总纲与情节** | 故事框架、主线/支线、伏笔设计 | `设计故事大纲` / `设计主线` |
| **📑 分纲与章节** | 分卷大纲到逐章分纲，再到正文写作 | `写分纲` / `写第1章` |
| **🎨 风格切换** | 20+ 内置风格，也可从参考文本提取 | `用凡人修仙风写` |
| **🔍 质量检测** | AI味、情节逻辑、角色一致性、世界观漏洞 | `检测AI味` / `看看写得怎么样` |
| **📚 知识库** | 导入参考书籍，写作时直接引用 | `把凡人修仙传加入知识库` |
| **✏️ 编辑修改** | 润色章节、调整角色、修改设定 | `把主角改得更果断一些` |
| **📤 格式导出** | EPUB / PDF / HTML / TXT / DOCX | `导出为EPUB` |

> 所有步骤**可以任意跳序**。不需要先做创意再做世界观、先写大纲再写章节。想到哪写到哪，AI 会自动判断上下文。

---

## 🔄 工作流

```
你说"新建项目'龙渊'"
      │
      ▼
Hermes 自动完成：
  用 项目管理 技能  →  创建目录结构 + config.yaml
  用 创意构思 技能  →  发散脑洞、收敛方向（可选）
  用 世界观建设 技能  →  力量体系 / 势力格局 / 地理历史
  用 角色创建 技能  →  主角 / 配角 / 反派档案
  用 总纲撰写 技能  →  故事框架 + 叙事策略
  用 情节构建 技能  →  主线 / 支线 / 伏笔规划
  用 分纲构建 技能  →  分卷大纲 → 逐章分纲
  用 章节写作 技能  →  完整章节正文（衔接前文）
  用 质量检测 技能  →  AI味 / 逻辑 / 一致性检查
  用 编辑 技能  →  润色修订
  用 导出 技能  →  EPUB / PDF / HTML / TXT
```

背后的 **17 个专业写作技能包** + **编排层智能调度**，让每一步都自动衔接。你只管说想做什么，剩下的交给系统。

---

## ⚡ 快速开始

### 1. 装 Python

去 [python.org/downloads](https://python.org/downloads) 下载最新版，安装时勾选 **Add Python to PATH**。已有 Python 的跳过。

### 2. 装 OpenCode

**桌面版（推荐）**：去 [opencode.ai](https://opencode.ai) 下载 → 打开

**命令行版**：
```bash
npm install -g @opencode/cli
```

### 3. 打开项目

```bash
cd Desktop\novel-create-hermes
opencode
```

按 Tab 键切换到 **Novel-writer** Agent。

### 4. 开始创作

```
你： 新建项目"龙渊" 类型：玄幻
AI： ✅ 项目创建完成！接下来想做什么？
```

这样就开始了。接下来 AI 会引导你完成后续步骤，你直接说就行。

---

## 📖 使用示例

### 从零开始一个项目

```
你： 新建项目"剑来" 类型：仙侠
AI： ✅ 创建完成！世界观方面有什么想法吗，还是我帮你生成一套？
```

### 导入灵感来源

```
你： 把 C:\书\凡人修仙传.epub 加入知识库
AI： ✅ 导入完成！已提取 37 个设定框架、12 种叙事模式。需要时直接说「参考凡人修仙传」即可。
```

### 创建角色并写作

```
你： 创建主角陈平安，性格坚韧，出身微末
你： 写第1章
```

### 换风格、查质量、导出

```
你： 用凡人修仙风来写第3章
你： 检测AI味
你： 导出为EPUB
```

---

## 📚 知识库（可选功能但很强大）

把你喜欢的书导入成结构化知识，写小说时可以直接引用它的力量体系、叙事节奏等。

支持的格式：**PDF、EPUB、TXT、DOCX、HTML、MOBI、AZW3**

常规用法是"先导入再引用"，但 AI 更聪明——你说"参考星辰变的力量体系"，它发现书还没导入时会自动帮你导入。

```
你： 参考星辰变的力量体系，给龙渊搭一套境界划分
AI： — 正在读取星辰变知识库 —
     ✅ 已参考，为你设计了 9 个境界：凝气→筑基→金丹→元婴→化神→炼虚→合体→大乘→渡劫
```

---

## 🎨 写作风格（可选功能但很好玩）

说一句就能换风格：

```
用凡人修仙风来写第3章     ← 单章风格覆盖
用金庸武侠风              ← 全局风格切换
切换成古龙风              ← 一样的效果
```

内置 20+ 风格：凡人修仙风、金庸武侠风、古龙武侠风、古典名著风、悬疑推理风、热血少年风……你也可以提交自己的参考文本，AI 会自动提取风格特征。

---

## ❓ 常见问题

<details>
<summary><strong>写出来的东西能直接用吗？</strong></summary>

初稿质量已经很高，但建议读一遍。用 `检测AI味` 找出 AI 痕迹过重的地方，再润色修改——这是最推荐的流程。
</details>

<details>
<summary><strong>换电脑了怎么办？</strong></summary>

把整个 `novel-create-hermes` 文件夹拷走就行。所有数据都在这个目录里：
- `novels/` — 你的小说项目和全部章节
- `knowledge/` — 导入的知识库
- `.omo/` — 写作状态和上下文

拷到新电脑上装好 OpenCode 重新打开，直接续写。
</details>

<details>
<summary><strong>导入的书存在哪？我能直接看吗？</strong></summary>

存在 `knowledge/` 目录下，纯 Markdown 文件，你可以直接打开阅读和编辑。
</details>

<details>
<summary><strong>跟 GPT 写小说有什么不同？</strong></summary>

GPT 是对话窗口，每次都要手动粘贴上下文；Hermes 是**结构化写作系统**——它知道你的世界观设定、角色档案、情节伏笔、写作风格，每次生成章节时会自动收集全部上下文并保持一致性。而且内置了质量检测、风格管理、知识库引用等专为小说创作设计的能力。
</details>

<details>
<summary><strong>支持多人协作吗？</strong></summary>

目前是单人创作工具。但项目文件全部是纯文本（YAML + Markdown），可以配合 Git 做版本管理。也欢迎提交 PR 扩展功能。
</details>

---

## 🏗️ 项目架构（给开发者）

这个工具的核心是 **编排层 + 17 个技能包** 的 skill 架构：

```
novel-writer.md（编排层）→ 理解你的意图，调度对应的技能包
        │
        ├── novel-ideation      创意构思
        ├── novel-worldbuilding  世界观建设
        ├── novel-character      角色创建
        ├── novel-synopsis       总纲撰写
        ├── novel-plot           情节构建
        ├── novel-outline        分卷与分纲
        ├── novel-chapter        章节写作
        ├── novel-quality        质量检测
        ├── novel-edit           编辑修改
        ├── novel-style          风格管理
        ├── novel-export         格式导出
        └── ... 还有 6 个支撑技能
```

每个技能是一个独立的 SKILL.md + 配套 Python 脚本，可以单独修改、替换或扩展。详细的架构说明见 [DEVELOPER.md](DEVELOPER.md)，目录结构和技能列表见 [AGENTS.md](AGENTS.md)。

---

<p align="center"><strong>你说想法，它干活。</strong><br>
像聊天一样写小说，就这么简单。</p>

<p align="center">
  <sub>MIT License · Made for novel creators · 如有问题欢迎 <a href="https://github.com/your-repo/novel-create-hermes/issues">提 Issue</a></sub>
</p>
