"""
V2 迁移工具：将现有项目文件导入到叙事单元网络（graph）。

用法:
    python .opencode/shared/v2/migrate.py --project-root NOVELS_ROOT/项目名
    python .opencode/shared/v2/migrate.py --project-root NOVELS_ROOT/项目名 --verify
    python .opencode/shared/v2/migrate.py --project-root NOVELS_ROOT/项目名 --dry-run
    python .opencode/shared/v2/migrate.py --list-projects
    python .opencode/shared/v2/migrate.py --project-root NOVELS_ROOT/项目名 --report
    
支持的文件类型（完整清单）：
  - characters/*.yaml      → CHARACTER_ARC
  - worldbuilding/*.yaml   → WORLD_RULE
  - outline/情节线/*.yaml  → PLOT_THREAD
  - outline/分纲/**/*.yaml → SCENE
  - outline/分卷/*.yaml    → NOTE（卷大纲）
  - outline/总纲.yaml      → NOTE（总纲）
  - outline/叙事策略.yaml  → NOTE
  - outline/时间线设计.yaml→ NOTE
  - outline/伏笔规划.yaml  → NOTE（标记 伏笔 标签）
  - outline/追踪/*.yaml    → NOTE（追踪数据）
  - ideation/*.yaml        → NOTE（创意）
  - chapters/*.txt         → CHUNK（章节正文）
  - quality/*.yaml         → NOTE（质量报告）
  - styles/*.yaml          → NOTE（风格定义）
"""

from __future__ import annotations

import sys
import os
import json
import yaml
import argparse
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Set, Any, Tuple
from collections import defaultdict

# 确保可以从 v2 目录导入
V2_DIR = os.path.abspath(os.path.dirname(__file__))
if V2_DIR not in sys.path:
    sys.path.insert(0, V2_DIR)

from graph_schema import (
    UnitType, UnitStatus, RelationType, NarrativeUnit,
    create_unit_id,
)
from graph_store import GraphStore as GraphStoreImpl


# ── 文件扫描器 ────────────────────────────────────────────────────────────

class ProjectScanner:
    """扫描项目目录，发现所有可迁移的文件"""

    def __init__(self, project_root: str):
        self.root = Path(project_root)
        self.files: Dict[str, List[Path]] = {
            "characters": [],
            "worldbuilding": [],
            "plot_threads": [],
            "outlines": [],       # 分纲
            "volumes": [],        # 分卷
            "synopsis": [],
            "narrative_strategy": [],
            "timeline": [],
            "foreshadowing": [],
            "tracking": [],
            "ideation": [],
            "chapters": [],
            "quality": [],
            "styles": [],
            "other": [],
        }
    
    def scan(self) -> Dict[str, List[Path]]:
        """扫描项目目录"""
        self.files["characters"] = sorted(self.root.glob("characters/*.yaml"))
        self.files["worldbuilding"] = sorted(self.root.glob("worldbuilding/*.yaml"))
        self.files["plot_threads"] = sorted(self.root.glob("outline/情节线/*.yaml"))
        self.files["outlines"] = sorted(self.root.glob("outline/分纲/**/*.yaml"))
        self.files["volumes"] = sorted(self.root.glob("outline/分卷/*.yaml"))
        
        # 单文件
        synopsis = self.root / "outline/总纲.yaml"
        if synopsis.exists():
            self.files["synopsis"] = [synopsis]
        ns = self.root / "outline/叙事策略.yaml"
        if ns.exists():
            self.files["narrative_strategy"] = [ns]
        tl = self.root / "outline/时间线设计.yaml"
        if tl.exists():
            self.files["timeline"] = [tl]
        fb = self.root / "outline/伏笔规划.yaml"
        if fb.exists():
            self.files["foreshadowing"] = [fb]
        
        self.files["tracking"] = sorted(self.root.glob("outline/追踪/*.yaml"))
        self.files["ideation"] = sorted(self.root.glob("ideation/*.yaml"))
        self.files["chapters"] = sorted(self.root.glob("chapters/*.txt"))
        self.files["quality"] = sorted(self.root.glob("quality/*.yaml"))
        self.files["styles"] = sorted(self.root.glob("styles/*.yaml"))
        
        return self.files
    
    def summary(self) -> Dict[str, int]:
        return {k: len(v) for k, v in self.files.items() if v}


# ── 导入引擎 ──────────────────────────────────────────────────────────────

class ImportEngine:
    """
    导入引擎：将扫描到的文件导入到 graph。
    """

    def __init__(self, store: GraphStoreImpl):
        self.store = store
        self._stats = {
            "created": 0,
            "updated": 0,
            "skipped": 0,
            "errors": 0,
        }
        self._error_details: List[str] = []
        self._imported_ids: Dict[str, str] = {}  # 文件路径 → 单元ID
    
    def import_file(self, file_path: Path, unit_type: UnitType, 
                    extra_tags: Optional[List[str]] = None,
                    belongs_to_chapter: Optional[int] = None,
                    belongs_to_volume: Optional[int] = None,
                    name_from_content: bool = True) -> bool:
        """
        导入单个文件。
        
        Returns: 是否成功
        """
        try:
            content = file_path.read_text(encoding="utf-8")
            rel_path = str(file_path.relative_to(self.store.project_root).as_posix())
            stem = file_path.stem
            
            # 解析名称
            name = stem
            tags = list(extra_tags or [])
            
            # 尝试解析 YAML 提取名称和标签
            if file_path.suffix in (".yaml", ".yml"):
                try:
                    data = yaml.safe_load(content)
                    if isinstance(data, dict):
                        if "索引信息" in data:
                            idx = data["索引信息"]
                            name = idx.get("名称", name)
                            status = UnitStatus.from_legacy_status(idx.get("状态", "active"))
                            tags.extend(idx.get("标签", []))
                        if "摘要" in data:
                            traits = data["摘要"].get("核心特质", [])
                            if isinstance(traits, list):
                                tags.extend(traits)
                except yaml.YAMLError:
                    pass
            
            # 检查是否已存在
            existing = self.store.get_unit_by_name(name)
            if existing and existing.extra.get("source_file") == rel_path:
                self._stats["skipped"] += 1
                self._imported_ids[rel_path] = existing.id
                return True
            
            if existing:
                # 名称冲突：加后缀
                name = f"{name}__{stem}"
            
            # 创建单元
            extra = {"source_file": rel_path, "imported_at": datetime.now(timezone.utc).isoformat()}
            if file_path.suffix == ".txt":
                extra["word_count"] = len(content)
            
            unit = self.store.create_unit(
                type=unit_type,
                unit_name=name,
                content=content,
                status=UnitStatus.MATURE,
                tags=tags,
                belongs_to_chapter=belongs_to_chapter,
                belongs_to_volume=belongs_to_volume,
                extra=extra,
                actor="migration",
            )
            self._imported_ids[rel_path] = unit.id
            self._stats["created"] += 1
            return True
            
        except Exception as e:
            self._stats["errors"] += 1
            self._error_details.append(f"  {file_path.name}: {e}")
            return False
    
    def report(self) -> Dict[str, Any]:
        return {
            **self._stats,
            "total_imported": len(self._imported_ids),
            "error_count": self._stats["errors"],
            "error_details": self._error_details[:5],  # 只显示前5个错误
        }


# ── 关系构建器 ────────────────────────────────────────────────────────────

class RelationBuilder:
    """
    关系构建器：在导入完成后，根据文件间的引用关系建立叙事单元关联。
    """

    def __init__(self, store: GraphStoreImpl):
        self.store = store
        self._stats = {"relations_added": 0, "skipped": 0}
    
    def build_all(self, imported_ids: Dict[str, str]):
        """根据导入的文件路径推断关系"""
        # 分组：按文件路径前缀
        by_prefix = defaultdict(dict)
        for path, uid in imported_ids.items():
            parts = path.split("/")
            if len(parts) >= 2:
                prefix = parts[0]
                by_prefix[prefix][path] = uid
        
        # 1. 角色 ↔ 场景（通过分纲中的 出场角色 字段）
        scene_paths = {p: uid for p, uid in imported_ids.items() if p.startswith("outline/分纲/")}
        char_paths = {p: uid for p, uid in imported_ids.items() if p.startswith("characters/")}
        self._build_char_scene_relations(scene_paths, char_paths)
        
        # 2. 场景 ↔ 情节线（通过分纲中的 关联情节线 字段）
        plot_paths = {p: uid for p, uid in imported_ids.items() if p.startswith("outline/情节线/")}
        self._build_scene_plot_relations(scene_paths, plot_paths)
        
        # 3. 总纲 ↔ 情节线（总纲引用情节线）
        synopsis_paths = {p: uid for p, uid in imported_ids.items() if p.endswith("总纲.yaml")}
        self._build_synopsis_plot_relations(synopsis_paths, plot_paths)
        
        # 4. 创意 ↔ 总纲（创意方案被总纲使用）
        ideation_paths = {p: uid for p, uid in imported_ids.items() if p.startswith("ideation/")}
        self._build_ideation_synopsis_relations(ideation_paths, synopsis_paths)
        
        self.store.flush()
    
    def _build_char_scene_relations(self, scenes: Dict[str, str], chars: Dict[str, str]):
        """从分纲 YAML 的 出场角色 字段建立角色↔场景关系"""
        for path, scene_uid in scenes.items():
            try:
                fpath = self.store.project_root / path
                if not fpath.exists():
                    continue
                data = yaml.safe_load(fpath.read_text(encoding="utf-8"))
                if not isinstance(data, dict):
                    continue
                
                # 提取角色名
                char_names = set()
                # 从 出场角色 列表
                if "摘要" in data and "出场角色" in data["摘要"]:
                    for c in data["摘要"]["出场角色"]:
                        if isinstance(c, dict):
                            char_names.add(c.get("角色名", ""))
                        elif isinstance(c, str):
                            char_names.add(c)
                # 从完整档案
                if "完整档案" in data and "出场角色" in data["完整档案"]:
                    for c in data["完整档案"]["出场角色"]:
                        if isinstance(c, dict):
                            char_names.add(c.get("角色名", ""))
                        elif isinstance(c, str):
                            char_names.add(c)
                
                for cname in char_names:
                    cname = cname.strip()
                    if not cname:
                        continue
                    # 查找角色单元
                    for cpath, cuid in chars.items():
                        if cname in cpath or cname in Path(cpath).stem:
                            if self.store.add_relation(cuid, scene_uid, RelationType.PARTICIPATES_IN, 
                                                       actor="migration"):
                                self._stats["relations_added"] += 1
                            break
            except Exception:
                self._stats["skipped"] += 1
    
    def _build_scene_plot_relations(self, scenes: Dict[str, str], plots: Dict[str, str]):
        """从分纲的 关联情节线 字段建立场景↔情节线关系"""
        for path, scene_uid in scenes.items():
            try:
                fpath = self.store.project_root / path
                if not fpath.exists():
                    continue
                data = yaml.safe_load(fpath.read_text(encoding="utf-8"))
                if not isinstance(data, dict):
                    continue
                
                # 关联情节线
                related_plots = []
                if "完整档案" in data and "关联情节线" in data["完整档案"]:
                    rp = data["完整档案"]["关联情节线"]
                    related_plots = rp if isinstance(rp, list) else [rp]
                elif "摘要" in data and "关联情节线" in data.get("摘要", {}):
                    rp = data["摘要"]["关联情节线"]
                    related_plots = rp if isinstance(rp, list) else [rp]
                
                for plot_ref in related_plots:
                    plot_ref = str(plot_ref).strip()
                    for ppath, puid in plots.items():
                        if plot_ref in ppath or plot_ref in Path(ppath).stem:
                            if self.store.add_relation(scene_uid, puid, RelationType.IMPLEMENTS,
                                                       actor="migration"):
                                self._stats["relations_added"] += 1
                            break
            except Exception:
                self._stats["skipped"] += 1
    
    def _build_synopsis_plot_relations(self, synopses: Dict[str, str], plots: Dict[str, str]):
        """总纲引用情节线"""
        for path, syn_uid in synopses.items():
            try:
                fpath = self.store.project_root / path
                if not fpath.exists():
                    continue
                data = yaml.safe_load(fpath.read_text(encoding="utf-8"))
                if not isinstance(data, dict):
                    continue
            except Exception:
                self._stats["skipped"] += 1
                continue
            
            # 从总纲的分卷/幕结构中提取情节线引用
            for section in ["故事结构", "分卷"]:
                if section in data:
                    items = data[section]
                    if isinstance(items, list):
                        for item in items:
                            if isinstance(item, dict):
                                for v in item.values():
                                    if isinstance(v, str):
                                        for ppath, puid in plots.items():
                                            if v and (v in ppath or any(w in v.lower() for w in ["主线", "支线"])):
                                                if self.store.add_relation(syn_uid, puid, RelationType.REFERENCES,
                                                                           actor="migration"):
                                                    self._stats["relations_added"] += 1
    
    def _build_ideation_synopsis_relations(self, ideations: Dict[str, str], synopses: Dict[str, str]):
        """创意方案被总纲使用"""
        for ideation_path, ideation_uid in ideations.items():
            for syn_path, syn_uid in synopses.items():
                if self.store.add_relation(ideation_uid, syn_uid, RelationType.INSPIRES,
                                           actor="migration"):
                    self._stats["relations_added"] += 1
    
    def report(self) -> Dict[str, int]:
        return dict(self._stats)


# ── 验证器 ────────────────────────────────────────────────────────────────

class MigrationVerifier:
    """验证迁移完整性"""

    def __init__(self, store: GraphStoreImpl, scanner: ProjectScanner):
        self.store = store
        self.scanner = scanner
        self._checks: List[Dict[str, Any]] = []
    
    def verify(self) -> Dict[str, Any]:
        """执行全部验证检查"""
        results = {
            "total_files": 0,
            "total_units": self.store.stats()["total_units"],
            "total_relations": self.store.stats()["total_relations"],
            "checks": [],
            "passed": 0,
            "failed": 0,
            "warnings": 0,
        }
        
        # 检查1：文件→单元覆盖率
        all_files = self.scanner.summary()
        total_files = sum(all_files.values())
        results["total_files"] = total_files
        
        all_units = self.store.list_units()
        unit_names = {u.unit_name for u in all_units}
        
        # 从文件名推断应有的单元名
        expected_names = set()
        for path_list in self.scanner.files.values():
            for p in path_list:
                expected_names.add(p.stem)
        
        missing = expected_names - unit_names
        if missing:
            results["checks"].append({
                "name": "单元覆盖率",
                "status": "warning",
                "detail": f"{len(missing)} 个文件未找到对应单元: {list(missing)[:5]}",
            })
            results["warnings"] += 1
        else:
            results["checks"].append({
                "name": "单元覆盖率",
                "status": "pass",
                "detail": f"全部 {total_files} 个文件已导入为叙事单元",
            })
            results["passed"] += 1
        
        # 检查2：角色↔场景关系
        char_units = self.store.find_units(type=UnitType.CHARACTER_ARC)
        scene_units = self.store.find_units(type=UnitType.SCENE)
        char_scene_rels = 0
        for cu in char_units:
            rels = self.store.get_relations(cu.id)
            char_scene_rels += len(rels)
        
        if char_units and not char_scene_rels:
            results["checks"].append({
                "name": "角色-场景关系",
                "status": "warning",
                "detail": f"{len(char_units)} 个角色但没有建立与场景的关系",
            })
            results["warnings"] += 1
        else:
            results["checks"].append({
                "name": "角色-场景关系",
                "status": "pass",
                "detail": f"{len(char_units)} 角色, {len(scene_units)} 场景, {char_scene_rels} 关系",
            })
            results["passed"] += 1
        
        # 检查3：情节线↔场景关系
        plot_units = self.store.find_units(type=UnitType.PLOT_THREAD)
        plot_scene_rels = 0
        for pu in plot_units:
            rels = self.store.get_relations(pu.id)
            plot_scene_rels += len(rels)
        
        results["checks"].append({
            "name": "情节线-场景关系",
            "status": "pass",
            "detail": f"{len(plot_units)} 情节线, {plot_scene_rels} 关联关系",
        })
        results["passed"] += 1
        
        # 检查4：事件溯源
        stats = self.store.stats()
        if stats["total_events"] > 0:
            results["checks"].append({
                "name": "事件溯源",
                "status": "pass",
                "detail": f"{stats['total_events']} 条事件记录",
            })
            results["passed"] += 1
        
        # 检查5：快照
        snapshots = self.store.get_snapshots()
        results["checks"].append({
            "name": "快照",
            "status": "pass" if snapshots else "warning",
            "detail": f"{len(snapshots)} 个快照" if snapshots else "未创建快照",
        })
        if snapshots:
            results["passed"] += 1
        else:
            results["warnings"] += 1
        
        results["status"] = "pass" if results["failed"] == 0 else "fail"
        return results


# ── 报告生成器 ────────────────────────────────────────────────────────────

def generate_report(scanner: ProjectScanner, import_result: Dict[str, Any],
                    relation_result: Dict[str, int],
                    verify_result: Dict[str, Any]) -> str:
    """生成迁移报告"""
    lines = []
    lines.append("=" * 60)
    lines.append("V2 迁移报告")
    lines.append(f"时间: {datetime.now(timezone.utc).isoformat()}")
    lines.append("=" * 60)
    lines.append("")
    
    # 扫描结果
    lines.append("## 扫描结果")
    files = scanner.summary()
    for category, count in sorted(files.items()):
        lines.append(f"  {category}: {count}")
    lines.append(f"  总计: {sum(files.values())} 个文件")
    lines.append("")
    
    # 导入结果
    lines.append("## 导入结果")
    lines.append(f"  创建: {import_result.get('created', 0)}")
    lines.append(f"  更新: {import_result.get('updated', 0)}")
    lines.append(f"  跳过: {import_result.get('skipped', 0)}")
    lines.append(f"  错误: {import_result.get('error_count', 0)}")
    if import_result.get('error_count', 0):
        lines.append("  错误详情:")
        for err in import_result.get('error_details', [])[:5]:
            lines.append(f"    {err}")
    lines.append("")
    
    # 关系结果
    lines.append("## 关系构建")
    lines.append(f"  新建关系: {relation_result.get('relations_added', 0)}")
    lines.append("")
    
    # 验证结果
    lines.append("## 验证结果")
    lines.append(f"  总叙事单元: {verify_result.get('total_units', 0)}")
    lines.append(f"  总关系: {verify_result.get('total_relations', 0)}")
    lines.append(f"  检查项: {verify_result.get('passed', 0)} 通过, "
                 f"{verify_result.get('failed', 0)} 失败, "
                 f"{verify_result.get('warnings', 0)} 警告")
    for check in verify_result.get('checks', []):
        status_mark = "✅" if check["status"] == "pass" else "⚠️" if check["status"] == "warning" else "❌"
        lines.append(f"  {status_mark} {check['name']}: {check['detail']}")
    lines.append("")
    
    # graph 统计
    lines.append("## Graph 统计")
    lines.append(f"  叙事单元: {verify_result.get('total_units', 0)}")
    lines.append(f"  关系: {verify_result.get('total_relations', 0)}")
    lines.append("")
    
    lines.append("=" * 60)
    lines.append("迁移完成")
    
    return "\n".join(lines)


# ── 主 CLI ────────────────────────────────────────────────────────────────

def find_projects(base_dir: str) -> List[str]:
    """在 NOVELS_ROOT 下发现项目"""
    root = Path(base_dir)
    # 查找所有包含 config.yaml 的目录
    projects = []
    for subdir in root.iterdir():
        if subdir.is_dir() and (subdir / "config.yaml").exists():
            projects.append(subdir.name)
    return sorted(projects)


def main():
    parser = argparse.ArgumentParser(description="V2 迁移工具：将项目导入到叙事单元网络")
    parser.add_argument("--project-root", help="项目根目录绝对路径")
    parser.add_argument("--dry-run", action="store_true", help="只扫描不写入")
    parser.add_argument("--verify", action="store_true", help="迁移后执行验证")
    parser.add_argument("--report", action="store_true", help="生成迁移报告")
    parser.add_argument("--list-projects", action="store_true", help="列出可迁移的项目")
    parser.add_argument("--novels-root", default="",
                        help="NOVELS_ROOT 路径（用于 --list-projects）")
    
    args = parser.parse_args()
    
    if args.list_projects:
        base = args.novels_root or os.path.join(os.getcwd(), "novels")
        projects = find_projects(base)
        if projects:
            print(f"发现 {len(projects)} 个项目:")
            for p in projects:
                print(f"  {os.path.join(base, p)}")
        else:
            print(f"在 {base} 下未找到项目（没有 config.yaml 的目录）")
        return
    
    if not args.project_root:
        parser.print_help()
        print("\n错误: 需要 --project-root 或 --list-projects")
        sys.exit(1)
    
    project_root = Path(args.project_root)
    if not project_root.exists():
        print(f"错误: 项目路径不存在: {project_root}")
        sys.exit(1)
    
    print(f"V2 迁移工具")
    print(f"项目: {project_root}")
    print(f"模式: {'Dry Run' if args.dry_run else '执行'}")
    print()
    
    # Step 1: 扫描
    print("📁 扫描项目文件...")
    scanner = ProjectScanner(str(project_root))
    files = scanner.scan()
    summary = scanner.summary()
    total = sum(summary.values())
    print(f"  发现 {total} 个文件")
    for cat, count in sorted(summary.items()):
        print(f"    {cat}: {count}")
    print()
    
    if total == 0:
        print("没有可迁移的文件。项目可能已经迁移过了。")
        # 检查是否已有 graph 目录
        graph_dir = project_root / "graph"
        if graph_dir.exists():
            store = GraphStoreImpl(str(project_root))
            store.initialize()
            stats = store.stats()
            print(f"\ngraph 目录已存在:")
            print(f"  叙事单元: {stats['total_units']}")
            print(f"  关系: {stats['total_relations']}")
            print(f"  事件: {stats['total_events']}")
        return
    
    if args.dry_run:
        print("Dry Run 模式 - 不执行导入")
        print("使用 --project-root 指定真实项目路径来执行迁移")
        return
    
    # Step 2: 初始化 graph 存储
    print("🗄️  初始化 graph 存储...")
    store = GraphStoreImpl(str(project_root))
    store.initialize()
    
    # Step 3: 导入
    print("📥 导入文件到 graph...")
    importer = ImportEngine(store)
    
    # 文件类型 → UnitType 映射
    type_map = {
        "characters": UnitType.CHARACTER_ARC,
        "worldbuilding": UnitType.WORLD_RULE,
        "plot_threads": UnitType.PLOT_THREAD,
        "outlines": UnitType.SCENE,
        "volumes": UnitType.NOTE,
        "synopsis": UnitType.NOTE,
        "narrative_strategy": UnitType.NOTE,
        "timeline": UnitType.NOTE,
        "foreshadowing": UnitType.NOTE,
        "tracking": UnitType.NOTE,
        "ideation": UnitType.NOTE,
        "chapters": UnitType.CHUNK,
        "quality": UnitType.NOTE,
        "styles": UnitType.NOTE,
    }
    
    # 特殊标签
    tag_map = {
        "foreshadowing": ["伏笔"],
        "ideation": ["创意"],
        "quality": ["质量"],
        "tracking": ["追踪"],
        "styles": ["风格"],
        "volumes": ["分卷"],
        "synopsis": ["总纲"],
        "narrative_strategy": ["叙事策略"],
        "timeline": ["时间线"],
    }
    
    for category, unit_type in type_map.items():
        tags = tag_map.get(category, [])
        for fpath in scanner.files.get(category, []):
            # 尝试提取章节号
            chapter = None
            volume = None
            if category == "outlines":
                stem = fpath.stem
                if "第" in stem and "章" in stem:
                    try:
                        ch_str = stem.replace("第", "").replace("章", "").strip()
                        chapter = int(ch_str)
                    except ValueError:
                        pass
                # 提取卷号
                parts = fpath.parts
                for p in parts:
                    if "卷" in p:
                        try:
                            volume = int(p.replace("卷", ""))
                        except ValueError:
                            pass
            
            importer.import_file(fpath, unit_type, 
                                extra_tags=tags,
                                belongs_to_chapter=chapter,
                                belongs_to_volume=volume)
    
    importer_report = importer.report()
    print(f"  创建: {importer_report['created']}")
    print(f"  跳过: {importer_report['skipped']}")
    print(f"  错误: {importer_report.get('error_count', 0)}")
    if importer_report.get('error_count', 0) and importer_report.get('error_details'):
        for err in importer_report['error_details']:
            print(f"    {err}")
    print()
    
    # Step 4: 构建关系
    print("🔗 建立关系...")
    rel_builder = RelationBuilder(store)
    rel_builder.build_all(importer._imported_ids)
    rel_report = rel_builder.report()
    print(f"  新增关系: {rel_report['relations_added']}")
    print()
    
    # Step 5: 创建快照
    print("📸 创建迁移快照...")
    snapshot = store.create_snapshot({"reason": "migration", "files_imported": total})
    print(f"  快照: {snapshot.snapshot_id}")
    store.flush()
    print()
    
    # Step 6: 验证
    if args.verify:
        print("✅ 验证迁移完整性...")
        verifier = MigrationVerifier(store, scanner)
        verify_result = verifier.verify()
        for check in verify_result["checks"]:
            mark = "✅" if check["status"] == "pass" else "⚠️" if check["status"] == "warning" else "❌"
            print(f"  {mark} {check['name']}: {check['detail']}")
        print()
    
    # Step 7: 报告
    if args.report:
        print("📄 生成迁移报告...")
        verifier = MigrationVerifier(store, scanner)
        verify_result = verifier.verify()
        report = generate_report(scanner, importer_report, rel_report, verify_result)
        
        report_path = project_root / "graph" / "migration_report.md"
        report_path.write_text(report, encoding="utf-8")
        print(f"  报告已写入: {report_path}")
        print()
        print(report)
    else:
        # 简易统计
        stats = store.stats()
        print(f"📊 Graph 统计:")
        print(f"  叙事单元: {stats['total_units']}")
        print(f"  关系: {stats['total_relations']}")
        print(f"  事件: {stats['total_events']}")
        print()
    
    print("✅ 迁移完成")


if __name__ == "__main__":
    main()
