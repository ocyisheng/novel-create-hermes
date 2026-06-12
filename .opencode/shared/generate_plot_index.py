#!/usr/bin/env python3
"""
generate_plot_index.py — 从情节线文件自动生成主索引

读取 outline/情节线/*.yaml，生成或刷新 outline/情节线/主索引.yaml。
自动生成：目录、线速览、多线交织总图（交汇检测）。
保留人工编辑：节奏总览、交汇注释不会被覆盖。

用法:
    # 首次生成
    python generate_plot_index.py --project-root NOVELS_ROOT/空山闻仙

    # 刷新（只更新自动字段，保留人工编辑）
    python generate_plot_index.py --project-root NOVELS_ROOT/空山闻仙 --refresh

    # 仅检测交汇点（不写文件，调试用）
    python generate_plot_index.py --project-root NOVELS_ROOT/空山闻仙 --detect-only --window 3
"""

import argparse
import sys
from datetime import datetime
from pathlib import Path

# _utils.py 位于同目录
sys.path.insert(0, str(Path(__file__).parent))
from _utils import load_yaml, save_yaml


# ═══════════════════════════════════════════════════════════════
# 数据提取
# ═══════════════════════════════════════════════════════════════

def _get_nested(data: dict, path: str, default=None):
    """按点号路径读取嵌套字段。"""
    keys = path.split(".")
    for k in keys:
        if isinstance(data, dict):
            data = data.get(k)
        else:
            return default
        if data is None:
            return default
    return data


def _extract_catalog(plot_dir: Path) -> dict:
    """生成目录表。"""
    catalog = {"主线": "主线.yaml", "支线": []}
    subplot_files = sorted(
        [f for f in plot_dir.glob("支线*.yaml") if f.name != "主索引.yaml"]
    )
    for f in subplot_files:
        data = load_yaml(f)
        if data:
            eid = _get_nested(data, "索引信息.实体ID", "")
            catalog["支线"].append({"文件": f.name, "实体ID": eid})
    return catalog


def _extract_speed_view(plot_dir: Path, total_chapters: int) -> dict:
    """生成线速览表。"""
    speed_view = {}

    for f in sorted(plot_dir.glob("*.yaml")):
        if f.name == "主索引.yaml":
            continue

        data = load_yaml(f)
        if not data:
            continue

        name = _get_nested(data, "索引信息.名称", f.stem)
        ptype = _get_nested(data, "完整档案.类型", "")
        start_ch = _get_nested(data, "索引信息.起始章节", 0)
        conflict = _get_nested(data, "完整档案.冲突核心", "")
        chars = _get_nested(data, "完整档案.角色参与.涉及角色", [])
        if not isinstance(chars, list):
            chars = []

        # 计算覆盖范围
        if start_ch and total_chapters:
            coverage = f"第{start_ch}-{total_chapters}章"
        elif start_ch:
            coverage = f"第{start_ch}章起"
        else:
            coverage = "全篇"

        speed_view[name] = {
            "类型": ptype,
            "覆盖": coverage,
            "核心冲突": conflict,
            "角色": chars,
        }

    return speed_view


def _detect_interweaving(plot_dir: Path, window: int = 2) -> list[dict]:
    """检测多条情节线的交汇章节。

    Args:
        plot_dir: 情节线目录
        window: 聚合窗口大小（章节 ±N 范围内视为同一交汇区间）

    Returns:
        交汇点列表，按章节号排序
    """
    # Step 1: 收集所有关键事件的 (章节号, 情节线名, 事件描述)
    events = []
    for f in sorted(plot_dir.glob("*.yaml")):
        if f.name == "主索引.yaml":
            continue
        data = load_yaml(f)
        if not data:
            continue
        name = _get_nested(data, "索引信息.名称", f.stem)
        key_events = _get_nested(data, "完整档案.关键事件", [])
        if not isinstance(key_events, list):
            continue
        for evt in key_events:
            if not isinstance(evt, dict):
                continue
            ch = evt.get("章节", 0)
            if ch and ch > 0:
                events.append((ch, name, evt.get("事件", "")))

    if not events:
        return []

    # Step 2: 按章节号排序后窗口聚合
    events.sort(key=lambda x: x[0])
    clusters = []
    current_cluster = []
    current_max = 0

    for ch, name, desc in events:
        if not current_cluster or ch <= current_max + window:
            current_cluster.append((ch, name, desc))
            current_max = max(current_max, ch)
        else:
            clusters.append(current_cluster)
            current_cluster = [(ch, name, desc)]
            current_max = ch
    if current_cluster:
        clusters.append(current_cluster)

    # Step 3: 筛选涉及 ≥2 条线的交汇点
    interweaving = []
    for cluster in clusters:
        unique_threads = {}
        for ch, name, desc in cluster:
            if name not in unique_threads:
                unique_threads[name] = []
            unique_threads[name].append({"事件": desc, "章节": ch})

        if len(unique_threads) < 2:
            continue

        chapters = [ch for ch, _, _ in cluster]
        evidence = []
        for tname, evts in unique_threads.items():
            for evt in evts:
                evidence.append({
                    "情节线": tname,
                    "事件": evt["事件"],
                    "章节": evt["章节"],
                })

        interweaving.append({
            "章节范围": f"第{min(chapters)}-{max(chapters)}章" if min(chapters) != max(chapters) else f"第{min(chapters)}章",
            "涉及线": sorted(unique_threads.keys()),
            "涉及线数量": len(unique_threads),
            "自动检测依据": evidence,
            "内容": "",
            "优先级": "high" if len(unique_threads) >= 3 else "medium",
            "状态": "待发生",
        })

    # 按章节号排序
    interweaving.sort(key=lambda x: int(x["章节范围"].replace("第", "").split("-")[0].replace("章", "")))

    return interweaving


# ═══════════════════════════════════════════════════════════════
# 写入策略
# ═══════════════════════════════════════════════════════════════

def _smart_merge(old_index: dict, catalog: dict, speed_view: dict,
                 interweaving: list[dict], now: str, is_refresh: bool) -> dict:
    """智能合并：自动字段覆盖，人工字段保留。"""
    if old_index:
        result = old_index
    else:
        result = {
            "_meta": {
                "entity_type": "plot_index",
                "schema_version": "1.0",
                "project_total_chapters": 0,
            },
            "目录": {},
            "线速览": {},
            "多线交织总图": [],
            "节奏总览": {},
        }

    # 更新 _meta
    result.setdefault("_meta", {})
    result["_meta"]["generated_at"] = now
    if not is_refresh and not old_index:
        result["_meta"]["created_at"] = now

    # 目录 — 完全覆盖
    result["目录"] = catalog

    # 线速览 — 覆盖自动字段，保留人工可能覆写的值
    old_speed = old_index.get("线速览", {}) if old_index else {}
    for name, info in speed_view.items():
        old_info = old_speed.get(name, {})
        merged = dict(info)
        # 若人工修改过类型且脚本提取为空，保留人工值
        if not merged.get("类型") and old_info.get("类型"):
            merged["类型"] = old_info["类型"]
        result["线速览"][name] = merged

    # 多线交织总图 — 新增追加，已存在的保留人工字段
    old_iw_list = old_index.get("多线交织总图", []) if old_index else []
    old_iw_map = {}
    for iw in old_iw_list:
        if not isinstance(iw, dict):
            continue
        # 兼容旧格式: 章节 → 章节范围
        ch_range = iw.get("章节范围", "") or iw.get("章节", "")
        threads = tuple(sorted(iw.get("涉及线", [])))
        key = (ch_range, threads) if ch_range else None
        if key:
            old_iw_map[key] = iw

    merged_iw = []
    matched_keys = set()

    # Phase 1: 合并新检测结果
    for iw in interweaving:
        key = (iw["章节范围"], tuple(sorted(iw["涉及线"])))
        matched_keys.add(key)
        if key in old_iw_map:
            old_entry = old_iw_map[key]
            iw["内容"] = old_entry.get("内容", "")
            iw["优先级"] = old_entry.get("优先级", iw["优先级"])
            iw["状态"] = old_entry.get("状态", iw.get("状态", "待发生"))
        merged_iw.append(iw)

    # Phase 2: 保留旧的有手工内容的条目（新检测未发现的）
    for key, old_iw in old_iw_map.items():
        if key not in matched_keys:
            # 仅保留有人工注释的旧条目
            if old_iw.get("内容"):
                old_iw["_preserved"] = True
                merged_iw.append(old_iw)

    # 按章节号排序
    def _sort_key(iw):
        ch_range = iw.get("章节范围", "") or iw.get("章节", "") or "第0章"
        try:
            return int(ch_range.replace("第", "").split("-")[0].replace("章", ""))
        except (ValueError, IndexError):
            return 0
    merged_iw.sort(key=_sort_key)

    result["多线交织总图"] = merged_iw

    # 节奏总览 — 完全不触碰
    if old_index and "节奏总览" in old_index:
        result["节奏总览"] = old_index["节奏总览"]

    return result


# ═══════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="从情节线文件生成主索引")
    parser.add_argument("--project-root", required=True, help="项目根目录")
    parser.add_argument("--refresh", action="store_true", help="刷新模式：只更新自动字段")
    parser.add_argument("--detect-only", action="store_true", help="仅检测交汇点，不写文件")
    parser.add_argument("--window", type=int, default=2, help="交汇检测窗口大小（默认 2）")
    args = parser.parse_args()

    project_root = Path(args.project_root).resolve()
    plot_dir = project_root / "outline" / "情节线"

    if not plot_dir.is_dir():
        print("错误: outline/情节线/ 目录不存在，请先完成 P4 情节构建")
        sys.exit(1)

    # 检查是否有情节线文件
    plot_files = [f for f in plot_dir.glob("*.yaml") if f.name != "主索引.yaml"]
    if not plot_files:
        print("提示: 情节线目录为空，无需生成主索引")
        sys.exit(0)

    # 读取目标章节数
    total_chapters = 0
    config_file = project_root / "config.yaml"
    if config_file.exists():
        config = load_yaml(config_file)
        if config:
            total_chapters = config.get("创作目标", {}).get("目标章节数", 0)

    now = datetime.now().isoformat()

    # 生成自动字段
    catalog = _extract_catalog(plot_dir)
    speed_view = _extract_speed_view(plot_dir, total_chapters)
    interweaving = _detect_interweaving(plot_dir, args.window)

    if args.detect_only:
        print(f"目录: 主线 + {len(catalog['支线'])} 条支线")
        print(f"线速览: {len(speed_view)} 条")
        print(f"交汇点: {len(interweaving)} 个")
        for iw in interweaving:
            print(f"  {iw['章节范围']} ({iw['涉及线数量']}线): {', '.join(iw['涉及线'])}")
        return

    # 读取已有主索引（如存在）
    index_file = plot_dir / "主索引.yaml"
    old_index = load_yaml(index_file) if index_file.exists() else None

    # 合并
    result = _smart_merge(old_index, catalog, speed_view, interweaving, now, args.refresh)

    # 写入前备份已有文件
    if index_file.exists():
        import shutil
        bak = index_file.with_suffix(".yaml.bak")
        shutil.copy(index_file, bak)

    save_yaml(index_file, result)

    action = "刷新" if args.refresh else "生成"
    if old_index:
        artificial = sum(1 for iw in result.get("多线交织总图", []) if iw.get("内容"))
        preserved = sum(1 for iw in result.get("多线交织总图", []) if iw.get("_preserved"))
        print(f"主索引已{action}: 主线 + {len(catalog['支线'])} 条支线, "
              f"{len(interweaving)} 个自动检测交汇点"
              f"（{artificial} 个人工注释, {preserved} 个保留条目）")
    else:
        print(f"主索引已{action}: 主线 + {len(catalog['支线'])} 条支线, {len(interweaving)} 个交汇点")
        print('  提示: 请编辑 主索引.yaml，填写多线交织总图的"内容"和"节奏总览"。')


if __name__ == "__main__":
    main()
