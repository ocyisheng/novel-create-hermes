# 标准项目结构

所有小说项目均遵循以下标准目录结构。卷数（默认3卷）和幕数（默认三幕3幕）可在 `init.py new` 时通过 `--volumes` 和 `--acts` / `--structure` 参数自定义。

```
{项目名}/
├── config.yaml              # 项目配置（含 结构配置、进度、检查标准）
├── chapters/                # 章节正文（.txt 纯文本）
│   ├── 第1章.txt            # 第{编号}章.txt
│   ├── 第2章.txt
│   └── .metas/              # 章节元数据标记（被 chapter_tracking 自动维护）
│       ├── 第1章.txt
│       └── ...
├── characters/              # 角色档案（.yaml，按角色名命名）
│   ├── 林默.yaml
│   └── 角色统计.yaml        # 角色出场统计（被 chapter_tracking 自动修改）
├── ideation/                # 创意构思产物（P1 生成）
│   ├── 需求分析.yaml        # 边界条件和目标
│   ├── 约束集.yaml          # 6 大类约束
│   ├── 创意简报.yaml        # 3-5 个创意方向
│   ├── 评估报告.yaml        # 4 维度评分
│   └── 最终创意方案.yaml    # 选定创意的完整方案（供 P4/P6 读取）
├── outline/                 # 大纲文件（规划目录）
│   ├── 总纲.yaml            # 故事宏观骨架：故事结构（幕列表）、分卷概览、节奏（P4 生成）
│   ├── 时间线设计.yaml      # ★ 规划：全局时间线设计，按时代/阶段分组的结构化世界年表（P4 新增）
│   ├── 分卷/                # 各卷大纲（P6 生成，每卷独立文件）
│   │   ├── 卷1_开端.yaml    # 卷{N}_{名称}.yaml，含微弧/POV/叙事任务/卷末钩子
│   │   └── ...
│   ├── 情节线/              # 情节线实体（P5 生成）
│   │   ├── 主线.yaml        # 主线情节
│   │   └── 支线_*.yaml      # 支线情节（多条）
│   ├── 伏笔规划.yaml        # ★ 规划：全局伏笔设计总表，跨情节线管理（P5 新增）
│   ├── 分纲/                # 分章节大纲（P7 生成，按卷拆分目录）
│   │   ├── 卷1/             # 卷1 的分纲文件
│   │   │   ├── 第1章.yaml
│   │   │   └── ...
│   │   ├── 卷2/
│   │   └── ...
│   └── 追踪/                # ★ 记录目录（写后自动维护，不接受规划数据）
│       ├── 伏笔.yaml        # 记录：实际埋设/回收记录（扁平追加）
│       ├── 时间线.yaml      # 记录：实际事件（扁平追加）
│       ├── 角色统计.yaml    # 记录：实际出场（扁平追加）
│       ├── 情节线进度.yaml  # 记录：实际进度（扁平追加）
│       └── 章节摘要.yaml    # 记录：实际摘要（扁平追加）
├── relation/                 # ★ 关系图谱（由 project_graph.py 自动维护）
│   ├── graph/                # 图谱数据（节点、边、校验和）
│   │   ├── 01_nodes.yaml
│   │   ├── 10_edges_domain.yaml
│   │   ├── 11_edges_cross.yaml
│   │   ├── 02_deviation_state.yaml
│   │   ├── 20_checksums.yaml
│   │   └── meta.yaml
│   └── htmls/                # 可视化输出
│       ├── 关系图.html
│       └── {entity_id}_时间线.html
├── project_index.yaml       # 项目索引（由 rebuild_project_index.py 重建）
├── quality/                 # 质量检测报告（P9 生成）
│   ├── 第{N}章_AI味道检测.yaml
│   ├── 第{N}章_情节逻辑检测.yaml
│   ├── 第{N}章_角色一致性检查.yaml
│   ├── 第{N}章_世界观漏洞检测.yaml
│   └── 第{N}章_综合质量报告.yaml
├── styles/                  # 写作风格定义
│   ├── index.yaml           # 风格清单（由 style_manager.py 维护）
│   └── {名称}.yaml          # 7 维度风格文件（每风格 ≤30 行）
└── worldbuilding/           # 世界观文件（.yaml，P2 生成）
    ├── 基本信息.yaml
    ├── 核心规则.yaml
    ├── 力量体系.yaml
    ├── 势力格局.yaml
    ├── 地理位置.yaml
    ├── 历史.yaml
    ├── 文化.yaml
    ├── 经济体系.yaml         # 新增
    ├── 政治制度.yaml         # 新增
    └── 社会阶层.yaml         # 新增
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
工具链（`rebuild_project_index.py`, `chapter_tracking.py`）通过 glob 动态发现分纲目录，无需感知具体卷数。

## 各文件内容说明

| 文件 | 内容 | 写入者 |
|------|------|--------|
| `ideation/` | 创意构思 5 个阶段文件 | `novel-ideation` |
| `outline/总纲.yaml` | 故事结构（幕列表）、分卷概览、节奏说明（P4） | `init.py`（骨架）+ `novel-outline`（P4 填充） |
| `outline/时间线设计.yaml` | ★ 全局时间线设计（P4）：按时代分组的结构化世界年表 | `novel-outline`（P4 新增） |
| `outline/情节线/` | 主线/支线实体（plot_thread） | `novel-outline`（P5） |
| `outline/伏笔规划.yaml` | ★ 全局伏笔设计总表（P5）：跨情节线的完整伏笔规划 | `novel-outline`（P5 新增） |

| `outline/分卷/卷N_*.yaml` | 单卷大纲：核心冲突、叙事任务、微弧、POV、角色发展（P6） | `init.py`（骨架）+ `novel-outline`（P6 填充） |
| `outline/追踪/伏笔.yaml` | 记录：实际埋设/回收记录（扁平追加） | `chapter_tracking.py` |
| `outline/追踪/时间线.yaml` | 记录：实际事件日志（扁平追加） | `chapter_tracking.py` |
| `outline/追踪/角色统计.yaml` | 记录：实际出场记录（扁平追加） | `chapter_tracking.py` |
| `outline/追踪/情节线进度.yaml` | 记录：实际进度（扁平追加） | `chapter_tracking.py` |
| `outline/追踪/章节摘要.yaml` | 记录：实际摘要（扁平追加） | `chapter_tracking.py` |
| `chapters/.metas/` | 章节元数据标记（摘要/伏笔/出场角色） | `novel-chapter`（P8 写作时）+ `chapter_tracking.py` |
| `characters/角色统计.yaml` | 角色出场统计（旧位置，逐步迁移到 `outline/追踪/`） | `chapter_tracking.py` |
| `quality/` | 质量检测分路报告 + 综合报告（P9） | `novel-quality` |
| `styles/index.yaml` | 风格清单 | `style_manager.py` |

## 文件命名规范

- **章节文件**：`chapters/第{编号}章.txt`（如 `chapters/第1章.txt`）
- **章节元数据**：`chapters/.metas/第{编号}章.txt`
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
