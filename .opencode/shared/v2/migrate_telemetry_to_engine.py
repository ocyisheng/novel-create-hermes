"""
migrate_telemetry_to_engine.py — 遥测数据从旧项目路径迁移到 .engine/。

将旧格式的遥测和会话总结迁移到新的 .engine/ 统一存储。
迁移后不删除旧文件（安全策略），手动确认后再清理。

用法:
    python .opencode/shared/v2/migrate_telemetry_to_engine.py              # 迁移所有项目
    python .opencode/shared/v2/migrate_telemetry_to_engine.py --project 龙渊  # 迁移指定项目
    python .opencode/shared/v2/migrate_telemetry_to_engine.py --dry-run     # 试运行
"""

import json
import os
import sys
import argparse
from datetime import datetime, timezone
from pathlib import Path
from collections import Counter

# 确保 shared/ 在 path 中
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 工具根目录
_TOOL_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_ENGINE_DIR = os.path.join(_TOOL_ROOT, ".engine")
_NOVELS_DIR = os.path.join(_TOOL_ROOT, "novels")


def _find_projects(filter_name: str = "") -> list[str]:
    """发现所有 V2 小说项目。"""
    projects = []
    if not os.path.isdir(_NOVELS_DIR):
        return projects
    
    for name in os.listdir(_NOVELS_DIR):
        proj_path = os.path.join(_NOVELS_DIR, name)
        if not os.path.isdir(proj_path):
            continue
        if os.path.isdir(os.path.join(proj_path, "graph")):
            if not filter_name or name == filter_name:
                projects.append((name, proj_path))
    
    return projects


def migrate_telemetry(projects: list[tuple[str, str]], dry_run: bool = False) -> dict:
    """迁移 graph/telemetry.ndjson 到 .engine/telemetry/。"""
    stats = Counter()
    
    for proj_name, proj_path in projects:
        old_file = os.path.join(proj_path, "graph", "telemetry.ndjson")
        if not os.path.exists(old_file):
            print(f"  ⏭  {proj_name}: 无 telemetry.ndjson")
            continue
        
        entries = []
        with open(old_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        entry = json.loads(line)
                        # 补充 project 和 caller 字段（旧数据缺失）
                        entry.setdefault("project", proj_name)
                        entry.setdefault("caller", "unknown")
                        entries.append(entry)
                    except json.JSONDecodeError:
                        pass
        
        if not entries:
            print(f"  ⏭  {proj_name}: telemetry.ndjson 为空")
            continue
        
        # 按月份分片写入 .engine/telemetry/
        by_month = {}
        for entry in entries:
            ts = entry.get("ts", "")
            month = ts[:7] if len(ts) >= 7 else datetime.now(timezone.utc).strftime("%Y-%m")
            by_month.setdefault(month, []).append(entry)
        
        if dry_run:
            print(f"  🔍 {proj_name}: 将迁移 {len(entries)} 条遥测记录到 {len(by_month)} 个月份文件")
            stats["telemetry_entries"] += len(entries)
            stats["telemetry_projects"] += 1
            continue
        
        for month, month_entries in by_month.items():
            month_dir = os.path.join(_ENGINE_DIR, "telemetry")
            os.makedirs(month_dir, exist_ok=True)
            month_file = os.path.join(month_dir, f"{month}.ndjson")
            
            with open(month_file, "a", encoding="utf-8") as f:
                for entry in month_entries:
                    f.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")
        
        stats["telemetry_entries"] += len(entries)
        stats["telemetry_projects"] += 1
        print(f"  ✅ {proj_name}: 迁移 {len(entries)} 条遥测记录")
    
    return dict(stats)


def migrate_summaries(projects: list[tuple[str, str]], dry_run: bool = False) -> dict:
    """迁移 .omo/analysis/logs/*.summary.md 到 .engine/summaries/。"""
    stats = Counter()
    
    for proj_name, proj_path in projects:
        old_log_dir = os.path.join(proj_path, ".omo", "analysis", "logs")
        if not os.path.isdir(old_log_dir):
            print(f"  ⏭  {proj_name}: 无 summary logs")
            continue
        
        summary_files = [f for f in os.listdir(old_log_dir) if f.endswith(".summary.md")]
        if not summary_files:
            print(f"  ⏭  {proj_name}: 无 .summary.md 文件")
            continue
        
        for fname in summary_files:
            old_file = os.path.join(old_log_dir, fname)
            content = Path(old_file).read_text(encoding="utf-8")
            
            # 提取时间戳（从文件名或内容）
            ts_str = fname[:19] if len(fname) >= 19 else datetime.now(timezone.utc).strftime("%Y-%m-%d_%H%M%S")
            try:
                ts = datetime.strptime(ts_str, "%Y-%m-%d_%H%M%S")
            except ValueError:
                ts = datetime.now(timezone.utc)
            
            month = ts.strftime("%Y-%m")
            new_fname = f"{proj_name}_{ts.strftime('%Y-%m-%d_%H%M%S')}.summary.md"
            
            if dry_run:
                print(f"  🔍 {proj_name}: 将迁移 {fname} → {month}/{new_fname}")
                stats["summary_files"] += 1
                continue
            
            # 确保 front matter 中有 project 字段
            if content.startswith("---"):
                parts = content.split("---", 2)
                if len(parts) >= 3:
                    try:
                        fm = json.loads(parts[1])
                    except json.JSONDecodeError:
                        fm = {}
                    fm["project"] = proj_name
                    content = f"---\n{json.dumps(fm, ensure_ascii=False)}\n---\n{parts[2].strip()}\n"
            elif not content.startswith("---"):
                # 没有 front matter，添加
                fm = {"type": "session_summary", "project": proj_name, "created": ts.isoformat()}
                content = f"---\n{json.dumps(fm, ensure_ascii=False)}\n---\n\n{content.strip()}\n"
            
            month_dir = os.path.join(_ENGINE_DIR, "summaries", month)
            os.makedirs(month_dir, exist_ok=True)
            new_file = os.path.join(month_dir, new_fname)
            
            with open(new_file, "w", encoding="utf-8") as f:
                f.write(content)
            
            stats["summary_files"] += 1
        
        # 迁移旧 index.json 条目到新 index.json
        old_index = os.path.join(proj_path, ".omo", "analysis", "index.json")
        if os.path.exists(old_index):
            try:
                with open(old_index, "r", encoding="utf-8") as f:
                    old_data = json.load(f)
                old_entries = old_data.get("entries", [])
            except (json.JSONDecodeError, Exception):
                old_entries = []
            
            for entry in old_entries:
                entry["project"] = proj_name
        
        print(f"  ✅ {proj_name}: 迁移 {len(summary_files)} 个会话总结")
        stats["summary_projects"] += 1
    
    # 重建统一 index.json
    if not dry_run and stats.get("summary_files", 0) > 0:
        _rebuild_summary_index()
    
    return dict(stats)


def _rebuild_summary_index():
    """从 .engine/summaries/ 重建 index.json。"""
    summaries_dir = os.path.join(_ENGINE_DIR, "summaries")
    index_path = os.path.join(summaries_dir, "index.json")
    
    entries = []
    for root, dirs, files in os.walk(summaries_dir):
        for fname in files:
            if fname.endswith(".summary.md"):
                rel_month = os.path.basename(root)
                fpath = os.path.join(root, fname)
                
                # 解析 front matter
                fm = {}
                content = Path(fpath).read_text(encoding="utf-8")
                if content.startswith("---"):
                    parts = content.split("---", 2)
                    if len(parts) >= 3:
                        try:
                            fm = json.loads(parts[1])
                        except json.JSONDecodeError:
                            pass
                
                entries.append({
                    "file": fname,
                    "month": rel_month,
                    "timestamp": fm.get("created", ""),
                    "project": fm.get("project", ""),
                    "tags": fm.get("tags", []),
                    "session_id": fm.get("session_id", ""),
                    "focus_type": fm.get("focus_type", ""),
                    "focus_name": fm.get("focus_name", ""),
                })
    
    entries.sort(key=lambda e: e.get("timestamp", ""), reverse=True)
    
    with open(index_path, "w", encoding="utf-8") as f:
        json.dump({"entries": entries, "total": len(entries)}, f, ensure_ascii=False, indent=2)
    
    print(f"  📋 重建 index.json: {len(entries)} 条记录")


def main():
    parser = argparse.ArgumentParser(description="迁移遥测数据到 .engine/")
    parser.add_argument("--project", "-p", default="", help="指定项目名（不传则迁移所有项目）")
    parser.add_argument("--dry-run", action="store_true", help="试运行，不实际写入")
    parser.add_argument("--skip-telemetry", action="store_true", help="跳过 telemetry 迁移")
    parser.add_argument("--skip-summaries", action="store_true", help="跳过 summaries 迁移")
    
    args = parser.parse_args()
    
    projects = _find_projects(args.project)
    if not projects:
        print(f"❌ 未找到 V2 项目" + (f" '{args.project}'" if args.project else ""))
        sys.exit(1)
    
    mode = "试运行" if args.dry_run else "迁移"
    print(f"\n{'='*60}")
    print(f"🚀 遥测数据 {mode}")
    print(f"目标: .engine/")
    print(f"项目: {', '.join(p[0] for p in projects)}")
    print(f"{'='*60}\n")
    
    all_stats = {}
    
    if not args.skip_telemetry:
        print("📡 迁移 telemetry...")
        all_stats.update(migrate_telemetry(projects, args.dry_run))
    
    if not args.skip_summaries:
        print("\n📝 迁移 summaries...")
        all_stats.update(migrate_summaries(projects, args.dry_run))
    
    print(f"\n{'='*60}")
    print(f"📊 迁移统计: {all_stats}")
    print(f"{'='*60}")
    
    if args.dry_run:
        print("\n⚠️ 试运行完成。使用不带 --dry-run 的命令执行实际迁移。")
        print("   迁移后请手动检查 .engine/ 目录，确认无误后删除旧文件。")
    else:
        print("\n✅ 迁移完成。")
        print("   旧文件仍保留在原位置，检查无误后可手动删除：")
        for proj_name, proj_path in projects:
            old_telemetry = os.path.join(proj_path, "graph", "telemetry.ndjson")
            old_summaries = os.path.join(proj_path, ".omo", "analysis")
            if os.path.exists(old_telemetry):
                print(f"   - {old_telemetry}")
            if os.path.exists(old_summaries):
                print(f"   - {old_summaries}")


if __name__ == "__main__":
    main()
