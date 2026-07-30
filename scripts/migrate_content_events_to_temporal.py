"""
存量数据迁移脚本：将现有 content 中的事件一次性转为 TEMPORAL_EVENT 节点。

用法：
    python scripts/migrate_content_events_to_temporal.py <project_root>

功能：
    遍历指定项目下的所有 SCENE / CHARACTER_ARC / PLOT_THREAD / WORLD_RULE，
    使用 EventExtractor 抽取其中的事件，为每个事件创建 TEMPORAL_EVENT 节点
    和关联边（HAS_EVENT / INVOLVES / LOCATED_AT）。

    可重复运行（幂等）：已通过 HAS_EVENT 边关联到 TEMPORAL_EVENT 的单元会被跳过。

迁移完成后，可设置环境变量关闭 TemporalEventIndex 的 content fallback：
    set NOVEL_TEMPORAL_CONTENT_FALLBACK=0
"""

from __future__ import annotations

import json
import os
import sys
import logging

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

# 确保能找到 shared 模块
_SHARED_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".opencode", "shared")
_V2_DIR = os.path.join(_SHARED_DIR, "v2")
for _p in (_SHARED_DIR, _V2_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)


def _ensure_imports():
    """延迟导入，避免未安装依赖时直接崩溃。"""
    global GraphStore, UnitType, UnitStatus, RelationType, EventExtractor
    from graph_store import GraphStore
    from graph_schema import UnitType, UnitStatus, RelationType
    from event_extractor import EventExtractor


def _has_temporal_events(store, unit_id: str) -> bool:
    """检查单元是否已有 TEMPORAL_EVENT 节点（通过 HAS_EVENT 入边）。"""
    for rel in store.get_relations(unit_id, direction="incoming"):
        if rel.relation_type == RelationType.HAS_EVENT:
            # 检查目标单元确实是 TEMPORAL_EVENT 类型且未归档
            target = store.get_unit(rel.source_id)
            if target and target.type == UnitType.TEMPORAL_EVENT and target.status != UnitStatus.ARCHIVED:
                return True
    for rel in store.get_relations(unit_id, direction="outgoing"):
        if rel.relation_type == RelationType.HAS_EVENT:
            target = store.get_unit(rel.target_id)
            if target and target.type == UnitType.TEMPORAL_EVENT and target.status != UnitStatus.ARCHIVED:
                return True
    return False


def migrate_project(project_root: str, dry_run: bool = False) -> int:
    """
    迁移一个项目中的所有存量事件。

    Args:
        project_root: 项目根目录路径
        dry_run: 如果为 True，只打印将要执行的操作但不实际写入

    Returns:
        创建的事件总数
    """
    _ensure_imports()

    store = GraphStore(project_root)
    store.initialize()
    extractor = EventExtractor(store)

    extractable_types = {
        UnitType.SCENE,
        UnitType.CHARACTER_ARC,
        UnitType.PLOT_THREAD,
        UnitType.WORLD_RULE,
    }

    total_created = 0
    total_skipped = 0
    total_units = 0

    for unit in list(store._units.values()):
        if unit.type not in extractable_types:
            continue
        if unit.status == UnitStatus.ARCHIVED:
            continue

        total_units += 1

        # 跳过已有关联 TEMPORAL_EVENT 的单元（幂等）
        if _has_temporal_events(store, unit.id):
            total_skipped += 1
            continue

        # 解析 content
        content = unit.content
        if not content:
            continue
        try:
            content_dict = json.loads(content) if isinstance(content, str) else content
        except (json.JSONDecodeError, TypeError, ValueError):
            continue
        if not isinstance(content_dict, dict):
            continue

        # 用 EventExtractor 抽取事件
        events = extractor.extract(unit.id, content_dict, unit.type)
        if not events:
            continue

        if dry_run:
            logger.info(f"[DRY RUN] {unit.type.value} '{unit.unit_name}' → {len(events)} 个事件")
            for evt in events:
                logger.info(f"    - [{evt.event_type}] {evt.summary} (ordinal={evt.ordinal})")
            total_created += len(events)
            continue

        # 实际创建 TEMPORAL_EVENT 节点
        for evt in events:
            try:
                event_unit = store.create_unit(
                    type=UnitType.TEMPORAL_EVENT,
                    unit_name=evt.summary[:80],
                    content=json.dumps(evt.to_temporal_content(), ensure_ascii=False),
                    actor="migration_script",
                )
                if not event_unit:
                    continue

                # HAS_EVENT 边：源实体 → 事件
                if evt.source_entity_id:
                    store.add_relation(
                        source_id=evt.source_entity_id,
                        target_id=event_unit.id,
                        relation_type=RelationType.HAS_EVENT,
                        actor="migration_script",
                    )

                # 关联参与者（INVOLVES 边）
                for char_name in evt.characters:
                    if char_name == evt.source_entity_name:
                        continue
                    char_unit = store.get_unit_by_name(char_name)
                    if char_unit:
                        store.add_relation(
                            source_id=event_unit.id,
                            target_id=char_unit.id,
                            relation_type=RelationType.INVOLVES,
                            actor="migration_script",
                        )

                total_created += 1

            except Exception as e:
                logger.error(f"创建事件失败: {evt.summary}: {e}")
                continue

        logger.info(
            f"  {unit.type.value} '{unit.unit_name}' → {len(events)} 个事件"
        )

    # 持久化
    if not dry_run and total_created > 0:
        store.flush()
        logger.info(f"已持久化 {total_created} 个新事件")

    logger.info(
        f"\n迁移完成：共扫描 {total_units} 个单元，"
        f"创建 {total_created} 个事件，跳过 {total_skipped} 个（已有事件）"
    )
    return total_created


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        print("用法: python scripts/migrate_content_events_to_temporal.py <project_root> [--dry-run]")
        sys.exit(1)

    project_root = sys.argv[1]
    dry_run = "--dry-run" in sys.argv

    if not os.path.isdir(project_root):
        print(f"错误：项目目录不存在: {project_root}")
        sys.exit(1)

    migrate_project(project_root, dry_run=dry_run)


if __name__ == "__main__":
    main()
