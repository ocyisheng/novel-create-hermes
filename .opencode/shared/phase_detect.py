#!/usr/bin/env python3
"""
phase_detect.py — 从文件证据推导当前创作阶段

Usage:
    python phase_detect.py --project-root <PATH>

Example:
    python phase_detect.py --project-root NOVELS_ROOT/穿越三国成刘谌
    # 输出:
    #   推导阶段: P8 章节写作进行中
    #   依据: chapters/ 下有 .txt 文件

优先级从高到低（后建设的阶段覆盖前阶段）：
    P9 可深度检查           chapters/ 文件数 >= 目标章节数
    P8 章节写作进行中        chapters/ 下有 .txt 文件
    P7 分纲已就绪            outline/分纲/ 下有文件
    P6 角色已创建            characters/ 下有角色 .yaml
    P5 世界观已建设          worldbuilding/ 基础文件存在
    P4 情节线已设计          outline/情节线/ 下有文件
    P3 分卷大纲已生成        outline/分卷/ 下有文件
    P2 大纲已规划            outline/总纲.yaml 有内容
    P1 创意构思中            ideation/ 有内容但无最终方案
    P0 新建项目              config.yaml 存在但无产出
"""

import argparse
import sys
from pathlib import Path


def count_files(directory: Path, pattern: str = "*.yaml") -> int:
    if not directory.is_dir():
        return 0
    return len(list(directory.glob(pattern)))


def content_exists(filepath: Path) -> bool:
    return filepath.is_file() and filepath.stat().st_size > 0


def detect_phase(project_root: Path) -> tuple[str, str]:
    """推导当前阶段。返回 (phase_label, evidence)。"""
    config = project_root / "config.yaml"
    chapters_dir = project_root / "chapters"
    ideation_dir = project_root / "ideation"
    characters_dir = project_root / "characters"
    worldbuilding_dir = project_root / "worldbuilding"
    outline_dir = project_root / "outline"
    zonggang = outline_dir / "总纲.yaml"
    fengang_dir = outline_dir / "分纲"
    volume_dir = outline_dir / "分卷"
    plot_dir = outline_dir / "情节线"

    # Read target chapter count from config
    target = 0
    if config.is_file():
        import yaml
        try:
            data = yaml.safe_load(config.read_text(encoding="utf-8")) or {}
            target = data.get("创作目标", {}).get("目标章节数", 0)
        except Exception:
            target = 0

    # Priority: most advanced phase wins (check from P9 down to P0)
    chapter_count = count_files(chapters_dir, "*.txt")
    if target > 0 and chapter_count >= target:
        return ("P9 可深度检查", f"chapters/ 文件数({chapter_count}) >= 目标({target})")
    if chapter_count > 0:
        return ("P8 章节写作进行中", f"chapters/ 下有 {chapter_count} 个 .txt 文件")

    if fengang_dir.is_dir() and list(fengang_dir.rglob("*.yaml")):
        return ("P7 分纲已就绪", "outline/分纲/ 下有文件")

    if count_files(characters_dir) > 1:  # >1 to skip 角色统计.yaml
        return ("P6 角色已创建", f"characters/ 下有 {count_files(characters_dir)} 个文件")

    if worldbuilding_dir.is_dir() and list(worldbuilding_dir.glob("*.yaml")):
        return ("P5 世界观已建设", "worldbuilding/ 基础文件存在")

    if plot_dir.is_dir() and list(plot_dir.glob("*.yaml")):
        return ("P4 情节线已设计", "outline/情节线/ 下有文件")

    if volume_dir.is_dir() and list(volume_dir.glob("*.yaml")):
        return ("P3 分卷大纲已生成", "outline/分卷/ 下有文件")

    if content_exists(zonggang):
        return ("P2 大纲已规划", "outline/总纲.yaml 有内容")

    if ideation_dir.is_dir() and list(ideation_dir.glob("*.yaml")):
        final = ideation_dir / "最终创意方案.yaml"
        if content_exists(final):
            return ("P1 创意构思完成", "ideation/最终创意方案.yaml 已生成")
        return ("P1 创意构思中", "ideation/ 有内容但无最终方案")

    if config.is_file():
        return ("P0 新建项目", "config.yaml 存在但无创作产出")

    return ("未初始化", "未找到 config.yaml")


def main():
    parser = argparse.ArgumentParser(description="从文件证据推导当前创作阶段")
    parser.add_argument("--project-root", required=True, help="项目根目录")
    args = parser.parse_args()

    project_root = Path(args.project_root).resolve()
    if not project_root.is_dir():
        print(f"Error: Project root not found: {project_root}", file=sys.stderr)
        sys.exit(1)

    phase, evidence = detect_phase(project_root)
    print(f"推导阶段: {phase}")
    print(f"依据: {evidence}")


if __name__ == "__main__":
    main()
