"""Deep enrichment of WORLD_RULE descriptions from original YAML files."""
import json, sys, os, yaml

sys.path.insert(0, ".opencode/shared/v2")
from graph_store import GraphStore
from graph_schema import UnitType

PROJECT = "novels/凡人之诡影重重"
OLD_WB = "novels/空山闻仙/worldbuilding"

store = GraphStore(PROJECT)
store.initialize()

def build_description(data):
    """Build rich description from full YAML structure."""
    summary = data.get("摘要", {})
    full = data.get("完整档案", {})
    idx = data.get("索引信息", {})

    parts = []

    # 一句话描述
    oneline = summary.get("一句话描述", "")
    if oneline:
        parts.append(oneline)

    # 核心特质 as tags
    traits = summary.get("核心特质", [])
    if traits and isinstance(traits, list):
        tags_str = " | ".join(traits)
        parts.append(f"核心特征：{tags_str}")

    # 完整档案 - find all text content
    for key, val in full.items():
        if isinstance(val, str) and len(val) > 10:
            # Skip if already covered
            if val not in parts and val[:40] not in str(parts):
                parts.append(val.strip()[:300])
        elif isinstance(val, list) and len(val) > 0:
            # List items like 等级划分, 关键事件
            items = []
            for item in val:
                if isinstance(item, dict):
                    name = item.get("等级名", item.get("名称", item.get("事件", "")))
                    desc = item.get("描述", item.get("说明", ""))
                    if name and desc:
                        items.append(f"{name}：{desc[:80]}")
                    elif name:
                        items.append(name)
                elif isinstance(item, str) and len(item) > 5:
                    items.append(item.strip()[:120])
            if items:
                summary_items = "；".join(items[:5])
                parts.append(f"{key}：{summary_items}")

    # Join all parts
    if parts:
        return "\n\n".join(parts)
    return idx.get("名称", "")

fixed = 0
for fname in sorted(os.listdir(OLD_WB)):
    if not fname.endswith(".yaml"):
        continue
    name = fname.replace(".yaml", "")
    fpath = os.path.join(OLD_WB, fname)
    try:
        data = yaml.safe_load(open(fpath, "r", encoding="utf-8"))
    except:
        continue
    if not isinstance(data, dict):
        continue

    u = store.get_unit_by_name(name)
    if not u or u.type != UnitType.WORLD_RULE:
        continue

    desc = build_description(data)
    if not desc or desc == name:
        continue

    try:
        extra = json.loads(u.content)
    except:
        extra = {}
    extra["核心设定"] = desc
    if "_display" not in extra:
        extra["_display"] = {}
    extra["_display"]["描述"] = desc[:800]
    store.update_unit(u.id, content=json.dumps(extra, ensure_ascii=False), actor="enrich_deep")
    fixed += 1
    print(f"  ✅ {name}: {len(desc)} chars")

store.flush()
print(f"\n✅ 深度丰富: {fixed} 个 WORLD_RULE")
