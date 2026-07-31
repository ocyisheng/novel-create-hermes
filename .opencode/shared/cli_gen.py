"""CLI 参数定义自动生成 —— 从 OPERATION_REGISTRY 自动生成 argparse 子命令。

用法：
    from cli_gen import add_registry_commands, dispatch_registry_command
    add_registry_commands(v2_subparsers)
    if dispatch_registry_command(args):
        return
    # 否则走手动 if/elif
"""

import json
import sys
import inspect
from handlers import OPERATION_REGISTRY


# ── 参数 CLI 表现配置 ────────────────────────────────────────────

PARAM_OPTS = {
    "project_root": {"flags": ["--path"], "help": "项目根目录"},
    "id": {"flags": ["--id"], "help": "单元 ID"},
    "name": {"flags": ["--name"], "help": "名称"},
    "unit_type": {"flags": ["--unit-type"], "help": "单元类型"},
    "rel_type": {"flags": ["--rel-type"], "help": "关系类型"},
    "focus_type": {"flags": ["--focus-type"], "help": "会话焦点类型"},
    "content": {"flags": ["--content"], "help": "内容（JSON 字符串）"},
    "file_path": {"flags": ["--file"], "help": "从 JSON 文件读取内容"},
    "tags": {"flags": ["--tags"], "help": "逗号分隔的标签列表"},
    "status": {"flags": ["--status"], "help": "状态"},
    "actor": {"flags": ["--actor"], "default": "script", "help": "操作者标识"},
    "keyword": {"flags": ["--keyword"], "help": "搜索关键词"},
    "pattern": {"flags": ["--pattern"], "help": "正则模式"},
    "scope": {"flags": ["--scope"], "help": "搜索范围"},
    "regex": {"flags": ["--regex"], "action": "store_true", "help": "启用正则搜索"},
    "case_sensitive": {"flags": ["--case-sensitive"], "action": "store_true", "help": "区分大小写"},
    "limit": {"flags": ["--limit"], "type": int, "default": 0, "help": "结果上限"},
    "chapter": {"flags": ["--chapter"], "type": int, "help": "章节号"},
    "source": {"flags": ["--source"], "help": "关系源 ID"},
    "target": {"flags": ["--target"], "help": "关系目标 ID"},
    "bidirectional": {"flags": ["--bidirectional"], "action": "store_true", "help": "自动建立反向关系"},
    "direction": {"flags": ["--direction"], "default": "both", "help": "方向"},
    "max_depth": {"flags": ["--max-depth"], "type": int, "help": "最大深度"},
    "out": {"flags": ["--out"], "help": "输出目录"},
    "dry_run": {"flags": ["--dry-run"], "action": "store_true", "help": "试运行"},
    "verify": {"flags": ["--verify"], "action": "store_true", "help": "迁移时验证"},
    "report": {"flags": ["--report"], "action": "store_true", "help": "输出报告"},
    "force": {"flags": ["--force"], "action": "store_true", "help": "强制模式"},
    "incremental": {"flags": ["--incremental"], "action": "store_true", "help": "增量生成"},
    "open_browser": {"flags": ["--open"], "action": "store_true", "help": "生成后打开浏览器"},
    "since_version": {"flags": ["--since-version"], "type": int, "help": "起始版本号"},
    "findings": {"flags": ["--findings"], "help": "偏差发现列表(JSON)"},
    "scan_version": {"flags": ["--scan-version"], "type": int, "help": "扫描版本号"},
    "full_scan_version": {"flags": ["--full-scan-version"], "type": int, "help": "全量扫描版本号"},
    "slug": {"flags": ["--slug"], "help": "知识库标识"},
    "topic": {"flags": ["--topic"], "help": "查询主题"},
    "level": {"flags": ["--level"], "default": "warm", "help": "预热级别"},
    "cycle_type": {"flags": ["--cycle-type"], "help": "循环类型"},
    "phase": {"flags": ["--phase"], "help": "会话阶段"},
    "parent_id": {"flags": ["--parent-id"], "help": "父级单元 ID"},
    "character": {"flags": ["--character"], "help": "角色名称/ID"},
    "timeline": {"flags": ["--timeline"], "help": "时间线角色"},
    "output": {"flags": ["--output"], "help": "输出路径"},
    "verbose": {"flags": ["--verbose"], "action": "store_true", "help": "详细模式"},
    "source_path": {"flags": ["--source-path"], "help": "导入源路径"},
    # subagent
    "task_id": {"flags": ["--task-id"], "help": "子 Agent 任务 ID"},
    "subagent": {"flags": ["--subagent"], "help": "子 Agent 类型"},
    "preheat_level": {"flags": ["--preheat-level"], "help": "预热级别"},
    "humanize": {"flags": ["--humanize"], "action": "store_true", "help": "是否去 AI 味"},
    "session_id": {"flags": ["--session-id"], "help": "关联的创作 session ID"},
    "result": {"flags": ["--result"], "help": "结果状态 (success/partial/failed)"},
    "prompt_summary": {"flags": ["--prompt-summary"], "help": "prompt 摘要"},
    "result_summary": {"flags": ["--result-summary"], "help": "结果摘要"},
    "new_units": {"flags": ["--new-units"], "type": int, "default": 0, "help": "新建单元数"},
    "updated_units": {"flags": ["--updated-units"], "type": int, "default": 0, "help": "更新单元数"},
    "duration_estimate_ms": {"flags": ["--duration-ms"], "type": int, "default": 0, "help": "预估耗时(ms)"},
    "error_summary": {"flags": ["--error-summary"], "help": "错误摘要"},
    "user_intent": {"flags": ["--user-intent"], "help": "用户原始输入摘要"},
    "focus_name": {"flags": ["--focus-name"], "help": "焦点名称"},
    # summary
    "file": {"flags": ["--file"], "help": "总结文件名"},
    "tag": {"flags": ["--tag"], "help": "按标签过滤"},
    "project": {"flags": ["--project"], "help": "按项目名过滤"},
    # analyze
    "mode": {"flags": ["--mode"], "default": "full", "help": "分析模式 (quick/full)"},
    "json_output": {"flags": ["--json"], "action": "store_true", "help": "输出 JSON"},
}

# 命令名 → 注册表操作名映射
# 假设命令名格式为 op_name.replace("_", "-").replace(".", "-")
# 少数特殊映射在此覆盖
CMD_OVERRIDES = {
    "open_browser": "open",
}


def _operation_to_command(op_name: str) -> str:
    """novel-tool 操作名 → CLI 子命令名。"""
    return op_name.replace("_", "-").replace(".", "-")


def _command_to_operation(cmd_name: str) -> str:
    """CLI 子命令名 → novel-tool 操作名。
    
    graph-get-unit → graph.get_unit
    session-start → session.start
    """
    # 第一个 '-' 替换为 '.'（分隔 domain 和 operation），其余 '-' 替换为 '_'
    idx = cmd_name.find("-")
    if idx == -1:
        return cmd_name
    return cmd_name[:idx] + "." + cmd_name[idx + 1:].replace("-", "_")


def add_registry_commands(v2_subparsers):
    """为每个 registry 操作注册 CLI 子命令。"""
    for op_name in sorted(OPERATION_REGISTRY.keys()):
        domain = op_name.split(".")[0]
        if domain not in ("graph", "session", "deviation", "knowledge", "subagent", "summary"):
            continue
        entry = OPERATION_REGISTRY[op_name]
        if "project_root" not in entry["params"]:
            continue

        cmd = _operation_to_command(op_name)
        p = v2_subparsers.add_parser(cmd, help=entry.get("help", ""))
        p.add_argument("--path", required=True, help="项目根目录")

        for param_name, param_config in entry["params"].items():
            if param_name == "project_root":
                continue
            opts = PARAM_OPTS.get(param_name, {})
            flags = opts.get("flags", [f"--{param_name.replace('_', '-')}"])
            kwargs = {
                "default": opts.get("default", ""),
                "help": opts.get("help", ""),
            }
            if "type" in opts:
                kwargs["type"] = opts["type"]
            if opts.get("action") == "store_true":
                kwargs["action"] = "store_true"
            if isinstance(param_config, dict) and param_config.get("required"):
                kwargs["required"] = True
            p.add_argument(*flags, **kwargs)


def dispatch_registry_command(args) -> bool:
    """根据 args 自动路由到 registry handler。

    返回 True 表示已处理，False 表示未命中（由手动 if/elif 处理）。
    """
    cmd = args.v2_command
    if not cmd:
        return False

    op_name = _command_to_operation(cmd)
    entry = OPERATION_REGISTRY.get(op_name)
    if not entry:
        return False

    # 从 args 提取 registry 声明的参数
    params = {"project_root": args.path}
    for pname in entry["params"]:
        if pname == "project_root":
            continue
        val = getattr(args, pname.replace("-", "_"), None)
        if val is not None and val != "":
            params[pname] = val

    try:
        result = entry["handler"](**params)
    except Exception as e:
        print(f"❌ 操作失败: {e}")
        sys.exit(1)

    if "error" in result:
        print(f"❌ {result['error']}")
        sys.exit(1)

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return True
