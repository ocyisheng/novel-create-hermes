#!/usr/bin/env python3
"""
phase_detect.py — 从文件证据推导当前创作阶段，输出多维审计报告

Usage:
    python phase_detect.py --project-root <PATH>

Output:
    推导阶段: P8 章节写作进行中         ← 单标签（兼容旧解析器）
    依据: chapters/ 下有 15 个 .txt 文件

    === 工作项审计 ===
    创意构思    ✅ 已完成              ideation/最终创意方案.yaml
    世界观      ✅ 已完成（14个）      worldbuilding/
    角色        ✅ 已完成（30个）      characters/
    总纲        ✅ 已完成              outline/总纲.yaml
    分卷大纲    ✅ 已完成（8卷）       outline/分卷/
    情节线      ⚠️ 部分完成（1条）     outline/情节线/
    分纲        ⚠️ 部分完成（20/60）   outline/分纲/
    章节写作    🔄 进行中（15/110）    chapters/
    质量检测    ❌ 未开始              quality/
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


def _load_config(config_path: Path) -> dict:
    """读取 config.yaml，失败返回空 dict。"""
    import yaml
    try:
        if config_path.is_file():
            data = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
            return data if isinstance(data, dict) else {}
    except Exception:
        pass
    return {}


def detect_phase(project_root: Path) -> tuple[str, str]:
    """推导当前阶段。返回 (phase_label, evidence)。保持原有签名兼容。"""
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

    config_data = _load_config(config)
    target = config_data.get("创作目标", {}).get("目标章节数", 0) or 0

    chapter_count = count_files(chapters_dir, "*.txt")
    if target > 0 and chapter_count >= target:
        return ("P9 可深度检查", f"chapters/ 文件数({chapter_count}) >= 目标({target})")
    if chapter_count > 0:
        return ("P8 章节写作进行中", f"chapters/ 下有 {chapter_count} 个 .txt 文件")
    if fengang_dir.is_dir() and list(fengang_dir.rglob("*.yaml")):
        return ("P7 分纲已就绪", "outline/分纲/ 下有文件")
    if volume_dir.is_dir() and list(volume_dir.glob("*.yaml")):
        return ("P6 分卷大纲已生成", "outline/分卷/ 下有文件")
    if plot_dir.is_dir() and list(plot_dir.glob("*.yaml")):
        return ("P5 情节线已设计", "outline/情节线/ 下有文件")
    if content_exists(zonggang):
        narrative_strategy = outline_dir / "叙事策略.yaml"
        if not content_exists(narrative_strategy):
            return ("P4.5 叙事策略设计", "outline/总纲.yaml 有内容但叙事策略未生成")
        return ("P4 大纲已规划", "outline/总纲.yaml 有内容")
    if count_files(characters_dir) > 0:
        return ("P3 角色已创建", f"characters/ 下有 {count_files(characters_dir)} 个文件")
    if worldbuilding_dir.is_dir() and list(worldbuilding_dir.glob("*.yaml")):
        return ("P2 世界观已建设", "worldbuilding/ 基础文件存在")
    if ideation_dir.is_dir() and list(ideation_dir.glob("*.yaml")):
        final = ideation_dir / "最终创意方案.yaml"
        if content_exists(final):
            return ("P1 创意构思完成", "ideation/最终创意方案.yaml 已生成")
        return ("P1 创意构思中", "ideation/ 有内容但无最终方案")
    if config.is_file():
        return ("P0 新建项目", "config.yaml 存在但无创作产出")
    return ("未初始化", "未找到 config.yaml")


def audit_workstreams(project_root: Path) -> list[dict]:
    """逐项审计各创作维度的完成状态，返回结构化记录列表。"""
    # fmt: (name, detect_fn) → (status, detail, evidence)
    config_path = project_root / "config.yaml"
    config_data = _load_config(config_path)
    target = config_data.get("创作目标", {}).get("目标章节数", 0) or 0

    chapters_dir = project_root / "chapters"
    ideation_dir = project_root / "ideation"
    characters_dir = project_root / "characters"
    worldbuilding_dir = project_root / "worldbuilding"
    outline_dir = project_root / "outline"
    zonggang = outline_dir / "总纲.yaml"
    fengang_dir = outline_dir / "分纲"
    volume_dir = outline_dir / "分卷"
    plot_dir = outline_dir / "情节线"
    quality_dir = project_root / "quality"

    items = []

    # ── 1. 创意构思 ──
    has_final = content_exists(ideation_dir / "最终创意方案.yaml") if ideation_dir.is_dir() else False
    has_any = bool(ideation_dir.is_dir() and list(ideation_dir.glob("*.yaml")))
    if has_final:
        items.append(dict(name="创意构思", status="✅ 已完成", detail="", evidence="ideation/最终创意方案.yaml"))
    elif has_any:
        items.append(dict(name="创意构思", status="🔄 进行中", detail="有草稿无最终方案", evidence="ideation/ 有内容"))
    else:
        items.append(dict(name="创意构思", status="❌ 未开始", detail="", evidence="ideation/ 空"))

    # ── 2. 世界观 ──
    wb_cnt = count_files(worldbuilding_dir)
    if wb_cnt >= 10:
        items.append(dict(name="世界观", status="✅ 已完成", detail=f"{wb_cnt}个文件", evidence=f"worldbuilding/ {wb_cnt} 文件"))
    elif wb_cnt > 0:
        items.append(dict(name="世界观", status="⚠️ 部分完成", detail=f"{wb_cnt}个文件", evidence=f"worldbuilding/ {wb_cnt} 文件"))
    else:
        items.append(dict(name="世界观", status="❌ 未开始", detail="", evidence="worldbuilding/ 空"))

    # ── 3. 角色 ──
    ch_cnt = count_files(characters_dir)
    if ch_cnt >= 10:
        items.append(dict(name="角色", status="✅ 已完成", detail=f"{ch_cnt}个", evidence=f"characters/ {ch_cnt} 文件"))
    elif ch_cnt > 0:
        items.append(dict(name="角色", status="⚠️ 部分完成", detail=f"{ch_cnt}个", evidence=f"characters/ {ch_cnt} 文件"))
    else:
        items.append(dict(name="角色", status="❌ 未开始", detail="", evidence="characters/ 空"))

    # ── 4. 总纲 ──
    if content_exists(zonggang):
        has_strategy = content_exists(outline_dir / "叙事策略.yaml")
        detail = "含叙事策略" if has_strategy else "待补充叙事策略"
        items.append(dict(name="总纲", status="✅ 已完成", detail=detail, evidence="outline/总纲.yaml"))
    else:
        items.append(dict(name="总纲", status="❌ 未开始", detail="", evidence="outline/总纲.yaml 不存在"))

    # ── 5. 分卷大纲 ──
    vol_cnt = count_files(volume_dir)
    if vol_cnt > 0:
        items.append(dict(name="分卷大纲", status="✅ 已完成" if vol_cnt >= 8 else "⚠️ 部分完成",
                          detail=f"{vol_cnt}卷", evidence=f"outline/分卷/ {vol_cnt} 文件"))
    else:
        items.append(dict(name="分卷大纲", status="❌ 未开始", detail="", evidence="outline/分卷/ 空"))

    # ── 6. 情节线 ──
    plot_cnt = count_files(plot_dir)
    if plot_cnt > 0:
        items.append(dict(name="情节线", status="✅ 已完成" if plot_cnt >= 3 else "⚠️ 部分完成",
                          detail=f"{plot_cnt}条", evidence=f"outline/情节线/ {plot_cnt} 文件"))
    else:
        items.append(dict(name="情节线", status="❌ 未开始", detail="", evidence="outline/情节线/ 空"))

    # ── 7. 分纲 ──
    fg_cnt = 0
    if fengang_dir.is_dir():
        fg_cnt = len(list(fengang_dir.rglob("第*章.yaml")))
    if fg_cnt > 0:
        tgt = f"/{target}" if target else ""
        done = bool(target and fg_cnt >= target)
        items.append(dict(name="分纲", status="✅ 已完成" if done else "⚠️ 部分完成",
                          detail=f"{fg_cnt}章{tgt}", evidence=f"outline/分纲/ {fg_cnt} 文件"))
    else:
        items.append(dict(name="分纲", status="❌ 未开始", detail="", evidence="outline/分纲/ 空"))

    # ── 8. 章节写作 ──
    chapter_files = sorted(chapters_dir.glob("*.txt")) if chapters_dir.is_dir() else []
    chw_cnt = len(chapter_files)
    if chw_cnt > 0:
        tgt = f"/{target}" if target else ""
        total_words = sum(f.stat().st_size for f in chapter_files)
        done = bool(target and chw_cnt >= target)
        items.append(dict(name="章节写作", status="✅ 已完成" if done else "🔄 进行中",
                          detail=f"{chw_cnt}章{tgt}，约{total_words}字", evidence=f"chapters/ {chw_cnt} txt"))
    else:
        items.append(dict(name="章节写作", status="❌ 未开始", detail="", evidence="chapters/ 空"))

    # ── 9. 质量检测 ──
    has_q = quality_dir.is_dir() and any(quality_dir.glob("*.yaml"))
    items.append(dict(name="质量检测", status="✅ 有报告" if has_q else "❌ 未开始",
                      detail="", evidence=f"quality/ {'有内容' if has_q else '空'}"))

    return items


def format_audit_report(items: list[dict]) -> str:
    """将审计记录格式化为等宽表格字符串。"""
    lines = ["", "=== 工作项审计 ==="]
    # 计算对齐宽度
    name_w = max(len(item["name"]) for item in items) + 1
    status_w = 20
    for item in items:
        status = item["status"]
        if item["detail"]:
            status += f"（{item['detail']}）"
        lines.append(
            f"  {item['name'].ljust(name_w)} {status.ljust(status_w)} {item['evidence']}"
        )
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="从文件证据推导当前创作阶段，输出多维审计报告")
    parser.add_argument("--project-root", required=True, help="项目根目录")
    parser.add_argument("--audit-only", action="store_true",
                        help="只输出工作项审计，跳过阶段推导摘要")
    args = parser.parse_args()

    project_root = Path(args.project_root).resolve()
    if not project_root.is_dir():
        print(f"Error: Project root not found: {project_root}", file=sys.stderr)
        sys.exit(1)

    if not args.audit_only:
        phase, evidence = detect_phase(project_root)
        print(f"推导阶段: {phase}")
        print(f"依据: {evidence}")

    items = audit_workstreams(project_root)
    print(format_audit_report(items))


if __name__ == "__main__":
    main()
