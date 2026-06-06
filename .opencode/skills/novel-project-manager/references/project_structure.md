# 标准项目结构

所有小说项目均遵循以下标准目录结构。卷数（默认3卷）和幕数（默认三幕3幕）可在 `init.py new` 时通过 `--volumes` 和 `--acts` / `--structure` 参数自定义。

```
{项目名}/
├── config.yaml              # 项目配置（含 结构配置、干预等级、进度、检查标准）
├── chapters/                # 章节文件（.txt 纯文本）
│   └── chapter_01.txt
├── characters/              # 角色档案（.yaml，按角色名命名）
│   ├── protagonist.yaml
│   └── 角色统计.yaml       # 角色出场统计（被 auto_update 自动修改）
├── project_index.yaml       # 项目索引（由 rebuild_project_index.py 重建，包含所有实体的当前状态）
├── outline/                 # 大纲文件
│   ├── 总纲.yaml            # 故事宏观骨架：故事结构（幕列表）、分卷列表、节奏
│   ├── 情节线/              # 情节线实体文件夹
│   │   ├── 主线.yaml        # 主线情节
│   │   └── 支线.yaml        # 支线情节
│   ├── 分卷/                # 各卷元文档（按卷数量动态生成）
│   │   ├── 卷1_开端.yaml     # 卷{N}_{名称}.yaml，默认3卷可自定义
│   │   └── ...
│   ├── 追踪/               # 运行时数据（被 auto_update 自动修改）
│   │   ├── 伏笔.yaml
│   │   └── 时间线.yaml
│   └── 分纲/               # 分章节大纲（按卷拆分目录）
│       ├── 卷1/             # 卷1 的分纲文件
│       │   ├── 第1章.yaml
│       │   └── ...
│       ├── 卷2/
│       └── ...
└── worldbuilding/           # 世界观文件（.yaml）
    ├── 基本信息.yaml
    ├── 核心规则.yaml
    ├── 力量体系.yaml
    ├── 势力格局.yaml
    ├── 地理位置.yaml
    ├── 历史.yaml
    └── 文化.yaml
```

## config.yaml 结构配置段

新建项目时通过 `--structure` 和 `--volumes` 参数控制，写入 config.yaml 的 `结构配置` 段：

```yaml
结构配置:
  结构类型: "三幕"            # 三幕 / 五幕 / 自定义
  卷数: 3                    # 由 --volumes 指定
  幕数: 3                    # 由 --acts 指定（--structure 五幕 时默认为5）
  章节分布: [25, 50, 25]     # 各幕章节百分比，自动根据幕类型计算
```

该配置影响初始化时生成的文件结构和总纲模板，但后续可由用户在 config.yaml 中自由修改。
工具链（`rebuild_project_index.py`, `auto_update.py`）通过 glob 动态发现分纲目录，无需感知具体卷数。

## 各文件内容说明

| 文件 | 内容 | 写入者 |
|------|------|--------|
| `outline/总纲.yaml` | 故事结构（幕列表）、分卷列表、章节分布、节奏说明 | `init.py`（骨架）+ `novel-writing`（填充） |
| `outline/分卷/卷N_*.yaml` | 单卷故事上下文（概要、情节点、角色发展） | `init.py`（骨架）+ `novel-writing`（填充） |
| `outline/情节线/` | 主线/支线实体（plot_thread） | `novel-writing` |
| `outline/追踪/伏笔.yaml` | 伏笔设置与回收追踪 | `auto_update.py` |
| `outline/追踪/时间线.yaml` | 事件时序 | `auto_update.py` |
| `characters/角色统计.yaml` | 角色出场统计 | `auto_update.py` |

## 文件命名规范

- **章节文件**：`chapters/chapter_{编号}.txt`（如 `chapter_01.txt`）
- **角色档案**：`characters/{角色名}.yaml`（如 `characters/林默.yaml`）
- **角色统计**：`characters/角色统计.yaml`
- **分卷文件**：`outline/分卷/卷{编号}_{名称}.yaml`（如 `outline/分卷/卷1_开端.yaml`）
- **分纲文件**：`outline/分纲/卷{编号}/第{编号}章.yaml`（如 `outline/分纲/卷1/第1章.yaml`）

## 结构自定义示例

```bash
# 五卷五幕式（适合史诗奇幻）
python init.py new "星辰帝国" "玄幻" --volumes 5 --structure 五幕

# 四卷三幕式（适合都市悬疑）
python init.py new "迷雾追踪" "悬疑" --volumes 4 --acts 3

# 六卷自定义幕
python init.py new "银河纪元" "科幻" --volumes 6 --acts 6 --structure 自定义

# 导入已有项目，按5卷划分分纲目录
python init.py import "D:/旧小说" "迁移项目" --volumes 5
```
