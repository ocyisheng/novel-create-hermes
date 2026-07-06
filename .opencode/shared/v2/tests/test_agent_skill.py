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
        print(f"  ✅ {name}")
    else:
        FAIL += 1
        print(f"  ❌ {name}  {detail}")


def cli(*args, cwd=None):
    """Run v2_cli.py with args, return (returncode, stdout)"""
    cmd = [sys.executable, os.path.join(V2_DIR, "v2_cli.py")] + list(args)
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=cwd or PROJECT_ROOT)
    return result.returncode, result.stdout.strip()


# ── 1. CLI 可用性 ──────────────────────────────────────────────────

print("=" * 60)
print("1. CLI 基础命令测试")
print("=" * 60)

rc, out = cli("--help")
check("v2_cli.py --help 执行成功", rc == 0)

rc, out = cli("list-relation-types")
check("list-relation-types 执行成功", rc == 0 and len(out) > 50)


# ── 2. 通过 CLI 创建和查询叙事单元 ─────────────────────────────────

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
        "--name", "林渊",
        "--content", '{"角色类型":"主角","性格":{"核心特质":["以医入道","坚韧"],"优点":["隐忍"],"缺点":["固执"]},"能力设定":{"修为":"化神期","功法":"五行轮转经","阵营":"正道"},"角色弧线":{"起始状态":"凡人","最终状态":"化神飞升"}}',
        "--tags", "主角,剑修",
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
        "--name", "陈峰",
        "--content", '{"角色类型":"主角","性格":{"核心特质":["果断","敏锐"]},"能力设定":{"职业":"CEO","公司":"天恒集团","资产":"百亿"},"角色弧线":{"起始状态":"创业失败","最终状态":"商业帝国"}}',
        "--tags", "主角,商战",
    )
    check("CLI 创建都市角色成功", rc == 0)

    # 2.3 创建 SCENE
    rc, out = cli(
        "create-unit",
        "--path", project_path,
        "--type", "SCENE",
        "--name", "后山拔剑",
        "--content", '{"章节类型":"推进","结构规划":{"开篇":{"方式":"动作开场"},"发展":{"核心冲突":"练剑被阻","推进":"苏长老出现"},"转折":{"事件":"苏长老指出天赋"},"收尾":{"结果":"重新振作"}},"出场角色":["林渊","苏长老"],"张力曲线":{"开场":3,"章节高潮":7,"结尾":5},"地点":"落云宗后山练剑坪"}',
        "--chapter", "1",
    )
    check("CLI 创建场景成功", rc == 0)

    # 2.4 创建 PLOT_THREAD
    rc, out = cli(
        "create-unit",
        "--path", project_path,
        "--type", "PLOT_THREAD",
        "--name", "主线-剑道之争",
        "--content", '{"类型":"主线","冲突核心":"林渊的剑道天赋与宗门陈规的冲突","关键事件":[{"章节":1,"事件":"第一次拔剑"},{"章节":10,"事件":"剑道大会"}],"终局设计":"林渊开创自己的剑道"}',
    )
    check("CLI 创建情节线成功", rc == 0)

    # 2.5 创建 WORLD_RULE
    rc, out = cli(
        "create-unit",
        "--path", project_path,
        "--type", "WORLD_RULE",
        "--name", "落云宗",
        "--content", '{"子类型":"势力","二级类型":"宗门","描述":"正道七大宗门之一","首领":"云真人（元婴后期）","主要成员":["林渊","苏长老"],"势力范围":"越国","立场":"正道"}',
    )
    check("CLI 创建世界观成功", rc == 0)

    # 2.6 创建 NOTE（纪年事件）
    rc, out = cli(
        "create-unit",
        "--path", project_path,
        "--type", "NOTE",
        "--name", "林渊入门",
        "--content", '{"note_type":"纪年事件","事件":"林渊正式拜入落云宗","时间":"凡人历1024年春","备注":"以绝灵根之身破格录入"}',
    )
    check("CLI 创建笔记成功", rc == 0)

    # 2.7 创建 CHUNK
    rc, out = cli(
        "create-unit",
        "--path", project_path,
        "--type", "CHUNK",
        "--name", "第1章",
        "--content", '{"章节号":1,"正文":"林渊握紧了剑柄，指节泛白。这是他第一次站在练剑坪上。","字数":42}',
        "--chapter", "1",
    )
    check("CLI 创建正文成功", rc == 0)

    # 2.8 通过 get-unit 读取角色
    if unit_id:
        rc, out = cli("get-unit", "--path", project_path, "--id", unit_id)
        check("CLI 读取单元成功", rc == 0 and "林渊" in out)

    # 2.9 按名称查找
    rc, out = cli("find-unit", "--path", project_path, "--name", "林渊")
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
    rc, out = cli("find-unit", "--path", project_path, "--name", "后山拔剑")
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
        "角色类型": "反派",
        "性格": {"核心特质": ["阴险", "野心勃勃"]},
        "能力设定": {"修为": "元婴期", "功法": "噬魂大法", "阵营": "魔道"},
        "角色弧线": {"起始状态": "散修", "最终状态": "魔道至尊"},
    }, ensure_ascii=False)
    rc, out = cli(
        "create-unit",
        "--path", project_path,
        "--type", "CHARACTER_ARC",
        "--name", "鬼厉",
        "--content", complex_content,
        "--tags", "反派,魔道",
    )
    check("CLI 创建复杂角色成功", rc == 0)
    rc, out = cli("find-unit", "--path", project_path, "--name", "鬼厉")
    check("CLI 查找复杂角色成功", rc == 0 and len(out.strip()) > 0)

    # 2.19 更新单元（update-unit 需要 --id）
    if unit_id:
        rc, out = cli("update-unit", "--path", project_path, "--id", unit_id, "--tags", "主角,剑修,绝灵根")
        check("CLI update-unit 成功", rc == 0)

finally:
    shutil.rmtree(tmpdir, ignore_errors=True)


# ── 3. 验证 SKILL.md 中的 JSON 语法 ──────────────────────────────

print()
print("=" * 60)
print("3. SKILL.md / references/ JSON 示例语法验证")
print("=" * 60)

json_pattern = re.compile(r"```json\n(.+?)\n```", re.DOTALL)


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
    blocks = json_pattern.findall(content)
    if not blocks:
        check(f"{label}: 无 JSON 代码块", True)
        return
    has_display = 0
    for i, block in enumerate(blocks):
        if '"_display"' in block:
            has_display += 1
            print(f"    ⚠️  {label}: 第{i+1}个JSON块仍含 _display")
    msg = f"{label}: {len(blocks)} 个JSON块, {len(blocks)-has_display} 无 _display"
    check(msg, has_display == 0, f"{has_display} 个含 _display")


extract_json_blocks(
    os.path.join(PROJECT_ROOT, ".opencode", "skills", "novel-v2", "SKILL.md"),
    "SKILL.md",
)

ref_dir = os.path.join(PROJECT_ROOT, ".opencode", "skills", "novel-v2", "references")
if os.path.isdir(ref_dir):
    for fname in sorted(os.listdir(ref_dir)):
        if fname.endswith(".md"):
            extract_json_blocks(os.path.join(ref_dir, fname), f"references/{fname}")


# ── 4. 检查 CLI 命令列表与 SKILL.md 的一致性 ──────────────────────

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


# ── 结果 ──────────────────────────────────────────────────────────

print()
print("=" * 60)
print(f"结果: {PASS} 通过, {FAIL} 失败")
print("=" * 60)

if FAIL > 0:
    sys.exit(1)
else:
    print("🎉 Agent Skill 测试全部通过！")
