**Generated:** 2026-07-28
**Branch:** `v2`

## CODE MAP

Core symbols across the codebase — skip when obvious from context.

> All core implementation lives under `.opencode/shared/`. See `.opencode/shared/AGENTS.md` for the full architecture map.

| Symbol | Type | Location (within `.opencode/shared/`) | Role |
|--------|------|---------------------------------------|------|
| `run_operation` | fn | `handlers/__init__.py` | Operation router |
| `GraphStore` | class | `v2/graph_store.py` | Node/edge CRUD + event sourcing |
| `SearchEngine` | class | `v2/search_engine.py` | Keyword/regex search + consistency checks |
| `DeviationManager` | class | `v2/deviation_manager.py` | Deviation state persistence |
| `WorkspaceBuilder` | class | `v2/workspace.py` | Focus preheat + context construction |
| `ProjectionEngine` | class | `v2/projection_engine.py` | graph → filesystem projection |
| `RelationInferrer` | class | `v2/relation_inferrer.py` | Automatic relation inference |
| `novel_tool` | fn | `tools/novel_tool.py` | JSON adapter layer (params → handlers) |
| `main` (CLI) | fn | `cli.py` | Unified CLI entry (argparse) |

## COMMANDS

```bash
# Environment setup
skill("novel-env-setup")

# Novel project management
skill("novel-project-manager")

# V2 unified creation
task(subagent_type="novel-v2-crafter", load_skills=["novel-v2"], prompt="...")

# Deep diagnostics
task(subagent_type="novel-search-analysis", load_skills=["novel-search-analysis"], prompt="...")
```

## CONVENTIONS

- **Language**: Python 3.10+, type-annotated throughout
- **Graph storage**: JSONL (nodes.jsonl + edges.jsonl) with event-sourced append log
- **Core code location**: All Python implementation is under `.opencode/shared/`
- **Operation pattern**: `OPERATION_REGISTRY` dict in `.opencode/shared/handlers/__init__.py` maps string → handler function
- **Handler signature**: All handlers accept `**kwargs` and return `dict` with `status` + `data`/`error`
- **Tool layer**: `.opencode/shared/tools/novel_tool.py` is thin JSON adapter — no business logic
- **Testing**: pytest with conftest fixtures

## ANTI-PATTERNS (THIS PROJECT)

- **Direct file editing**: Never edit `novels/*/chapters/` or `novels/*/characters/` directly — these are projections from graph
- **V1 skills in V2**: Do not use standalone V1 subagents (novel-ideation/synopsis/outline as subagent) in V2 projects
- **Bypassing graph**: All writes go through GraphStore CRUD, never direct JSONL edit
- **Empty catches**: No `except: pass` — deviations are persisted via DeviationManager
