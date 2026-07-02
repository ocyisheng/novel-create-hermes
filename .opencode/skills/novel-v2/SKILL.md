---
name: "novel-v2"
description: "V2 创作引擎：基于叙事单元网络(graph)的下一代创作能力。用于已迁移项目的章节写作、角色管理、世界观维护、情节规划、质量检测等全部创作操作。触发词：V2、graph、叙事单元、QUERY、migrate"
license: "MIT"
version: "1.0.0"
compatibility: "OpenCode"
tags: ["novel", "v2", "graph"]
---

# novel-v2 — V2 创作引擎

## 定位

本技能是 V2 架构的操作指引。不替代现有技能，而是在项目已迁移到 V2（存在 `graph/` 目录）时，提供基于叙事单元网络的创作能力。

**使用条件**：项目根目录下存在 `graph/nodes.jsonl` 文件（已执行过 `migrate.py`）。

---

## 上下文契约

V2 写作不再通过 chapter_context.py 全量推送上下文。改为通过 **WorkspaceBuilder** 按焦点按需加载，子 Agent 写作过程中可通过 **QUERY 协议**自主请求更多信息。

### 焦点启动（编排层负责）

编排层在调用 `task(subagent_type="novel-v2-crafter", load_skills=["novel-v2"])` 时，在 prompt 中注入以下 V2 上下文：

```
CURRENT PROJECT: {项目名}
PROJECT PATH: {NOVELS_ROOT/项目名}
FOCUS TYPE: scene | character_arc | plot_thread
FOCUS ID: {叙事单元ID}
FOCUS NAME: {叙事单元名称}
PREHEAT LEVEL: cold | warm | hot
WRITING MODE: draft | polish | rewrite
```

---

## V2 操作指南

### 1. 读取 graph 数据

```bash
# 获取叙事单元详情
python -c "
import sys; sys.path.insert(0, '.opencode/shared/v2')
from graph_store import GraphStore
s = GraphStore('{PROJECT_PATH}'); s.initialize()
unit = s.get_unit('{单元ID}')
print(f'名称: {unit.unit_name}')
print(f'类型: {unit.type.value}')
print(f'内容: {unit.content[:500]}')
print(f'标签: {unit.tags}')
"

# 查询关联关系（1度邻居）
python -c "
import sys; sys.path.insert(0, '.opencode/shared/v2')
from graph_store import GraphStore
s = GraphStore('{PROJECT_PATH}'); s.initialize()
neighbors = s.get_neighbors('{单元ID}', max_depth=1)
for nid in neighbors.get(1, set()):
    n = s.get_unit(nid)
    if n: print(f'{n.type.value}: {n.unit_name}')
"

# 按类型搜索
python -c "
import sys; sys.path.insert(0, '.opencode/shared/v2')
from graph_store import GraphStore
s = GraphStore('{PROJECT_PATH}'); s.initialize()
for u in s.find_units(type=UnitType.SCENE, chapter=5):
    print(f'{u.unit_name} [{u.status.value}]')
"
```

注意：导入时需要在 Python 代码中先 import 类型：
```python
from graph_schema import UnitType, RelationType, UnitStatus
```

### 2. 写入 graph 数据

```bash
# 创建新叙事单元
python -c "
import sys; sys.path.insert(0, '.opencode/shared/v2')
from graph_schema import UnitType
from graph_store import GraphStore
s = GraphStore('{PROJECT_PATH}'); s.initialize()
u = s.create_unit(
    type=UnitType.SCENE,
    unit_name='{单元名}',
    content='''{内容}''',
    tags=[{标签}],
    belongs_to_chapter={章节号},
    actor='{actor}',
)
s.flush()
print(f'创建成功: {u.id}')
"

# 建立关系
python -c "
import sys; sys.path.insert(0, '.opencode/shared/v2')
from graph_schema import RelationType
from graph_store import GraphStore
s = GraphStore('{PROJECT_PATH}'); s.initialize()
s.add_relation('{源ID}', '{目标ID}', RelationType.PARTICIPATES_IN, actor='{actor}')
s.flush()
print('关系已建立')
"
```

### 3. 通过 QUERY 协议获取上下文

写作过程中如果缺少信息，在回复中包含 QUERY 指令：

```
QUERY: character_background(name="角色名")
QUERY: scene_detail(scene_id="场景ID")  
QUERY: scene_detail(name="场景名")
QUERY: world_rule(name="规则名")
QUERY: plot_thread_summary(name="情节线名")
QUERY: plot_thread_summary()
QUERY: foreshadowing_status(id="伏笔编号")
QUERY: foreshadowing_status()
QUERY: style_check(text="待检查的文字")
QUERY: advanced_search(keywords=["关键词1","关键词2"], limit=5)
QUERY: chapter_status(number=章节号)
QUERY: recent_context(chapter=章节号, limit=5)
```

编排层会拦截 QUERY，从 graph 查询，将结果注入 session 上下文。
**QUERY 指令不会出现在最终输出中。**

### 4. 使用工作空间构建上下文

```bash
python -c "
import sys; sys.path.insert(0, '.opencode/shared/v2')
from graph_store import GraphStore
from workspace import WorkspaceBuilder
s = GraphStore('{PROJECT_PATH}'); s.initialize()
b = WorkspaceBuilder(s)
ws = b.build(focus_unit_id='{焦点单元ID}', preheat_level='warm')
print(ws.to_prompt_block('warm'))
"
```

### 5. 写后持久化

完成创作后，将新增/修改的内容持久化：

```bash
python -c "
import sys; sys.path.insert(0, '.opencode/shared/v2')
from graph_store import GraphStore
s = GraphStore('{PROJECT_PATH}'); s.initialize()
s.flush()
print('graph 已持久化')
"
```

### 6. 投影到文件（保持与现有文件体系兼容）

```bash
python -c "
import sys; sys.path.insert(0, '.opencode/shared/v2')
from graph_store import GraphStore
from projection_engine import ProjectionEngine, ProjectionView
s = GraphStore('{PROJECT_PATH}'); s.initialize()
p = ProjectionEngine(s, '{PROJECT_PATH}')
p.rebuild_all()
print('投影已重建')
"
```

---

## 核心原则（HARD CONSTRAINTS）

1. **graph 是真相源** — 所有创作数据优先写入 graph，投影到文件是次要的
2. **按需查询，勿全量推送** — 使用 QUERY 协议获取缺失信息，不要一次性加载全部数据
3. **写后 flush** — 每次 task() 完成后执行 `store.flush()` 确保持久化
4. **记录 actor** — 所有 create/update 操作传入 `actor` 参数（如 `actor="novel-v2-crafter"`）
5. **不要手工编辑 graph/ 下的 JSONL 文件** — 通过 GraphStore API 操作
6. **不要在回复中包含 QUERY 指令原文** — QUERY 是编排层协议，不会自动剥离
