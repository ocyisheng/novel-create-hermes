"""Deep enrichment of WORLD_RULE descriptions from original YAML files."""
import json, sys, os

sys.path.insert(0, ".opencode/shared/v2")
from graph_store import GraphStore
from graph_schema import UnitType

PROJECT = "novels/凡人之诡影重重"
OLD_WB = "novels/空山闻仙/worldbuilding"

store = GraphStore(PROJECT)
store.initialize()

def load_yaml_safe(path):
    """Load YAML file safely."""
    import yaml
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

def build_description(data):
    summary = data.get("摘要", {})
    full = data.get("完整档案", {})
    parts = []
    oneline = summary.get("一句话描述", "")
    if oneline:
        parts.append(oneline)
    traits = summary.get("核心特质", [])
    if traits and isinstance(traits, list):
        parts.append("核心特征：" + " | ".join(traits))
    for key, val in full.items():
        if isinstance(val, str) and len(val) > 10 and val[:40] not in str(parts):
            parts.append(val.strip()[:300])
        elif isinstance(val, list):
            items = []
            for item in val[:8]:
                if isinstance(item, dict):
                    name = item.get("等级名", item.get("名称", item.get("事件", "")))
                    desc_text = item.get("描述", item.get("说明", ""))
                    if name and desc_text:
                        items.append(f"{name}：{desc_text[:80]}")
                    elif name:
                        items.append(name)
                elif isinstance(item, str) and len(item) > 5:
                    items.append(item.strip()[:120])
            if items:
                parts.append(f"{key}：" + "；".join(items))
    return "\n\n".join(parts) if parts else ""

fixed = 0
for fname in sorted(os.listdir(OLD_WB)):
    if not fname.endswith(".yaml"):
        continue
    name = fname.replace(".yaml", "")
    try:
        data = load_yaml_safe(os.path.join(OLD_WB, fname))
    except Exception as e:
        print(f"  ⚠️ {name}: yaml error {e}")
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
    store.update_unit(u.id, content=json.dumps(extra, ensure_ascii=False), actor="enrich2")
    fixed += 1
    print(f"  ✅ {name}: {len(desc)} chars")

store.flush()
print(f"\n✅ 深度丰富: {fixed} 个 WORLD_RULE")
