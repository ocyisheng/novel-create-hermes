# V2 内容字段验证与消费分析

## Objective
Analyze which content fields in V2's schemas.py need mandatory validation vs. warning-only, based on actual consumption paths and failure modes.

## Core Finding: No Content Field Is System-Critical
Every consumer reads content fields with defensive `.get(key, default)` — **zero content fields will crash the application if missing**. Worst case: blank section in visualization output. This is by design — schemas.py validation is purely advisory.

## Field Consumption Classification

### Tier 1 — Actually Consumed (has logic beyond rendering)
These fields are read by name in business logic (not just generic `for k,v` iteration):

| UnitType | Field | Consumer(s) | Failure Mode if Missing |
|----------|-------|-------------|------------------------|
| SCENE | `地点` | workspace.py (writing context) | Empty location context |
| SCENE | `时间` | workspace.py + v2_graph_viz.py | Empty time context, no timeline event |
| SCENE | `核心冲突` | workspace.py (falls back to 一句话概要) | Falls back silently |
| SCENE | `出场角色` | workspace.py (character states) | Empty character_states in writing context |
| SCENE | `一句话概要` | workspace.py + projection_engine.py | Empty writing guide + blank output |
| SCENE | `子类型` | workspace.py + projection_engine + viz + density table | Empty type label, default density |
| SCENE | `POV角色` | projection_engine.py | Blank line in output |
| CHUNK | `正文路径` / `正文分片` | search_engine.py (file integrity checks) | Check skipped silently |
| CHUNK | `章节号` | search_engine.py (consistency check) | Check skipped |
| CHUNK | `字数` | projection_engine.py (display) | Displays "?" |
| WORLD_RULE | `子类型` | v2_graph_viz.py (timeline + viz label) | Blank label, no timeline events |
| WORLD_RULE | `时间` / `事件` | v2_graph_viz.py (timeline events) | No timeline events |
| CHARACTER_ARC | `核心特质` | adapter/migrate → unit tags | Empty tags on migration |
| CHARACTER_ARC | `子类型` | v2_graph_viz.py (label/color) | Blank subtype label |

### Tier 2 — Rendering-Only (consumed via generic content iteration)
These fields exist in schemas and appear in rendering output, but no code reads them by field name:

- CHARACTER_ARC: `性格/优点`, `性格/缺点`, `角色弧线/起始状态`, `角色弧线/最终状态`, `背景故事`, `动机`, `目标`, `能力`, `关系网络`
- PLOT_THREAD: `冲突核心`, `关键事件`, `终局设计`
- WORLD_RULE: `二级类型`, `描述`
- SCENE: `关联情节线`, `叙事密度`

### Tier 3 — Schema-Only / Dead (validated but never read by any consumer)
These fields only exist in schemas for LLM prompt guidance:

- CHARACTER_ARC: `背景`, `目标与冲突` (optional dicts)
- CHUNK: `章节名` (dead — written by adapter, never read anywhere)
- OUTLINE: `模式选择`, `本体论`, `美学承诺`, `七面观照`, `总纲`
- NARRATIVE_VOICE: all fields
- THEMATIC_MOTIF: all fields
- VOLUME_PLAN / CHAPTER_PLAN: all fields

## Recommended Validation Tiers

Based on this analysis:

### No field should be escalated to blocking/error validation

The design philosophy is sound: LLMs produce flexible JSON, schemas guide but never block.

### Only improvement worth making:
**Add an info-level hint** in `validate_content()` for fields that:
- Are conceptually important for downstream quality
- But currently never cause runtime issues when missing

Candidate: CHARACTER_ARC `角色弧线/起始状态` and `角色弧线/最终状态` — they're the core of "character arc" tracking but no code reads them, so LLMs commonly skip them. An info note would encourage filling them without being annoying.

### Key Architectural Note
**workspace.py never reads CHARACTER_ARC content fields.** When building context for a CHARACTER_ARC focus unit, it only reads `unit_name`, `tags`, `status`, and graph relations — not the structured personality/arc data. The AI crafter thus receives CHARACTER_ARC context without any character development state. This is likely a more impactful improvement than tightening validation.

## Identified Conflicts (from earlier analysis)
1. SKILL.md field name mismatch (`角色类型` vs `子类型`) — resolved by SUBTYPE_REGISTRY
2. Consumer code reads content without defensive checks → verified: ALL consumers use `.get()` with defaults
3. `schema_info()` and `default_content()` — confirmed dead code (zero callers)
4. `default_content()` skeleton prefill vs. creative incomplete-transition philosophy → not actionable
5. SPECIAL_RENDER_MAP hardcoded names vs. LLM-free fields → confirmed consistent
6. Strict `_check_type` vs. loose LLM JSON output → advisory-only by design, not a bug

## Relevant Files
- `.opencode/shared/v2/schemas.py`: 12 UnitType schemas, validate_content(), dead schema_info()/default_content(), SUBTYPE_REGISTRY
- `.opencode/shared/v2/graph_store.py`: create_unit() calls validate_content() but never blocks writes
- `.opencode/shared/v2/projection_engine.py`: 32 content.get() calls — heaviest consumer
- `.opencode/shared/v2/workspace.py`: SCENE field reads for writing context; never reads CHARACTER_ARC content
- `.opencode/shared/v2/render_utils.py`: SPECIAL_RENDER_MAP, infer_render_mode(), extract_entity_refs(), render_content()
- `.opencode/shared/v2/v2_graph_viz.py`: subtype label/color injection, WORLD_RULE timeline events
- `.opencode/shared/v2/search_engine.py`: CHUNK file integrity checks, consistency checks
- `.opencode/shared/v2/relation_inferrer.py`: INFER_RULES, extract_entity_refs() for graph relationships
- `.opencode/shared/v2/v2_cli.py`: CHUNK content reads for display
- `.opencode/shared/v2/adapter.py`: V1→V2 migration — reads 核心特质 for tags, writes CHUNK fields
- `.opencode/shared/v2/migrate.py`: Subtype normalization, legacy field mapping
- `.opencode/skills/novel-v2/SKILL.md`: LLM prompt guidance (references 性格.核心特质)

## Next Move
Synthesis complete. Awaiting user direction on any specific changes.
