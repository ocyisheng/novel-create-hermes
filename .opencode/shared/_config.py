"""_config.py — 全系统共享常量（单一真实源）

所有技能包和共享脚本需要跨模块引用的配置常量集中在此。
被 skills/*/SKILL.md 和 shared/*.py 共同引用。
"""

# ── 实体扫描配置 ──────────────────────────────────────────────────────────────
# 定义项目目录下各实体类型的扫描目录、文件模式、索引字段映射。
# 被 rebuild_project_index.py 和 validate_entity_format.py 共同使用。

ENTITY_SCAN_CONFIG = {
    "characters": {
        "dir": "characters",
        "glob": "*.yaml",
        "skip": [],
        "id_path": "索引信息.实体ID",
        "fields": {
            "name": "索引信息.名称",
            "status": "索引信息.状态",
            "one_line": "摘要.一句话描述",
        },
        "extra": {
            "type": "索引信息.角色类型",
            "first_chapter": "索引信息.首次出场章节",
        },
    },
    "worldbuilding": {
        "dir": "worldbuilding",
        "glob": "*.yaml",
        "skip": [],
        "id_path": "索引信息.实体ID",
        "fields": {
            "name": "索引信息.名称",
            "status": "索引信息.状态",
            "one_line": "摘要.一句话描述",
        },
        "extra": {
            "subtype": "索引信息.实体子类型",
        },
    },
    "plot_threads": {
        "dir": "outline/情节线",
        "glob": "*.yaml",
        "skip": ["主索引.yaml"],
        "id_path": "索引信息.实体ID",
        "fields": {
            "name": "索引信息.名称",
            "status": "索引信息.状态",
            "one_line": "摘要.一句话描述",
        },
        "extra": {
            "first_chapter": "索引信息.起始章节",
            "start_time": "索引信息.起始时间",
            "end_time": "索引信息.结束时间",
        },
    },
    "chapters": {
        "dir": "outline/分纲",
        "glob": "**/*.yaml",
        "skip": [],
        "id_path": "索引信息.实体ID",
        "fields": {
            "name": "索引信息.名称",
            "status": "索引信息.状态",
            "one_line": "摘要.一句话描述",
        },
        "extra": {
            "chapter_num": "索引信息.章节号",
        },
    },
}
