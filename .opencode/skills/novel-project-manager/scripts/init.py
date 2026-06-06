#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
小说项目管理统一入口

子命令:
  new      新建项目
  import   导入项目
  status   查看状态
  resume   续写项目
  delete   删除项目

用法:
  python init.py new "项目名" "类型" [-d 目录]
  python init.py import "源路径" "项目名" [-d 目录]
  python init.py status "项目名" [-d 目录] [--phase 阶段] [--intervention high|medium|low]
  python init.py resume "项目名" [-d 目录]
  python init.py delete "项目名" [-d 目录] [--force]
"""

import os
import sys
import re
import io
import math
import shutil
import yaml
import subprocess
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any

# 项目技能根目录
SKILLS_DIR = Path(__file__).parent.parent
TOOL_ROOT = SKILLS_DIR.parent.parent  # novel-create-hermes/


def find_novels_root() -> Path:
    """发现 NOVELS_ROOT，按 novel-writer.md §1.1 优先级。"""
    import os
    # 1. 环境变量
    env_root = os.environ.get("NOVELS_ROOT", "")
    if env_root:
        p = Path(env_root)
        if p.is_dir():
            return p
    # 2. CWD 如果包含 novels/ 子目录
    cwd = Path.cwd()
    if (cwd / "novels").is_dir():
        return cwd / "novels"
    # 3. CWD 的父目录
    if (cwd.parent / "novels").is_dir():
        return cwd.parent / "novels"
    # 4. 工具根目录
    return TOOL_ROOT / "novels"


# ===========================================================================
# 内容识别关键词（用于旧项目迁移时的文件分类）
# ===========================================================================

# 角色文件识别关键词
CHARACTER_KEYWORDS = {"角色", "character", "人物", "档案", "姓名", "性格", "外貌"}
# 大纲文件识别关键词（文件名）
OUTLINE_FILENAME_KEYWORDS = {"大纲", "outline", "总纲", "分纲", "情节", "伏笔", "时间线"}
# 世界观文件识别关键词
WORLDBUILDING_KEYWORDS = {"世界观", "world", "设定", "规则", "力量体系", "势力", "地理", "历史", "文化"}
# 章节文件识别关键词
CHAPTER_KEYWORDS = {"章节", "chapter", "正文", "场景"}


# ===========================================================================
# 新建项目
# ===========================================================================

class ProjectInitializer:
    def __init__(self, project_name: str, genre: str = "通用", target_dir: str = None,
                 volume_count: int = 3, act_count: int = 0, structure_type: str = "三幕"):
        self.project_name = project_name
        if target_dir is None:
            target_dir = str(find_novels_root())
        self.genre = genre
        self.target_dir = Path(target_dir)
        self.project_path = self.target_dir / project_name
        self.volume_count = max(1, volume_count)
        # Auto-detect structure type from act_count if not explicitly 三幕
        if structure_type == "三幕" and act_count not in (0, 3):
            self.structure_type = "自定义"
        else:
            self.structure_type = structure_type
        if act_count > 0:
            self.act_count = act_count
        else:
            self.act_count = 5 if self.structure_type == "五幕" else 3
        self.act_count = max(1, self.act_count)
        # Pre-compute derived names
        self.act_names = self._get_act_names()
        self.volume_names = self._get_volume_names()
        self.chapter_distribution = self._calculate_chapter_distribution()

    def _get_act_names(self) -> list[str]:
        """Return display names for each act based on structure type and count."""
        ACT_NAMED_MAP = {
            "三幕": ["开端", "发展", "高潮结局"],
            "五幕": ["建置", "上升", "高潮", "下降", "结局"],
        }
        if self.structure_type in ACT_NAMED_MAP:
            names = ACT_NAMED_MAP[self.structure_type]
            if self.act_count <= len(names):
                return names[:self.act_count]
            # Extend with numbered names if act_count > predefined
            return names + [f"第{i}幕" for i in range(len(names) + 1, self.act_count + 1)]
        # Fallback: numbered acts
        return [f"第{i}幕" for i in range(1, self.act_count + 1)]

    def _get_volume_names(self) -> list[str]:
        """Return default short names for each volume (overridable later in 总纲.yaml)."""
        VOL_NAMED_MAP = {
            3: ["开端", "发展", "高潮结局"],
            5: ["初入", "崛起", "巅峰", "转折", "终局"],
        }
        if self.volume_count in VOL_NAMED_MAP:
            return VOL_NAMED_MAP[self.volume_count]
        return [f"第{i}卷" for i in range(1, self.volume_count + 1)]

    def _calculate_chapter_distribution(self) -> list[int]:
        """Return percentage distribution across acts (sums to 100)."""
        TEMPLATES = {
            (3, "三幕"): [25, 50, 25],
            (5, "五幕"): [15, 25, 20, 15, 25],
        }
        dist = TEMPLATES.get((self.act_count, self.structure_type))
        if dist is not None:
            return dist
        # Generic: even distribution
        base = 100 // self.act_count
        remainder = 100 - base * self.act_count
        dist = [base] * self.act_count
        for i in range(remainder):
            dist[i] += 1
        return dist

    def create_directory_structure(self):
        directories = [
            "chapters",
            "characters",
            "ideation",
            "outline/分卷",
            "outline/情节线",
            "outline/追踪",
            "worldbuilding",
            "quality",
        ]
        # Dynamic volume directories
        for v in range(1, self.volume_count + 1):
            directories.append(f"outline/分纲/卷{v}")
        for directory in directories:
            dir_path = self.project_path / directory
            dir_path.mkdir(parents=True, exist_ok=True)

    def _create_style_index(self):
        """创建 styles/index.yaml 初始骨架"""
        styles_dir = self.project_path / "styles"
        styles_dir.mkdir(parents=True, exist_ok=True)
        index_content = f"""# {self.project_name} - 风格清单
# 由 novel-style/style_manager.py 自动维护

styles: []
"""
        (styles_dir / "index.yaml").write_text(index_content, encoding='utf-8')

    def create_config_file(self):
        now = datetime.now().strftime("%Y-%m-%d")
        # Friendly act/volume labels for the config
        if self.structure_type == "五幕":
            structure_label = "五幕"
        elif self.act_count != 3:
            structure_label = f"{self.act_count}幕"
        else:
            structure_label = "三幕"
        config_content = f"""# {self.project_name} - 项目配置
# 创建时间: {now}

项目名称: "{self.project_name}"
项目类型: "{self.genre}"
活跃风格: ""
作者: ""
状态: "进行中"
当前阶段: "创意构思"
创建时间: "{now}"
最后编辑: "{now}"

结构配置:
  结构类型: "{structure_label}"
  卷数: {self.volume_count}
  幕数: {self.act_count}
  章节分布: {self.chapter_distribution}

创作进度:
  当前章节: 0
  已完成字数: 0

创作目标:
  目标字数: 100000
  目标章节数: 100
  每日目标: 2000

工作流:
  干预等级: "medium"
  AI自主度: true
  检查频率: "weekly"

质量检查:
  章节最少字数: 1500
  章节最多字数: 6000
"""
        (self.project_path / "config.yaml").write_text(config_content, encoding='utf-8')

    def create_worldbuilding_files(self):
        """创建世界观实体文件，遵循 worldbuilding_schema.yaml 三层结构。
        
        每个文件包含:
          - _meta (entity_type, schema_version)
          - 索引信息 (实体ID, 名称, 实体子类型, 状态)
          - 摘要 (一句话描述, 章节关联, 关键词)
          - 完整档案 (原模板内容)
        """
        wb_path = self.project_path / "worldbuilding"
        templates = {
            "基本信息.yaml": (
                "# 世界观基本信息\n\n"
                "_meta:\n"
                "  entity_type: \"world_overview\"\n"
                "  schema_version: \"1.0\"\n"
                "  created_at: \"\"\n"
                "  updated_at: \"\"\n\n"
                "索引信息:\n"
                "  实体ID: \"world_overview\"\n"
                "  名称: \"世界观概览\"\n"
                "  实体子类型: \"world_overview\"\n"
                "  状态: \"active\"\n\n"
                "摘要:\n"
                "  一句话描述: \"\"\n"
                "  章节关联: []\n"
                "  关键词: []\n\n"
                "完整档案:\n"
                "  世界名称: \"\"\n"
                "  世界类型: \"\"\n"
                "  时间背景: \"\"\n"
                "  空间背景: \"\"\n"
                "  核心设定: \"\"\n"
                "  一句话概述: \"\"\n"
            ),
            "核心规则.yaml": (
                "# 世界核心规则\n\n"
                "_meta:\n"
                "  entity_type: \"rule\"\n"
                "  schema_version: \"1.0\"\n"
                "  created_at: \"\"\n"
                "  updated_at: \"\"\n\n"
                "索引信息:\n"
                "  实体ID: \"core_rules\"\n"
                "  名称: \"世界核心规则\"\n"
                "  实体子类型: \"rule\"\n"
                "  状态: \"active\"\n\n"
                "摘要:\n"
                "  一句话描述: \"\"\n"
                "  章节关联: []\n"
                "  关键词: []\n\n"
                "完整档案:\n"
                "  物理法则: \"\"\n"
                "  魔法或科技体系: \"\"\n"
                "  禁忌与限制: \"\"\n"
                "  因果规律: \"\"\n"
                "  特殊机制: \"\"\n"
            ),
            "力量体系.yaml": (
                "# 力量体系\n\n"
                "_meta:\n"
                "  entity_type: \"power_system\"\n"
                "  schema_version: \"1.0\"\n"
                "  created_at: \"\"\n"
                "  updated_at: \"\"\n\n"
                "索引信息:\n"
                "  实体ID: \"power_system\"\n"
                "  名称: \"力量体系\"\n"
                "  实体子类型: \"power_system\"\n"
                "  状态: \"active\"\n\n"
                "摘要:\n"
                "  一句话描述: \"\"\n"
                "  章节关联: []\n"
                "  关键词: []\n\n"
                "完整档案:\n"
                "  体系名称: \"\"\n"
                "  等级划分:\n"
                "    - 等级名: \"等级1\"\n"
                "      描述: \"\"\n"
                "  晋升条件: \"\"\n"
                "  力量来源: \"\"\n"
            ),
            "势力格局.yaml": (
                "# 势力格局\n\n"
                "_meta:\n"
                "  entity_type: \"faction\"\n"
                "  schema_version: \"1.0\"\n"
                "  created_at: \"\"\n"
                "  updated_at: \"\"\n\n"
                "索引信息:\n"
                "  实体ID: \"factions\"\n"
                "  名称: \"势力格局\"\n"
                "  实体子类型: \"faction\"\n"
                "  状态: \"active\"\n\n"
                "摘要:\n"
                "  一句话描述: \"\"\n"
                "  章节关联: []\n"
                "  关键词: []\n\n"
                "完整档案:\n"
                "  势力列表:\n"
                "    - 名称: \"\"\n"
                "      性质: \"\"\n"
                "      核心目标: \"\"\n"
                "  势力平衡: \"\"\n"
                "  隐藏势力: \"\"\n"
                "  冲突焦点: \"\"\n"
            ),
            "地理位置.yaml": (
                "# 世界地理\n\n"
                "_meta:\n"
                "  entity_type: \"location\"\n"
                "  schema_version: \"1.0\"\n"
                "  created_at: \"\"\n"
                "  updated_at: \"\"\n\n"
                "索引信息:\n"
                "  实体ID: \"geography\"\n"
                "  名称: \"世界地理\"\n"
                "  实体子类型: \"location\"\n"
                "  状态: \"active\"\n\n"
                "摘要:\n"
                "  一句话描述: \"\"\n"
                "  章节关联: []\n"
                "  关键词: []\n\n"
                "完整档案:\n"
                "  版图总览: \"\"\n"
                "  主要区域:\n"
                "    - 名称: \"\"\n"
                "      位置: \"\"\n"
                "      气候: \"\"\n"
                "  交通要道: \"\"\n"
                "  危险区域: \"\"\n"
                "  资源分布: \"\"\n"
            ),
            "历史.yaml": (
                "# 世界历史\n\n"
                "_meta:\n"
                "  entity_type: \"history\"\n"
                "  schema_version: \"1.0\"\n"
                "  created_at: \"\"\n"
                "  updated_at: \"\"\n\n"
                "索引信息:\n"
                "  实体ID: \"history\"\n"
                "  名称: \"世界历史\"\n"
                "  实体子类型: \"history\"\n"
                "  状态: \"active\"\n\n"
                "摘要:\n"
                "  一句话描述: \"\"\n"
                "  章节关联: []\n"
                "  关键词: []\n\n"
                "完整档案:\n"
                "  纪元划分:\n"
                "    - 名称: \"远古时代\"\n"
                "      描述: \"\"\n"
                "  重大事件:\n"
                "    - 名称: \"\"\n"
                "      时间: \"\"\n"
                "      影响: \"\"\n"
                "  传说与秘辛: \"\"\n"
                "  历史遗留问题: \"\"\n"
            ),
            "文化.yaml": (
                "# 世界文化\n\n"
                "_meta:\n"
                "  entity_type: \"culture\"\n"
                "  schema_version: \"1.0\"\n"
                "  created_at: \"\"\n"
                "  updated_at: \"\"\n\n"
                "索引信息:\n"
                "  实体ID: \"culture\"\n"
                "  名称: \"世界文化\"\n"
                "  实体子类型: \"culture\"\n"
                "  状态: \"active\"\n\n"
                "摘要:\n"
                "  一句话描述: \"\"\n"
                "  章节关联: []\n"
                "  关键词: []\n\n"
                "完整档案:\n"
                "  种族或民族:\n"
                "    - 名称: \"\"\n"
                "      特征: \"\"\n"
                "  宗教与信仰:\n"
                "    - 名称: \"\"\n"
                "      教义: \"\"\n"
                "  社会结构: \"\"\n"
                "  风俗习惯: \"\"\n"
                "  语言与文字: \"\"\n"
                "  科技或文明水平: \"\"\n"
            ),
        }
        for filename, content in templates.items():
            (wb_path / filename).write_text(content, encoding='utf-8')

    def create_outline_files(self):
        """创建大纲文件，遵循三层结构：
        
        元文档（不索引）: 总纲.yaml / 分卷/
        实体文件（可索引）: 情节线/ (plot_thread) / 分纲/ (chapter)
        追踪文件: 追踪/伏笔.yaml / 追踪/时间线.yaml
        """
        ol_path = self.project_path / "outline"
        now = datetime.now().strftime("%Y-%m-%d")

        # ── Calculate chapter ranges for each act ──
        # Read target chapter count from config if available, fall back to 100
        total_chapters = 100
        config_path = self.project_path / "config.yaml"
        if config_path.is_file():
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    cfg = yaml.safe_load(f)
                if isinstance(cfg, dict):
                    target = cfg.get("目标章节数")
                    if target and isinstance(target, int) and target > 0:
                        total_chapters = target
            except Exception:
                pass
        act_ranges = []
        current_start = 1
        for i, (act_name, pct) in enumerate(zip(self.act_names, self.chapter_distribution)):
            ch_count = max(1, round(total_chapters * pct / 100))
            # Last act takes remaining
            if i == len(self.act_names) - 1:
                act_end = total_chapters
            else:
                act_end = min(current_start + ch_count - 1, total_chapters)
            act_ranges.append((current_start, act_end, act_name))
            current_start = act_end + 1

        # ── Build acts section for 总纲.yaml ──
        acts_lines = []
        acts_lines.append("故事结构:")
        acts_lines.append(f"  结构类型: \"{self.structure_type}\"")
        acts_lines.append("  幕:")
        for i, (s, e, name) in enumerate(act_ranges, 1):
            acts_lines.append(f"    - 幕号: {i}")
            acts_lines.append(f"      名称: \"{name}\"")
            acts_lines.append(f"      章节范围: \"第{s}章 - 第{e}章\"")
            acts_lines.append(f"      主线: \"\"")
            acts_lines.append(f"      关键节点: []")
            acts_lines.append(f"      主角状态: \"\"")
        acts_block = "\n".join(acts_lines)

        # ── Build 分卷 section for 总纲.yaml ──
        vol_dist = []
        # Distribute total chapters evenly across volumes
        ch_per_vol = math.ceil(total_chapters / self.volume_count)
        for v in range(self.volume_count):
            vs = v * ch_per_vol + 1
            ve = min((v + 1) * ch_per_vol, total_chapters)
            vol_dist.append((vs, ve))

        vol_list_lines = []
        vol_list_lines.append("分卷:")
        for v, (vs, ve) in enumerate(vol_dist):
            vol_list_lines.append(f"  - 卷号: {v + 1}")
            vol_list_lines.append(f"    卷名: \"{self.volume_names[v]}\"")
            vol_list_lines.append(f"    章节范围: \"第{vs}章 - 第{ve}章\"")
            vol_list_lines.append(f"    核心问题: \"\"")
            vol_list_lines.append(f"    主角转变: \"\"")
        vol_list_block = "\n".join(vol_list_lines)

        # ── 总纲.yaml（元文档，遵循 novel-writing/assets/outline.yaml 模板） ──
        (
            ol_path / "总纲.yaml"
        ).write_text(
            f"# 总纲\n\n"
            f"项目名称: \"{self.project_name}\"\n"
            f"类型: \"{self.genre}\"\n"
            f"目标字数: 100000\n"
            f"预计章节数: {total_chapters}\n"
            f"目标读者: \"\"\n\n"
            f"核心概念:\n"
            f"  一句话概述: \"\"\n"
            f"  核心卖点: \"\"\n"
            f"  主题关键词: []\n"
            f"  主题:\n"
            f"    核心: \"\"\n"
            f"    呈现: \"\"\n\n"
            f"人物与世界:\n"
            f"  主角与世界的关系: \"\"\n"
            f"  主角的特殊性: \"\"\n"
            f"  世界规则对主角的约束: []\n"
            f"  主角打破/利用世界规则的方式: \"\"\n"
            f"  初始境况: \"\"\n\n"
            f"{acts_block}\n\n"
            f"{vol_list_block}\n\n"
            f"节奏:\n"
            f"  前期基调: \"\"\n"
            f"  中期基调: \"\"\n"
            f"  后期基调: \"\"\n"
            f"  章节分布: {self.chapter_distribution}\n\n"
            f"结局类型: \"\"\n"
            f"结局设计: \"\"\n",
            encoding="utf-8",
        )

        # ── 分卷/（元文档，遵循 novel-writing/assets/volume.yaml 模板） ──
        vol_dir = ol_path / "分卷"
        for v in range(self.volume_count):
            vs, ve = vol_dist[v]
            vol_name = self.volume_names[v]
            vol_file_name = f"卷{v + 1}_{vol_name}.yaml"
            (vol_dir / vol_file_name).write_text(
                f"# 第{self._cn_ordinal(v + 1)}卷：{vol_name}\n\n"
                f"分卷名称: \"{vol_name}\"\n"
                f"卷号: {v + 1}\n"
                f"章节范围: \"第{vs}章 - 第{ve}章\"\n\n"
                f"概要: \"\"\n\n"
                f"核心问题: \"\"\n\n"
                f"关键情节点:\n"
                f"  - 节点: \"\"\n"
                f"    涉及章节: \"\"\n"
                f"    角色: []\n"
                f"    影响: \"\"\n\n"
                f"卷内角色发展:\n"
                f"  主角:\n"
                f"    起始状态: \"\"\n"
                f"    目标: \"\"\n"
                f"    障碍: []\n"
                f"    成长: \"\"\n"
                f"    卷终状态: \"\"\n"
                f"  重要配角: []\n\n"
                f"势力变动: []\n"
                f"世界观揭示: []\n\n"
                f"本卷容易踩的坑: []\n"
                f"与其他卷的衔接注意: \"\"\n",
                encoding="utf-8",
            )

        # ── 情节线/（实体，遵循 plot_thread_schema） ──
        # 主线固定一个，支线可按需创建多个（支线_爱情线.yaml、支线_复仇线.yaml …）
        plot_dir = ol_path / "情节线"
        plot_templates = {
            "主线.yaml": (
                "# 主线\n\n"
                "_meta:\n"
                "  entity_type: \"plot_thread\"\n"
                "  schema_version: \"3.0\"\n"
                "  created_at: \"\"\n"
                "  updated_at: \"\"\n\n"
                "索引信息:\n"
                "  实体ID: \"main_plot\"\n"
                "  名称: \"主线\"\n"
                "  类型: \"main\"\n"
                "  状态: \"active\"\n"
                "  起始章节: 1\n"
                "  当前章节位置: 0\n\n"
                "摘要:\n"
                "  一句话描述: \"\"\n"
                "  当前境况: \"\"\n"
                "  核心特质: []\n"
                "  当前目标: \"\"\n"
                "  关键关系: []\n"
                "  当前区间: \"\"\n"
                "  区间情节点: []\n"
                "  关联角色: []\n\n"
                "完整档案:\n"
                "  描述: \"\"\n"
                "  类型: \"主线\"\n"
                "  冲突核心: \"\"\n"
                "  关键事件: []\n"
                "  关联支线: []\n"
                "  终局设计: \"\"\n"
                "  创作笔记:\n"
                "    注意事项: []\n"
            ),
            "支线_示例.yaml": (
                "# 支线示例（可按需创建多条：支线_爱情线.yaml、支线_复仇线.yaml …）\n\n"
                "_meta:\n"
                "  entity_type: \"plot_thread\"\n"
                "  schema_version: \"3.0\"\n"
                "  created_at: \"\"\n"
                "  updated_at: \"\"\n\n"
                "索引信息:\n"
                "  实体ID: \"sub_plot_example\"\n"
                "  名称: \"支线示例\"\n"
                "  类型: \"sub\"\n"
                "  状态: \"active\"\n"
                "  起始章节: 0\n"
                "  当前章节位置: 0\n\n"
                "摘要:\n"
                "  一句话描述: \"\"\n"
                "  当前境况: \"\"\n"
                "  核心特质: []\n"
                "  当前目标: \"\"\n"
                "  关键关系: []\n"
                "  当前区间: \"\"\n"
                "  区间情节点: []\n"
                "  关联角色: []\n\n"
                "完整档案:\n"
                "  描述: \"（删除此文件并创建自己的支线，如 支线_爱情线.yaml）\"\n"
                "  类型: \"支线\"\n"
                "  冲突核心: \"\"\n"
                "  关键事件: []\n"
                "  关联支线: []\n"
                "  终局设计: \"\"\n"
                "  创作笔记:\n"
                "    注意事项: []\n"
            ),
        }
        for filename, content in plot_templates.items():
            (plot_dir / filename).write_text(content, encoding="utf-8")

        # ── 追踪/（运行时数据） ──
        track_dir = ol_path / "追踪"
        track_templates = {
            "伏笔.yaml": (
                "# 伏笔追踪\n\n"
                "伏笔:\n"
                "  - 描述: \"\"\n"
                "    章节: \"\"\n"
                "    状态: \"\"\n"
            ),
            "时间线.yaml": (
                "# 时间线事件\n\n"
                "事件:\n"
                "  - 描述: \"\"\n"
                "    时间: \"\"\n"
                "    章节: \"\"\n"
            ),
        }
        for filename, content in track_templates.items():
            (track_dir / filename).write_text(content, encoding="utf-8")

    @staticmethod
    def _cn_ordinal(n: int) -> str:
        """Convert integer to Chinese ordinal (1→一, 2→二, ..., 12→十二)."""
        digits = "零一二三四五六七八九"
        if n <= 10:
            return digits[n]
        if n < 20:
            return f"十{digits[n - 10]}" if n > 10 else "十"
        tens = n // 10
        rem = n % 10
        if rem == 0:
            return f"{digits[tens]}十"
        return f"{digits[tens]}十{digits[rem]}"

    def create_character_stats_file(self):
        """创建角色统计文件（移到了 characters/ 下）"""
        char_path = self.project_path / "characters"
        content = "# 角色出场统计\n\n角色:\n  \"\":\n    总出场章节: 0\n    出场章节列表: []\n    首次出场: 0\n    最近出场: 0\n"
        (char_path / "角色统计.yaml").write_text(content, encoding='utf-8')

    def create_ideation_templates(self):
        """创建创意构思目录及 5 个阶段模板文件"""
        ideation_path = self.project_path / "ideation"

        templates = {
            "需求分析.yaml": f"""# 需求分析 — {self.project_name}
# 此文件定义创作的边界条件和目标

类型: "{self.genre}"
目标读者: ""
篇幅: ""
基调: ""
核心元素: []
排斥元素: []
创新诉求: ""
""",
            "约束集.yaml": """# 约束集
# 6 大类约束，每类可包含多项

结构约束: []
内容约束: []
角色约束: []
设定约束: []
形式约束: []
主题约束: []
""",
            "创意简报.yaml": """# 创意简报
# 3-5 个创意方向，选定后标记 选定: true

- 方向编号: 1
  一句话概述: ""
  核心冲突: ""
  主角设定: ""
  亮点卖点: ""
  选定: false
- 方向编号: 2
  一句话概述: ""
  核心冲突: ""
  主角设定: ""
  亮点卖点: ""
  选定: false
- 方向编号: 3
  一句话概述: ""
  核心冲突: ""
  主角设定: ""
  亮点卖点: ""
  选定: false
""",
            "评估报告.yaml": """# 评估报告
# 4 维度评分（0-5 分），阈值：总分 ≥ 16，原创性 ≥ 4，吸引力 ≥ 4

评估维度:
  原创性: {}
  可行性: {}
  吸引力: {}
  独特性: {}
推荐方向: 0
改进建议: []
""",
            "最终创意方案.yaml": f"""# 最终创意方案 — {self.project_name}
# 选定创意方向后的完整方案，供 novel-writing 读取

故事概念: ""
类型: "{self.genre}"
主角:
  姓名: ""
  角色类型: "主角"
  一句话描述: ""
  核心特质: []
  当前目标: ""
核心冲突: ""
世界观关键词: []
情节主线: ""
预期章节数: 0
""",
        }
        for filename, content in templates.items():
            (ideation_path / filename).write_text(content, encoding='utf-8')

    def create_index_file(self):
        """创建空的项目索引骨架，供 context-service 逐步填充。
        
        格式遵循 update_index.py 的 load_or_create_index() 输出约定。
        """
        from datetime import datetime
        now = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
        index_content = f"""# 项目实体索引 — 由 rebuild_project_index.py 维护
# 此文件记录所有实体（角色/世界观/情节线/章节）的 Layer 1 索引信息
# rebuild_project_index.py 自动更新，请勿手动编辑

_meta:
  generated_by: "novel-project-manager/init.py"
  created_at: "{now}"
  last_updated: "{now}"
  project_name: "{self.project_name}"
  entity_counts:
    characters: 0
    worldbuilding: 0
    plot_threads: 0
    chapters: 0

characters: {{}}
worldbuilding: {{}}
plot_threads: {{}}
chapters: {{}}
"""
        (self.project_path / "project_index.yaml").write_text(index_content, encoding='utf-8')

    def _index_initial_entities(self):
        """项目创建后，调用 rebuild_project_index.py 建立初始索引。"""
        rebuild_script = (
            Path(__file__).parent.parent.parent.parent
            / "shared" / "rebuild_project_index.py"
        ).resolve()
        proj_root = str(self.project_path.resolve())

        result = subprocess.run(
            [sys.executable, str(rebuild_script), "--project-root", proj_root],
            capture_output=True,
            timeout=30,
        )
        if result.returncode != 0:
            print(f"  ⚠️ 索引重建失败: {result.stderr.decode('utf-8', errors='replace').strip()[:200]}",
                  file=sys.stderr)
        else:
            print(result.stdout.decode('utf-8', errors='replace').strip())


    def _persist_old_project_context(self, notepad_dir):
        """如果 novel-context.md 已有旧项目内容，先保存到 projects/ 目录。"""
        context_path = notepad_dir / "novel-context.md"
        if not context_path.is_file():
            return
        old_content = context_path.read_text(encoding="utf-8")
        # 提取旧项目名
        import re
        match = re.search(r'# 项目上下文: (.+)', old_content)
        if not match:
            return
        old_project = match.group(1).strip()
        if old_project == self.project_name:
            return  # 同一项目，不保存
        # 持久化到 projects/{旧项目名}.md
        projects_dir = notepad_dir / "projects"
        projects_dir.mkdir(parents=True, exist_ok=True)
        save_path = projects_dir / f"{old_project}.md"
        save_path.write_text(old_content, encoding="utf-8")

    def _init_notepad_files(self):
        """从模板初始化 .omo/notepads/ 下的三个运行时文件。"""
        script_root = Path(__file__).resolve().parent.parent.parent.parent.parent
        template_dir = script_root / ".omo" / "notepads" / "templates"
        notepad_dir = script_root / ".omo" / "notepads"

        # 持久化旧项目上下文（如果存在且不是同一项目）
        self._persist_old_project_context(notepad_dir)

        templates = {
            "novel-context.template.md": "novel-context.md",
            "novel-issues.template.md": "novel-issues.md",
            "novel-learnings.template.md": "novel-learnings.md",
        }

        for tpl_name, out_name in templates.items():
            tpl_path = template_dir / tpl_name
            if tpl_path.is_file():
                out_path = notepad_dir / out_name
                # novel-context.md 总是覆盖为新项目；issues/learnings 首次创建后保留
                if out_name != "novel-context.md" and out_path.is_file():
                    continue
                content = tpl_path.read_text(encoding="utf-8")
                content = content.replace("{项目名}", self.project_name)
                out_path.write_text(content, encoding="utf-8")


    def initialize(self):
        if self.project_path.exists():
            print(f"⚠️  项目 '{self.project_name}' 已存在！")
            return False

        self.create_directory_structure()
        self.create_config_file()
        self._create_style_index()
        self.create_worldbuilding_files()
        self.create_outline_files()
        self.create_character_stats_file()
        self.create_ideation_templates()
        self.create_index_file()
        self._index_initial_entities()
        self._init_notepad_files()

        print(f"📁 创建项目: {self.project_name}")
        print("-" * 40)
        print(f"  结构: {self.structure_type} / {self.volume_count}卷 / {self.act_count}幕")
        print("  ✓ chapters/")
        print("  ✓ characters/")
        print("  ✓ ideation/（5 个文件）")
        print("  ✓ outline/总纲.yaml")
        print("  ✓ outline/分卷/")
        print("  ✓ outline/情节线/")
        vol_dirs = f"卷1~{self.volume_count}"
        print(f"  ✓ outline/分纲/{vol_dirs}/")
        print("  ✓ outline/追踪/")
        print("  ✓ worldbuilding/")
        print("  ✓ config.yaml")
        for wb in ["基本信息", "核心规则", "力量体系", "势力格局", "地理位置", "历史", "文化"]:
            print(f"  ✓ worldbuilding/{wb}.yaml")
        print("  ✓ characters/角色统计.yaml")
        print("  ✓ project_index.yaml")
        print("-" * 40)
        print(f"✅ 项目 '{self.project_name}' 创建完成！")
        print(f"📂 位置: {self.project_path.absolute()}")
        print(f"📐 结构: {self.structure_type} / {self.volume_count}卷 / {self.act_count}幕")
        return True


# ===========================================================================
# 导入项目
# ===========================================================================

class ProjectImporter:
    def __init__(self, source_path: str, project_name: str, target_dir: str = None,
                 volume_count: int = 3):
        self.source_path = Path(source_path)
        self.project_name = project_name
        if target_dir is None:
            target_dir = str(find_novels_root())
        self.target_dir = Path(target_dir)
        self.project_path = self.target_dir / project_name
        self.volume_count = max(1, volume_count)

    def _classify_yaml_content(self, file_path: Path) -> str:
        """读取 YAML 顶层 key，判断内容类型"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f)
            if not isinstance(data, dict):
                return 'unknown'

            keys = set(data.keys())
            all_keys_str = ' '.join(str(k) for k in keys)

            # 大纲特征
            if keys & {'大纲', '三幕结构', '情感发展', '核心概念', '结构'}:
                return 'outline'
            if any(k in all_keys_str for k in ['幕结构', '分卷', '情节点']):
                return 'outline'

            # 角色特征
            if keys & {'角色', '姓名', '年龄', '性格', '外貌', '背景故事'}:
                return 'character'
            if any(k in all_keys_str for k in ['角色档案', '人物设定']):
                return 'character'

            # 世界观特征
            if keys & {'世界名称', '力量体系', '势力格局', '核心规则', '地理位置'}:
                return 'worldbuilding'
            if any(k in all_keys_str for k in ['世界观', '世界设定']):
                return 'worldbuilding'

            # 章节分纲特征
            if keys & {'章节号', '正文', '场景', '情节点'}:
                return 'chapter_outline'

            return 'unknown'
        except Exception:
            return 'unknown'

    def _guess_file_type_by_name(self, file_path: Path) -> str:
        """基于文件名猜测类型（启发式，不读取内容）"""
        name = file_path.name.lower()
        if any(k in name for k in CHARACTER_KEYWORDS):
            return 'likely_character'
        if any(k in name for k in OUTLINE_FILENAME_KEYWORDS):
            return 'likely_outline'
        if any(k in name for k in WORLDBUILDING_KEYWORDS):
            return 'likely_worldbuilding'
        if any(k in name for k in CHAPTER_KEYWORDS):
            return 'likely_chapter'
        return 'unknown'

    def _upgrade_worldbuilding_to_threelayer(self, file_path: Path) -> str | None:
        """尝试将旧格式 worldbuilding YAML 升级为三层结构。

        检测是否已有 _meta 块；若没有，自动添加并嵌套原内容到 完整档案。
        返回升级后的 YAML 字符串，或 None（升级失败/已是三层格式）。
        """
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f)
            if not isinstance(data, dict):
                return None
        except Exception:
            return None

        # 已是三层格式 → 不需要升级
        if '_meta' in data and '索引信息' in data:
            return None

        # 推测子类型
        subtype_map = {
            "基本信息": "world_overview",
            "核心规则": "rule",
            "力量体系": "power_system",
            "势力格局": "faction",
            "地理位置": "location",
            "历史": "history",
            "文化": "culture",
        }
        stem = file_path.stem
        subtype = subtype_map.get(stem, "worldbuilding")

        # 提取名称
        name = data.get("世界名称", "") or data.get("体系名称", "") or data.get("世界名称", "") or stem

        # 提取已有的一行描述
        one_liner = data.pop("一句话概述", "") or data.pop("一句话描述", "") or ""

        # 保留所有原始字段作为完整档案
        original_content = data

        now = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
        upgraded = {
            "_meta": {
                "entity_type": subtype,
                "schema_version": "1.0",
                "created_at": "",
                "updated_at": now,
            },
            "索引信息": {
                "实体ID": stem,
                "名称": name,
                "实体子类型": subtype,
                "状态": "active",
            },
            "摘要": {
                "一句话描述": one_liner,
                "章节关联": [],
                "关键词": [],
            },
            "完整档案": original_content,
        }

        output = io.StringIO()
        yaml.safe_dump(upgraded, output, default_flow_style=False, sort_keys=False, allow_unicode=True)
        return output.getvalue()
    

    def _detect_outline_version(self, data: dict) -> str:
        """检测大纲格式版本"""
        outline = data.get('大纲', {})
        if isinstance(outline, dict):
            version = outline.get('版本', '')
            if version == '2.0':
                return 'v2.0'
            if '模块' in outline:
                return 'v1.x'  # 带索引的旧格式
        # 检查是否为单文件大 YAML（顶层 key 数量多）
        if len(data) > 5:
            return 'single_file'
        return 'unknown'

    def _generate_migration_report(self) -> dict:
        """生成迁移报告，列出待处理的文件和分类建议"""
        report = {
            "migration_report": {
                "source_path": str(self.source_path),
                "imported_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
                "status": "pending_agent_review",
                "auto_classified": [],
                "needs_agent_review": [],
                "outline_files": [],
                "summary": {
                    "total_files": 0,
                    "auto_classified_count": 0,
                    "needs_review_count": 0,
                }
            }
        }

        total = 0
        auto_count = 0
        review_count = 0

        for item in self.project_path.rglob("*"):
            if not item.is_file():
                continue
            total += 1
            rel_path = str(item.relative_to(self.project_path))

            # 跳过已放入标准目录的文件
            if rel_path.startswith(("chapters/", "characters/", "worldbuilding/", "outline/")):
                continue
            if item.name in ("config.yaml",):
                continue

            suffix = item.suffix.lower()

            if suffix in (".yaml", ".yml"):
                # 先基于文件名猜测
                name_guess = self._guess_file_type_by_name(item)
                # 再基于内容判断
                content_type = self._classify_yaml_content(item)

                final_type = content_type if content_type != 'unknown' else name_guess

                entry = {
                    "path": rel_path,
                    "name_guess": name_guess,
                    "content_type": content_type,
                    "final_classification": final_type,
                    "needs_review": content_type == 'unknown' and name_guess == 'unknown',
                }

                if content_type == 'outline':
                    # 检测大纲版本
                    try:
                        with open(item, 'r', encoding='utf-8') as f:
                            data = yaml.safe_load(f)
                        entry["outline_version"] = self._detect_outline_version(data) if isinstance(data, dict) else "unknown"
                    except Exception:
                        entry["outline_version"] = "unknown"
                    report["migration_report"]["outline_files"].append(entry)

                if entry["needs_review"]:
                    review_count += 1
                    report["migration_report"]["needs_agent_review"].append(entry)
                else:
                    auto_count += 1
                    report["migration_report"]["auto_classified"].append(entry)

            elif suffix in (".txt", ".md"):
                # 文本文件可能是章节
                entry = {
                    "path": rel_path,
                    "suggested_action": "check_if_chapter",
                    "needs_review": True,
                }
                review_count += 1
                report["migration_report"]["needs_agent_review"].append(entry)

            else:
                entry = {
                    "path": rel_path,
                    "suggested_action": "review_or_delete",
                    "needs_review": True,
                }
                review_count += 1
                report["migration_report"]["needs_agent_review"].append(entry)

        report["migration_report"]["summary"] = {
            "total_files": total,
            "auto_classified_count": auto_count,
            "needs_review_count": review_count,
        }

        return report

    def import_project(self):
        if not self.source_path.exists():
            print(f"❌ 源路径不存在: {self.source_path}")
            return False

        if self.project_path.exists():
            print(f"⚠️  项目 '{self.project_name}' 已存在！")
            return False

        # 1. 创建标准目录（与新项目结构一致）
        import_dirs = [
            "chapters", "characters",
            "outline/总纲", "outline/分卷", "outline/情节线",
            "outline/追踪", "worldbuilding",
        ]
        for v in range(1, self.volume_count + 1):
            import_dirs.append(f"outline/分纲/卷{v}")
        for d in import_dirs:
            (self.project_path / d).mkdir(parents=True, exist_ok=True)

        # 2. 复制源文件到暂存区
        staging_dir = self.project_path / "_migration_staging"
        staging_dir.mkdir(parents=True, exist_ok=True)

        for item in self.source_path.iterdir():
            dest = staging_dir / item.name
            if item.is_file():
                shutil.copy2(item, dest)
            elif item.is_dir():
                shutil.copytree(item, dest, dirs_exist_ok=True)

        # 3. 自动分类已知文件（带细粒度路由）
        auto_moved = 0
        worldbuilding_upgraded = 0
        for item in list(staging_dir.rglob("*")):
            if not item.is_file():
                continue

            suffix = item.suffix.lower()

            # .txt 文件 → chapters/
            if suffix == ".txt":
                dest = self.project_path / "chapters" / item.name
                shutil.move(str(item), str(dest))
                auto_moved += 1
                continue

            # 基于文件名精准路由
            name = item.name

            # 大纲元文档 → 分路由
            if name in ("故事结构.yaml", "故事结构.yml"):
                dest = self.project_path / "outline" / "总纲" / f"总纲{Path(item.name).suffix}"
                shutil.move(str(item), str(dest))
                auto_moved += 1
                continue
            if name in ("情节线.yaml", "情节线.yml"):
                dest = self.project_path / "outline" / "情节线" / f"主线{Path(item.name).suffix}"
                shutil.move(str(item), str(dest))
                auto_moved += 1
                continue
            if name in ("伏笔.yaml", "伏笔.yml"):
                dest = self.project_path / "outline" / "追踪" / f"伏笔{Path(item.name).suffix}"
                shutil.move(str(item), str(dest))
                auto_moved += 1
                continue
            if name in ("时间线.yaml", "时间线.yml"):
                dest = self.project_path / "outline" / "追踪" / f"时间线{Path(item.name).suffix}"
                shutil.move(str(item), str(dest))
                auto_moved += 1
                continue
            if name in ("角色弧光.yaml", "角色弧光.yml", "世界观接轨.yaml", "世界观接轨.yml"):
                dest = self.project_path / "outline" / item.name
                shutil.move(str(item), str(dest))
                auto_moved += 1
                continue

            # 章节分纲 → 按章号动态分入对应卷
            chapter_match = re.match(r"第\s*(\d+)\s*章", name)
            if chapter_match and suffix in (".yaml", ".yml"):
                ch_num = int(chapter_match.group(1))
                # Use volume count from config or default to 3
                vol_count = getattr(self, 'volume_count', 3)
                ch_per_vol = max(1, math.ceil(100 / vol_count))
                vol_num = min(math.ceil(ch_num / ch_per_vol), vol_count)
                vol = f"卷{vol_num}"
                vol_dir = self.project_path / "outline" / "分纲" / vol
                vol_dir.mkdir(parents=True, exist_ok=True)
                dest = vol_dir / item.name
                shutil.move(str(item), str(dest))
                auto_moved += 1
                continue

            # 通用分类
            guess = self._guess_file_type_by_name(item)

            if guess == 'likely_character' and suffix in (".yaml", ".yml"):
                dest = self.project_path / "characters" / item.name
                shutil.move(str(item), str(dest))
                auto_moved += 1
                continue
            elif guess == 'likely_worldbuilding' and suffix in (".yaml", ".yml"):
                # 尝试升级为三层格式
                upgraded = self._upgrade_worldbuilding_to_threelayer(item)
                if upgraded:
                    dest = self.project_path / "worldbuilding" / item.name
                    dest.write_text(upgraded, encoding='utf-8')
                    item.unlink()  # 删除暂存区旧文件
                    worldbuilding_upgraded += 1
                    auto_moved += 1
                else:
                    dest = self.project_path / "worldbuilding" / item.name
                    shutil.move(str(item), str(dest))
                    auto_moved += 1
                continue

        # 4. 生成 migration_report
        report = self._generate_migration_report()
        report_path = self.project_path / "migration_report.yaml"

        with open(report_path, 'w', encoding='utf-8') as f:
            yaml.safe_dump(report, f, allow_unicode=True, default_flow_style=False)

        # 5. 生成 config.yaml（如果不存在）
        config_path = self.project_path / "config.yaml"
        if not config_path.exists():
            now = datetime.now().strftime("%Y-%m-%d")
            config_content = f"""项目名称: "{self.project_name}"
项目类型: "未知"
状态: "进行中"
当前阶段: "创意构思"
创建时间: "{now}"
最后编辑: "{now}"

创作进度:
  当前章节: 0
  已完成字数: 0

工作流:
  干预等级: "medium"
  AI自主度: true
  检查频率: "weekly"

质量检查:
  章节最少字数: 1500
  章节最多字数: 6000
"""
            config_path.write_text(config_content, encoding='utf-8')

        # 5.5 生成 project_index.yaml 骨架
        index_path = self.project_path / "project_index.yaml"
        if not index_path.exists():
            from datetime import datetime as dt_ix
            now_ix = dt_ix.now().strftime("%Y-%m-%dT%H:%M:%S")
            index_content = f"""# 项目实体索引 — 由 rebuild_project_index.py 维护
_meta:
  generated_by: "novel-project-manager/init.py"
  created_at: "{now_ix}"
  last_updated: "{now_ix}"
  project_name: "{self.project_name}"
  entity_counts:
    characters: 0
    worldbuilding: 0
    plot_threads: 0
    chapters: 0

characters: {{}}
worldbuilding: {{}}
plot_threads: {{}}
chapters: {{}}
"""
            index_path.write_text(index_content, encoding='utf-8')

        # 6. 输出结果
        summary = report["migration_report"]["summary"]
        print(f"📁 导入项目: {self.project_name}")
        print("-" * 40)
        print(f"📂 位置: {self.project_path.absolute()}")
        print(f"📋 自动分类: {auto_moved} 个文件")
        if worldbuilding_upgraded > 0:
            print(f"⬆️  worldview 三层升级: {worldbuilding_upgraded} 个文件")
        print(f"🔍 待 Agent 审查: {summary['needs_review_count']} 个文件")
        print(f"📄 迁移报告: migration_report.yaml")
        print(f"📊 项目索引: project_index.yaml")
        if summary['needs_review_count'] > 0:
            print("⚠️  请 Agent 读取 migration_report.yaml 并处理待分类文件")
        print(f"✅ 项目 '{self.project_name}' 导入完成！")

        # 8. 清理暂存区
        staging_dir = self.project_path / "_migration_staging"
        if staging_dir.exists():
            shutil.rmtree(staging_dir)
        return True


# ===========================================================================
# 查看状态
# ===========================================================================

class ProjectStatus:
    def __init__(self, project_name: str, target_dir: str = None):
        self.project_name = project_name
        if target_dir is None:
            target_dir = str(find_novels_root())
        self.target_dir = Path(target_dir)
        self.project_path = self.target_dir / project_name

    def show_status(self, phase: Optional[str] = None, intervention: Optional[str] = None):
        if not self.project_path.exists():
            print(f"❌ 项目 '{self.project_name}' 不存在！")
            return False

        config_path = self.project_path / "config.yaml"
        if not config_path.exists():
            print(f"❌ config.yaml 不存在！")
            return False

        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)

        # 更新阶段
        if phase:
            config['当前阶段'] = phase
            config['最后编辑'] = datetime.now().strftime("%Y-%m-%d")
            with open(config_path, 'w', encoding='utf-8') as f:
                yaml.safe_dump(config, f, allow_unicode=True, default_flow_style=False)
            print(f"✅ 阶段已更新为: {phase}")

        # 更新干预等级
        if intervention:
            if '工作流' not in config:
                config['工作流'] = {}
            config['工作流']['干预等级'] = intervention
            with open(config_path, 'w', encoding='utf-8') as f:
                yaml.safe_dump(config, f, allow_unicode=True, default_flow_style=False)
            print(f"✅ 干预等级已更新为: {intervention}")

        # 显示状态
        print(f"📊 项目状态: {self.project_name}")
        print("-" * 40)
        print(f"状态: {config.get('状态', '未知')}")
        print(f"当前阶段: {config.get('当前阶段', '未知')}")
        print(f"作者: {config.get('作者', '')}")
        print(f"干预等级: {config.get('工作流', {}).get('干预等级', 'medium')}")

        progress = config.get('创作进度', {})
        print(f"当前章节: {progress.get('当前章节', 0)}")
        print(f"已完成字数: {progress.get('已完成字数', 0)}")
        print(f"创建时间: {config.get('创建时间', '')}")
        print(f"最后编辑: {config.get('最后编辑', '')}")

        # 统计章节数
        chapters_dir = self.project_path / "chapters"
        if chapters_dir.exists():
            chapter_count = len(list(chapters_dir.glob("*.txt")))
            print(f"章节文件数: {chapter_count}")

        return True


# ===========================================================================
# 续写项目
# ===========================================================================

class ProjectResume:
    def __init__(self, project_name: str, target_dir: str = None):
        self.project_name = project_name
        if target_dir is None:
            target_dir = str(find_novels_root())
        self.target_dir = Path(target_dir)
        self.project_path = self.target_dir / project_name

    def resume_project(self):
        if not self.project_path.exists():
            print(f"❌ 项目 '{self.project_name}' 不存在！")
            return False

        config_path = self.project_path / "config.yaml"
        if not config_path.exists():
            print(f"❌ config.yaml 不存在！")
            return False

        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)

        # 查找最新章节
        chapters_dir = self.project_path / "chapters"
        last_chapter = "无"
        chapter_count = 0
        if chapters_dir.exists():
            chapters = sorted(chapters_dir.glob("*.txt"))
            chapter_count = len(chapters)
            if chapters:
                last_chapter = chapters[-1].name

        # 更新最后编辑时间
        config['最后编辑'] = datetime.now().strftime("%Y-%m-%d")
        with open(config_path, 'w', encoding='utf-8') as f:
            yaml.safe_dump(config, f, allow_unicode=True, default_flow_style=False)

        print(f"📖 继续项目: {self.project_name}")
        print("-" * 40)
        print(f"当前阶段: {config.get('当前阶段', '未知')}")
        progress = config.get('创作进度', {})
        print(f"已写字数: {progress.get('已完成字数', 0)}")
        print(f"章节数: {chapter_count}")
        if last_chapter != "无":
            print(f"最新章节: {last_chapter}")
        print("-" * 40)

        # 更新 .omo/notepads/novel-context.md（切换项目时持久化旧上下文）
        script_root = Path(__file__).resolve().parent.parent.parent.parent.parent
        notepad_dir = script_root / ".omo" / "notepads"
        context_path = notepad_dir / "novel-context.md"

        if context_path.is_file():
            old_content = context_path.read_text(encoding="utf-8")
            old_match = re.search(r'# 项目上下文: (.+)', old_content)
            if old_match and old_match.group(1).strip() != self.project_name:
                # 持久化旧项目上下文
                projects_dir = notepad_dir / "projects"
                projects_dir.mkdir(parents=True, exist_ok=True)
                save_path = projects_dir / f"{old_match.group(1).strip()}.md"
                save_path.write_text(old_content, encoding="utf-8")

        # 写入新项目上下文
        tpl_path = notepad_dir / "templates" / "novel-context.template.md"
        if tpl_path.is_file():
            content = tpl_path.read_text(encoding="utf-8")
            content = content.replace("{项目名}", self.project_name)
            context_path.write_text(content, encoding="utf-8")

        print("✅ 项目已准备好继续创作")
        return True


# ===========================================================================
# 删除项目
# ===========================================================================

class ProjectDeleter:
    def __init__(self, project_name: str, target_dir: str = None, force: bool = False):
        self.project_name = project_name
        if target_dir is None:
            target_dir = str(find_novels_root())
        self.target_dir = Path(target_dir)
        self.project_path = self.target_dir / project_name
        self.force = force

    def delete_project(self):
        if not self.project_path.exists():
            print(f"❌ 项目 '{self.project_name}' 不存在！")
            return False

        if not self.force:
            response = input(f"⚠️  确认删除项目 '{self.project_name}'？(y/n): ").strip().lower()
            if response != 'y':
                print("❌ 已取消删除")
                return False

        shutil.rmtree(self.project_path)
        print(f"✅ 项目 '{self.project_name}' 已删除")
        return True


# ===========================================================================
# CLI 入口
# ===========================================================================

def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="小说项目管理 - 统一入口",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 新建项目
  python init.py new "我的小说" "玄幻"
  python init.py new "星辰修仙路" "仙侠" -d C:/projects

  # 导入项目
  python init.py import "C:/已有小说" "项目名"

  # 查看状态
  python init.py status "我的小说"
  python init.py status "我的小说" --phase "章节创作"
  python init.py status "我的小说" --intervention high

  # 续写项目
  python init.py resume "我的小说"

  # 删除项目
  python init.py delete "我的小说"
  python init.py delete "我的小说" --force
        """
    )

    subparsers = parser.add_subparsers(dest="command", help="子命令")

    # new
    p_new = subparsers.add_parser("new", help="新建项目")
    p_new.add_argument("name", help="项目名称")
    p_new.add_argument("genre", nargs="?", default="通用", help="小说类型")
    p_new.add_argument("--root", "-r", default="novels", help="目标目录（默认 novels/）")
    p_new.add_argument("--volumes", type=int, default=3, help="卷数（默认 3）")
    p_new.add_argument("--acts", type=int, default=0,
                       help="幕数（默认：三幕=3, 五幕=5）；与 --structure 配合使用")
    p_new.add_argument("--structure", default="三幕", choices=["三幕", "五幕", "自定义"],
                       help="结构类型（默认 三幕）")

    # import
    p_import = subparsers.add_parser("import", help="导入项目")
    p_import.add_argument("source", help="源路径")
    p_import.add_argument("name", help="项目名称")
    p_import.add_argument("--root", "-r", default="novels", help="目标目录（默认 novels/）")
    p_import.add_argument("--volumes", type=int, default=3,
                          help="目标卷数（仅影响分纲目录划分，默认 3）")

    # status
    p_status = subparsers.add_parser("status", help="查看状态")
    p_status.add_argument("name", help="项目名称")
    p_status.add_argument("--root", "-r", default=None, help="目标目录（默认自动发现 NOVELS_ROOT）")
    p_status.add_argument("--phase", choices=["创意构思", "大纲规划", "分纲撰写", "章节创作", "完稿", "暂停"], help="更新阶段")
    p_status.add_argument("--intervention", choices=["high", "medium", "low"], help="修改干预等级")

    # resume
    p_resume = subparsers.add_parser("resume", help="续写项目")
    p_resume.add_argument("name", help="项目名称")
    p_resume.add_argument("--root", "-r", default=None, help="目标目录（默认自动发现 NOVELS_ROOT）")

    # delete
    p_delete = subparsers.add_parser("delete", help="删除项目")
    p_delete.add_argument("name", help="项目名称")
    p_delete.add_argument("--root", "-r", default=None, help="目标目录（默认自动发现 NOVELS_ROOT）")
    p_delete.add_argument("--force", action="store_true", help="跳过确认")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    if args.command == "new":
        initializer = ProjectInitializer(
            args.name, args.genre, args.root,
            volume_count=args.volumes,
            act_count=args.acts,
            structure_type=args.structure,
        )
        success = initializer.initialize()
        sys.exit(0 if success else 1)

    elif args.command == "import":
        importer = ProjectImporter(
            args.source, args.name, args.root,
            volume_count=args.volumes,
        )
        success = importer.import_project()
        sys.exit(0 if success else 1)

    elif args.command == "status":
        status = ProjectStatus(args.name, args.root)
        success = status.show_status(args.phase, args.intervention)
        sys.exit(0 if success else 1)

    elif args.command == "resume":
        resume = ProjectResume(args.name, args.root)
        success = resume.resume_project()
        sys.exit(0 if success else 1)

    elif args.command == "delete":
        deleter = ProjectDeleter(args.name, args.root, args.force)
        success = deleter.delete_project()
        sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()

