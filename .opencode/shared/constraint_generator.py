"""创意约束生成器 - 基于 6 大类约束库生成创意约束组合"""

import random
import yaml
from typing import Any

# 6 大类约束
CONSTRAINT_TYPES = {
    "结构": ["非线性叙事", "倒叙开篇", "多视角交替", "环形结构", "嵌套结构"],
    "内容": ["末世背景", "日常温馨", "权谋斗争", "冒险探索", "校园生活"],
    "角色": ["反英雄主角", "多主角群像", "非人类主角", "失忆主角", "双重人格"],
    "设定": ["低魔世界", "科幻现实", "架空历史", "平行宇宙", "游戏化系统"],
    "形式": ["日记体", "书信体", "第一人称", "第三人称限知", "多线叙事"],
    "主题": ["救赎", "复仇", "成长", "真相", "自由"],
}


def load_constraints_from_file(path: str | None = None) -> dict[str, list[str]]:
    """从 YAML 文件加载约束库"""
    if path:
        try:
            with open(path, encoding="utf-8") as f:
                data = yaml.safe_load(f)
                if data and isinstance(data, dict):
                    return data
        except (FileNotFoundError, yaml.YAMLError):
            pass
    return CONSTRAINT_TYPES


def generate_combinations(
    constraints: dict[str, list[str]],
    count: int = 3,
    genre: str | None = None,
) -> list[dict[str, Any]]:
    """生成约束组合

    Args:
        constraints: 约束字典，key=大类，value=约束列表
        count: 生成组合数
        genre: 可选，指定小说类型

    Returns:
        约束组合列表
    """
    combinations = []
    type_names = list(constraints.keys())

    for i in range(count):
        combo = {}
        # 从每个大类中随机选一个约束
        for t in type_names:
            if constraints.get(t):
                combo[t] = random.choice(constraints[t])
        combinations.append({
            "组合编号": i + 1,
            "约束集": combo,
            "创作指导": _generate_guidance(combo, genre),
        })

    return combinations


def _generate_guidance(combo: dict[str, str], genre: str | None = None) -> str:
    """为约束组合生成创作指导"""
    items = list(combo.values())
    genre_hint = f"（{genre}类型）" if genre else ""
    return f"在{genre_hint}背景下，结合「{'」「'.join(items)}」这些约束，探索它们之间的化学反应和创意可能性。"


def main():
    import argparse

    parser = argparse.ArgumentParser(
        prog="constraint_generator.py",
        description="创意约束生成器",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""示例:
  python constraint_generator.py --count 3 --genre 玄幻    # 生成 3 个玄幻约束组合
  python constraint_generator.py --count 5 --genre 科幻    # 生成 5 个科幻约束组合
  python constraint_generator.py --file custom.yaml        # 使用自定义约束库

说明:
  从 6 大类约束（结构/内容/角色/设定/形式/主题）中随机组合，
  激发创意灵感。每个组合包含约束集和创作指导。"""
    )
    parser.add_argument("--count", type=int, default=3, help="生成组合数 (默认 3)")
    parser.add_argument("--genre", type=str, help="小说类型 (玄幻/科幻/都市/悬疑/历史)")
    parser.add_argument("--file", type=str, help="约束库 YAML 文件路径")
    args = parser.parse_args()

    constraints = load_constraints_from_file(args.file)
    combos = generate_combinations(constraints, args.count, args.genre)

    output = {"约束组合": combos}
    print(yaml.dump(output, allow_unicode=True, sort_keys=False))


if __name__ == "__main__":
    main()
