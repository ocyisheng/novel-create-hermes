"""
SCENE schema 单元测试：新单场域格式的创建、校验、迁移、投影。
"""

import json
import os
import sys
import tempfile
from pathlib import Path

# 确保能找到 v2 模块和 handlers 模块
_v2_dir = Path(__file__).resolve().parent.parent.parent / "v2"
_shared_dir = _v2_dir.parent
sys.path.insert(0, str(_v2_dir))
sys.path.insert(0, str(_shared_dir))

import pytest
from graph_schema import UnitType, NarrativeUnit
from schemas import validate_content, default_content
from type_registry import TypeRegistry
from projection_engine import ProjectionEngine


# ── 测试数据 ───────────────────────────────────────────────────────

VALID_NEW_SCENE = {
    "synopsis": "林渊在练剑坪第一次拔剑",
    "subtype": "推进",
    "pov_character": "林渊",
    "location": "落云宗后山练剑坪",
    "time_text": "午后",
    "one_line_summary": "林渊在练剑坪第一次拔剑",
    "cast": [{"name": "林渊"}, {"name": "苏长老"}],
    "core_conflict": "林渊练剑被苏长老阻挠",
    "related_plotlines": ["主线·剑道之争"],
    "word_count": 1500,
}

VALID_NEW_SCENE_MINIMAL = {
    "synopsis": "林渊接受宗门任务",
    "subtype": "展示",
    "pov_character": "林渊",
    "location": "宗门大殿",
    "one_line_summary": "林渊接受宗门任务",
}

OLD_SCENE = {
    "subtype": "推进",
    "结构规划": {
        "开篇": {"方式": "动作开场", "上章衔接": "林渊被嘲笑后独自离开"},
        "发展": {"核心冲突": "林渊练剑被阻", "推进": "苏长老出现"},
        "转折": {"事件": "苏长老指出林渊的潜在天赋"},
        "收尾": {"结果": "林渊重新振作", "下章铺垫": "次日考核"},
    },
    "出场角色": ["林渊", "苏长老"],
    "关联情节线": ["主线·剑道之争"],
    "张力曲线": {"开场": 3, "章节高潮": 7, "结尾": 5},
    "场域规划": [{"场域名": "练剑坪", "POV角色": "林渊", "功能": "展示冲突"}],
    "location": "落云宗后山练剑坪",
    "time_text": "午后",
    "one_line_summary": "林渊在落云宗后山第一次拔剑",
}

V1_MIGRATION_DATA = {
    "索引信息": {"chapter_number": 3, "名称": "初试锋芒"},
    "摘要信息": {"描述": "林渊在落云宗后山第一次拔剑,展露天资"},
    "内容": "林渊被同门嘲笑后独自来到后山练剑，苏长老暗中观察...",
    "出场角色": ["林渊", "苏长老"],
}


# ── 创建辅助 ─────────────────────────────────────────────────────

@pytest.fixture
def temp_graph_dir():
    """创建临时 graph 目录用于测试"""
    with tempfile.TemporaryDirectory() as tmp:
        graph_dir = Path(tmp) / "graph"
        graph_dir.mkdir()
        yield tmp


# ── 1. Schema 校验 ────────────────────────────────────────────────

class TestSchemaValidation:
    def test_valid_new_scene_passes(self):
        errors = validate_content(UnitType.SCENE, VALID_NEW_SCENE)
        assert errors == []

    def test_minimal_scene_passes(self):
        errors = validate_content(UnitType.SCENE, VALID_NEW_SCENE_MINIMAL)
        assert errors == []

    def test_missing_subtype(self):
        data = VALID_NEW_SCENE.copy()
        del data["subtype"]
        errors = validate_content(UnitType.SCENE, data)
        assert any("subtype" in e for e in errors)

    def test_missing_pov(self):
        data = VALID_NEW_SCENE.copy()
        del data["pov_character"]
        errors = validate_content(UnitType.SCENE, data)
        assert any("pov_character" in e for e in errors)

    def test_missing_location(self):
        data = VALID_NEW_SCENE.copy()
        del data["location"]
        errors = validate_content(UnitType.SCENE, data)
        assert any("location" in e for e in errors)

    def test_missing_summary(self):
        data = VALID_NEW_SCENE.copy()
        del data["one_line_summary"]
        errors = validate_content(UnitType.SCENE, data)
        assert any("one_line_summary" in e for e in errors)

    def test_invalid_subtype_value(self):
        data = VALID_NEW_SCENE.copy()
        data["subtype"] = "高潮"
        errors = validate_content(UnitType.SCENE, data)
        assert any("高潮" in e for e in errors)

    def test_new_subtype_values_all_valid(self):
        """所有新 subtype 值都应通过校验"""
        valid_types = ["开篇", "推进", "冲突", "转折", "展示", "过渡", "收束"]
        for st in valid_types:
            data = VALID_NEW_SCENE_MINIMAL.copy()
            data["subtype"] = st
            errors = validate_content(UnitType.SCENE, data)
            assert errors == [], f"subtype '{st}' 应通过校验，但报错: {errors}"

    def test_old_subtype_values_fail(self):
        """旧 subtype 值（高潮/引入/铺垫）应失败"""
        old_types = ["高潮", "引入", "铺垫"]
        for st in old_types:
            data = VALID_NEW_SCENE_MINIMAL.copy()
            data["subtype"] = st
            errors = validate_content(UnitType.SCENE, data)
            assert any(st in e for e in errors), f"subtype '{st}' 应报错"

    def test_old_schema_structure_detected(self):
        """含 结构规划 的旧 schema 应缺必填字段"""
        errors = validate_content(UnitType.SCENE, OLD_SCENE)
        # 旧 schema 缺 pov_character 字段
        assert any("pov_character" in e for e in errors)

    def test_default_content_has_required_fields(self):
        content_str = default_content(UnitType.SCENE)
        d = json.loads(content_str)
        assert "subtype" in d
        assert "pov_character" in d  # 新 schema 新增
        assert "location" in d     # 新 schema 必填


# ── 2. Subtype config via TypeRegistry ─────────────────────────

class TestSubtypeRegistry:
    def test_scene_subtype_options(self):
        cfg = TypeRegistry.get_global().get_subtype_config("scene")
        assert cfg is not None
        assert cfg.get("options") == ["开篇", "推进", "冲突", "转折", "展示", "过渡", "收束"]

    def test_old_subtype_not_in_registry(self):
        cfg = TypeRegistry.get_global().get_subtype_config("scene")
        assert "高潮" not in cfg.get("options", [])
        assert "引入" not in cfg.get("options", [])
        assert "铺垫" not in cfg.get("options", [])


# ── 3. 投影格式化 ───────────────────────────────────────────────

class TestSceneFormatting:
    def test_format_valid_new_scene(self):
        result = ProjectionEngine._format_scene_content(json.dumps(VALID_NEW_SCENE))
        assert "功能: 推进" in result
        assert "概要: 林渊在练剑坪第一次拔剑" in result
        assert "POV: 林渊" in result
        assert "地点: 落云宗后山练剑坪" in result
        assert "冲突: 林渊练剑被苏长老阻挠" in result
        assert "林渊" in result

    def test_format_minimal_scene(self):
        result = ProjectionEngine._format_scene_content(json.dumps(VALID_NEW_SCENE_MINIMAL))
        assert "功能: 展示" in result
        assert "POV: 林渊" in result
        assert "地点: 宗门大殿" in result

    def test_format_old_schema_without_new_fields(self):
        """旧 schema 无任何新字段名时应提示升级"""
        old_only = {"结构规划": {"开篇": {"方式": "动作开场"}}, "张力曲线": {}}
        result = ProjectionEngine._format_scene_content(json.dumps(old_only))
        assert "旧 schema" in result

    def test_format_empty_content(self):
        result = ProjectionEngine._format_scene_content("")
        assert "暂无内容" in result

    def test_format_invalid_json(self):
        result = ProjectionEngine._format_scene_content("不是 JSON { 残缺")
        assert result == "不是 JSON { 残缺"  # 回退到 raw 文本

    def test_format_v1_data(self):
        result = ProjectionEngine._format_scene_content(json.dumps(V1_MIGRATION_DATA))
        # V1 数据无新 schema 字段也无 结构规划，回退 raw
        assert result != "（暂无内容）"


# ── 4. Graph 存储集成 ────────────────────────────────────────────

class TestSceneGraphStore:
    def test_create_new_scene(self, temp_graph_dir):
        from graph_store import GraphStore
        store = GraphStore(temp_graph_dir)
        store.initialize()

        unit = store.create_unit(
            type=UnitType.SCENE,
            unit_name="新场景测试",
            content=json.dumps(VALID_NEW_SCENE, ensure_ascii=False),
            chapter_number=3,
            actor="test",
        )
        assert unit is not None
        assert unit.type == UnitType.SCENE
        assert unit.chapter_number == 3

    def test_find_scenes_by_chapter(self, temp_graph_dir):
        from graph_store import GraphStore
        store = GraphStore(temp_graph_dir)
        store.initialize()
        for i in range(3):
            store.create_unit(
                type=UnitType.SCENE,
                unit_name=f"场景{i+1}",
                content=json.dumps(VALID_NEW_SCENE_MINIMAL, ensure_ascii=False),
                chapter_number=2,
                actor="test",
            )
        store.flush()

        scenes = store.find_units(type=UnitType.SCENE, chapter=2)
        assert len(scenes) == 3

    def test_multiple_scenes_per_chapter_order(self, temp_graph_dir):
        """同章多个 SCENE 按创建时间排序的结构"""
        from graph_store import GraphStore
        store = GraphStore(temp_graph_dir)
        store.initialize()
        scenes = []
        for name in ["开篇", "冲突", "收束"]:
            data = VALID_NEW_SCENE_MINIMAL.copy()
            data["subtype"] = name
            u = store.create_unit(
                type=UnitType.SCENE,
                unit_name=name,
                content=json.dumps(data, ensure_ascii=False),
                chapter_number=5,
                actor="test",
            )
            scenes.append(u)
        store.flush()
        assert len(scenes) == 3
        assert scenes[0].unit_name == "开篇"


# ── 6. CHUNK schema ──────────────────────────────────────────────

class TestChunkSchema:
    """CHUNK 元数据格式验证"""

    VALID_CHUNK = {
        "text": "林渊握紧了剑柄...",
        "chapter_number": 3,
        "file_path": "chapters/第3章.txt",
        "subtype": "v1",
        "word_count": 3200,
    }

    def test_valid_chunk_passes(self):
        errors = validate_content(UnitType.CHUNK, self.VALID_CHUNK)
        assert errors == []

    def test_chunk_minimal_passes(self):
        """只有必填字段 subtype + text + word_count"""
        errors = validate_content(UnitType.CHUNK, {"subtype": "v1", "text": "content", "word_count": 100})
        assert errors == []

    def test_chunk_missing_word_count(self):
        """缺少必填字段 word_count"""
        errors = validate_content(UnitType.CHUNK, {"subtype": "v1"})
        assert any("word_count" in e for e in errors)

    def test_chunk_plain_text_skips_validation(self):
        """旧格式纯文本 CHUNK 应跳过校验"""
        errors = validate_content(UnitType.CHUNK, "林渊握紧了剑柄的纯文本...")
        assert errors == []

    def test_chunk_with_file_path_passes(self):
        data = {"subtype": "v2", "chapter_number": 5, "file_path": "chapters/第5章.txt", "text": "content", "word_count": 100}
        errors = validate_content(UnitType.CHUNK, data)
        assert errors == []

    def test_default_content_optional_fields_only(self):
        """default_content 含字段"""
        content_str = default_content(UnitType.CHUNK)
        d = json.loads(content_str)
        assert isinstance(d, dict)
        assert "text" in d
        assert "word_count" in d

    def test_create_chunk_in_store(self, temp_graph_dir):
        from graph_store import GraphStore
        store = GraphStore(temp_graph_dir)
        store.initialize()
        unit = store.create_unit(
            type=UnitType.CHUNK,
            unit_name="第3章",
            content=json.dumps(self.VALID_CHUNK, ensure_ascii=False),
            chapter_number=3,
            actor="test",
        )
        assert unit.type == UnitType.CHUNK
        assert unit.chapter_number == 3
        loaded = json.loads(unit.content)
        assert loaded["file_path"] == "chapters/第3章.txt"

    def test_export_chunk_reads_from_file(self, temp_graph_dir):
        """handle_export_chunks 应从 file_path 指向的文件读取正文"""
        from graph_store import GraphStore
        from handlers.handlers_graph import handle_export_chunks

        store = GraphStore(temp_graph_dir)
        store.initialize()

        # 创建正文文件
        chapters_dir = Path(temp_graph_dir) / "chapters"
        chapters_dir.mkdir()
        text_file = chapters_dir / "第3章.txt"
        text_file.write_text("林渊握紧了剑柄...", encoding="utf-8")

        # 创建 CHUNK 元数据
        store.create_unit(
            type=UnitType.CHUNK,
            unit_name="第3章",
            content=json.dumps({
                "chapter_number": 3,
                "file_path": str(text_file),
                "word_count": 12,
            }, ensure_ascii=False),
            chapter_number=3,
            actor="test",
        )
        store.flush()

        out_dir = Path(temp_graph_dir) / "export"
        out_dir.mkdir()
        result = handle_export_chunks(project_root=temp_graph_dir, out=str(out_dir))
        assert "files" in result
        assert len(result["files"]) >= 1

        exported = out_dir / "第3章.txt"
        assert exported.exists()
        assert exported.read_text(encoding="utf-8") == "林渊握紧了剑柄..."
