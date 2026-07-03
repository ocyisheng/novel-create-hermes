# 标准项目结构

所有小说项目均遵循以下标准目录结构。卷数（默认3卷）和幕数（默认三幕3幕）可在 `init.py new` 时通过 `--volumes` 和 `--acts` / `--structure` 参数自定义。

```
{项目名}/
├── config.yaml              # 项目配置（含 结构配置、进度、检查标准）
├── chapters/                # 章节正文（.txt 纯文本）
│   ├── 第1章.txt            # 第{编号}章.txt
│   ├── 第2章.txt
│   └── .metas/              # 章节元数据标记
│       ├── 第1章.txt
│       └── ...
├── characters/              # 角色档案（.yaml，按角色名命名）
│   ├── 林默.yaml
│   └── 角色统计.yaml        # 角色出场统计
├── graph/                   # V2 叙事单元网络（V2 项目新增）
│   ├── nodes.jsonl          # 叙事单元数据
│   ├── edges.jsonl          # 关系数据
│   ├── events.olog          # 事件溯源日志
│   └── snapshots/           # 快照
├── ideation/                # 创意构思产物
│   ├── 需求分析.yaml
│   ├── 约束集.yaml
│   ├── 创意简报.yaml
│   ├── 评估报告.yaml
│   └── 最终创意方案.yaml
├── outline/                 # 大纲文件（规划目录）
│   ├── 总纲.yaml            # 故事宏观骨架：故事结构（幕列表）、分卷概览、节奏
│   ├── 时间线设计.yaml      # 全局时间线设计，按时代/阶段分组的结构化世界年表
│   ├── 分卷/                # 各卷大纲，每卷独立文件
│   │   ├── 卷1_开端.yaml
│   │   └── ...
│   ├── 情节线/              # 情节线实体
│   │   ├── 主线.yaml
│   │   └── 支线_*.yaml
│   ├── 伏笔规划.yaml        # 全局伏笔设计总表
│   ├── 分纲/                # 分章节大纲，按卷拆分目录
│   │   ├── 卷1/
│   │   │   ├── 第1章.yaml
│   │   │   └── ...
│   │   ├── 卷2/
│   │   └── ...
│   └── 追踪/                # 写后自动维护的记录数据
│       ├── 伏笔.yaml
│       ├── 时间线.yaml
│       ├── 角色统计.yaml
│       ├── 情节线进度.yaml
│       └── 章节摘要.yaml
├── quality/                 # 质量检测报告
│   ├── 第{N}章_AI味道检测.yaml
│   ├── 第{N}章_情节逻辑检测.yaml
│   ├── 第{N}章_角色一致性检查.yaml
│   ├── 第{N}章_世界观漏洞检测.yaml
│   └── 第{N}章_综合质量报告.yaml
├── styles/                  # 写作风格定义
│   ├── index.yaml
│   └── {名称}.yaml
├── worldbuilding/           # 世界观文件（.yaml）
│   ├── 基本信息.yaml
│   ├── 核心规则.yaml
│   ├── 力量体系.yaml
│   ├── 势力格局.yaml
│   ├── 地理位置.yaml
│   ├── 历史.yaml
│   ├── 文化.yaml
│   ├── 经济体系.yaml
│   ├── 政治制度.yaml
│   └── 社会阶层.yaml
├── .omo/                    # OpenCode 运行时记忆
│   ├── notepads/
│   └── plans/
└── output/                  # 导出产物
```

## 结构自定义

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

## V2 项目结构

使用 `--v2` 标志创建的项目采用精简结构，`graph/` 是单一真相源：

```
{项目名}/
├── config.yaml              # 项目配置（含 架构: v2 标记）
├── graph/                   # 叙事单元网络（真相源）
│   ├── nodes.jsonl          # 全部叙事单元
│   ├── edges.jsonl          # 单元间关系
│   ├── events.olog          # 事件溯源日志
│   └── snapshots/           # 时间点快照
├── quality/                 # 质量检测报告
├── styles/                  # 写作风格定义
├── output/                  # 导出产物
└── .omo/                    # OpenCode 运行时记忆
```

| 文件 | 内容 | 维护方式 |
|------|------|---------|
| `graph/nodes.jsonl` | 全部叙事单元（场景/角色弧线/情节线/世界观规则/笔记/正文片段） | GraphStore API 自动维护 |
| `graph/edges.jsonl` | 单元间关系（参与/实现/引用/矛盾/前置等10种类型） | GraphStore API 自动维护 |
| `graph/events.olog` | 事件溯源日志（每次修改的记录） | store.flush() 自动追加 |
| `graph/snapshots/` | 时间点快照 | store.create_snapshot() |

graph 是 V2 的**单一真相源**。不再生成 `characters/`、`worldbuilding/`、`outline/`、`chapters/`、`ideation/` 目录。创作数据全部通过 GraphStore API 读写。
