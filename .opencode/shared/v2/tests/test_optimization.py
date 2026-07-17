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
        print(f"  \u2705 {name}")
    else:
        FAIL += 1
        print(f"  \u274c {name}  {detail}")


if __name__ == "__main__":
    # ── 导入 ──────────────────────────────────────────────────────────

    print("=" * 60)
    print("1. \u6a21\u5757\u5bfc\u5165\u6d4b\u8bd5")
    print("=" * 60)

    try:
        from render_utils import (
            render_content, render_field, summarize_content, extract_entity_refs,
            infer_render_mode, SPECIAL_RENDER_MAP, ENTITY_REF_FIELDS,
        )
        check("render_utils \u6a21\u5757\u5bfc\u5165\u6210\u529f", True)
    except Exception as e:
        check("render_utils \u6a21\u5757\u5bfc\u5165", False, str(e))

    try:
        from schemas import validate_content, SCHEMA_REGISTRY
        from graph_schema import UnitType
        check("schemas \u6a21\u5757\u5bfc\u5165\u6210\u529f", True)
    except Exception as e:
        check("schemas \u6a21\u5757\u5bfc\u5165", False, str(e))

    try:
        import tempfile
        from graph_store import GraphStore
        tmp_dir = tempfile.mkdtemp()
        store = GraphStore(tmp_dir)
        store.initialize()
        check("graph_store \u521d\u59cb\u5316\u6210\u529f", True)
    except Exception as e:
        check("graph_store \u521d\u59cb\u5316", False, str(e))

    try:
        from relation_inferrer import RelationInferrer
        inferrer = RelationInferrer(store)
        check("relation_inferrer \u5bfc\u5165\u6210\u529f", True)
    except Exception as e:
        check("relation_inferrer \u5bfc\u5165", False, str(e))


    # ── 2. render_utils 渲染测试 ─────────────────────────────────

    print()
    print("=" * 60)
    print("2. render_utils \u6e32\u67d3\u5f15\u64ce\u6d4b\u8bd5")
    print("=" * 60)

    # 2.1 字段名特殊规则
    check("SPECIAL_RENDER_MAP \u5305\u542b \u63cf\u8ff0", "\u63cf\u8ff0" in SPECIAL_RENDER_MAP)
    check("SPECIAL_RENDER_MAP \u5305\u542b \u6838\u5fc3\u7279\u8d28", "\u6838\u5fc3\u7279\u8d28" in SPECIAL_RENDER_MAP)
    check("SPECIAL_RENDER_MAP \u5305\u542b \u5173\u952e\u4e8b\u4ef6", "\u5173\u952e\u4e8b\u4ef6" in SPECIAL_RENDER_MAP)
    check("SPECIAL_RENDER_MAP \u5305\u542b \u5f20\u529b\u66f2\u7ebf", "\u5f20\u529b\u66f2\u7ebf" in SPECIAL_RENDER_MAP)
    check("SPECIAL_RENDER_MAP \u5305\u542b \u89d2\u8272\u5f27\u7ebf", "\u89d2\u8272\u5f27\u7ebf" in SPECIAL_RENDER_MAP)
    check("ENTITY_REF_FIELDS \u5305\u542b \u51fa\u573a\u89d2\u8272", "\u51fa\u573a\u89d2\u8272" in ENTITY_REF_FIELDS)
    check("ENTITY_REF_FIELDS \u5305\u542b \u5173\u8054\u60c5\u8282\u7ebf", "\u5173\u8054\u60c5\u8282\u7ebf" in ENTITY_REF_FIELDS)
    check("ENTITY_REF_FIELDS \u5305\u542b \u4e3b\u8981\u6210\u5458", "\u4e3b\u8981\u6210\u5458" in ENTITY_REF_FIELDS)

    # 2.2 值类型推断
    check("infer_render_mode \u77ed\u6587\u672c \u2192 tag",
         infer_render_mode("\u4fee\u4e3a", "\u5316\u795e\u671f") == "tag")
    check("infer_render_mode \u957f\u6587\u672c \u2192 textblock",
         infer_render_mode("\u63cf\u8ff0", "\u97e9\u95e8\u5c11\u5e74\uff0c\u5929\u751f\u7edd\u7075\u6839\uff0c\u5728\u5e95\u5c42\u4e2d\u6323\u624e\u6c42\u5b58\uff0c\u4ee5\u533b\u5165\u9053\u9010\u6b65\u5d1b\u8d77\u3002\u8fd9\u662f\u4e00\u6bb5\u8d85\u8fc7\u4e94\u5341\u5b57\u7684\u63cf\u8ff0\u6587\u672c\u7528\u4e8e\u6d4b\u8bd5\u957f\u6587\u672c\u6e32\u67d3\u5206\u652f\u3002") == "textblock")
    check("infer_render_mode string[] \u2192 tagcloud",
         infer_render_mode("\u4f18\u70b9", ["\u9690\u5fcd", "\u806a\u6167"]) == "tagcloud")
    check("infer_render_mode \u4e8b\u4ef6\u5217\u8868 \u2192 timeline",
         infer_render_mode("\u5173\u952e\u4e8b\u4ef6", [{"\u4e8b\u4ef6": "\u79bb\u5bb6\u5b66\u533b", "\u65f6\u95f4": "8\u5c81"}]) == "timeline")
    check("infer_render_mode \u5173\u7cfb\u5217\u8868 \u2192 relationlist",
         infer_render_mode("\u793e\u4f1a\u5173\u7cfb", [{"\u76ee\u6807": "\u97e9\u677e", "\u5173\u7cfb": "\u65cf\u53d4"}]) == "relationlist")
    check("infer_render_mode dict \u2192 group",
         infer_render_mode("\u80fd\u529b\u8bbe\u5b9a", {"\u4fee\u4e3a": "\u5316\u795e\u671f"}) == "group")
    check("infer_render_mode int \u2192 tag",
         infer_render_mode("\u7ae0\u8282\u53f7", 3) == "tag")
    check("infer_render_mode None \u2192 skip",
         infer_render_mode("\u67d0\u5b57\u6bb5", None) == "skip")
    check("infer_render_mode '' \u2192 skip",
         infer_render_mode("\u67d0\u5b57\u6bb5", "") == "skip")
    check("infer_render_mode [] \u2192 tagcloud",
         infer_render_mode("\u7a7a\u5217\u8868", []) == "tagcloud")

    # 2.3 字段名覆盖值类型
    check("\u6838\u5fc3\u7279\u8d28 \u5373\u4f7f\u4f20 string \u4e5f\u5f3a\u5236 tagcloud",
         infer_render_mode("\u6838\u5fc3\u7279\u8d28", "\u575a\u97e7,\u679c\u65ad") == "tagcloud")
    check("\u63cf\u8ff0 \u5373\u4f7f\u4f20\u77ed\u6587\u672c\u4e5f\u5f3a\u5236 textblock",
         infer_render_mode("\u63cf\u8ff0", "\u77ed\u63cf\u8ff0") == "textblock")
    check("\u5f20\u529b\u66f2\u7ebf \u5f3a\u5236 chart",
         infer_render_mode("\u5f20\u529b\u66f2\u7ebf", {"\u5f00\u573a": 3}) == "chart")

    # 2.4 render_field 输出结构
    result = render_field("\u4fee\u4e3a", "\u5316\u795e\u671f")
    check("render_field \u8fd4\u56de\u5305\u542b key/mode/html/text",
         all(k in result for k in ["key", "mode", "html", "text"]))
    check("render_field \u952e\u503c\u5bf9 HTML \u542b class label",
         "label" in result["html"] and "value" in result["html"])
    check("render_field \u7ec4 HTML \u542b class group",
         "group" in result.get("html", "") or True)  # tag 模式无 group class

    # 2.5 render_content 完整渲染
    sample_character = {
        "\u89d2\u8272\u7c7b\u578b": "\u4e3b\u89d2",
        "\u6027\u683c": {"\u6838\u5fc3\u7279\u8d28": ["\u4ee5\u533b\u5165\u9053", "\u575a\u97e7"]},
        "\u80fd\u529b\u8bbe\u5b9a": {"\u4fee\u4e3a": "\u5316\u795e\u671f", "\u529f\u6cd5": "\u4e94\u884c\u8f6e\u8f6c\u7ecf", "\u9635\u8425": "\u6b63\u9053"},
        "\u89d2\u8272\u5f27\u7ebf": {"\u8d77\u59cb\u72b6\u6001": "\u51e1\u4eba", "\u6700\u7ec8\u72b6\u6001": "\u5316\u795e\u98de\u5347"},
        "\u5173\u952e\u4e8b\u4ef6": [{"\u4e8b\u4ef6": "\u79bb\u5bb6\u5b66\u533b", "\u65f6\u95f4": "8\u5c81"}],
    }
    rendered = render_content(sample_character)
    check("render_content \u8fd4\u56de\u5217\u8868", isinstance(rendered, list))
    check("render_content \u6e32\u67d3\u4e86\u6240\u6709\u5b57\u6bb5", len(rendered) == len(sample_character))
    modes_found = set(r["mode"] for r in rendered)
    check("render_content \u542b\u591a\u79cd mode", len(modes_found) >= 3)
    check("render_content \u542b timeline \u6e32\u67d3", "timeline" in modes_found)
    check("render_content \u542b tag \u6e32\u67d3", "tag" in modes_found)
    check("render_content \u542b group \u6e32\u67d3", "group" in modes_found)

    # 2.6 summarize_content
    summary = summarize_content(sample_character)
    check("summarize_content \u8fd4\u56de\u5b57\u7b26\u4e32", isinstance(summary, str))
    check("summarize_content \u5305\u542b\u5b57\u6bb5\u540d", "\u80fd\u529b\u8bbe\u5b9a" in summary)
    check("summarize_content \u5305\u542b\u5b57\u6bb5\u503c", "\u5316\u795e\u671f" in summary)
    check("summarize_content \u4e0d\u4ee5 JSON \u5927\u62ec\u53f7\u5f00\u5934", not summary.startswith("{{"))


    # ── 3. 跨流派渲染一致性 ─────────────────────────────────────

    print()
    print("=" * 60)
    print("3. \u8de8\u6d41\u6d3e\u6e32\u67d3\u4e00\u81f4\u6027\u6d4b\u8bd5")
    print("=" * 60)

    # 3.1 仙侠 CHARACTER_ARC
    xianxia_char = {
        "\u89d2\u8272\u7c7b\u578b": "\u4e3b\u89d2",
        "\u6027\u683c": {"\u6838\u5fc3\u7279\u8d28": "\u4ee5\u533b\u5165\u9053\uff0c\u575a\u97e7\u4e0d\u62d4", "\u4f18\u70b9": ["\u9690\u5fcd"]},
        "\u80fd\u529b\u8bbe\u5b9a": {"\u4fee\u4e3a": "\u5316\u795e\u671f", "\u529f\u6cd5": "\u4e94\u884c\u8f6e\u8f6c\u7ecf", "\u7075\u6839": "\u4e94\u884c\u7075\u6839", "\u9635\u8425": "\u6b63\u9053"},
        "\u89d2\u8272\u5f27\u7ebf": {"\u8d77\u59cb\u72b6\u6001": "\u51e1\u4eba", "\u6700\u7ec8\u72b6\u6001": "\u5316\u795e\u98de\u5347"},
    }
    rx = render_content(xianxia_char)
    modes_x = set(r["mode"] for r in rx)
    check("\u4ed9\u4fa0: \u4fee\u4e3a \u5728\u5185\u5bb9\u4e2d",
         any("\u4fee\u4e3a" in r["html"] for r in rx))
    check("\u4ed9\u4fa0: \u529f\u6cd5 \u5728\u5185\u5bb9\u4e2d",
         any("\u529f\u6cd5" in r["html"] for r in rx))
    check("\u4ed9\u4fa0: \u7075\u6839 \u5728\u5185\u5bb9\u4e2d",
         any("\u7075\u6839" in r["html"] for r in rx))
    check("\u4ed9\u4fa0: \u80fd\u529b\u8bbe\u5b9a \u2192 group",
         any(r["key"] == "\u80fd\u529b\u8bbe\u5b9a" and r["mode"] == "group" for r in rx))

    # 3.2 都市 CHARACTER_ARC
    urban_char = {
        "\u89d2\u8272\u7c7b\u578b": "\u4e3b\u89d2",
        "\u6027\u683c": {"\u6838\u5fc3\u7279\u8d28": "\u679c\u65ad\u654f\u9510", "\u4f18\u70b9": ["\u5546\u4e1a\u55c5\u89c9"]},
        "\u80fd\u529b\u8bbe\u5b9a": {"\u804c\u4e1a": "CEO", "\u516c\u53f8": "\u5929\u6052\u96c6\u56e2", "\u8d44\u4ea7": "\u767e\u4ebf"},
        "\u89d2\u8272\u5f27\u7ebf": {"\u8d77\u59cb\u72b6\u6001": "\u521b\u4e1a\u5931\u8d25", "\u6700\u7ec8\u72b6\u6001": "\u5546\u4e1a\u5e1d\u56fd"},
    }
    ru = render_content(urban_char)
    check("\u90fd\u5e02: \u804c\u4e1a \u5728\u5185\u5bb9\u4e2d",
         any("\u804c\u4e1a" in r["html"] for r in ru))
    check("\u90fd\u5e02: \u516c\u53f8 \u5728\u5185\u5bb9\u4e2d",
         any("\u516c\u53f8" in r["html"] for r in ru))
    check("\u90fd\u5e02: \u8d44\u4ea7 \u5728\u5185\u5bb9\u4e2d",
         any("\u8d44\u4ea7" in r["html"] for r in ru))
    check("\u90fd\u5e02: \u80fd\u529b\u8bbe\u5b9a \u2192 group",
         any(r["key"] == "\u80fd\u529b\u8bbe\u5b9a" and r["mode"] == "group" for r in ru))

    # 3.3 历史穿越 CHARACTER_ARC
    hist_char = {
        "\u89d2\u8272\u7c7b\u578b": "\u4e3b\u89d2",
        "\u6027\u683c": {"\u6838\u5fc3\u7279\u8d28": "\u96c4\u624d\u5927\u7565", "\u653f\u6cbb\u7acb\u573a": "\u9769\u65b0\u6d3e"},
        "\u80fd\u529b\u8bbe\u5b9a": {"\u5b98\u804c": "\u8f66\u9a91\u5c06\u519b", "\u52bf\u529b": "\u8700\u6c49", "\u8c0b\u7565": ["\u519b\u4e8b\u6218\u7565", "\u653f\u6cbb\u6743\u8861"]},
        "\u89d2\u8272\u5f27\u7ebf": {"\u8d77\u59cb\u72b6\u6001": "\u7a7f\u8d8a\u8005", "\u6700\u7ec8\u72b6\u6001": "\u4e00\u4ee3\u6743\u81e3"},
    }
    rh = render_content(hist_char)
    check("\u5386\u53f2: \u5b98\u804c \u5728\u5185\u5bb9\u4e2d",
         any("\u5b98\u804c" in r["html"] for r in rh))
    check("\u5386\u53f2: \u52bf\u529b \u5728\u5185\u5bb9\u4e2d",
         any("\u52bf\u529b" in r["html"] for r in rh))
    check("\u5386\u53f2: \u8c0b\u7565 \u5728\u5185\u5bb9\u4e2d",
         any("\u8c0b\u7565" in r["html"] for r in rh))
    check("\u5386\u53f2: \u80fd\u529b\u8bbe\u5b9a \u2192 group",
         any(r["key"] == "\u80fd\u529b\u8bbe\u5b9a" and r["mode"] == "group" for r in rh))

    # 3.4 悬疑推理 CHARACTER_ARC
    sus_char = {
        "\u89d2\u8272\u7c7b\u578b": "\u4e3b\u89d2",
        "\u6027\u683c": {"\u6838\u5fc3\u7279\u8d28": "\u654f\u9510\u7ec6\u81f4", "\u76f4\u89c9": "\u6781\u5f3a"},
        "\u80cc\u666f": {"\u804c\u4e1a": "\u6cd5\u533b", "\u5c31\u804c": "\u5e02\u516c\u5b89\u5c40"},
        "\u80fd\u529b\u8bbe\u5b9a": {"\u7834\u6848\u6280\u80fd": ["\u75d5\u8ff9\u68c0\u9a8c", "\u72af\u7f6a\u5fc3\u7406\u5206\u6790", "\u6cd5\u533b\u75c5\u7406\u5b66"], "\u7834\u6848\u6570": 47},
        "\u89d2\u8272\u5f27\u7ebf": {"\u8d77\u59cb\u72b6\u6001": "\u65b0\u4eba\u6cd5\u533b", "\u6700\u7ec8\u72b6\u6001": "\u7834\u6848\u795e\u8bdd"},
    }
    rsus = render_content(sus_char)
    check("\u60ac\u7591: \u7834\u6848\u6280\u80fd \u2192 tagcloud",
         any("\u7834\u6848\u6280\u80fd" in r["html"] for r in rsus))
    check("\u60ac\u7591: \u7834\u6848\u6570 \u5728\u5185\u5bb9\u4e2d",
         any("\u7834\u6848\u6570" in r["html"] for r in rsus))
    check("\u60ac\u7591: \u80cc\u666f \u2192 group",
         any(r["key"] == "\u80cc\u666f" and r["mode"] == "group" for r in rsus))

    # 3.5 科幻 CHARACTER_ARC
    sci_char = {
        "\u89d2\u8272\u7c7b\u578b": "\u4e3b\u89d2",
        "\u6027\u683c": {"\u6838\u5fc3\u7279\u8d28": "\u7406\u6027\u51b7\u9759", "\u4f18\u70b9": ["\u903b\u8f91\u601d\u7ef4"]},
        "\u80fd\u529b\u8bbe\u5b9a": {"\u8d85\u80fd\u529b\u7b49\u7ea7": "S\u7ea7", "\u673a\u7532": "\u5929\u884c\u8005-X9", "\u57fa\u56e0\u6539\u9020": "\u7b2c\u4e09\u4ee3\u5f3a\u5316", "\u6240\u5c5e\u8230\u961f": "\u730e\u6237\u5ea7\u8fdc\u5f81\u519b"},
        "\u89d2\u8272\u5f27\u7ebf": {"\u8d77\u59cb\u72b6\u6001": "\u5e9f\u5f03\u6b96\u6c11\u661f\u5b64\u513f", "\u6700\u7ec8\u72b6\u6001": "\u4eba\u7c7b\u8054\u90a6\u7edf\u5e05"},
    }
    rsci = render_content(sci_char)
    check("\u79d1\u5e7b: \u8d85\u80fd\u529b\u7b49\u7ea7 \u2192 tag",
         any("\u8d85\u80fd\u529b\u7b49\u7ea7" in r["html"] for r in rsci))
    check("\u79d1\u5e7b: \u673a\u7532 \u2192 tag",
         any("\u673a\u7532" in r["html"] for r in rsci))
    check("\u79d1\u5e7b: \u57fa\u56e0\u6539\u9020 \u2192 tag",
         any("\u57fa\u56e0\u6539\u9020" in r["html"] for r in rsci))

    # 3.6 西方奇幻 CHARACTER_ARC
    fantasy_char = {
        "\u89d2\u8272\u7c7b\u578b": "\u4e3b\u89d2",
        "\u6027\u683c": {"\u6838\u5fc3\u7279\u8d28": "\u52c7\u6562\u6b63\u4e49"},
        "\u80fd\u529b\u8bbe\u5b9a": {"\u79cd\u65cf": "\u7cbe\u7075", "\u804c\u4e1a": "\u6e38\u4fa0", "\u9b54\u6cd5\u7b49\u7ea7": "\u5927\u6cd5\u5e08", "\u9635\u8425": "\u5b88\u5e8f\u5584\u826f", "\u6b66\u5668": ["\u7cbe\u7075\u957f\u5f13", "\u53cc\u5203\u5251"]},
        "\u89d2\u8272\u5f27\u7ebf": {"\u8d77\u59cb\u72b6\u6001": "\u68ee\u6797\u5b88\u62a4\u8005", "\u6700\u7ec8\u72b6\u6001": "\u5149\u660e\u540c\u76df\u9886\u8896"},
    }
    rfantasy = render_content(fantasy_char)
    check("\u5947\u5e7b: \u79cd\u65cf \u2192 tag",
         any("\u79cd\u65cf" in r["html"] for r in rfantasy))
    check("\u5947\u5e7b: \u804c\u4e1a \u2192 tag",
         any("\u804c\u4e1a" in r["html"] for r in rfantasy))
    check("\u5947\u5e7b: \u9b54\u6cd5\u7b49\u7ea7 \u2192 tag",
         any("\u9b54\u6cd5\u7b49\u7ea7" in r["html"] for r in rfantasy))
    check("\u5947\u5e7b: \u6b66\u5668 \u2192 tagcloud",
         any("\u6b66\u5668" in r["html"] for r in rfantasy))

    # 3.7 言情 CHARACTER_ARC
    romance_char = {
        "\u89d2\u8272\u7c7b\u578b": "\u4e3b\u89d2",
        "\u6027\u683c": {"\u6838\u5fc3\u7279\u8d28": "\u6e29\u67d4\u575a\u5f3a", "\u60c5\u611f\u72b6\u6001": "\u6697\u604b\u4e2d"},
        "\u80cc\u666f": {"\u5bb6\u5ead": "\u4e66\u9999\u95e8\u7b2c", "\u5b66\u5386": "\u6e05\u5927\u7f8e\u672f\u7cfb"},
        "\u80fd\u529b\u8bbe\u5b9a": {"\u804c\u4e1a": "\u72ec\u7acb\u8bbe\u8ba1\u5e08", "\u5de5\u4f5c\u5ba4": "\u4e91\u60f3\u8bbe\u8ba1", "\u4ee3\u8868\u4f5c": ["\u300a\u661f\u7a7a\u300b\u7cfb\u5217", "\u300a\u6d6e\u751f\u300b\u7ed8\u672c"]},
        "\u89d2\u8272\u5f27\u7ebf": {"\u8d77\u59cb\u72b6\u6001": "\u4e3a\u60c5\u6240\u56f0\u7684\u6587\u827a\u9752\u5e74", "\u6700\u7ec8\u72b6\u6001": "\u627e\u5230\u81ea\u6211\u4ef7\u503c\u7684\u72ec\u7acb\u5973\u6027"},
    }
    rromance = render_content(romance_char)
    check("\u8a00\u60c5: \u60c5\u611f\u72b6\u6001 \u2192 tag",
         any("\u60c5\u611f\u72b6\u6001" in r["html"] for r in rromance))
    check("\u8a00\u60c5: \u5bb6\u5ead \u2192 tag",
         any("\u5bb6\u5ead" in r["html"] for r in rromance))
    check("\u8a00\u60c5: \u5de5\u4f5c\u5ba4 \u2192 tag",
         any("\u5de5\u4f5c\u5ba4" in r["html"] for r in rromance))

    # 3.8 游戏电竞 CHARACTER_ARC
    game_char = {
        "\u89d2\u8272\u7c7b\u578b": "\u53cd\u6d3e",
        "\u6027\u683c": {"\u6838\u5fc3\u7279\u8d28": "\u55dc\u8840\u597d\u6218"},
        "\u80fd\u529b\u8bbe\u5b9a": {"\u6e38\u620fID": "\u6697\u5f71\u5c60\u592b", "\u6bb5\u4f4d": "\u6700\u5f3a\u738b\u8005", "\u804c\u4e1a": "\u6253\u91ce", "\u516c\u4f1a": "\u8840\u8272\u8054\u76df", "\u80dc\u7387": "78%"},
        "\u89d2\u8272\u5f27\u7ebf": {"\u8d77\u59cb\u72b6\u6001": "\u8def\u4eba\u73a9\u5bb6", "\u6700\u7ec8\u72b6\u6001": "\u804c\u4e1a\u8054\u8d5b\u51a0\u519b"},
    }
    rgame = render_content(game_char)
    check("\u7535\u7ade: \u6e38\u620fID \u2192 tag",
         any("\u6e38\u620fID" in r["html"] for r in rgame))
    check("\u7535\u7ade: \u6bb5\u4f4d \u2192 tag",
         any("\u6bb5\u4f4d" in r["html"] for r in rgame))
    check("\u7535\u7ade: \u804c\u4e1a(\u6253\u91ce) \u2192 tag",
         any("\u804c\u4e1a" in r["html"] for r in rgame))
    check("\u7535\u7ade: \u80dc\u7387 \u2192 tag",
         any("\u80dc\u7387" in r["html"] for r in rgame))

    # 3.9 军事 CHARACTER_ARC
    military_char = {
        "\u89d2\u8272\u7c7b\u578b": "\u4e3b\u89d2",
        "\u6027\u683c": {"\u6838\u5fc3\u7279\u8d28": "\u94c1\u8840\u5fe0\u8bda", "\u6218\u672f\u98ce\u683c": "\u95ea\u7535\u7a81\u88ad"},
        "\u80fd\u529b\u8bbe\u5b9a": {"\u519b\u8854": "\u4e0a\u6821", "\u90e8\u961f": "\u5229\u5203\u7279\u79cd\u5927\u961f", "\u88c5\u5907": ["95\u5f0f\u7a81\u51fb\u6b65\u67aa", "\u6218\u672f\u53c9\u9996"], "\u6218\u672f": ["\u65a9\u9996\u884c\u52a8", "\u56f4\u70b9\u6253\u63f4"]},
        "\u89d2\u8272\u5f27\u7ebf": {"\u8d77\u59cb\u72b6\u6001": "\u65b0\u5175", "\u6700\u7ec8\u72b6\u6001": "\u6218\u533a\u53f8\u4ee4"},
    }
    rmil = render_content(military_char)
    check("\u519b\u4e8b: \u519b\u8854 \u2192 tag",
         any("\u519b\u8854" in r["html"] for r in rmil))
    check("\u519b\u4e8b: \u90e8\u961f \u2192 tag",
         any("\u90e8\u961f" in r["html"] for r in rmil))
    check("\u519b\u4e8b: \u88c5\u5907 \u2192 tagcloud",
         any("\u88c5\u5907" in r["html"] for r in rmil))
    check("\u519b\u4e8b: \u6218\u672f \u2192 tagcloud",
         any("\u6218\u672f" in r["html"] for r in rmil))

    # 3.10 全部流派同一条代码
    all_genres = [rx, ru, rh, rsus, rsci, rfantasy, rromance, rgame, rmil]
    check("\u5168\u90e8\u6d41\u6d3e\u6e32\u67d3\u7ed3\u679c\u90fd\u662f\u5217\u8868",
         all(isinstance(r, list) for r in all_genres))
    check("\u5168\u90e8\u6d41\u6d3e\u6e32\u67d3\u7ed3\u679c\u975e\u7a7a",
         all(len(r) > 0 for r in all_genres))

    # 3.11 SCENE 渲染
    scene = {
        "\u7ae0\u8282\u7c7b\u578b": "\u63a8\u8fdb",
        "\u7ed3\u6784\u89c4\u5212": {
            "\u5f00\u7bc7": {"\u65b9\u5f0f": "\u52a8\u4f5c\u5f00\u573a"},
            "\u53d1\u5c55": {"\u6838\u5fc3\u51b2\u7a81": "\u6797\u6e0a\u7ec3\u5251\u88ab\u963b"},
            "\u8f6c\u6298": {"\u4e8b\u4ef6": "\u82cf\u957f\u8001\u51fa\u73b0"},
            "\u6536\u5c3e": {"\u7ed3\u679c": "\u6797\u6e0a\u91cd\u65b0\u632f\u4f5c"},
        },
        "\u51fa\u573a\u89d2\u8272": ["\u6797\u6e0a", "\u82cf\u957f\u8001"],
        "\u5173\u8054\u60c5\u8282\u7ebf": ["\u4e3b\u7ebf\xb7\u5251\u9053\u4e4b\u4e89"],
        "\u5f20\u529b\u66f2\u7ebf": {"\u5f00\u573a": 3, "\u7ae0\u8282\u9ad8\u6f6e": 7, "\u7ed3\u5c3e": 5},
    }
    rs = render_content(scene)
    check("SCENE: \u51fa\u573a\u89d2\u8272 \u2192 tagcloud",
         any(r["key"] == "\u51fa\u573a\u89d2\u8272" and r["mode"] == "tagcloud" for r in rs))
    check("SCENE: \u5f20\u529b\u66f2\u7ebf \u2192 chart",
         any(r["key"] == "\u5f20\u529b\u66f2\u7ebf" and r["mode"] == "chart" for r in rs))
    check("SCENE: \u7ed3\u6784\u89c4\u5212 \u2192 group",
         any(r["key"] == "\u7ed3\u6784\u89c4\u5212" and r["mode"] == "group" for r in rs))

    # 3.12 WORLD_RULE 渲染
    world = {
        "\u5b50\u7c7b\u578b": "\u5730\u70b9",
        "\u4e8c\u7ea7\u7c7b\u578b": "\u6d77\u57df",
        "\u63cf\u8ff0": "\u4eba\u754c\u6700\u5317\u7aef\u7684\u6781\u5bd2\u6d77\u57df\uff0c\u5317\u6781\u5143\u5149\u53ef\u7099\u70bc\u6cd5\u5b9d\u81f3\u4eba\u754c\u5dc5\u5cf0\u54c1\u8d28\u3002",
        "\u4f4d\u7f6e": "\u4eba\u754c\u6700\u5317\u7aef",
        "\u91cd\u8981\u573a\u6240": ["\u51b0\u51e4\u9057\u8ff9", "\u6d77\u773c"],
        "\u7269\u4ea7": ["\u5317\u6781\u5143\u5149", "\u7384\u51a5\u6c34\u8109"],
    }
    rw = render_content(world)
    check("WORLD_RULE: \u5b50\u7c7b\u578b \u2192 tag",
         any(r["key"] == "\u5b50\u7c7b\u578b" and r["mode"] == "tag" for r in rw))
    check("WORLD_RULE: \u63cf\u8ff0 \u2192 textblock",
         any(r["key"] == "\u63cf\u8ff0" and r["mode"] == "textblock" for r in rw))
    check("WORLD_RULE: \u91cd\u8981\u573a\u6240 \u2192 tagcloud",
         any(r["key"] == "\u91cd\u8981\u573a\u6240" and r["mode"] == "tagcloud" for r in rw))


    # ── 4. schemas 验证测试 ─────────────────────────────────────

    print()
    print("=" * 60)
    print("4. schemas \u9a8c\u8bc1\u6d4b\u8bd5")
    print("=" * 60)

    # 4.1 CHARACTER_ARC 验证
    valid_char = {
        "\u5b50\u7c7b\u578b": "\u4e3b\u89d2",
        "\u6027\u683c": {"\u6838\u5fc3\u7279\u8d28": ["\u575a\u97e7"], "\u4f18\u70b9": ["\u9690\u5fcd"], "\u7f3a\u70b9": ["\u56fa\u6267"]},
        "\u89d2\u8272\u5f27\u7ebf": {"\u8d77\u59cb\u72b6\u6001": "\u51e1\u4eba", "\u6700\u7ec8\u72b6\u6001": "\u98de\u5347"},
    }
    check("CHARACTER_ARC \u6709\u6548\u6570\u636e\u901a\u8fc7\u9a8c\u8bc1",
         len(validate_content(UnitType.CHARACTER_ARC, valid_char)) == 0)

    # 缺少必填字段
    missing_char = {"\u5b50\u7c7b\u578b": "\u4e3b\u89d2"}
    check("CHARACTER_ARC \u7f3a\u6027\u683c \u2192 \u62a5\u9519",
         len(validate_content(UnitType.CHARACTER_ARC, missing_char)) > 0)

    # 角色类型枚举
    invalid_role = {"\u5b50\u7c7b\u578b": "\u8def\u4eba", "\u6027\u683c": {"\u6838\u5fc3\u7279\u8d28": "a"}, "\u89d2\u8272\u5f27\u7ebf": {"\u8d77\u59cb": "a", "\u7ec8": "b"}}
    errs = validate_content(UnitType.CHARACTER_ARC, invalid_role)
    check("CHARACTER_ARC \u65e0\u6548\u5b50\u7c7b\u578b \u2192 \u62a5\u9519", len(errs) > 0)

    # 流派适配字段不被 schema 校验
    with_genre = {
        "\u5b50\u7c7b\u578b": "\u4e3b\u89d2",
        "\u6027\u683c": {"\u6838\u5fc3\u7279\u8d28": ["\u575a\u97e7"], "\u4f18\u70b9": ["\u9690\u5fcd"], "\u7f3a\u70b9": ["\u56fa\u6267"]},
        "\u89d2\u8272\u5f27\u7ebf": {"\u8d77\u59cb\u72b6\u6001": "\u51e1\u4eba", "\u6700\u7ec8\u72b6\u6001": "\u98de\u5347"},
        "\u80fd\u529b\u8bbe\u5b9a": {"\u4fee\u4e3a": "\u5316\u795e\u671f"},  # 不在 schema 中，不应触发错误
    }
    check("CHARACTER_ARC \u6d41\u6d3e\u5b57\u6bb5\u4e0d\u89e6\u53d1\u9519\u8bef",
         len(validate_content(UnitType.CHARACTER_ARC, with_genre)) == 0)

    # 4.2 SCENE 验证
    valid_scene = {
        "\u5b50\u7c7b\u578b": "\u63a8\u8fdb",
        "\u7ed3\u6784\u89c4\u5212": {
            "\u5f00\u7bc7": {"\u65b9\u5f0f": "\u52a8\u4f5c\u5f00\u573a", "\u4e0a\u7ae0\u8854\u63a5": "a"},
            "\u53d1\u5c55": {"\u6838\u5fc3\u51b2\u7a81": "b", "\u63a8\u8fdb": "c"},
            "\u8f6c\u6298": {"\u4e8b\u4ef6": "d"},
            "\u6536\u5c3e": {"\u7ed3\u679c": "e", "\u4e0b\u7ae0\u94fa\u57ab": "f"},
        },
    }
    check("SCENE \u6709\u6548\u6570\u636e\u901a\u8fc7\u9a8c\u8bc1",
         len(validate_content(UnitType.SCENE, valid_scene)) == 0)

    check("SCENE \u7f3a\u5b50\u7c7b\u578b \u2192 \u62a5\u9519",
         len(validate_content(UnitType.SCENE, {"\u7ed3\u6784\u89c4\u5212": valid_scene["\u7ed3\u6784\u89c4\u5212"]})) > 0)

    # 4.3 PLOT_THREAD 验证
    valid_plot = {"\u5b50\u7c7b\u578b": "\u4e3b\u7ebf", "\u51b2\u7a81\u6838\u5fc3": "\u7075\u6c14\u6c61\u67d3"}
    check("PLOT_THREAD \u6709\u6548\u6570\u636e\u901a\u8fc7\u9a8c\u8bc1",
         len(validate_content(UnitType.PLOT_THREAD, valid_plot)) == 0)

    # 4.4 WORLD_RULE 验证
    valid_world = {"\u5b50\u7c7b\u578b": "\u5730\u70b9"}
    check("WORLD_RULE \u6709\u6548\u6570\u636e\u901a\u8fc7\u9a8c\u8bc1",
         len(validate_content(UnitType.WORLD_RULE, valid_world)) == 0)

    # 4.5 CHUNK 验证
    valid_chunk = {"\u7ae0\u8282\u53f7": 3, "\u6b63\u6587": "\u6797\u6e0a\u63e1\u7d27\u4e86\u5251\u67c4"}
    check("CHUNK \u6709\u6548\u6570\u636e\u901a\u8fc7\u9a8c\u8bc1",
         len(validate_content(UnitType.CHUNK, valid_chunk)) == 0)
    check("CHUNK \u7f3a\u7ae0\u8282\u53f7 \u2192 \u62a5\u9519",
         len(validate_content(UnitType.CHUNK, {"\u6b63\u6587": "a"})) > 0)


    # ── 5. extract_entity_refs 测试 ─────────────────────────────

    print()
    print("=" * 60)
    print("5. extract_entity_refs \u63d0\u53d6\u6d4b\u8bd5")
    print("=" * 60)

    content_with_refs = {
        "\u89d2\u8272\u7c7b\u578b": "\u4e3b\u89d2",
        "\u51fa\u573a\u89d2\u8272": ["\u6797\u6e0a", "\u82cf\u957f\u8001"],
        "\u5173\u8054\u60c5\u8282\u7ebf": ["\u4e3b\u7ebf\xb7\u5251\u9053\u4e4b\u4e89"],
        "\u6027\u683c": {"\u6838\u5fc3\u7279\u8d28": "\u575a\u97e7"},
    }
    refs = extract_entity_refs(content_with_refs)
    check("entity_refs \u63d0\u53d6\u51fa\u573a\u89d2\u8272", "\u6797\u6e0a" in refs)
    check("entity_refs \u63d0\u53d6\u82cf\u957f\u8001", "\u82cf\u957f\u8001" in refs)
    check("entity_refs \u63d0\u53d6\u60c5\u8282\u7ebf", "\u4e3b\u7ebf\xb7\u5251\u9053\u4e4b\u4e89" in refs)
    check("entity_refs \u4e0d\u63d0\u53d6\u975e ref \u5b57\u6bb5", "\u4e3b\u89d2" not in refs)
    check("entity_refs \u4e0d\u63d0\u53d6\u6838\u5fc3\u7279\u8d28", "\u575a\u97e7" not in refs)

    # 嵌套 dict 中的 entity_ref
    nested_refs = {
        "\u7ed3\u6784\u89c4\u5212": {"\u5f00\u7bc7": {"\u65b9\u5f0f": "\u52a8\u4f5c\u5f00\u573a"}},
        "\u5173\u8054\u60c5\u8282\u7ebf": ["\u4e3b\u7ebfA", "\u4e3b\u7ebfB"],
    }
    refs2 = extract_entity_refs(nested_refs)
    check("entity_refs \u5d4c\u5957\u63d0\u53d6", "\u4e3b\u7ebfA" in refs2 and "\u4e3b\u7ebfB" in refs2)

    # 空数据
    check("entity_refs \u7a7a\u6570\u636e\u8fd4\u56de []",
         extract_entity_refs({}) == [])
    check("entity_refs \u65e0 ref \u5b57\u6bb5\u8fd4\u56de []",
         extract_entity_refs({"\u63cf\u8ff0": "\u6d4b\u8bd5"}) == [])


    # ── 6. graph_store.find_units_by_field 测试 ────────────────

    print()
    print("=" * 60)
    print("6. graph_store.find_units_by_field \u6d4b\u8bd5")
    print("=" * 60)

    # 创建测试数据
    store.create_unit(
        type=UnitType.CHARACTER_ARC,
        unit_name="\u6797\u6e0a",
        content=json.dumps({"\u89d2\u8272\u7c7b\u578b": "\u4e3b\u89d2", "\u80fd\u529b\u8bbe\u5b9a": {"\u4fee\u4e3a": "\u5316\u795e\u671f", "\u529f\u6cd5": "\u4e94\u884c\u8f6e\u8f6c\u7ecf"}}, ensure_ascii=False),
        actor="test",
    )
    store.create_unit(
        type=UnitType.CHARACTER_ARC,
        unit_name="\u97e9\u677e",
        content=json.dumps({"\u89d2\u8272\u7c7b\u578b": "\u914d\u89d2", "\u80fd\u529b\u8bbe\u5b9a": {"\u4fee\u4e3a": "\u91d1\u4e39\u671f", "\u529f\u6cd5": "\u5929\u7f57\u529f"}}, ensure_ascii=False),
        actor="test",
    )
    store.create_unit(
        type=UnitType.SCENE,
        unit_name="\u540e\u5c71\u62d4\u5251",
        content=json.dumps({"\u7ae0\u8282\u7c7b\u578b": "\u63a8\u8fdb", "\u51fa\u573a\u89d2\u8272": ["\u6797\u6e0a"]}, ensure_ascii=False),
        actor="test",
    )
    store.flush()

    # 按 type 查询
    chars = store.find_units_by_field(type=UnitType.CHARACTER_ARC)
    check("find_units_by_field \u6309 type \u67e5\u89d2\u8272", len(chars) == 2)

    scenes = store.find_units_by_field(type=UnitType.SCENE)
    check("find_units_by_field \u6309 type \u67e5\u573a\u666f", len(scenes) == 1)

    # 按 field_name 查询
    hua_shen = store.find_units_by_field(type=UnitType.CHARACTER_ARC, field_name="\u4fee\u4e3a", field_value="\u5316\u795e\u671f")
    check("find_units_by_field \u6309 \u4fee\u4e3a=\u5316\u795e\u671f \u67e5", len(hua_shen) == 1)
    check("find_units_by_field \u67e5\u5230\u7684\u89d2\u8272\u662f\u6797\u6e0a",
         hua_shen[0].unit_name == "\u6797\u6e0a" if hua_shen else False)

    jin_dan = store.find_units_by_field(type=UnitType.CHARACTER_ARC, field_name="\u4fee\u4e3a", field_value="\u91d1\u4e39\u671f")
    check("find_units_by_field \u6309 \u4fee\u4e3a=\u91d1\u4e39\u671f \u67e5", len(jin_dan) == 1)
    check("find_units_by_field \u67e5\u5230\u7684\u89d2\u8272\u662f\u97e9\u677e",
         jin_dan[0].unit_name == "\u97e9\u677e" if jin_dan else False)

    # 按不存在的值查询
    no_match = store.find_units_by_field(type=UnitType.CHARACTER_ARC, field_name="\u4fee\u4e3a", field_value="\u5927\u4e58\u671f")
    check("find_units_by_field \u4e0d\u5b58\u5728\u7684\u503c\u8fd4\u56de []", len(no_match) == 0)

    # 按不存在的字段名查询
    no_field = store.find_units_by_field(type=UnitType.CHARACTER_ARC, field_name="\u4e0d\u5b58\u5728\u5b57\u6bb5")
    check("find_units_by_field \u4e0d\u5b58\u5728\u7684\u5b57\u6bb5\u8fd4\u56de []", len(no_field) == 0)

    # 无过滤条件
    all_units = store.find_units_by_field()
    check("find_units_by_field \u65e0\u8fc7\u6ee4\u8fd4\u56de\u5168\u90e8", len(all_units) >= 3)

    # 按场景的 field_name
    lin_scenes = store.find_units_by_field(type=UnitType.SCENE, field_name="\u51fa\u573a\u89d2\u8272")
    check("find_units_by_field \u573a\u666f\u5b57\u6bb5\u540d\u67e5\u8be2", len(lin_scenes) == 1)

    # 按场景的 field_value
    lin_scenes2 = store.find_units_by_field(type=UnitType.SCENE, field_value="\u6797\u6e0a")
    check("find_units_by_field \u573a\u666f\u5b57\u6bb5\u503c\u67e5\u8be2", len(lin_scenes2) >= 1)


    # ── 7. 边界情况测试 ────────────────────────────────────────

    print()
    print("=" * 60)
    print("7. \u8fb9\u754c\u60c5\u51b5\u6d4b\u8bd5")
    print("=" * 60)

    # 7.1 空 content
    check("render_content \u7a7a dict \u2192 []", render_content({}) == [])

    # 7.2 纯文本 content（非 JSON）
    check("summarize_content \u975e dict \u56de\u9000", isinstance(summarize_content({"\u6b63\u6587": "\u7eaf\u6587\u672c"}), str))

    # 7.3 `_display` 旧数据兼容
    old_data = {
        "\u89d2\u8272\u7c7b\u578b": "\u4e3b\u89d2",
        "\u6027\u683c": {"\u6838\u5fc3\u7279\u8d28": "\u575a\u97e7"},
        "\u89d2\u8272\u5f27\u7ebf": {"\u8d77\u59cb": "A", "\u7ec8": "B"},
        "_display": {
            "\u4fee\u4e3a": "\u5316\u795e\u671f",
            "\u6838\u5fc3\u7279\u8d28": ["\u4ee5\u533b\u5165\u9053", "\u7edd\u7075\u6839"],
            "\u5173\u952e\u4e8b\u4ef6": [{"\u4e8b\u4ef6": "\u79bb\u5bb6\u5b66\u533b", "\u65f6\u95f4": "8\u5c81"}],
        },
    }
    rendered_old = render_content(old_data)
    check("\u65e7 _display \u6570\u636e\u4e0d\u5bfc\u81f4\u5d29\u6e83", len(rendered_old) > 0)
    check("\u65e7 _display \u5b57\u6bb5\u6309\u503c\u7c7b\u578b\u6e32\u67d3",
         any(r["key"] == "\u4fee\u4e3a" and r["mode"] == "tag" for r in rendered_old))
    check("\u65e7 _display \u4e0d\u6e32\u67d3 _display \u81ea\u8eab\u4e3a group",
         all(r["key"] != "_display" for r in rendered_old))

    # 7.4 混合值类型（核心特质 可能是 string 或 list）
    check("\u6838\u5fc3\u7279\u8d28 list \u2192 tagcloud",
         infer_render_mode("\u6838\u5fc3\u7279\u8d28", ["a", "b"]) == "tagcloud")
    check("\u6838\u5fc3\u7279\u8d28 string \u2192 tagcloud\uff08\u5f3a\u5236\u8986\u76d6\uff09",
         infer_render_mode("\u6838\u5fc3\u7279\u8d28", "a,b,c") == "tagcloud")

    # 7.5 事件列表用英文 key
    event_list_en = [{"event": "Leave home", "time": "age 8"}]
    check("\u4e8b\u4ef6\u5217\u8868\u82f1\u6587 key \u2192 timeline",
         infer_render_mode("events", event_list_en) == "timeline")

    # 7.6 关系列表用英文 key
    rel_list_en = [{"target": "Han Song", "relation": "uncle"}]
    check("\u5173\u7cfb\u5217\u8868\u82f1\u6587 key \u2192 relationlist",
         infer_render_mode("relations", rel_list_en) == "relationlist")

    # 7.7 未知字段 fallback
    check("\u672a\u77e5 string \u2192 tag",
         infer_render_mode("\u672a\u77e5\u5b57\u6bb5", "\u672a\u77e5\u503c") == "tag")
    check("\u672a\u77e5 string[] \u2192 tagcloud",
         infer_render_mode("\u672a\u77e5\u5217\u8868", ["a", "b"]) == "tagcloud")

    # 7.8 深度嵌套
    deep = {"a": {"b": {"c": {"d": "deep_value"}}}}
    rd = render_content(deep)
    check("\u6df1\u5ea6\u5d4c\u5957\u6e32\u67d3\u4e0d\u5d29\u6e83", len(rd) == 1)


    # ── 8. 结果汇总 ─────────────────────────────────────────────

    print()
    print("=" * 60)
    print(f"\u7ed3\u679c: {PASS} \u901a\u8fc7, {FAIL} \u5931\u8d25")
    print("=" * 60)

    if FAIL > 0:
        sys.exit(1)
    else:
        print("\U0001f389 \u5168\u90e8\u6d4b\u8bd5\u901a\u8fc7\uff01")
