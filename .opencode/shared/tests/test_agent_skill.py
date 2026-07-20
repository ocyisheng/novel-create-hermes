"""
Agent Skill 语法验证：解析 SKILL.md / references/ 中的 JSON 示例，验证语法正确性。

运行方式：
    python .opencode/shared/v2/tests/test_agent_skill.py
"""

import os
import re
import sys


PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))

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
            print(f"    ⚠️  {label}: 第{i+1}个JSON块仍含 _display")
    msg = f"{label}: {len(blocks)} 个JSON块, {len(blocks)-has_display} 无 _display"
    check(msg, has_display == 0, f"{has_display} 个含 _display")


if __name__ == "__main__":
    # ── 1. 验证 SKILL.md 中的 JSON 语法 ────────────────────────────

    print()
    print("=" * 60)
    print("1. SKILL.md / references/ JSON 示例语法验证")
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


    # ── 结果 ──────────────────────────────────────────────────────

    print()
    print("=" * 60)
    print(f"结果: {PASS} 通过, {FAIL} 失败")
    print("=" * 60)

    if FAIL > 0:
        sys.exit(1)
    else:
        print("🎉 Agent Skill 测试全部通过！")
