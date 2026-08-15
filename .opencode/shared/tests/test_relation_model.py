"""
关系系统优化方案（docs/关系系统优化方案.md）核心测试。

覆盖：
- auto_reverse 三态（A/B/C 分类）
- role 端点模型（source_role/target_role 跟随端点翻转）
- handle_add_relation bidirectional 三态行为
- handle_fix_asymmetry 仅补 always 类型
- 非枚举降级（REFERENCES → RELATES_TO）
- 声明驱动建边（entity_reference rel_type）
- role 过滤查询
- 旧数据兼容性

注意：call_tool 每次调用创建新的 GraphStore 实例（无跨调用缓存），
因此写操作与读操作统一走 call_tool，不混用 fixture 的 store 实例。
"""

import json

import pytest

from conftest import call_tool, assert_success


# ── 1. auto_reverse 三态 ─────────────────────────────────────────

def test_auto_reverse_a_class_symmetric():
    """A 类（对称语义）：CONTRADICTS/PARALLEL/RELATES_TO/PARTICIPATES_IN/INVOLVES 自翻。"""
    from graph_schema import RelationType
    a_class = [
        RelationType.CONTRADICTS, RelationType.PARALLEL, RelationType.RELATES_TO,
        RelationType.PARTICIPATES_IN, RelationType.INVOLVES,
    ]
    for rt in a_class:
        assert rt.auto_reverse == "always", f"{rt} 应为 always"
        assert rt.inverse == rt, f"{rt} 应为自反类型"


def test_auto_reverse_b_class_pair():
    """B 类（配对类型）：MEMBER_OF/POSSESSES/CONTROLS/LOCATED_AT/HAS_EVENT/PLANS 自翻为 inverse。"""
    from graph_schema import RelationType
    b_pairs = [
        (RelationType.MEMBER_OF, RelationType.HAS_MEMBER),
        (RelationType.POSSESSES, RelationType.POSSESSED_BY),
        (RelationType.CONTROLS, RelationType.CONTROLLED_BY),
        (RelationType.LOCATED_AT, RelationType.LOCATION_OF),
        (RelationType.HAS_EVENT, RelationType.EVENT_OF),
        (RelationType.PLANS, RelationType.PLANNED_BY),
    ]
    for rt, inv in b_pairs:
        assert rt.auto_reverse == "always", f"{rt} 应为 always"
        assert rt.inverse == inv, f"{rt}.inverse 应为 {inv}"


def test_auto_reverse_optional_hierarchy():
    """层级 CONTAINS/BELONGS_TO 为 optional（默认不自动补）。"""
    from graph_schema import RelationType
    for rt in (RelationType.CONTAINS, RelationType.BELONGS_TO):
        assert rt.auto_reverse == "optional", f"{rt} 应为 optional"


def test_auto_reverse_never_one_way():
    """C 类（单向断言）：CAUSES/PRECEDES/IMPLEMENTS/REFERENCES/IMPLIES/INSPIRES/REFINES 禁止自翻。"""
    from graph_schema import RelationType
    c_class = [
        RelationType.CAUSES, RelationType.PRECEDES, RelationType.IMPLEMENTS,
        RelationType.REFERENCES, RelationType.IMPLIES, RelationType.INSPIRES,
        RelationType.REFINES,
    ]
    for rt in c_class:
        assert rt.auto_reverse == "never", f"{rt} 应为 never"


# ── 2. role 端点模型（store 层）──────────────────────────────────

def test_add_relation_with_roles(store):
    """add_relation 透传 source_role/target_role。"""
    from graph_schema import UnitType, RelationType
    lin = store.create_unit(type=UnitType.CHARACTER_ARC, unit_name="林渊", content="{}", actor="novel-v2-crafter")
    han = store.create_unit(type=UnitType.CHARACTER_ARC, unit_name="韩致", content="{}", actor="novel-v2-crafter")
    rel = store.add_relation(lin.id, han.id, RelationType.RELATES_TO,
                             source_role="师傅", target_role="徒弟", actor="novel-v2-crafter")
    assert rel is not None
    assert rel.source_role == "师傅"
    assert rel.target_role == "徒弟"


# ── 3. bidirectional 三态（handler 层，全 call_tool）──────────────

def _create_char(tmp_project, name):
    """通过 call_tool 创建角色，返回其 id。"""
    proj_path, _ = tmp_project
    res = call_tool("graph.create_unit", project=proj_path, unit_type="character_arc",
                    name=name, content='{"角色":"测试角色"}', actor="novel-v2-crafter")
    assert_success(res)
    return res["data"]["id"]


def test_bidirectional_a_class_role_swap(tmp_project):
    """A 类 bidirectional：反向同类型 + role 跟随端点（交换）。"""
    proj_path, _ = tmp_project
    lin = _create_char(tmp_project, "林渊")
    han = _create_char(tmp_project, "韩致")
    res = call_tool("graph.add_relation", project=proj_path,
                    source=lin, target=han,
                    rel_type="relates_to", source_role="师傅", target_role="徒弟",
                    bidirectional=True, actor="novel-v2-crafter")
    assert_success(res)
    assert res["data"]["inverse_id"] is not None

    # 查韩致（原 target）的 outgoing 边——应包含反向边
    rev = call_tool("graph.get_relations", project=proj_path, id=han, direction="outgoing")
    assert_success(rev)
    inv = [r for r in rev["data"]["relations"] if r["target_id"] == lin]
    assert inv, f"期望反向边 韩致→林渊，实际: {rev['data']['relations']}"
    assert inv[0]["type"] == "relates_to"
    # role 跟随端点：韩致 是徒弟（原 target_role），林渊 是师傅（原 source_role）
    assert inv[0]["source_role"] == "徒弟"
    assert inv[0]["target_role"] == "师傅"


def test_bidirectional_b_class_inverse_type(tmp_project):
    """B 类 bidirectional：反向为 inverse 类型 + role 跟随端点。"""
    proj_path, _ = tmp_project
    lin = _create_char(tmp_project, "林渊")
    wr = call_tool("graph.create_unit", project=proj_path, unit_type="world_rule",
                   name="落云宗", content='{"subtype":"势力"}', actor="novel-v2-crafter")
    assert_success(wr)
    wr_id = wr["data"]["id"]

    res = call_tool("graph.add_relation", project=proj_path,
                    source=lin, target=wr_id,
                    rel_type="member_of", source_role="弟子",
                    bidirectional=True, actor="novel-v2-crafter")
    assert_success(res)
    assert res["data"]["inverse_id"] is not None

    rev = call_tool("graph.get_relations", project=proj_path, id=wr_id, direction="outgoing")
    assert_success(rev)
    inv = [r for r in rev["data"]["relations"] if r["target_id"] == lin]
    assert inv, f"期望反向边 落云宗→林渊，实际: {rev['data']['relations']}"
    assert inv[0]["type"] == "has_member"
    # role 跟随端点：林渊 作为反向边 target，携带原 source_role（弟子）
    assert inv[0]["target_role"] == "弟子"
    assert inv[0]["source_role"] == ""  # 落云宗 作为反向边 source，原 target_role 为空


def test_bidirectional_c_class_never(tmp_project):
    """C 类 bidirectional：不建反向边，返回 warning。"""
    proj_path, _ = tmp_project
    # 创建场景（后山拔剑）与情节线（主线）
    sc = call_tool("graph.create_unit", project=proj_path, unit_type="scene",
                   name="后山拔剑",
                   content='{"subtype":"开篇","synopsis":"拔剑","pov_character":"林渊",'
                            '"one_line_summary":"后山拔剑","location":"落云宗"}',
                    actor="novel-v2-crafter")
    assert_success(sc)
    pt = call_tool("graph.create_unit", project=proj_path, unit_type="plot_thread",
                   name="主线-剑道之争", content='{"类型":"主线"}', actor="novel-v2-crafter")
    assert_success(pt)

    res = call_tool("graph.add_relation", project=proj_path,
                    source=sc["data"]["id"], target=pt["data"]["id"],
                    rel_type="implements", bidirectional=True,
                    actor="novel-v2-crafter")
    assert_success(res)
    assert "inverse_id" not in res["data"]
    assert "warning" in res["data"]
    assert "单向断言" in res["data"]["warning"]


def test_bidirectional_c_class_causes(tmp_project):
    """CAUSES bidirectional 不产生反向边（修复旧 fix_asymmetry 制造错误边）。"""
    proj_path, _ = tmp_project
    sc = call_tool("graph.create_unit", project=proj_path, unit_type="scene",
                   name="坠崖", content='{"subtype":"冲突","synopsis":"坠崖","pov_character":"林渊",'
                                          '"one_line_summary":"坠崖","location":"崖底"}',
                    actor="novel-v2-crafter")
    assert_success(sc)
    pt = call_tool("graph.create_unit", project=proj_path, unit_type="plot_thread",
                   name="得传承", content='{"类型":"主线"}', actor="novel-v2-crafter")
    assert_success(pt)

    res = call_tool("graph.add_relation", project=proj_path,
                    source=sc["data"]["id"], target=pt["data"]["id"],
                    rel_type="causes", bidirectional=True,
                    actor="novel-v2-crafter", override=True)
    assert_success(res)
    assert "inverse_id" not in res["data"]

    # 得传承 → 坠崖 的反向边不应存在
    rev = call_tool("graph.get_relations", project=proj_path,
                    id=pt["data"]["id"], direction="outgoing")
    assert_success(rev)
    inv = [r for r in rev["data"]["relations"]
           if r["target_id"] == sc["data"]["id"] and r["type"] == "causes"]
    assert not inv, f"CAUSES 不应有反向边，实际: {inv}"


# ── 4. fix_asymmetry 三态过滤 ────────────────────────────────────

def test_fix_asymmetry_skips_never_types(tmp_project):
    """fix_asymmetry 不补 C 类（never）反向边。"""
    proj_path, _ = tmp_project
    a = _create_char(tmp_project, "甲")
    b = _create_char(tmp_project, "乙")
    res = call_tool("graph.add_relation", project=proj_path,
                    source=a, target=b, rel_type="causes",
                    actor="novel-v2-crafter", override=True)
    assert_success(res)

    res = call_tool("graph.fix_asymmetry", project=proj_path)
    assert_success(res)
    assert res["data"]["created"] == 0

    rev = call_tool("graph.get_relations", project=proj_path, id=b, direction="outgoing")
    assert_success(rev)
    inv = [r for r in rev["data"]["relations"]
           if r["target_id"] == a and r["type"] == "causes"]
    assert not inv, f"CAUSES 不应被 fix_asymmetry 补反向，实际: {inv}"


def test_fix_asymmetry_creates_always_reverse(tmp_project):
    """fix_asymmetry 补 A 类（always）缺失反向边，role 跟随端点。"""
    proj_path, _ = tmp_project
    a = _create_char(tmp_project, "甲")
    b = _create_char(tmp_project, "乙")
    res = call_tool("graph.add_relation", project=proj_path,
                    source=a, target=b, rel_type="relates_to",
                    source_role="师傅", target_role="徒弟",
                    actor="novel-v2-crafter")
    assert_success(res)

    res = call_tool("graph.fix_asymmetry", project=proj_path)
    assert_success(res)
    assert res["data"]["created"] == 1

    rev = call_tool("graph.get_relations", project=proj_path, id=b, direction="outgoing")
    assert_success(rev)
    inv = [r for r in rev["data"]["relations"]
           if r["target_id"] == a and r["type"] == "relates_to"]
    assert inv, f"期望 fix_asymmetry 补反向边，实际: {rev['data']['relations']}"
    assert inv[0]["source_role"] == "徒弟"
    assert inv[0]["target_role"] == "师傅"


def test_fix_asymmetry_skips_optional_hierarchy(tmp_project):
    """fix_asymmetry 不补层级（optional）反向边。"""
    proj_path, _ = tmp_project
    parent = call_tool("graph.create_unit", project=proj_path, unit_type="world_rule",
                       name="落云山脉", content='{"subtype":"地点"}', actor="novel-v2-crafter")
    assert_success(parent)
    child = call_tool("graph.create_unit", project=proj_path, unit_type="world_rule",
                      name="青云峰", content='{"subtype":"地点"}', actor="novel-v2-crafter")
    assert_success(child)

    res = call_tool("graph.add_relation", project=proj_path,
                    source=parent["data"]["id"], target=child["data"]["id"],
                    rel_type="contains", actor="novel-v2-crafter")
    assert_success(res)

    res = call_tool("graph.fix_asymmetry", project=proj_path)
    assert_success(res)
    assert res["data"]["created"] == 0


# ── 5. 非枚举降级 ────────────────────────────────────────────────

def test_relation_label_degradation():
    """非枚举中文标签降级为 RELATES_TO + label（原 REFERENCES）。"""
    from handlers.handlers_graph import _resolve_rel_type
    from graph_schema import RelationType
    rt, label = _resolve_rel_type("师徒")
    assert rt == RelationType.RELATES_TO and label == "师徒"


def test_add_relation_invalid_type_degraded(tmp_project):
    """novel-tool 层非枚举降级：relates_to + label。"""
    proj_path, _ = tmp_project
    a = _create_char(tmp_project, "林渊")
    b = _create_char(tmp_project, "韩致")
    res = call_tool("graph.add_relation", project=proj_path,
                    source=a, target=b, rel_type="师徒",
                    actor="novel-v2-crafter")
    assert_success(res)
    assert res["data"]["type"] == "relates_to"
    assert res["data"]["label"] == "师徒"


# ── 6. role 过滤查询 ─────────────────────────────────────────────

def test_get_relations_role_filter(tmp_project):
    """get_relations 支持 role 精确/子串过滤。"""
    proj_path, _ = tmp_project
    lin = _create_char(tmp_project, "林渊")
    han = _create_char(tmp_project, "韩致")
    call_tool("graph.add_relation", project=proj_path,
              source=lin, target=han, rel_type="relates_to",
              source_role="师傅", target_role="徒弟", bidirectional=True,
              actor="novel-v2-crafter")

    # 精确匹配：林渊 的 outgoing 中 role=师傅 的边
    res = call_tool("graph.get_relations", project=proj_path, id=lin, role="师傅")
    assert_success(res)
    roles = [(r["source_role"], r["target_role"]) for r in res["data"]["relations"]]
    assert ("师傅", "徒弟") in roles, f"实际 roles: {roles}"

    # 子串匹配
    res = call_tool("graph.get_relations", project=proj_path,
                    id=lin, role="师", role_substring=True)
    assert_success(res)
    assert len(res["data"]["relations"]) >= 1


# ── 7. update_relation role ──────────────────────────────────────

def test_update_relation_roles(tmp_project):
    """update_relation 支持更新 source_role/target_role。"""
    proj_path, _ = tmp_project
    lin = _create_char(tmp_project, "林渊")
    han = _create_char(tmp_project, "韩致")
    res = call_tool("graph.add_relation", project=proj_path,
                    source=lin, target=han, rel_type="relates_to",
                    actor="novel-v2-crafter")
    rel_id = res["data"]["id"]

    res = call_tool("graph.update_relation", project=proj_path,
                    id=rel_id, source_role="师兄", target_role="师弟",
                    actor="novel-v2-crafter")
    assert_success(res)
    assert res["data"]["updated"] is True

    res = call_tool("graph.get_relations", project=proj_path, id=lin, direction="outgoing")
    assert_success(res)
    rel = [r for r in res["data"]["relations"] if r["id"] == rel_id][0]
    assert rel["source_role"] == "师兄"
    assert rel["target_role"] == "师弟"


# ── 8. 声明驱动建边 ──────────────────────────────────────────────

def test_declared_refs_scene_location(tmp_project):
    """场景 location_ref 声明 → LOCATED_AT 边（而非 REFERENCES）。"""
    proj_path, _ = tmp_project
    wr = call_tool("graph.create_unit", project=proj_path, unit_type="world_rule",
                   name="落云宗", content='{"subtype":"势力"}', actor="novel-v2-crafter")
    assert_success(wr)
    sc = call_tool("graph.create_unit", project=proj_path, unit_type="scene",
                   name="后山拔剑",
                   content='{"subtype":"开篇","synopsis":"拔剑","pov_character":"林渊",'
                           '"one_line_summary":"后山拔剑","location":"落云宗"}',
                   actor="novel-v2-crafter")
    assert_success(sc)

    res = call_tool("graph.get_relations", project=proj_path,
                    id=sc["data"]["id"], direction="outgoing")
    assert_success(res)
    located = [r for r in res["data"]["relations"]
               if r["type"] == "located_at" and r["target_id"] == wr["data"]["id"]]
    assert located, f"期望 LOCATED_AT 边（scene→world_rule），实际: {res['data']['relations']}"


def test_declared_refs_chapter_plan_plans(tmp_project):
    """章纲 scene_refs 声明 → PLANS 边（而非 REFERENCES）。"""
    proj_path, _ = tmp_project
    sc = call_tool("graph.create_unit", project=proj_path, unit_type="scene",
                   name="第一章开场",
                   content='{"subtype":"开篇","synopsis":"开场","pov_character":"林渊",'
                           '"one_line_summary":"开场","location":"村口"}',
                   actor="novel-v2-crafter")
    assert_success(sc)
    cp = call_tool("graph.create_unit", project=proj_path, unit_type="chapter_plan",
                   name="第1章",
                   content=json.dumps({
                       "scenes": [{"scene_id": sc["data"]["id"]}],
                       "synopsis": "第一章概要",
                       "chapter_number": 1,
                       "chapter_function": "开篇",
                       "scene_sequence": ["scene_1"],
                   }),
                   actor="novel-v2-crafter")
    assert_success(cp)

    res = call_tool("graph.get_relations", project=proj_path,
                    id=cp["data"]["id"], direction="outgoing")
    assert_success(res)
    plans = [r for r in res["data"]["relations"]
             if r["type"] == "plans" and r["target_id"] == sc["data"]["id"]]
    assert plans, f"期望 PLANS 边（chapter_plan→scene），实际: {res['data']['relations']}"


# ── 9. 旧数据兼容性 ──────────────────────────────────────────────

def test_relation_from_dict_legacy_missing_roles():
    """旧 edges.jsonl（无 role 字段）反序列化不报错，role 默认空串。"""
    from graph_schema import Relation, RelationType
    legacy = {
        "id": "rel_legacy1",
        "source_id": "ca_1",
        "target_id": "ca_2",
        "relation_type": "relates_to",
        "weight": 0.5,
        "description": "",
        "label": "师徒",
        "payload": {},
        "created_at": "2026-01-01T00:00:00+00:00",
        "updated_at": "2026-01-01T00:00:00+00:00",
    }
    rel = Relation.from_dict(legacy)
    assert rel.source_role == ""
    assert rel.target_role == ""
    assert rel.relation_type == RelationType.RELATES_TO


def test_relation_to_dict_includes_roles(tmp_project):
    """to_dict 序列化包含 source_role/target_role。"""
    proj_path, _ = tmp_project
    lin = _create_char(tmp_project, "林渊")
    han = _create_char(tmp_project, "韩致")
    res = call_tool("graph.add_relation", project=proj_path,
                    source=lin, target=han, rel_type="relates_to",
                    source_role="师傅", target_role="徒弟",
                    actor="novel-v2-crafter")
    rel_id = res["data"]["id"]

    from graph_store import GraphStore
    s = GraphStore(proj_path)
    s.initialize()
    rel = s.get_relation(rel_id)
    assert rel is not None
    d = rel.to_dict()
    assert d["source_role"] == "师傅"
    assert d["target_role"] == "徒弟"


# ── 10. weight 过滤（P2-12）──────────────────────────────────────

def test_get_relations_weight_filter(tmp_project):
    """get_relations 支持 min_weight/max_weight 过滤（含边界）。"""
    proj_path, _ = tmp_project
    a = _create_char(tmp_project, "甲")
    b = _create_char(tmp_project, "乙")
    c = _create_char(tmp_project, "丙")
    # 甲→乙 weight 0.2，甲→丙 weight 0.8
    call_tool("graph.add_relation", project=proj_path, source=a, target=b,
              rel_type="relates_to", weight=0.2, actor="novel-v2-crafter")
    call_tool("graph.add_relation", project=proj_path, source=a, target=c,
              rel_type="relates_to", weight=0.8, actor="novel-v2-crafter")

    # 无过滤：2 条
    res = call_tool("graph.get_relations", project=proj_path, id=a, direction="outgoing")
    assert_success(res)
    assert len(res["data"]["relations"]) == 2

    # min_weight=0.5：只留 weight 0.8
    res = call_tool("graph.get_relations", project=proj_path, id=a,
                    direction="outgoing", min_weight=0.5)
    assert_success(res)
    rels = res["data"]["relations"]
    assert len(rels) == 1 and rels[0]["target_id"] == c

    # max_weight=0.5：只留 weight 0.2
    res = call_tool("graph.get_relations", project=proj_path, id=a,
                    direction="outgoing", max_weight=0.5)
    assert_success(res)
    rels = res["data"]["relations"]
    assert len(rels) == 1 and rels[0]["target_id"] == b

    # 区间 [0.1, 0.9]：两条都在
    res = call_tool("graph.get_relations", project=proj_path, id=a,
                    direction="outgoing", min_weight=0.1, max_weight=0.9)
    assert_success(res)
    assert len(res["data"]["relations"]) == 2


# ── 11. 时态 payload 约定（P2-13）────────────────────────────────

def test_relation_temporal_scope_via_store(tmp_project):
    """时态约定键随 add_relation payload 持久化，get_relations 可读回。"""
    proj_path, _ = tmp_project
    lin = _create_char(tmp_project, "林渊")
    wr = call_tool("graph.create_unit", project=proj_path, unit_type="world_rule",
                   name="落云宗", content='{"subtype":"势力"}', actor="novel-v2-crafter")
    assert_success(wr)
    res = call_tool("graph.add_relation", project=proj_path, source=lin, target=wr["data"]["id"],
                    rel_type="member_of",
                    payload=json.dumps({"start_chapter": 1, "resolve_chapter": 50}),
                    actor="novel-v2-crafter")
    assert_success(res)
    assert res["data"]["payload"]["start_chapter"] == 1
    assert res["data"]["payload"]["source"] == "llm"  # crafter 通道

    # get_relations 输出含 payload
    rels = call_tool("graph.get_relations", project=proj_path, id=lin, direction="outgoing")
    assert_success(rels)
    rel = [r for r in rels["data"]["relations"] if r["target_id"] == wr["data"]["id"]][0]
    assert rel["payload"].get("start_chapter") == 1
    assert rel["payload"].get("source") == "llm"


# ── 12. 证据锚点（P2-14）─────────────────────────────────────────

def test_evidence_anchor_llm_channel(tmp_project):
    """handle_add_relation：crafter actor → source=llm。"""
    proj_path, _ = tmp_project
    a = _create_char(tmp_project, "甲")
    b = _create_char(tmp_project, "乙")
    res = call_tool("graph.add_relation", project=proj_path, source=a, target=b,
                    rel_type="relates_to", actor="novel-v2-crafter")
    assert_success(res)
    assert res["data"]["payload"]["source"] == "llm"


def test_evidence_anchor_manual_channel(tmp_project):
    """handle_add_relation：script actor → source=manual。"""
    proj_path, _ = tmp_project
    a = _create_char(tmp_project, "甲")
    b = _create_char(tmp_project, "乙")
    res = call_tool("graph.add_relation", project=proj_path, source=a, target=b,
                    rel_type="relates_to", actor="script")
    assert_success(res)
    assert res["data"]["payload"]["source"] == "manual"


def test_evidence_anchor_auto_channel(tmp_project):
    """声明驱动建边（_create_rel）→ source=auto + 出处章节。"""
    proj_path, _ = tmp_project
    wr = call_tool("graph.create_unit", project=proj_path, unit_type="world_rule",
                   name="落云宗", content='{"subtype":"势力"}', actor="novel-v2-crafter")
    assert_success(wr)
    sc = call_tool("graph.create_unit", project=proj_path, unit_type="scene",
                   name="后山拔剑",
                   content='{"subtype":"开篇","synopsis":"拔剑","pov_character":"林渊",'
                           '"one_line_summary":"后山拔剑","location":"落云宗"}',
                   chapter=3, actor="novel-v2-crafter")
    assert_success(sc)

    rels = call_tool("graph.get_relations", project=proj_path,
                     id=sc["data"]["id"], direction="outgoing")
    assert_success(rels)
    located = [r for r in rels["data"]["relations"]
               if r["type"] == "located_at" and r["target_id"] == wr["data"]["id"]]
    assert located, f"期望 LOCATED_AT 边，实际: {rels['data']['relations']}"
    # 自动边证据锚点：source=auto + 出处章节（场景章节 3）
    assert located[0]["payload"].get("source") == "auto"
    assert located[0]["payload"].get("chapter") == 3


def test_evidence_anchor_fix_asymmetry(tmp_project):
    """fix_asymmetry 补的反向边 → source=auto + auto_filled_reverse 标记。"""
    proj_path, _ = tmp_project
    a = _create_char(tmp_project, "甲")
    b = _create_char(tmp_project, "乙")
    call_tool("graph.add_relation", project=proj_path, source=a, target=b,
              rel_type="relates_to", actor="novel-v2-crafter")
    res = call_tool("graph.fix_asymmetry", project=proj_path)
    assert_success(res)
    assert res["data"]["created"] == 1

    rev = call_tool("graph.get_relations", project=proj_path, id=b, direction="outgoing")
    assert_success(rev)
    inv = [r for r in rev["data"]["relations"] if r["target_id"] == a]
    assert inv
    assert inv[0]["payload"].get("source") == "auto"
    assert inv[0]["payload"].get("auto_filled_reverse") is True


