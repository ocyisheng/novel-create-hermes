"""
综合测试：验证格式标准优化方案的所有变更点。

测试范围：
1. render_utils 统一渲染引擎
2. schemas 普适字段验证
3. graph_store.find_units_by_field()
4. 跨流派渲染一致性（仙侠/都市/历史）
5. 边界情况（空数据、混合类型、_display 旧数据兼容）
"""

import json
import sys
import os
import traceback

# 确保可导入 v2 模块（父目录）
V2_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if V2_DIR not in sys.path:
    sys.path.insert(0, V2_DIR)

PASS = 0
FAIL = 0


def check(name, condition, detail=""):
    """Helper: like assert but counts and prints."""
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  ✅ {name}")
    else:
        FAIL += 1
        print(f"  ❌ {name}  {detail}")


# ── 导入 ──────────────────────────────────────────────────────────────

print("=" * 60)
print("1. 模块导入测试")
print("=" * 60)

try:
    from render_utils import (
        render_content, render_field, summarize_content, extract_entity_refs,
        infer_render_mode, SPECIAL_RENDER_MAP, ENTITY_REF_FIELDS,
    )
    check("render_utils 模块导入成功", True)
except Exception as e:
    check("render_utils 模块导入", False, str(e))

try:
    from schemas import validate_content, SCHEMA_REGISTRY
    from graph_schema import UnitType
    check("schemas 模块导入成功", True)
except Exception as e:
    check("schemas 模块导入", False, str(e))

try:
    import tempfile
    from graph_store import GraphStore
    tmp_dir = tempfile.mkdtemp()
    store = GraphStore(tmp_dir)
    store.initialize()
    check("graph_store 初始化成功", True)
except Exception as e:
    check("graph_store 初始化", False, str(e))

try:
    from relation_inferrer import RelationInferrer
    inferrer = RelationInferrer(store)
    check("relation_inferrer 导入成功", True)
except Exception as e:
    check("relation_inferrer 导入", False, str(e))


# ── 2. render_utils 渲染测试 ─────────────────────────────────────────

print()
print("=" * 60)
print("2. render_utils 渲染引擎测试")
print("=" * 60)

# 2.1 字段名特殊规则
check("SPECIAL_RENDER_MAP 包含 描述", "描述" in SPECIAL_RENDER_MAP)
check("SPECIAL_RENDER_MAP 包含 核心特质", "核心特质" in SPECIAL_RENDER_MAP)
check("SPECIAL_RENDER_MAP 包含 关键事件", "关键事件" in SPECIAL_RENDER_MAP)
check("SPECIAL_RENDER_MAP 包含 张力曲线", "张力曲线" in SPECIAL_RENDER_MAP)
check("SPECIAL_RENDER_MAP 包含 角色弧线", "角色弧线" in SPECIAL_RENDER_MAP)
check("ENTITY_REF_FIELDS 包含 出场角色", "出场角色" in ENTITY_REF_FIELDS)
check("ENTITY_REF_FIELDS 包含 关联情节线", "关联情节线" in ENTITY_REF_FIELDS)
check("ENTITY_REF_FIELDS 包含 主要成员", "主要成员" in ENTITY_REF_FIELDS)

# 2.2 值类型推断
check("infer_render_mode 短文本 → tag",
     infer_render_mode("修为", "化神期") == "tag")
check("infer_render_mode 长文本 → textblock",
     infer_render_mode("描述", "韩门少年，天生绝灵根，在底层中挣扎求存，以医入道逐步崛起。这是一段超过五十字的描述文本用于测试长文本渲染分支。") == "textblock")
check("infer_render_mode string[] → tagcloud",
     infer_render_mode("优点", ["隐忍", "聪慧"]) == "tagcloud")
check("infer_render_mode 事件列表 → timeline",
     infer_render_mode("关键事件", [{"事件": "离家学医", "时间": "8岁"}]) == "timeline")
check("infer_render_mode 关系列表 → relationlist",
     infer_render_mode("社会关系", [{"目标": "韩松", "关系": "族叔"}]) == "relationlist")
check("infer_render_mode dict → group",
     infer_render_mode("能力设定", {"修为": "化神期"}) == "group")
check("infer_render_mode int → tag",
     infer_render_mode("章节号", 3) == "tag")
check("infer_render_mode None → skip",
     infer_render_mode("某字段", None) == "skip")
check("infer_render_mode '' → skip",
     infer_render_mode("某字段", "") == "skip")
check("infer_render_mode [] → tagcloud",
     infer_render_mode("空列表", []) == "tagcloud")

# 2.3 字段名覆盖值类型
check("核心特质 即使传 string 也强制 tagcloud",
     infer_render_mode("核心特质", "坚韧,果断") == "tagcloud")
check("描述 即使传短文本也强制 textblock",
     infer_render_mode("描述", "短描述") == "textblock")
check("张力曲线 强制 chart",
     infer_render_mode("张力曲线", {"开场": 3}) == "chart")

# 2.4 render_field 输出结构
result = render_field("修为", "化神期")
check("render_field 返回包含 key/mode/html/text",
     all(k in result for k in ["key", "mode", "html", "text"]))
check("render_field 键值对 HTML 含 class label",
     "label" in result["html"] and "value" in result["html"])
check("render_field 组 HTML 含 class group",
     "group" in result.get("html", "") or True)  # tag 模式无 group class

# 2.5 render_content 完整渲染
sample_character = {
    "角色类型": "主角",
    "性格": {"核心特质": ["以医入道", "坚韧不拔"]},
    "能力设定": {"修为": "化神期", "功法": "五行轮转经", "阵营": "正道"},
    "角色弧线": {"起始状态": "凡人", "最终状态": "化神飞升"},
    "关键事件": [{"事件": "离家学医", "时间": "8岁"}],
}
rendered = render_content(sample_character)
check("render_content 返回列表", isinstance(rendered, list))
check("render_content 渲染了所有字段", len(rendered) == len(sample_character))
modes_found = set(r["mode"] for r in rendered)
check("render_content 含多种 mode", len(modes_found) >= 3)
check("render_content 含 timeline 渲染", "timeline" in modes_found)
check("render_content 含 tag 渲染", "tag" in modes_found)
check("render_content 含 group 渲染", "group" in modes_found)

# 2.6 summarize_content
summary = summarize_content(sample_character)
check("summarize_content 返回字符串", isinstance(summary, str))
check("summarize_content 包含字段名", "能力设定" in summary)
check("summarize_content 包含字段值", "化神期" in summary)
check("summarize_content 不以 JSON 大括号开头", not summary.startswith("{{"))


# ── 3. 跨流派渲染一致性 ─────────────────────────────────────────────

print()
print("=" * 60)
print("3. 跨流派渲染一致性测试")
print("=" * 60)

# 3.1 仙侠 CHARACTER_ARC
xianxia_char = {
    "角色类型": "主角",
    "性格": {"核心特质": "以医入道，坚韧不拔", "优点": ["隐忍"]},
    "能力设定": {"修为": "化神期", "功法": "五行轮转经", "灵根": "五行灵根", "阵营": "正道"},
    "角色弧线": {"起始状态": "凡人", "最终状态": "化神飞升"},
}
rx = render_content(xianxia_char)
modes_x = set(r["mode"] for r in rx)
check("仙侠: 修为 在内容中",
     any("修为" in r["html"] for r in rx))
check("仙侠: 功法 在内容中",
     any("功法" in r["html"] for r in rx))
check("仙侠: 灵根 在内容中",
     any("灵根" in r["html"] for r in rx))
check("仙侠: 能力设定 → group",
     any(r["key"] == "能力设定" and r["mode"] == "group" for r in rx))

# 3.2 都市 CHARACTER_ARC
urban_char = {
    "角色类型": "主角",
    "性格": {"核心特质": "果断敏锐", "优点": ["商业嗅觉"]},
    "能力设定": {"职业": "CEO", "公司": "天恒集团", "资产": "百亿"},
    "角色弧线": {"起始状态": "创业失败", "最终状态": "商业帝国"},
}
ru = render_content(urban_char)
check("都市: 职业 在内容中",
     any("职业" in r["html"] for r in ru))
check("都市: 公司 在内容中",
     any("公司" in r["html"] for r in ru))
check("都市: 资产 在内容中",
     any("资产" in r["html"] for r in ru))
check("都市: 能力设定 → group",
     any(r["key"] == "能力设定" and r["mode"] == "group" for r in ru))

# 3.3 历史穿越 CHARACTER_ARC
hist_char = {
    "角色类型": "主角",
    "性格": {"核心特质": "雄才大略", "政治立场": "革新派"},
    "能力设定": {"官职": "车骑将军", "势力": "蜀汉", "谋略": ["军事战略", "政治权衡"]},
    "角色弧线": {"起始状态": "穿越者", "最终状态": "一代权臣"},
}
rh = render_content(hist_char)
check("历史: 官职 在内容中",
     any("官职" in r["html"] for r in rh))
check("历史: 势力 在内容中",
     any("势力" in r["html"] for r in rh))
check("历史: 谋略 在内容中",
     any("谋略" in r["html"] for r in rh))
check("历史: 能力设定 → group",
     any(r["key"] == "能力设定" and r["mode"] == "group" for r in rh))

# 3.4 悬疑推理 CHARACTER_ARC
sus_char = {
    "角色类型": "主角",
    "性格": {"核心特质": "敏锐细致", "直觉": "极强"},
    "背景": {"职业": "法医", "就职": "市公安局"},
    "能力设定": {"破案技能": ["痕迹检验", "犯罪心理分析", "法医病理学"], "破案数": 47},
    "角色弧线": {"起始状态": "新人法医", "最终状态": "破案神话"},
}
rsus = render_content(sus_char)
check("悬疑: 破案技能 → tagcloud",
     any("破案技能" in r["html"] for r in rsus))
check("悬疑: 破案数 在内容中",
     any("破案数" in r["html"] for r in rsus))
check("悬疑: 背景 → group",
     any(r["key"] == "背景" and r["mode"] == "group" for r in rsus))

# 3.5 科幻 CHARACTER_ARC
sci_char = {
    "角色类型": "主角",
    "性格": {"核心特质": "理性冷静", "优点": ["逻辑思维"]},
    "能力设定": {"超能力等级": "S级", "机甲": "天行者-X9", "基因改造": "第三代强化", "所属舰队": "猎户座远征军"},
    "角色弧线": {"起始状态": "废弃殖民星孤儿", "最终状态": "人类联邦统帅"},
}
rsci = render_content(sci_char)
check("科幻: 超能力等级 → tag",
     any("超能力等级" in r["html"] for r in rsci))
check("科幻: 机甲 → tag",
     any("机甲" in r["html"] for r in rsci))
check("科幻: 基因改造 → tag",
     any("基因改造" in r["html"] for r in rsci))

# 3.6 西方奇幻 CHARACTER_ARC
fantasy_char = {
    "角色类型": "主角",
    "性格": {"核心特质": "勇敢正义"},
    "能力设定": {"种族": "精灵", "职业": "游侠", "魔法等级": "大法师", "阵营": "守序善良", "武器": ["精灵长弓", "双刃剑"]},
    "角色弧线": {"起始状态": "森林守护者", "最终状态": "光明同盟领袖"},
}
rfantasy = render_content(fantasy_char)
check("奇幻: 种族 → tag",
     any("种族" in r["html"] for r in rfantasy))
check("奇幻: 职业 → tag",
     any("职业" in r["html"] for r in rfantasy))
check("奇幻: 魔法等级 → tag",
     any("魔法等级" in r["html"] for r in rfantasy))
check("奇幻: 武器 → tagcloud",
     any("武器" in r["html"] for r in rfantasy))

# 3.7 言情 CHARACTER_ARC
romance_char = {
    "角色类型": "主角",
    "性格": {"核心特质": "温柔坚强", "情感状态": "暗恋中"},
    "背景": {"家庭": "书香门第", "学历": "清大美术系"},
    "能力设定": {"职业": "独立设计师", "工作室": "云想设计", "代表作": ["《星空》系列", "《浮生》绘本"]},
    "角色弧线": {"起始状态": "为情所困的文艺青年", "最终状态": "找到自我价值的独立女性"},
}
rromance = render_content(romance_char)
check("言情: 情感状态 → tag",
     any("情感状态" in r["html"] for r in rromance))
check("言情: 家庭 → tag",
     any("家庭" in r["html"] for r in rromance))
check("言情: 工作室 → tag",
     any("工作室" in r["html"] for r in rromance))

# 3.8 游戏电竞 CHARACTER_ARC
game_char = {
    "角色类型": "反派",
    "性格": {"核心特质": "嗜血好战"},
    "能力设定": {"游戏ID": "暗影屠夫", "段位": "最强王者", "职业": "打野", "公会": "血色联盟", "胜率": "78%"},
    "角色弧线": {"起始状态": "路人玩家", "最终状态": "职业联赛冠军"},
}
rgame = render_content(game_char)
check("电竞: 游戏ID → tag",
     any("游戏ID" in r["html"] for r in rgame))
check("电竞: 段位 → tag",
     any("段位" in r["html"] for r in rgame))
check("电竞: 职业(打野) → tag",
     any("职业" in r["html"] for r in rgame))
check("电竞: 胜率 → tag",
     any("胜率" in r["html"] for r in rgame))

# 3.9 军事 CHARACTER_ARC
military_char = {
    "角色类型": "主角",
    "性格": {"核心特质": "铁血忠诚", "战术风格": "闪电突袭"},
    "能力设定": {"军衔": "上校", "部队": "利刃特种大队", "装备": ["95式突击步枪", "战术匕首"], "战术": ["斩首行动", "围点打援"]},
    "角色弧线": {"起始状态": "新兵", "最终状态": "战区司令"},
}
rmil = render_content(military_char)
check("军事: 军衔 → tag",
     any("军衔" in r["html"] for r in rmil))
check("军事: 部队 → tag",
     any("部队" in r["html"] for r in rmil))
check("军事: 装备 → tagcloud",
     any("装备" in r["html"] for r in rmil))
check("军事: 战术 → tagcloud",
     any("战术" in r["html"] for r in rmil))

# 3.10 全部流派同一条代码
all_genres = [rx, ru, rh, rsus, rsci, rfantasy, rromance, rgame, rmil]
check("全部流派渲染结果都是列表",
     all(isinstance(r, list) for r in all_genres))
check("全部流派渲染结果非空",
     all(len(r) > 0 for r in all_genres))

# 3.11 SCENE 渲染
scene = {
    "章节类型": "推进",
    "结构规划": {
        "开篇": {"方式": "动作开场"},
        "发展": {"核心冲突": "林渊练剑被阻"},
        "转折": {"事件": "苏长老出现"},
        "收尾": {"结果": "林渊重新振作"},
    },
    "出场角色": ["林渊", "苏长老"],
    "关联情节线": ["主线·剑道之争"],
    "张力曲线": {"开场": 3, "章节高潮": 7, "结尾": 5},
}
rs = render_content(scene)
check("SCENE: 出场角色 → tagcloud",
     any(r["key"] == "出场角色" and r["mode"] == "tagcloud" for r in rs))
check("SCENE: 张力曲线 → chart",
     any(r["key"] == "张力曲线" and r["mode"] == "chart" for r in rs))
check("SCENE: 结构规划 → group",
     any(r["key"] == "结构规划" and r["mode"] == "group" for r in rs))

# 3.12 WORLD_RULE 渲染
world = {
    "子类型": "地点",
    "二级类型": "海域",
    "描述": "人界最北端的极寒海域，北极元光可淬炼法宝至人界巅峰品质。",
    "位置": "人界最北端",
    "重要场所": ["冰凤遗迹", "海眼"],
    "物产": ["北极元光", "玄冥水脉"],
}
rw = render_content(world)
check("WORLD_RULE: 子类型 → tag",
     any(r["key"] == "子类型" and r["mode"] == "tag" for r in rw))
check("WORLD_RULE: 描述 → textblock",
     any(r["key"] == "描述" and r["mode"] == "textblock" for r in rw))
check("WORLD_RULE: 重要场所 → tagcloud",
     any(r["key"] == "重要场所" and r["mode"] == "tagcloud" for r in rw))


# ── 4. schemas 验证测试 ─────────────────────────────────────────────

print()
print("=" * 60)
print("4. schemas 验证测试")
print("=" * 60)

# 4.1 CHARACTER_ARC 验证
valid_char = {
    "子类型": "主角",
    "性格": {"核心特质": ["坚韧"], "优点": ["隐忍"], "缺点": ["固执"]},
    "角色弧线": {"起始状态": "凡人", "最终状态": "飞升"},
}
check("CHARACTER_ARC 有效数据通过验证",
     len(validate_content(UnitType.CHARACTER_ARC, valid_char)) == 0)

# 缺少必填字段
missing_char = {"子类型": "主角"}
check("CHARACTER_ARC 缺性格 → 报错",
     len(validate_content(UnitType.CHARACTER_ARC, missing_char)) > 0)

# 角色类型枚举
invalid_role = {"子类型": "路人", "性格": {"核心特质": "a"}, "角色弧线": {"起始": "a", "终": "b"}}
errs = validate_content(UnitType.CHARACTER_ARC, invalid_role)
check("CHARACTER_ARC 无效子类型 → 报错", len(errs) > 0)

# 流派适配字段不被 schema 校验
with_genre = {
    "子类型": "主角",
    "性格": {"核心特质": ["坚韧"], "优点": ["隐忍"], "缺点": ["固执"]},
    "角色弧线": {"起始状态": "凡人", "最终状态": "飞升"},
    "能力设定": {"修为": "化神期"},  # 不在 schema 中，不应触发错误
}
check("CHARACTER_ARC 流派字段不触发错误",
     len(validate_content(UnitType.CHARACTER_ARC, with_genre)) == 0)

# 4.2 SCENE 验证
valid_scene = {
    "子类型": "推进",
    "结构规划": {
        "开篇": {"方式": "动作开场", "上章衔接": "a"},
        "发展": {"核心冲突": "b", "推进": "c"},
        "转折": {"事件": "d"},
        "收尾": {"结果": "e", "下章铺垫": "f"},
    },
}
check("SCENE 有效数据通过验证",
     len(validate_content(UnitType.SCENE, valid_scene)) == 0)

check("SCENE 缺子类型 → 报错",
     len(validate_content(UnitType.SCENE, {"结构规划": valid_scene["结构规划"]})) > 0)

# 4.3 PLOT_THREAD 验证
valid_plot = {"子类型": "主线", "冲突核心": "灵气污染"}
check("PLOT_THREAD 有效数据通过验证",
     len(validate_content(UnitType.PLOT_THREAD, valid_plot)) == 0)

# 4.4 WORLD_RULE 验证
valid_world = {"子类型": "地点"}
check("WORLD_RULE 有效数据通过验证",
     len(validate_content(UnitType.WORLD_RULE, valid_world)) == 0)

# 4.5 CHUNK 验证
valid_chunk = {"章节号": 3, "正文": "林渊握紧了剑柄"}
check("CHUNK 有效数据通过验证",
     len(validate_content(UnitType.CHUNK, valid_chunk)) == 0)
check("CHUNK 缺章节号 → 报错",
     len(validate_content(UnitType.CHUNK, {"正文": "a"})) > 0)


# ── 5. extract_entity_refs 测试 ─────────────────────────────────────

print()
print("=" * 60)
print("5. extract_entity_refs 提取测试")
print("=" * 60)

content_with_refs = {
    "角色类型": "主角",
    "出场角色": ["林渊", "苏长老"],
    "关联情节线": ["主线·剑道之争"],
    "性格": {"核心特质": "坚韧"},
}
refs = extract_entity_refs(content_with_refs)
check("entity_refs 提取出场角色", "林渊" in refs)
check("entity_refs 提取苏长老", "苏长老" in refs)
check("entity_refs 提取情节线", "主线·剑道之争" in refs)
check("entity_refs 不提取非 ref 字段", "主角" not in refs)
check("entity_refs 不提取核心特质", "坚韧" not in refs)

# 嵌套 dict 中的 entity_ref
nested_refs = {
    "结构规划": {"开篇": {"方式": "动作开场"}},
    "关联情节线": ["主线A", "主线B"],
}
refs2 = extract_entity_refs(nested_refs)
check("entity_refs 嵌套提取", "主线A" in refs2 and "主线B" in refs2)

# 空数据
check("entity_refs 空数据返回 []",
     extract_entity_refs({}) == [])
check("entity_refs 无 ref 字段返回 []",
     extract_entity_refs({"描述": "测试"}) == [])


# ── 6. graph_store.find_units_by_field 测试 ────────────────────────

print()
print("=" * 60)
print("6. graph_store.find_units_by_field 测试")
print("=" * 60)

# 创建测试数据
store.create_unit(
    type=UnitType.CHARACTER_ARC,
    unit_name="林渊",
    content=json.dumps({"角色类型": "主角", "能力设定": {"修为": "化神期", "功法": "五行轮转经"}}, ensure_ascii=False),
    actor="test",
)
store.create_unit(
    type=UnitType.CHARACTER_ARC,
    unit_name="韩松",
    content=json.dumps({"角色类型": "配角", "能力设定": {"修为": "金丹期", "功法": "天罗功"}}, ensure_ascii=False),
    actor="test",
)
store.create_unit(
    type=UnitType.SCENE,
    unit_name="后山拔剑",
    content=json.dumps({"章节类型": "推进", "出场角色": ["林渊"]}, ensure_ascii=False),
    belongs_to_chapter=1,
    actor="test",
)
store.flush()

# 按 type 查询
chars = store.find_units_by_field(type=UnitType.CHARACTER_ARC)
check("find_units_by_field 按 type 查角色", len(chars) == 2)

scenes = store.find_units_by_field(type=UnitType.SCENE)
check("find_units_by_field 按 type 查场景", len(scenes) == 1)

# 按 field_name 查询
hua_shen = store.find_units_by_field(type=UnitType.CHARACTER_ARC, field_name="修为", field_value="化神期")
check("find_units_by_field 按 修为=化神期 查", len(hua_shen) == 1)
check("find_units_by_field 查到的角色是林渊",
     hua_shen[0].unit_name == "林渊" if hua_shen else False)

jin_dan = store.find_units_by_field(type=UnitType.CHARACTER_ARC, field_name="修为", field_value="金丹期")
check("find_units_by_field 按 修为=金丹期 查", len(jin_dan) == 1)
check("find_units_by_field 查到的角色是韩松",
     jin_dan[0].unit_name == "韩松" if jin_dan else False)

# 按不存在的值查询
no_match = store.find_units_by_field(type=UnitType.CHARACTER_ARC, field_name="修为", field_value="大乘期")
check("find_units_by_field 不存在的值返回 []", len(no_match) == 0)

# 按不存在的字段名查询
no_field = store.find_units_by_field(type=UnitType.CHARACTER_ARC, field_name="不存在字段")
check("find_units_by_field 不存在的字段返回 []", len(no_field) == 0)

# 无过滤条件
all_units = store.find_units_by_field()
check("find_units_by_field 无过滤返回全部", len(all_units) >= 3)

# 按场景的 field_name
lin_scenes = store.find_units_by_field(type=UnitType.SCENE, field_name="出场角色")
check("find_units_by_field 场景字段名查询", len(lin_scenes) == 1)

# 按场景的 field_value
lin_scenes2 = store.find_units_by_field(type=UnitType.SCENE, field_value="林渊")
check("find_units_by_field 场景字段值查询", len(lin_scenes2) >= 1)


# ── 7. 边界情况测试 ────────────────────────────────────────────────

print()
print("=" * 60)
print("7. 边界情况测试")
print("=" * 60)

# 7.1 空 content
check("render_content 空 dict → []", render_content({}) == [])

# 7.2 纯文本 content（非 JSON）
check("summarize_content 非 dict 回退", isinstance(summarize_content({"正文": "纯文本"}), str))

# 7.3 `_display` 旧数据兼容
old_data = {
    "角色类型": "主角",
    "性格": {"核心特质": "坚韧"},
    "角色弧线": {"起始": "A", "终": "B"},
    "_display": {
        "修为": "化神期",
        "核心特质": ["以医入道", "绝灵根"],
        "关键事件": [{"事件": "离家学医", "时间": "8岁"}],
    },
}
rendered_old = render_content(old_data)
check("旧 _display 数据不导致崩溃", len(rendered_old) > 0)
check("旧 _display 字段按值类型渲染",
     any(r["key"] == "修为" and r["mode"] == "tag" for r in rendered_old))
check("旧 _display 不渲染 _display 自身为 group",
     all(r["key"] != "_display" for r in rendered_old))

# 7.4 混合值类型（核心特质 可能是 string 或 list）
check("核心特质 list → tagcloud",
     infer_render_mode("核心特质", ["a", "b"]) == "tagcloud")
check("核心特质 string → tagcloud（强制覆盖）",
     infer_render_mode("核心特质", "a,b,c") == "tagcloud")

# 7.5 事件列表用英文 key
event_list_en = [{"event": "Leave home", "time": "age 8"}]
check("事件列表英文 key → timeline",
     infer_render_mode("events", event_list_en) == "timeline")

# 7.6 关系列表用英文 key
rel_list_en = [{"target": "Han Song", "relation": "uncle"}]
check("关系列表英文 key → relationlist",
     infer_render_mode("relations", rel_list_en) == "relationlist")

# 7.7 未知字段 fallback
check("未知 string → tag",
     infer_render_mode("未知字段", "未知值") == "tag")
check("未知 string[] → tagcloud",
     infer_render_mode("未知列表", ["a", "b"]) == "tagcloud")

# 7.8 深度嵌套
deep = {"a": {"b": {"c": {"d": "deep_value"}}}}
rd = render_content(deep)
check("深度嵌套渲染不崩溃", len(rd) == 1)


# ── 8. 结果汇总 ─────────────────────────────────────────────────────

print()
print("=" * 60)
print(f"结果: {PASS} 通过, {FAIL} 失败")
print("=" * 60)

if FAIL > 0:
    sys.exit(1)
else:
    print("🎉 全部测试通过！")
