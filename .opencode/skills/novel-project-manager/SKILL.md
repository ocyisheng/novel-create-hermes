---
name: "novel-project-manager"
description: "小说项目管理。新建/导入/查看状态/续写/删除。触发词：新建项目、导入项目、查看状态、续写、删除项目、项目管理、novel project"
license: "MIT"
version: "3.0.0"
compatibility: "OpenCode"
tags: ["novel", "project-management"]
---

# 小说项目管理

## 操作方式

通过 `bash` 执行 Python 脚本：

### 新建项目
```bash
# 标准三卷三幕（默认）
python .opencode/skills/novel-project-manager/scripts/init.py new "项目名" "玄幻"

# 五卷五幕史诗结构
python .opencode/skills/novel-project-manager/scripts/init.py new "星辰帝国" "玄幻" --volumes 5 --structure 五幕

# 四卷三幕（自定义幕数）
python .opencode/skills/novel-project-manager/scripts/init.py new "迷雾追踪" "悬疑" --volumes 4 --acts 3
```
创建标准目录、config.yaml、模板文件。项目默认创建到工具根目录下的 `novels/` 子目录（可通过 `-d` 指定其他位置）。卷数 (`--volumes`) 和幕结构 (`--structure`/`--acts`) 控制生成的分纲目录数和总纲模板格式。

💡 项目创建完成后，init.py 已自动完成初始实体索引（无需手动运行）。

### 导入已有小说
```bash
python .opencode/skills/novel-project-manager/scripts/init.py import "源路径" "项目名"
```
导入完成。

💡 导入完成后，init.py 已自动完成初始实体索引（无需手动运行）。

### 查看状态
```bash
python .opencode/skills/novel-project-manager/scripts/init.py status "项目名" [--phase 阶段] [--intervention high|medium|low]
```

### 续写
```bash
python .opencode/skills/novel-project-manager/scripts/init.py resume "项目名"
```

### 删除
```bash
python .opencode/skills/novel-project-manager/scripts/init.py delete "项目名" [--force]
```

## 前提

- Python 环境已初始化（先调用 `novel-env-setup`）
- 项目目录所在父目录存在 `.venv/`

## 触发词映射

| 用户说 | 子命令 | 必需参数 |
|--------|--------|---------|
| "新建/创建 项目" | new | 项目名、类型 |
| "导入 小说/项目" | import | 源路径、项目名 |
| "查看 状态/进度" | status | 项目名 |
| "续写/继续" | resume | 项目名 |
| "删除/移除 项目" | delete | 项目名 |

## 参考文件

- `references/project_structure.md` — 小说项目标准目录结构
- `references/import_guide.md` — 导入已有项目的详细指引

## HARD CONSTRAINTS

1. 首次使用前确保 `.venv` 存在（调用 `novel-env-setup`）
2. 输出为 YAML 格式
3. 删除操作无 `--force` 时必须确认
