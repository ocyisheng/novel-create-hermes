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
  python init.py status "项目名" [-d 目录] [--phase 阶段]
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
                "  起始章节: 1\n\n"
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
                "  起始章节: 0\n\n"
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
                "# 伏笔记录\n\n"
                "伏笔:\n"
                "  # 每章写后追加记录\n"
                "  # - 描述: \"伏笔内容\"\n"
                "  #   章节: 1\n"
                "  #   状态: \"待回收\"\n"
            ),
            "时间线.yaml": (
                "# 时间线记录\n\n"
                "事件:\n"
                "  # 每章写后追加记录\n"
                "  # - 描述: \"事件内容\"\n"
                "  #   章节: 1\n"
                "  #   时间: \"故事时间\"\n"
            ),
            "角色统计.yaml": (
                "# 角色出场统计\n\n"
                "出场:\n"
                "  # 每章写后追加记录\n"
                "  # - 角色: \"角色名\"\n"
                "  #   章节: 1\n"
                "  #   状态: \"重伤\"\n"
            ),
            "情节线进度.yaml": (
                "# 情节线进度记录（每章写后追加）\n\n"
                "进度:\n"
                "  # 每章写后追加记录\n"
                "  # - 情节线: \"main_plot\"\n"
                "  #   章节: 1\n"
                "  #   时间: \"2024-01-01T00:00:00\"\n"
            ),
            "章节摘要.yaml": (
                "# 章节摘要记录（每章写后追加）\n\n"
                "摘要:\n"
                "  # 每章写后追加记录\n"
                "  # - 章节: 1\n"
                "  #   摘要: \"本章讲了什么\"\n"
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
        print("  ✓ outline/追踪/角色统计.yaml")
        print("  ✓ project_index.yaml")
        print("-" * 40)
        print(f"✅ 项目 '{self.project_name}' 创建完成！")
        print(f"📂 位置: {self.project_path.absolute()}")
        print(f"📐 结构: {self.structure_type} / {self.volume_count}卷 / {self.act_count}幕")
        return True


# ===========================================================================
# Notepad 工具（init/resume/switch 共用）
# ===========================================================================

# 当前阶段 → P 编号标签（与 .omo/plans/novel-creation.md 命名一致）
PHASE_TO_P_TAG = {
    "创意构思": "P1",
    "世界观建设": "P2",
    "角色创建": "P3",
    "总纲撰写": "P4",
    "大纲规划": "P4",           # 旧名兼容
    "情节构建": "P5",
    "分卷大纲生成": "P6",
    "卷大纲生成": "P6",         # 旧名兼容
    "分纲构建": "P7",
    "分纲撰写": "P7",
    "章节写作": "P8",
    "章节创作": "P8",
    "质量检测": "P9",
    "完稿": "完稿",
    "已完成": "完稿",
    "暂停": "暂停",
}


def _load_notepad_dir() -> Path:
    """解析 .omo/notepads/ 目录路径（脚本在 .opencode/skills/*/scripts/ 下）。"""
    script_root = Path(__file__).resolve().parent.parent.parent.parent.parent
    return script_root / ".omo" / "notepads"


def _load_template_path() -> Optional[Path]:
    tpl = _load_notepad_dir() / "templates" / "novel-context.template.md"
    return tpl if tpl.is_file() else None


def _detect_current_project(notepad_dir: Path) -> Optional[str]:
    """从 novel-context.md 解析当前项目名（__CURRENT_PROJECT__ 优先，回退到 # 标题）。"""
    context_path = notepad_dir / "novel-context.md"
    if not context_path.is_file():
        return None
    try:
        content = context_path.read_text(encoding="utf-8")
    except Exception:
        return None
    m = re.search(r"__CURRENT_PROJECT__:\s*(.+)", content)
    if m:
        name = m.group(1).strip()
        if name:
            return name
    m = re.search(r"# 项目上下文:\s*(.+)", content)
    if m:
        return m.group(1).strip()
    return None


def _run_tool(tool_name: str, project_path: str, timeout: int = 30,
              extra_args: Optional[list] = None) -> tuple:
    """运行 .opencode/shared/ 下的 Python 工具。

    Returns: (returncode, stdout, stderr)
    """
    script_root = Path(__file__).resolve().parent.parent.parent.parent.parent
    tool_path = script_root / ".opencode" / "shared" / tool_name
    if not tool_path.is_file():
        return (127, "", f"工具不存在: {tool_path}")
    cmd = [sys.executable, str(tool_path), "--project-root", project_path]
    if extra_args:
        cmd.extend(extra_args)
    try:
        result = subprocess.run(cmd, capture_output=True, timeout=timeout)
        return (
            result.returncode,
            result.stdout.decode("utf-8", errors="replace"),
            result.stderr.decode("utf-8", errors="replace"),
        )
    except subprocess.TimeoutExpired:
        return (124, "", f"工具 {tool_name} 超时（{timeout}s）")
    except Exception as e:
        return (1, "", f"工具 {tool_name} 异常: {e}")


def _persist_current_context(notepad_dir: Path, current_project: str) -> Optional[Path]:
    """把 novel-context.md 持久化到 projects/{current_project}.md。

    Returns: 写入路径；None 表示无内容可持久化。
    """
    if not current_project:
        return None
    context_path = notepad_dir / "novel-context.md"
    if not context_path.is_file():
        return None
    content = context_path.read_text(encoding="utf-8")
    projects_dir = notepad_dir / "projects"
    projects_dir.mkdir(parents=True, exist_ok=True)
    save_path = projects_dir / f"{current_project}.md"
    save_path.write_text(content, encoding="utf-8")
    return save_path


def _parse_phase_detect_output(stdout: str) -> Optional[str]:
    """从 phase_detect.py 输出中解析推导的阶段名（'推导阶段: P8 章节写作进行中'）。"""
    if not stdout:
        return None
    m = re.search(r"推导阶段[:：]\s*\S+\s+(\S+)", stdout)
    if m:
        # 取完整阶段名（到空格/换行）
        m2 = re.search(r"推导阶段[:：]\s*\S+\s+(\S+(?:\s\S+)*?)(?=\n|$)", stdout)
        if m2:
            stage = m2.group(1).strip()
            # 去掉结尾修饰词（进行中/已完结/未开始）
            for suffix in ("进行中", "已完结", "未开始", "完成"):
                if stage.endswith(suffix):
                    stage = stage[: -len(suffix)].strip()
            return stage
    return None


def _build_context_from_project(project_path: Path, project_name: str) -> str:
    """从 config.yaml + project_index.yaml + filesystem 推导完整 notepad 内容。"""
    tpl_path = _load_template_path()
    if tpl_path:
        content = tpl_path.read_text(encoding="utf-8")
    else:
        content = (
            "__CURRENT_PROJECT__: {项目名}\n\n"
            "# 项目上下文: {项目名}\n\n"
            "## 项目信息\n"
            "- 项目名称：{项目名}\n"
            "- 项目类型：\n"
            "- 项目路径：\n"
            "- 环境已初始化：True\n\n"
            "## 当前状态\n"
            "- 写作阶段：\n"
            "- 上次写作：\n\n"
            "## 创作进度\n"
            "- 创意构思：未开始\n"
            "- 大纲规划：未开始\n"
            "- 章节写作：未开始\n"
            "- 质量检测：未开始\n"
            "- 角色：0 个已创建\n"
            "- 情节线：主线未设计 / 0 条支线\n"
            "- 世界观：0/7 文件中已初始化\n\n"
            "## 待处理事项\n- ...\n"
        )

    # === 从 config.yaml 读取 ===
    config_path = project_path / "config.yaml"
    config: Dict[str, Any] = {}
    if config_path.is_file():
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f) or {}
        except Exception:
            config = {}

    project_type = config.get("项目类型", "") or ""
    current_phase = config.get("当前阶段", "创意构思") or "创意构思"
    last_edit = config.get("最后编辑", "") or ""
    active_style = config.get("活跃风格", "") or ""
    workflow = config.get("工作流", {}) or {}
    progress = config.get("创作进度", {}) or {}
    current_chapter = int(progress.get("当前章节", 0) or 0)
    total_words = int(progress.get("已完成字数", 0) or 0)
    goals = config.get("创作目标", {}) or {}
    total_chapters_target = int(goals.get("目标章节数", 0) or 0)
    structure_cfg = config.get("结构配置", {}) or {}
    volume_count = int(structure_cfg.get("卷数", 0) or 0) if isinstance(structure_cfg, dict) else 0

    # === 从 project_index.yaml 读取 ===
    index_path = project_path / "project_index.yaml"
    counts = {"characters": 0, "worldbuilding": 0, "plot_threads": 0, "chapters": 0}
    active_subplots = 0
    on_hold_subplots = 0
    main_plot_name = ""
    subplot_names: list[str] = []
    written_chapters_idx = 0
    draft_chapters_idx = 0
    if index_path.is_file():
        try:
            with open(index_path, "r", encoding="utf-8") as f:
                idx = yaml.safe_load(f) or {}
            meta = idx.get("_meta", {}) or {}
            cnt = meta.get("entity_counts", {}) or {}
            counts.update({k: int(cnt.get(k, 0) or 0) for k in counts.keys()})
            for plot_key, p in (idx.get("plot_threads", {}) or {}).items():
                if isinstance(p, dict):
                    status = p.get("status", "")
                    name = p.get("name", "")
                    # index 摘要不含 type 字段，从 key 名前缀推断
                    is_sub = str(plot_key).startswith("subplot")
                    if not is_sub and status == "active":
                        main_plot_name = name or main_plot_name
                    elif is_sub:
                        if status == "active":
                            active_subplots += 1
                            if name and len(subplot_names) < 6:
                                subplot_names.append(name)
                        elif status == "on_hold":
                            on_hold_subplots += 1
            for c in (idx.get("chapters", {}) or {}).values():
                if isinstance(c, dict):
                    st = c.get("status")
                    if st == "written":
                        written_chapters_idx += 1
                    elif st == "draft":
                        draft_chapters_idx += 1
        except Exception:
            pass

    # === 从 filesystem 补充（权威源） ===
    ideation_done = (project_path / "ideation" / "最终创意方案.yaml").is_file()
    outline_done = (project_path / "outline" / "总纲.yaml").is_file()
    volume_dir = project_path / "outline" / "分卷"
    vol_outline_count = 0
    if volume_dir.is_dir():
        vol_outline_count = sum(1 for _ in volume_dir.glob("*.yaml"))
    chapters_dir = project_path / "chapters"
    written_count_fs = 0
    if chapters_dir.is_dir():
        written_count_fs = sum(1 for _ in chapters_dir.glob("*.txt"))
    subdirs = project_path / "outline" / "分纲"
    outline_files_count = 0
    if subdirs.is_dir():
        outline_files_count = sum(1 for _ in subdirs.rglob("第*章.yaml"))
    quality_dir = project_path / "quality"
    has_quality = any(quality_dir.glob("*.yaml")) if quality_dir.is_dir() else False

    # === 状态字符串推导 ===
    p_tag = PHASE_TO_P_TAG.get(current_phase, "")

    def _ideation_status() -> str:
        return "已完成" if ideation_done else "未开始"

    def _outline_status() -> str:
        if not outline_done:
            return "未开始"
        if volume_count and total_chapters_target:
            return f"已完成（{volume_count}卷{total_chapters_target}章）"
        return "已完成"

    def _volume_status() -> str:
        """分卷大纲生成（P6）状态"""
        if not outline_done or vol_outline_count == 0:
            return "未开始"
        if volume_count and vol_outline_count >= volume_count:
            return f"已完成（{vol_outline_count}/{volume_count}卷）"
        return f"进行中（{vol_outline_count}/{volume_count}卷）"

    def _suboutline_status() -> str:
        # 优先用分纲目录计数（filesystem 权威）
        if outline_files_count == 0 and draft_chapters_idx == 0:
            return "未开始"
        actual = max(outline_files_count, draft_chapters_idx + written_chapters_idx)
        # 进度判定：actual 与 current_chapter 差 ≤ 1 即视为分纲已就绪
        if current_chapter and actual >= current_chapter:
            return f"已完成至第 {actual} 章"
        return f"进行中（{actual} 章已撰写）"

    def _chapter_status() -> str:
        actual = max(written_count_fs, written_chapters_idx)
        if actual == 0:
            return "未开始"
        if current_chapter and total_chapters_target and current_chapter >= total_chapters_target:
            return f"已完成（第 1 ~ {actual} 章，共 {total_words:,} 字）"
        return f"进行中（第 1 ~ {actual} 章，共 {total_words:,} 字）"

    def _quality_status() -> str:
        return "进行中" if has_quality else "未开始"

    def _subplot_status() -> str:
        total = active_subplots + on_hold_subplots
        if total == 0 and not main_plot_name:
            return "主线未设计 / 0 条支线"
        if total == 0:
            return f"1 主线（{main_plot_name}）/ 0 条支线"
        if main_plot_name:
            head = f"1 主线（{main_plot_name}） + {total} 条支线"
        else:
            head = f"1 主线 + {total} 条支线"
        tail_parts = []
        if active_subplots:
            tail_parts.append(f"{active_subplots} 活跃")
        if on_hold_subplots:
            tail_parts.append(f"{on_hold_subplots} 暂挂")
        if subplot_names:
            return f"{head}（{', '.join(tail_parts)}: {', '.join(subplot_names[:6])}）"
        return f"{head}（{', '.join(tail_parts)}）"

    def _worldbuilding_status() -> str:
        if counts["worldbuilding"] == 0:
            return "未初始化"
        if counts["worldbuilding"] >= 7:
            return f"{counts['worldbuilding']} 个文件已初始化（完整）"
        return f"{counts['worldbuilding']} 个文件已初始化"

    def _todo_lines() -> list[str]:
        actual = max(written_count_fs, written_chapters_idx)
        # 阶段判定优先看 current_chapter（filesystem 真实进度）
        if current_chapter == 0:
            if not ideation_done:
                return ["- 项目处于初始化阶段，可启动 P1 创意构思"]
            if not outline_done:
                return ["- 总纲未就绪，可启动 P4 总纲撰写"]
            if vol_outline_count < (volume_count or 1):
                return [
                    "- 总纲已就绪，可启动 P6 分卷大纲生成",
                    f"- 当前仅 {vol_outline_count}/{volume_count or '?'} 卷有内容",
                ]
            if outline_files_count == 0:
                return [
                    "- 分卷大纲已就绪，可启动 P7 分纲构建",
                    "- 或先创建角色和世界观（P2/P3）再开始分纲",
                ]
        # 已在 P8（章节写作阶段）或更后
        if total_chapters_target and actual >= total_chapters_target:
            return ["- 全书章节已完成，建议启动 P9 质量检测"]
        next_chapter = actual + 1 if not total_chapters_target or actual < total_chapters_target else total_chapters_target
        todos = [f"- 第 {actual} 章已写完，分纲已就绪到第 {next_chapter} 章"]
        if has_quality:
            todos.append("- 质量检测已有部分报告，可继续推进 P9 全面质量检测")
        else:
            todos.append("- 建议在阶段性完成后启动质量检测（P9）")
        return todos

    # === 模板字段替换（用 lambda 避免 re.sub replacement 解析反斜杠） ===
    def _set_field(pattern, value, src):
        return re.sub(pattern, lambda m: value, src, count=1, flags=re.MULTILINE)

    content = content.replace("{项目名}", project_name)
    content = _set_field(r"^- 项目类型：.*$", f"- 项目类型：{project_type}", content)
    content = _set_field(r"^- 项目路径：.*$", f"- 项目路径：{project_path.resolve()}", content)
    content = _set_field(r"^- 环境已初始化：.*$", "- 环境已初始化：True", content)
    # 当前状态
    phase_line = f"- 写作阶段：{current_phase}"
    if p_tag and p_tag not in ("完稿", "暂停"):
        phase_line += f"（{p_tag}）"
    content = _set_field(r"^- 写作阶段：.*$", phase_line, content)
    content = _set_field(r"^- 上次写作：.*$", f"- 上次写作：{last_edit}", content)
    # 活跃风格 + 切换时间（如模板不含则插入）
    if "- 活跃风格：" not in content and "## 当前状态" in content:
        style_line = f"- 活跃风格：{active_style if active_style else '（未设置）'}"
        switch_time_line = f"- 切换时间：{datetime.now().strftime('%Y-%m-%d')}"
        content = re.sub(
            r"(^- 上次写作：.*$)",
            lambda m: f"{m.group(1)}\n{style_line}\n{switch_time_line}",
            content,
            count=1,
            flags=re.MULTILINE,
        )
    # 创作进度
    content = _set_field(r"^- 创意构思：.*$", f"- 创意构思：{_ideation_status()}", content)
    content = _set_field(r"^- 大纲规划：.*$", f"- 大纲规划：{_outline_status()}", content)
    # 分卷大纲生成（插入在大纲规划和分纲构建之间）
    if re.search(r"^- 分卷大纲生成：", content, flags=re.MULTILINE):
        content = _set_field(r"^- 分卷大纲生成：.*$", f"- 分卷大纲生成：{_volume_status()}", content)
    else:
        content = re.sub(
            r"(^- 大纲规划：.*$)",
            lambda m: f"{m.group(1)}\n- 分卷大纲生成：{_volume_status()}",
            content,
            count=1,
            flags=re.MULTILINE,
        )
    # 分纲构建（模板可能没有此行——如有则替换；如无则插入到"分卷大纲生成"后）
    if re.search(r"^- 分纲构建：", content, flags=re.MULTILINE):
        content = _set_field(r"^- 分纲构建：.*$", f"- 分纲构建：{_suboutline_status()}", content)
    else:
        content = re.sub(
            r"(^- 分卷大纲生成：.*$)",
            lambda m: f"{m.group(1)}\n- 分纲构建：{_suboutline_status()}",
            content,
            count=1,
            flags=re.MULTILINE,
        )
    content = _set_field(r"^- 章节写作：.*$", f"- 章节写作：{_chapter_status()}", content)
    content = _set_field(r"^- 质量检测：.*$", f"- 质量检测：{_quality_status()}", content)
    content = _set_field(r"^- 角色：.*$", f"- 角色：{counts['characters']} 个已创建", content)
    content = _set_field(r"^- 情节线：.*$", f"- 情节线：{_subplot_status()}", content)
    content = _set_field(r"^- 世界观：.*$", f"- 世界观：{_worldbuilding_status()}", content)
    # 待处理事项
    todo_block = "\n".join(_todo_lines())
    content = re.sub(
        r"(## 待处理事项\n)- .*$",
        lambda m: f"{m.group(1)}{todo_block}",
        content,
        count=1,
        flags=re.MULTILINE,
    )
    # 追加 __CURRENT_PROJECT__ 标记（如模板未含）
    if "__CURRENT_PROJECT__" not in content:
        content = f"__CURRENT_PROJECT__: {project_name}\n\n" + content
    return content


def _write_notepad(notepad_dir: Path, project_path: Path, project_name: str) -> Path:
    """写入完整的 notepad 上下文（从项目状态推导）。"""
    content = _build_context_from_project(project_path, project_name)
    context_path = notepad_dir / "novel-context.md"
    context_path.write_text(content, encoding="utf-8")
    return context_path


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

        # 3. 基于文件内容的智能分类、路由与格式转换
        # 调用 classify_import.py 替代旧版硬编码文件名/关键词规则
        classify_script = (
            Path(__file__).resolve().parent.parent.parent.parent
            / "shared" / "classify_import.py"
        )
        classify_ok = False
        try:
            result = subprocess.run(
                [sys.executable, str(classify_script),
                 "--staging-dir", str(staging_dir.resolve()),
                 "--project-root", str(self.project_path.resolve()),
                 "--volumes", str(self.volume_count),
                 "--source-path", str(self.source_path.resolve())],
                capture_output=True, text=True, timeout=120,
            )
            if result.returncode == 0:
                classify_ok = True
                # 读取 classify_import 生成的 migration_report
                report_path = self.project_path / "migration_report.yaml"
                if report_path.exists():
                    with open(report_path, 'r', encoding='utf-8') as f:
                        report = yaml.safe_load(f) or {}
                # 打印 classify_import 的输出
                for line in result.stdout.strip().splitlines():
                    print(line)
            else:
                print(f"  ⚠️  classify_import 失败（rc={result.returncode}），回退旧版路由")
                print(f"     stderr: {result.stderr.strip()[:300]}")
        except subprocess.TimeoutExpired:
            print("  ⚠️  classify_import 超时，回退旧版路由")
        except FileNotFoundError:
            print("  ⚠️  classify_import.py 未找到，回退旧版路由")
        except Exception as e:
            print(f"  ⚠️  classify_import 异常: {e}，回退旧版路由")

        # 旧版路由：作为 classify_import 的降级兜底
        if not classify_ok:
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

                # 通用分类（旧版：仅基于文件名）
                guess = self._guess_file_type_by_name(item)

                if guess == 'likely_character' and suffix in (".yaml", ".yml"):
                    dest = self.project_path / "characters" / item.name
                    shutil.move(str(item), str(dest))
                    auto_moved += 1
                    continue
                elif guess == 'likely_worldbuilding' and suffix in (".yaml", ".yml"):
                    upgraded = self._upgrade_worldbuilding_to_threelayer(item)
                    if upgraded:
                        dest = self.project_path / "worldbuilding" / item.name
                        dest.write_text(upgraded, encoding='utf-8')
                        item.unlink()
                        worldbuilding_upgraded += 1
                        auto_moved += 1
                    else:
                        dest = self.project_path / "worldbuilding" / item.name
                        shutil.move(str(item), str(dest))
                        auto_moved += 1
                    continue

            # 旧版 migration_report 生成
            report = self._generate_migration_report()
            report_path = self.project_path / "migration_report.yaml"
            with open(report_path, 'w', encoding='utf-8') as f:
                yaml.safe_dump(report, f, allow_unicode=True, default_flow_style=False)
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

        # 3b. 后处理：YAML 缩进修复 + 一致性校验 + 索引重建
        if classify_ok:
            print("\n🔧 后处理中...")
            shared_dir = Path(__file__).resolve().parent.parent.parent.parent / "shared"
            pp_dirs = ["characters", "worldbuilding", "outline/分纲"]
            for pp_dir in pp_dirs:
                target = self.project_path / pp_dir
                if target.is_dir():
                    fix_result = subprocess.run(
                        [sys.executable, str(shared_dir / "fix_yaml_indent.py"),
                         "--dir", str(target), "--recursive"],
                        capture_output=True, text=True, timeout=60,
                    )
                    if fix_result.returncode == 0 and fix_result.stdout.strip():
                        for line in fix_result.stdout.strip().splitlines():
                            print(f"     {line}")
            # 一致性校验
            validate_result = subprocess.run(
                [sys.executable, str(shared_dir / "validate_entity_consistency.py"),
                 "--project-root", str(self.project_path.resolve())],
                capture_output=True, text=True, timeout=60,
            )
            if validate_result.returncode == 0 and validate_result.stdout.strip():
                for line in validate_result.stdout.strip().splitlines():
                    print(f"     {line}")
            # 索引重建
            rebuild_result = subprocess.run(
                [sys.executable, str(shared_dir / "rebuild_project_index.py"),
                 "--project-root", str(self.project_path.resolve())],
                capture_output=True, text=True, timeout=60,
            )
            if rebuild_result.returncode == 0:
                for line in rebuild_result.stdout.strip().splitlines():
                    print(f"     {line}")

        # 4. 生成 config.yaml（如果不存在）
        config_path = self.project_path / "config.yaml"
        if not config_path.exists():
            now_cfg = datetime.now().strftime("%Y-%m-%d")
            config_content = f"""项目名称: "{self.project_name}"
项目类型: "未知"
状态: "进行中"
当前阶段: "创意构思"
创建时间: "{now_cfg}"
最后编辑: "{now_cfg}"

创作进度:
  当前章节: 0
  已完成字数: 0

工作流:
  AI自主度: true
  检查频率: "weekly"

质量检查:
  章节最少字数: 1500
  章节最多字数: 6000
"""
            config_path.write_text(config_content, encoding='utf-8')

        # 5. 生成 project_index.yaml 骨架
        index_path = self.project_path / "project_index.yaml"
        if not index_path.exists():
            now_ix = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
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

        # 6. 清理暂存区
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

    def show_status(self, phase: Optional[str] = None):
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

        # 显示状态
        print(f"📊 项目状态: {self.project_name}")
        print("-" * 40)
        print(f"状态: {config.get('状态', '未知')}")
        print(f"当前阶段: {config.get('当前阶段', '未知')}")
        print(f"作者: {config.get('作者', '')}")

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

        # === 切换 notepad：复用共享 helper（与 switch 一致的逻辑） ===
        notepad_dir = _load_notepad_dir()
        old_project = _detect_current_project(notepad_dir)
        if old_project and old_project != self.project_name:
            old_path = self.target_dir / old_project
            if old_path.is_dir():
                print(f"🔄 同步旧项目状态: {old_project}")
                _run_tool("rebuild_project_index.py", str(old_path.resolve()))
            saved = _persist_current_context(notepad_dir, old_project)
            if saved:
                print(f"💾 旧项目快照已保存: {saved.relative_to(notepad_dir.parent)}")
        # 同步目标项目索引
        print(f"🔄 同步目标项目状态: {self.project_name}")
        _run_tool("rebuild_project_index.py", str(self.project_path.resolve()))
        # 写入完整 notepad（从 config + index 推导）
        _write_notepad(notepad_dir, self.project_path, self.project_name)
        print("✅ 项目已准备好继续创作")
        return True


# ===========================================================================
# 切换项目（原子化）
# ===========================================================================

class ProjectSwitcher:
    """原子化的项目切换。替代 novel-writer.md §1 中手动 read/write 的切换协议。

    流程：发现旧项目 → 同步旧索引 → 持久化旧 notepad → 验证目标项目
        → 同步目标索引 → 推导并写入新 notepad → phase_detect 验证一致性
        → 输出摘要。

    Args:
        project_name: 目标项目名
        target_dir: novels 根目录（默认自动发现）
        skip_sync: 跳过 rebuild_project_index 同步
        no_verify: 跳过 phase_detect 一致性验证
        dry_run: 仅打印计划，不修改任何文件
    """

    def __init__(self, project_name: str, target_dir: str = None,
                 skip_sync: bool = False, no_verify: bool = False,
                 dry_run: bool = False):
        self.project_name = project_name
        if target_dir is None:
            target_dir = str(find_novels_root())
        self.target_dir = Path(target_dir)
        self.project_path = self.target_dir / project_name
        self.skip_sync = skip_sync
        self.no_verify = no_verify
        self.dry_run = dry_run

    def switch(self) -> bool:
        # ── Step 0: 验证目标项目 ──
        if not self.project_path.is_dir():
            print(f"❌ 目标项目 '{self.project_name}' 不存在：{self.project_path}")
            print(f"   可用项目: {self._list_available()}")
            return False
        config_path = self.project_path / "config.yaml"
        if not config_path.is_file():
            print(f"❌ 目标项目缺少 config.yaml: {config_path}")
            return False

        notepad_dir = _load_notepad_dir()
        old_project = _detect_current_project(notepad_dir)
        same_project = (old_project == self.project_name)

        print(f"🔀 切换项目: {(old_project or '（无）')} → {self.project_name}")
        print("-" * 40)

        warnings: list[str] = []

        # ── Step 1: 同步 + 持久化旧项目（仅切换不同项目时） ──
        if old_project and not same_project:
            old_path = self.target_dir / old_project
            if old_path.is_dir():
                if not self.skip_sync and not self.dry_run:
                    print(f"🔄 同步旧项目索引: {old_project}")
                    rc, out, err = _run_tool(
                        "rebuild_project_index.py", str(old_path.resolve())
                    )
                    if rc != 0:
                        warnings.append(
                            f"旧项目同步失败（rc={rc}）: {err.strip()[:200]}"
                        )
                if not self.dry_run:
                    saved = _persist_current_context(notepad_dir, old_project)
                    if saved:
                        print(
                            f"💾 旧项目快照已保存: {saved.relative_to(notepad_dir.parent)}"
                        )

        # ── Step 2: 同步目标项目索引 ──
        if not self.skip_sync and not self.dry_run:
            print(f"🔄 同步目标项目索引: {self.project_name}")
            rc, out, err = _run_tool(
                "rebuild_project_index.py", str(self.project_path.resolve())
            )
            if rc != 0:
                warnings.append(
                    f"目标项目同步失败（rc={rc}）: {err.strip()[:200]}"
                )
            else:
                for line in out.strip().splitlines()[:3]:
                    if line.strip():
                        print(f"   {line.strip()}")

        # ── Step 3: 写入新 notepad ──
        if not self.dry_run:
            written = _write_notepad(notepad_dir, self.project_path, self.project_name)
            print(f"📝 新 notepad 已写入: {written.name}")
        else:
            print("🧪 DRY RUN: 跳过 notepad 写入")

        # ── Step 4: phase_detect 验证（可选） ──
        if not self.no_verify and not self.dry_run:
            print(f"🔍 验证状态一致性: {self.project_name}")
            rc, out, err = _run_tool(
                "phase_detect.py", str(self.project_path.resolve())
            )
            if rc != 0:
                warnings.append(
                    f"phase_detect 失败（rc={rc}）: {err.strip()[:200]}"
                )
            else:
                detected = _parse_phase_detect_output(out)
                if detected:
                    with open(config_path, "r", encoding="utf-8") as f:
                        cfg = yaml.safe_load(f) or {}
                    cfg_phase = cfg.get("当前阶段", "")
                    if cfg_phase and detected != cfg_phase:
                        warnings.append(
                            f"config.当前阶段='{cfg_phase}' 与文件证据推导='{detected}' 不一致"
                        )
                    elif cfg_phase:
                        print(f"   ✓ 阶段一致: {cfg_phase}")
                    first_line = out.strip().splitlines()[0] if out.strip() else ""
                    if first_line:
                        print(f"   {first_line.strip()}")
                else:
                    first_line = out.strip().splitlines()[0] if out.strip() else ""
                    if first_line:
                        print(f"   {first_line.strip()}")

        # ── Step 5: 摘要 ──
        print("-" * 40)
        if self.dry_run:
            print(f"🧪 DRY RUN 完成（未修改任何文件）")
            print(f"   旧项目: {old_project or '（无）'}")
            print(f"   目标: {self.project_name} ({self.project_path})")
        elif same_project:
            print(f"✅ 项目 '{self.project_name}' 已是当前活跃项目（已重新同步）")
        else:
            print(f"✅ 已切换到项目: {self.project_name}")
        print(f"📂 位置: {self.project_path}")
        if warnings:
            print("⚠️  警告:")
            for w in warnings:
                print(f"   - {w}")
        return True

    def _list_available(self) -> str:
        if not self.target_dir.is_dir():
            return "（无法列出）"
        names = sorted(
            p.name for p in self.target_dir.iterdir()
            if p.is_dir() and (p / "config.yaml").is_file()
        )
        return ", ".join(names) if names else "（空）"


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

  # 续写项目
  python init.py resume "我的小说"

  # 切换项目（原子化：同步旧→持久化旧→同步新→推导新→验证）
  python init.py switch "我的小说"
  python init.py switch "我的小说" --dry-run
  python init.py switch "我的小说" --skip-sync --no-verify

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

    # resume
    p_resume = subparsers.add_parser("resume", help="续写项目")
    p_resume.add_argument("name", help="项目名称")
    p_resume.add_argument("--root", "-r", default=None, help="目标目录（默认自动发现 NOVELS_ROOT）")

    # switch
    p_switch = subparsers.add_parser("switch", help="切换项目（原子化：同步旧→持久化→同步新→推导→验证）")
    p_switch.add_argument("name", help="目标项目名")
    p_switch.add_argument("--root", "-r", default=None, help="目标目录（默认自动发现 NOVELS_ROOT）")
    p_switch.add_argument("--skip-sync", action="store_true",
                          help="跳过 rebuild_project_index 同步（旧/新项目都不同步）")
    p_switch.add_argument("--no-verify", action="store_true",
                          help="跳过 phase_detect 状态一致性验证")
    p_switch.add_argument("--dry-run", action="store_true",
                          help="仅打印计划，不修改任何文件")

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
        success = status.show_status(args.phase)
        sys.exit(0 if success else 1)

    elif args.command == "resume":
        resume = ProjectResume(args.name, args.root)
        success = resume.resume_project()
        sys.exit(0 if success else 1)

    elif args.command == "switch":
        switcher = ProjectSwitcher(
            args.name, args.root,
            skip_sync=args.skip_sync,
            no_verify=args.no_verify,
            dry_run=args.dry_run,
        )
        success = switcher.switch()
        sys.exit(0 if success else 1)

    elif args.command == "delete":
        deleter = ProjectDeleter(args.name, args.root, args.force)
        success = deleter.delete_project()
        sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()

