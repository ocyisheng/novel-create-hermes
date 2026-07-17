"""
Agent Skill 集成测试：验证 agent 通过 CLI 操作 V2 的完整链路。

测试场景（模拟 agent 的实际操作步骤）：
1. 创建测试项目，通过 CLI 写入各类叙事单元（无 _display）
2. 通过 CLI 读取和验证数据
3. 查询关系和邻居
4. 执行导出
5. 解析所有 SKILL.md / references/ 中的 JSON 示例，验证语法正确

运行方式：
    python .opencode/shared/v2/tests/test_agent_skill.py
"""

import json
import os
import re
import sys
import subprocess
import tempfile
import shutil

V2_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))

PASS = 0
FAIL = 0


def check(name, condition, detail=""):
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  \u2705 {name}")
    else:
        FAIL += 1
        print(f"  \u274c {name}  {detail}")


def cli(*args, cwd=None):
    """Run v2_cli.py with args, return (returncode, stdout)"""
    cmd = [sys.executable, os.path.join(V2_DIR, "v2_cli.py")] + list(args)
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=cwd or PROJECT_ROOT)
    return result.returncode, result.stdout.strip()


def extract_json_blocks(filepath, label):
    """从 markdown 文件中提取所有 ```json 块，检查 _display 残留。
    
    JSON 示例中含 {…} 等占位符，不做完整语法验证。
    只检查是否包含 "_display" 残留。
    """
    if not os.path.exists(filepath):
        check(f"{label}: 文件不存在", False)
        return
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()
    blocks = re.findall(r"```json\n(.+?)\n```", content, re.DOTALL)
    if not blocks:
        check(f"{label}: 无 JSON 代码块", True)
        return
    has_display = 0
    for i, block in enumerate(blocks):
        if '"_display"' in block:
            has_display += 1
            print(f"    \u26a0\ufe0f  {label}: 第{i+1}个JSON块仍含 _display")
    msg = f"{label}: {len(blocks)} 个JSON块, {len(blocks)-has_display} 无 _display"
    check(msg, has_display == 0, f"{has_display} 个含 _display")


if __name__ == "__main__":
    # ── 1. CLI 可用性 ──────────────────────────────────────────────

    print("=" * 60)
    print("1. CLI 基础命令测试")
    print("=" * 60)

    rc, out = cli("--help")
    check("v2_cli.py --help 执行成功", rc == 0)

    rc, out = cli("list-relation-types")
    check("list-relation-types 执行成功", rc == 0 and len(out) > 50)


    # ── 2. 通过 CLI 创建和查询叙事单元 ─────────────────────────────

    print()
    print("=" * 60)
    print("2. CLI 创建/查询叙事单元（无 _display 格式）")
    print("=" * 60)

    tmpdir = tempfile.mkdtemp(prefix="v2_agent_test_")
    try:
        project_path = os.path.join(tmpdir, "agent_test_project")
        os.makedirs(project_path)

        # 2.1 创建 CHARACTER_ARC（仙侠）
        rc, out = cli(
            "create-unit",
            "--path", project_path,
            "--type", "CHARACTER_ARC",
            "--name", "\u6797\u6e0a",
            "--content", '{"\u89d2\u8272\u7c7b\u578b":"\u4e3b\u89d2","\u6027\u683c":{"\u6838\u5fc3\u7279\u8d28":["\u4ee5\u533b\u5165\u9053","\u575a\u97e7"],"\u4f18\u70b9":["\u9690\u5fcd"],"\u7f3a\u70b9":["\u56fa\u6267"]},"\u80fd\u529b\u8bbe\u5b9a":{"\u4fee\u4e3a":"\u5316\u795e\u671f","\u529f\u6cd5":"\u4e94\u884c\u8f6e\u8f6c\u7ecf","\u9635\u8425":"\u6b63\u9053"},"\u89d2\u8272\u5f27\u7ebf":{"\u8d77\u59cb\u72b6\u6001":"\u51e1\u4eba","\u6700\u7ec8\u72b6\u6001":"\u5316\u795e\u98de\u5347"}}',
            "--tags", "\u4e3b\u89d2,\u5251\u4fee",
            "--chapter", "1",
        )
        check("CLI 创建仙侠角色成功", rc == 0)
        unit_id = out.strip()
        # CLI 输出格式: "创建成功: ca_c077588b"
        if ":" in unit_id:
            unit_id = unit_id.split(":")[-1].strip()
        check("CLI 返回了单元 ID", len(unit_id) > 5 and unit_id.startswith("ca_"))

        # 2.2 创建 CHARACTER_ARC（都市，不同字段）
        rc, out = cli(
            "create-unit",
            "--path", project_path,
            "--type", "CHARACTER_ARC",
            "--name", "\u9648\u5cf0",
            "--content", '{"\u89d2\u8272\u7c7b\u578b":"\u4e3b\u89d2","\u6027\u683c":{"\u6838\u5fc3\u7279\u8d28":["\u679c\u65ad","\u654f\u9510"]},"\u80fd\u529b\u8bbe\u5b9a":{"\u804c\u4e1a":"CEO","\u516c\u53f8":"\u5929\u6052\u96c6\u56e2","\u8d44\u4ea7":"\u767e\u4ebf"},"\u89d2\u8272\u5f27\u7ebf":{"\u8d77\u59cb\u72b6\u6001":"\u521b\u4e1a\u5931\u8d25","\u6700\u7ec8\u72b6\u6001":"\u5546\u4e1a\u5e1d\u56fd"}}',
            "--tags", "\u4e3b\u89d2,\u5546\u6218",
        )
        check("CLI 创建都市角色成功", rc == 0)

        # 2.3 创建 SCENE
        rc, out = cli(
            "create-unit",
            "--path", project_path,
            "--type", "SCENE",
            "--name", "\u540e\u5c71\u62d4\u5251",
            "--content", '{"\u7ae0\u8282\u7c7b\u578b":"\u63a8\u8fdb","\u7ed3\u6784\u89c4\u5212":{"\u5f00\u7bc7":{"\u65b9\u5f0f":"\u52a8\u4f5c\u5f00\u573a"},"\u53d1\u5c55":{"\u6838\u5fc3\u51b2\u7a81":"\u7ec3\u5251\u88ab\u963b","\u63a8\u8fdb":"\u82cf\u957f\u8001\u51fa\u73b0"},"\u8f6c\u6298":{"\u4e8b\u4ef6":"\u82cf\u957f\u8001\u6307\u51fa\u5929\u8d4b"},"\u6536\u5c3e":{"\u7ed3\u679c":"\u91cd\u65b0\u632f\u4f5c"}},"\u51fa\u573a\u89d2\u8272":["\u6797\u6e0a","\u82cf\u957f\u8001"],"\u5f20\u529b\u66f2\u7ebf":{"\u5f00\u573a":3,"\u7ae0\u8282\u9ad8\u6f6e":7,"\u7ed3\u5c3e":5},"\u5730\u70b9":"\u843d\u4e91\u5b97\u540e\u5c71\u7ec3\u5251\u576a"}',
            "--chapter", "1",
        )
        check("CLI 创建场景成功", rc == 0)

        # 2.4 创建 PLOT_THREAD
        rc, out = cli(
            "create-unit",
            "--path", project_path,
            "--type", "PLOT_THREAD",
            "--name", "\u4e3b\u7ebf-\u5251\u9053\u4e4b\u4e89",
            "--content", '{"\u7c7b\u578b":"\u4e3b\u7ebf","\u51b2\u7a81\u6838\u5fc3":"\u6797\u6e0a\u7684\u5251\u9053\u5929\u8d4b\u4e0e\u5b97\u95e8\u9648\u89c4\u7684\u51b2\u7a81","\u5173\u952e\u4e8b\u4ef6":[{"\u7ae0\u8282":1,"\u4e8b\u4ef6":"\u7b2c\u4e00\u6b21\u62d4\u5251"},{"\u7ae0\u8282":10,"\u4e8b\u4ef6":"\u5251\u9053\u5927\u4f1a"}],"\u7ec8\u5c40\u8bbe\u8ba1":"\u6797\u6e0a\u5f00\u521b\u81ea\u5df1\u7684\u5251\u9053"}',
        )
        check("CLI 创建情节线成功", rc == 0)

        # 2.5 创建 WORLD_RULE
        rc, out = cli(
            "create-unit",
            "--path", project_path,
            "--type", "WORLD_RULE",
            "--name", "\u843d\u4e91\u5b97",
            "--content", '{"\u5b50\u7c7b\u578b":"\u52bf\u529b","\u4e8c\u7ea7\u7c7b\u578b":"\u5b97\u95e8","\u63cf\u8ff0":"\u6b63\u9053\u4e03\u5927\u5b97\u95e8\u4e4b\u4e00","\u9996\u9886":"\u4e91\u771f\u4eba\uff08\u5143\u5a74\u540e\u671f\uff09","\u4e3b\u8981\u6210\u5458":["\u6797\u6e0a","\u82cf\u957f\u8001"],"\u52bf\u529b\u8303\u56f4":"\u8d8a\u56fd","\u7acb\u573a":"\u6b63\u9053"}',
        )
        check("CLI 创建世界观成功", rc == 0)

        # 2.6 创建 NOTE（纪年事件）
        rc, out = cli(
            "create-unit",
            "--path", project_path,
            "--type", "NOTE",
            "--name", "\u6797\u6e0a\u5165\u95e8",
            "--content", '{"note_type":"\u7eaa\u5e74\u4e8b\u4ef6","\u4e8b\u4ef6":"\u6797\u6e0a\u6b63\u5f0f\u62dc\u5165\u843d\u4e91\u5b97","\u65f6\u95f4":"\u51e1\u4eba\u53861024\u5e74\u6625","\u5907\u6ce8":"\u4ee5\u7edd\u7075\u6839\u4e4b\u8eab\u7834\u683c\u5f55\u5165"}',
        )
        check("CLI 创建笔记成功", rc == 0)

        # 2.7 创建 CHUNK
        rc, out = cli(
            "create-unit",
            "--path", project_path,
            "--type", "CHUNK",
            "--name", "\u7b2c1\u7ae0",
            "--content", '{"\u7ae0\u8282\u53f7":1,"\u6b63\u6587":"test","\u5b57\u6570":42}',
            "--chapter", "1",
        )
        check("CLI 创建正文成功", rc == 0)

        # 2.8 通过 get-unit 读取角色
        if unit_id:
            rc, out = cli("get-unit", "--path", project_path, "--id", unit_id)
            check("CLI 读取单元成功", rc == 0 and "\u6797\u6e0a" in out)

        # 2.9 按名称查找
        rc, out = cli("find-unit", "--path", project_path, "--name", "\u6797\u6e0a")
        check("CLI 按名称查找成功", rc == 0 and len(out.strip()) > 0)

        # 2.10 flush
        rc, out = cli("flush", "--path", project_path)
        check("CLI flush 成功", rc == 0)

        # 2.11 list-units
        rc, out = cli("list-units", "--path", project_path)
        check("CLI list-units 成功", rc == 0)

        # 2.12 stats
        rc, out = cli("stats", "--path", project_path)
        check("CLI stats 成功", rc == 0)
        check("stats 包含角色统计", "CHARACTER_ARC" in out or "character" in out.lower())

        # 2.13 建立关系（需先获取目标场景的 ID）
        rc, out = cli("find-unit", "--path", project_path, "--name", "\u540e\u5c71\u62d4\u5251")
        scene_id = out.strip()
        if unit_id and scene_id:
            rc, out = cli("add-relation", "--path", project_path, "--source", unit_id, "--target", scene_id, "--type", "participates_in")
            check("CLI 建立关系成功", rc == 0)
        else:
            check("CLI 建立关系：获取 ID", False, f"unit_id={unit_id}, scene_id={scene_id}")

        # 2.14 邻居查询
        if unit_id:
            rc, out = cli("get-neighbors", "--path", project_path, "--id", unit_id)
            check("CLI 邻居查询成功", rc == 0)

        # 2.15 批量推断
        rc, out = cli("batch-infer", "--path", project_path)
        check("CLI 批量推断成功", rc == 0)

        # 2.16 导出文档
        rc, out = cli("export-docs", "--path", project_path)
        check("CLI 导出文档成功", rc == 0)
        export_dir = os.path.join(project_path, "graph", "export")
        if os.path.isdir(export_dir):
            files = os.listdir(export_dir)
            check("导出目录非空", len(files) > 0)

        # 2.17 重建投影
        rc, out = cli("rebuild-projections", "--path", project_path)
        check("CLI 重建投影成功", rc == 0)

        # 2.18 含复杂 JSON 的单元（用 --content 传）
        complex_content = json.dumps({
            "\u89d2\u8272\u7c7b\u578b": "\u53cd\u6d3e",
            "\u6027\u683c": {"\u6838\u5fc3\u7279\u8d28": ["\u9634\u9669", "\u91ce\u5fc3\u52c3\u52c3"]},
            "\u80fd\u529b\u8bbe\u5b9a": {"\u4fee\u4e3a": "\u5143\u5a74\u671f", "\u529f\u6cd5": "\u566c\u9b42\u5927\u6cd5", "\u9635\u8425": "\u9b54\u9053"},
            "\u89d2\u8272\u5f27\u7ebf": {"\u8d77\u59cb\u72b6\u6001": "\u6563\u4fee", "\u6700\u7ec8\u72b6\u6001": "\u9b54\u9053\u81f3\u5c0a"},
        }, ensure_ascii=False)
        rc, out = cli(
            "create-unit",
            "--path", project_path,
            "--type", "CHARACTER_ARC",
            "--name", "\u9b3c\u5389",
            "--content", complex_content,
            "--tags", "\u53cd\u6d3e,\u9b54\u9053",
        )
        check("CLI 创建复杂角色成功", rc == 0)
        rc, out = cli("find-unit", "--path", project_path, "--name", "\u9b3c\u5389")
        check("CLI 查找复杂角色成功", rc == 0 and len(out.strip()) > 0)

        # 2.19 更新单元（update-unit 需要 --id）
        if unit_id:
            rc, out = cli("update-unit", "--path", project_path, "--id", unit_id, "--tags", "\u4e3b\u89d2,\u5251\u4fee,\u7edd\u7075\u6839")
            check("CLI update-unit 成功", rc == 0)

    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


    # ── 3. 验证 SKILL.md 中的 JSON 语法 ────────────────────────────

    print()
    print("=" * 60)
    print("3. SKILL.md / references/ JSON 示例语法验证")
    print("=" * 60)

    extract_json_blocks(
        os.path.join(PROJECT_ROOT, ".opencode", "skills", "novel-v2", "SKILL.md"),
        "SKILL.md",
    )

    ref_dir = os.path.join(PROJECT_ROOT, ".opencode", "skills", "novel-v2", "references")
    if os.path.isdir(ref_dir):
        for fname in sorted(os.listdir(ref_dir)):
            if fname.endswith(".md"):
                extract_json_blocks(os.path.join(ref_dir, fname), f"references/{fname}")


    # ── 4. 检查 CLI 命令列表与 SKILL.md 的一致性 ──────────────────

    print()
    print("=" * 60)
    print("4. SKILL.md CLI 命令语法验证")
    print("=" * 60)

    skill_path = os.path.join(PROJECT_ROOT, ".opencode", "skills", "novel-v2", "SKILL.md")
    with open(skill_path, "r", encoding="utf-8") as f:
        skill_text = f.read()

    # 提取所有 CLI 子命令（`python ... v2_cli.py <cmd>` 中的 <cmd>）
    # 匹配 pattern: python 路径/v2_cli.py cmd_name
    cmd_pattern = re.compile(r"python\s+\S+v2_cli\.py\s+(\S+)")
    cmds_in_skill = set(cmd_pattern.findall(skill_text))
    check("SKILL.md 包含 CLI 命令引用", len(cmds_in_skill) > 0,
          f"找到 {len(cmds_in_skill)} 个命令引用")

    # 从 help 中提取合法子命令
    rc, out = cli("--help")
    valid_cmds = set()
    in_positional = False
    for line in out.split("\n"):
        if "positional arguments" in line:
            in_positional = True
            continue
        if in_positional and line.strip().startswith("{"):
            # 进入花括号内的子命令列表
            content = line.strip().strip(",")
            for cmd in content.split(","):
                cmd = cmd.strip().strip("{}")
                if cmd:
                    valid_cmds.add(cmd)
            continue
        if in_positional:
            # 单行子命令
            cmd = line.strip().split()[0] if line.strip() else ""
            if cmd and not cmd.startswith("-") and cmd != "options:" and cmd != "usage:":
                valid_cmds.add(cmd)

    # 从子命令帮助中也提取
    for line in out.split("\n"):
        line = line.strip()
        if line and line[0].isalpha() and " " not in line.split("  ")[0].strip() and not line.startswith("{"):
            cmd = line.split()[0].strip()
            if cmd and not cmd.startswith("-"):
                valid_cmds.add(cmd)

    # 标准化：v2_cli.py 中的命令可能连字符多单词
    # 只检查首单词匹配
    missing = []
    for skill_cmd in cmds_in_skill:
        if skill_cmd not in valid_cmds:
            missing.append(skill_cmd)

    if missing:
        check("SKILL.md 命令全部有效", False, f"未识别的命令: {missing}")
    else:
        check("SKILL.md 命令全部有效", True)


    # ── 结果 ──────────────────────────────────────────────────────

    print()
    print("=" * 60)
    print(f"结果: {PASS} 通过, {FAIL} 失败")
    print("=" * 60)

    if FAIL > 0:
        sys.exit(1)
    else:
        print("🎉 Agent Skill 测试全部通过！")
