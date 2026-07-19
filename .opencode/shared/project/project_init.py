#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
project_init.py — 项目管理（兼容桥接层）

管理小说项目的创建、导入、状态查看、续写、切换和删除。

业务逻辑已迁移至 handlers/handlers_project.py。
cli.py 直接调用 handlers，不再经过本模块。
run_project_command() 保留作为向后兼容接口，内部委托给 handlers。

依赖: Python 3.8+, PyYAML
"""

from __future__ import annotations

import os
import sys
import shutil
import yaml
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, List

# ── 目录配置 ──────────────────────────────────────────────────────────────

def find_novels_root() -> str:
    """从多个候选位置发现 NOVELS_ROOT"""
    # 1. 环境变量
    env = os.environ.get("NOVELS_ROOT")
    if env and os.path.isdir(env):
        return env
    # 2. CWD 下的 novels/
    cwd_novels = os.path.join(os.getcwd(), "novels")
    if os.path.isdir(cwd_novels):
        return cwd_novels
    # 3. 工具根目录下的 novels/
    tool_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    tool_novels = os.path.join(tool_root, "novels")
    if os.path.isdir(tool_novels):
        return tool_novels
    return cwd_novels


NOVELS_ROOT = find_novels_root()
NOW = datetime.now(timezone.utc).strftime("%Y-%m-%d")


# ── 工具函数 ──────────────────────────────────────────────────────────────

def project_path(name: str) -> str:
    return os.path.join(NOVELS_ROOT, name)


def project_exists(name: str) -> bool:
    return os.path.isdir(project_path(name)) and os.path.isfile(os.path.join(project_path(name), "config.yaml"))


def load_config(name: str) -> dict:
    cfg = os.path.join(project_path(name), "config.yaml")
    if not os.path.exists(cfg):
        return {}
    with open(cfg, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def save_config(name: str, config: dict):
    cfg = os.path.join(project_path(name), "config.yaml")
    with open(cfg, "w", encoding="utf-8") as f:
        yaml.dump(config, f, allow_unicode=True, sort_keys=False, default_flow_style=False)
    print(f"  ✅ config.yaml 已更新")


def get_omo_context_path(project_name: str) -> str:
    """获取 novel-context.md 中对应项目的持久化上下文路径"""
    return os.path.join(NOVELS_ROOT, project_name, ".omo", "notepads", "novel-context.md")


def omo_context_exists() -> str:
    """获取当前 novel-context.md 路径（工具根目录下的全局上下文）"""
    tool_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    return os.path.join(tool_root, ".omo", "notepads", "novel-context.md")


# ── 子命令：新建项目 ──────────────────────────────────────────────────────

def cmd_new(args):
    """创建新小说项目"""
    name = args.name.strip()
    genre = args.genre.strip()

    if args.v2:
        return _cmd_new_v2(args)

    volumes = args.volumes
    acts = args.acts
    structure = args.structure

    proj_dir = project_path(name)
    if os.path.exists(proj_dir):
        print(f"❌ 项目已存在: {proj_dir}")
        sys.exit(1)

    # 创建目录结构
    print(f"📁 正在创建项目「{name}」({genre})...")

    dirs = [
        "chapters",
        "chapters/.metas",
        "characters",
        "ideation",
        f"outline/分纲",
        "outline/分卷",
        "outline/情节线",
        "outline/追踪",
        "output",
        "quality",
        "styles",
        "worldbuilding",
    ]
    # 按卷创建分纲目录
    for v in range(1, volumes + 1):
        dirs.append(f"outline/分纲/第{v}卷")

    for d in dirs:
        os.makedirs(os.path.join(proj_dir, d), exist_ok=True)

    # 创建 config.yaml
    chapter_dist = _calc_chapter_distribution(volumes, acts)

    config = {
        "架构": "v1",
        "项目名称": name,
        "项目类型": genre,
        "活跃风格": "通俗网文风",
        "当前状态": "起步",
        "预期结构": f"{volumes}卷{sum(chapter_dist)}章",
        "创建时间": NOW,
        "写作进度": {
            "当前卷": 0,
            "当前章": 0,
            "卷大纲状态": "",
            "卷大纲完成数": 0,
        },
        "创作目标": {
            "目标字数": 200000,
            "目标章节数": sum(chapter_dist),
            "每日目标": 2000,
        },
    }
    save_config(name, config)

    print(f"\n✅ 项目「{name}」创建完成！")
    print(f"   路径: {proj_dir}")
    print(f"   类型: {genre}")
    print(f"   结构: {volumes}卷/{acts}幕 ({structure})")
    print(f"   章节: {'+'.join(str(d) for d in chapter_dist)} = {sum(chapter_dist)} 章")
    print()
    print(f"   下一步：运行 V2 迁移即可开始创作")
    print(f"   python .opencode/shared/cli.py migrate --project-root \"{proj_dir}\" --verify --report")
    print(f"   python .opencode/shared/cli.py v2 batch-infer --path \"{proj_dir}\"")


def _cmd_new_v2(args):
    """创建 V2 原生项目（不建旧 YAML 目录）"""
    name = args.name.strip()
    genre = args.genre.strip()

    proj_dir = project_path(name)
    if os.path.exists(proj_dir):
        print(f"❌ 项目已存在: {proj_dir}")
        sys.exit(1)

    print(f"📁 正在创建 V2 项目「{name}」({genre})...")

    # V2 目录结构（只有 graph/ 是真相源，其余是人可读的持久化层）
    dirs = [
        "graph",      # V2 叙事单元网络（真相源）
        "quality",    # 搜索分析报告输出
        "styles",     # 风格配置
        "output",     # 导出文件
    ]
    for d in dirs:
        os.makedirs(os.path.join(proj_dir, d), exist_ok=True)

    # 初始化 GraphStore 并创建初始文件
    try:
        v2_dir = os.path.join(os.path.dirname(__file__), "..", "v2")
        if v2_dir not in sys.path:
            sys.path.insert(0, v2_dir)
        from graph_store import GraphStore
        from graph_schema import EventType
        store = GraphStore(str(proj_dir))
        store.initialize()
        # 写入初始化事件，确保 JSONL 文件落盘
        store._record_event(
            EventType.SYSTEM_EVENT, actor="project_init",
            payload={"action": "project_created", "project": name},
        )
        store.flush()
        # 确保空文件也创建（nodes.jsonl / edges.jsonl 可能无内容）
        for fname in ["nodes.jsonl", "edges.jsonl"]:
            fpath = os.path.join(str(proj_dir), "graph", fname)
            if not os.path.exists(fpath):
                open(fpath, "w", encoding="utf-8").close()
        graph_ok = True
    except Exception as e:
        print(f"  ⚠️  GraphStore 初始化失败: {e}")
        print(f"  可稍后手动初始化")
        graph_ok = False

    # 创建 config.yaml（V2 精简版：运行时必需 + 项目概览字段）
    config = {
        "架构": "v2",
        "项目名称": name,
        "项目类型": genre,
        "活跃风格": "通俗网文风",
        "当前状态": "起步",
        "预期结构": "待定",
        "创建时间": NOW,
        "写作进度": {
            "当前卷": 0,
            "当前章": 0,
            "卷大纲状态": "",
            "卷大纲完成数": 0,
        },
        "创作目标": {
            "目标字数": 200000,
            "目标章节数": 40,
            "每日目标": 2000,
        },
    }
    save_config(name, config)

    print(f"\n✅ V2 项目「{name}」创建完成！")
    print(f"   路径: {proj_dir}")
    print(f"   类型: {genre}")
    print(f"   架构: V2 叙事单元网络")
    if graph_ok:
        print(f"   graph/: nodes.jsonl + edges.jsonl + events.olog 已就绪")
    print()
    print(f"   开始创作：直接告诉 novel-writer Agent 即可")


def _calc_chapter_distribution(volumes: int, acts: int) -> List[int]:
    """按卷计算章节分布（三幕比例 25:50:25，其他均匀分布）"""
    total = 100
    if acts == 3:
        # 三幕: 25-50-25
        ratios = [0.25, 0.50, 0.25]
    else:
        # 均匀分布
        ratios = [1.0 / acts] * acts
    # 每幕分配章节数
    act_chapters = [int(total * r) for r in ratios]
    # 按卷拆分
    base = total // volumes
    result = [base] * volumes
    remainder = total - base * volumes
    for i in range(remainder):
        result[i] += 1
    return result


# ── 子命令：导入 ───────────────────────────────────────────────────────────

def cmd_import(args):
    """导入已有小说项目"""
    src = args.source.strip()
    name = args.name.strip()

    if not os.path.exists(src):
        print(f"❌ 源路径不存在: {src}")
        sys.exit(1)

    proj_dir = project_path(name)
    if os.path.exists(proj_dir):
        print(f"❌ 目标项目已存在: {proj_dir}")
        sys.exit(1)

    print(f"📥 正在导入: {src} → {proj_dir}")
    shutil.copytree(src, proj_dir)
    print(f"✅ 导入完成！项目「{name}」")
    print(f"   路径: {proj_dir}")

    # 检测 V2 迁移提示
    has_graph = os.path.isdir(os.path.join(proj_dir, "graph"))
    if not has_graph:
        print()
        print(f"💡 建议执行 V2 迁移以获得完整功能：")
        print(f"   python .opencode/shared/cli.py migrate "
              f"--project-root \"{proj_dir}\" --verify --report")
        print(f"   python .opencode/shared/cli.py v2 batch-infer "
              f"--path \"{proj_dir}\"")


# ── 子命令：查看状态 ──────────────────────────────────────────────────────

def cmd_status(args):
    """查看项目状态"""
    name = args.name.strip()
    if not project_exists(name):
        print(f"❌ 项目不存在: {name}")
        sys.exit(1)

    config = load_config(name)
    if not config:
        print(f"⚠️ config.yaml 为空或格式错误")
        return

    print(f"━━━ 项目状态: {name} ━━━")
    print(f"类型: {config.get('项目类型', '未设置')}")
    print(f"活跃风格: {config.get('活跃风格', '未设置')}")
    print(f"当前状态: {config.get('当前状态', '未设置')}")
    print(f"预期结构: {config.get('预期结构', '未设置')}")

    prog = config.get("写作进度", {})
    print(f"写作进度: 第{prog.get('当前卷', 0)}卷 第{prog.get('当前章', 0)}章")
    vds = prog.get("卷大纲状态", "")
    if vds:
        print(f"卷大纲: {vds}")

    goals = config.get("创作目标", {})
    print(f"目标章节: {goals.get('目标章节数', 0)}")
    print(f"目标字数: {goals.get('目标字数', 0)}")

    # 统计（V2 优先）
    proj = project_path(name)
    is_v2 = config.get("架构") == "v2" or os.path.isdir(os.path.join(proj, "graph"))

    if is_v2:
        try:
            v2_dir = os.path.join(os.path.dirname(__file__), "..", "v2")
            if v2_dir not in sys.path:
                sys.path.insert(0, v2_dir)
            from graph_store import GraphStore
            store = GraphStore(str(proj))
            store.initialize()
            stats = store.stats()
            print(f"架构: V2（叙事单元网络）")
            print(f"叙事单元: {stats['total_units']}")
            for typ, count in sorted(stats.get('by_type', {}).items()):
                print(f"  {typ}: {count}")
            print(f"关系: {stats['total_relations']}")
        except Exception:
            print(f"架构: V2（graph/ 目录就绪）")
    else:
        char_count = len(list(Path(proj).glob("characters/*.yaml")))
        wb_count = len(list(Path(proj).glob("worldbuilding/*.yaml")))
        ch_count = len(list(Path(proj).glob("chapters/*.txt")))
        print(f"架构: V1（YAML 文件）")
        print(f"角色: {char_count} | 世界观: {wb_count} | 章节: {ch_count}")


# ── 子命令：续写 ───────────────────────────────────────────────────────────

def cmd_resume(args):
    """续写（刷新项目上下文）"""
    name = args.name.strip()
    if not project_exists(name):
        print(f"❌ 项目不存在: {name}")
        sys.exit(1)

    config = load_config(name)
    save_config(name, config)
    print(f"✅ 项目「{name}」已刷新，可以继续创作")


# ── 子命令：切换项目 ──────────────────────────────────────────────────────

def cmd_switch(args):
    """切换当前项目"""
    name = args.name.strip()
    if not project_exists(name) and not args.dry_run:
        print(f"❌ 项目不存在: {name}")
        sys.exit(1)

    ctx_path = omo_context_exists()
    if not os.path.exists(os.path.dirname(ctx_path)):
        os.makedirs(os.path.dirname(ctx_path), exist_ok=True)

    if args.dry_run:
        print(f"🔍 [Dry Run] 将切换到项目: {name}")
        print(f"   更新: {ctx_path}")
        return

    config = load_config(name) if project_exists(name) else {}

    # 生成新的 context 内容
    genre = config.get("项目类型", "未知")
    style = config.get("活跃风格", "通俗网文风")

    context = f"""__CURRENT_PROJECT__: {name}

# 项目上下文: {name}

> 由项目管理器自动生成。不要手动编辑此文件。

## 项目信息
- 项目名称：{name}
- 项目类型：{genre}
- 项目路径：{project_path(name)}
- 环境已初始化：True

## 当前状态
- 活跃风格：{style}
- 切换时间：{NOW}
"""

    with open(ctx_path, "w", encoding="utf-8") as f:
        f.write(context)

    print(f"✅ 已切换到项目「{name}」")
    print(f"   路径: {project_path(name)}")
    print(f"   类型: {genre}")
    print(f"   阶段: {phase}")

    # 检查 V2 迁移状态
    graph_dir = os.path.join(project_path(name), "graph")
    if os.path.isdir(graph_dir):
        print(f"   V2: ✅ 已迁移（graph 就绪）")
    else:
        print(f"   V2: ⬜ 未迁移（可执行 V2 迁移）")


# ── 子命令：删除项目 ──────────────────────────────────────────────────────

def cmd_delete(args):
    """删除项目"""
    name = args.name.strip()
    proj = project_path(name)

    if not os.path.isdir(proj):
        print(f"❌ 项目目录不存在: {proj}")
        sys.exit(1)

    if not args.force:
        print(f"⚠️  确认删除项目「{name}」?")
        print(f"   路径: {proj}")
        print(f"   此操作不可恢复！")
        print(f"   使用 --force 跳过确认")
        sys.exit(0)

    print(f"🗑️  正在删除项目「{name}」...")
    shutil.rmtree(proj, ignore_errors=True)
    print(f"✅ 项目「{name}」已删除")


# ── 程序化调度入口（无 argparse 依赖）─────────────────────────────────

def run_project_command(command: str, **kwargs):
    """运行项目管理命令。

    供 novel_tool.py 等程序化调用，不依赖 argparse。

    Args:
        command: 子命令名 (new/import/status/resume/switch/delete)
        **kwargs: 对应命令的参数（与 argparse 参数名一致）
    """
    from types import SimpleNamespace
    args = SimpleNamespace(**kwargs)
    dispatch = {
        "new": cmd_new,
        "import": cmd_import,
        "status": cmd_status,
        "resume": cmd_resume,
        "switch": cmd_switch,
        "delete": cmd_delete,
    }
    fn = dispatch.get(command)
    if fn:
        fn(args)
    else:
        print(f"错误: 未知命令 {command}")



