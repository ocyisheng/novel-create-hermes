# 检查点规则格式规范（统一标准）

本文档是 novel-checkpoint-service 中所有 `checkpoint_rules` 操作的**单一事实源**。
所有技能的规则定义、项目覆盖均以此为准。

---

## 1. 语法格式

### 内置规则文件（`default_rules.yaml`）

```yaml
default: "continue"

checkpoints:
  writing_after_outline:
    high: pause
    medium: pause
    low: pause
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `default` | string | 未匹配检查点/等级时的默认决策 |
| `checkpoints` | dict | 检查点字典，key 为检查点名称 |
| `checkpoints.<name>.<level>` | string | 决策值，支持 `pause` / `continue` / `auto_fix` |

### 可用的干预等级

| 等级 | 说明 |
|------|------|
| `high` | 高干预：关键步骤后暂停 |
| `medium` | 中干预：主要节点暂停 |
| `low` | 低干预：仅强制要求暂停的节点暂停 |

### 可用的决策值

| 决策 | 行为 | 适用场景 |
|------|------|---------|
| `pause` | 暂停等待用户确认 | 需要用户审核/干预的节点 |
| `continue` | 自动继续，不中断 | 无需用户干预的节点 |
| `auto_fix` | 自动修复后继续 | 低干预等级下的自动修复 |

---

## 2. 项目覆盖规则

### 在 `config.yaml` 中覆盖

```yaml
# 项目根目录下的 config.yaml
checkpoint_rules:
  writing_after_chapters:
    high: pause          # 覆盖内置的 continue → pause
  quality_after_pacing:
    high: pause          # 覆盖内置的 continue → pause
    medium: pause
  after_chapter_generated:   # 新增检查点（内置规则中没有）
    high: pause
    medium: continue
    low: continue
```

### 合并规则

```
1. 内置规则从 default_rules.yaml 加载
2. 项目覆盖从 config.yaml 的 checkpoint_rules 段加载
3. 合并：项目覆盖规则 dict.update 内置规则

合并结果：
  - 项目覆盖中定义的检查点 → 覆盖内置规则
  - 项目覆盖中未定义的检查点 → 保持内置规则不变
  - 项目覆盖中定义但内置规则中没有的 → 新增检查点
```

---

## 3. 调用路径规范

### CLI（Agent 层）

```bash
# 从项目根目录调用
python .opencode/skills/novel-checkpoint-service/scripts/checkpoint_service.py check writing_after_outline high

# 返回
# {
#   "checkpoint": "writing_after_outline",
#   "level": "high",
#   "decision": "pause"
# }
```

### Python API（脚本层）

```python
import sys
from pathlib import Path

SERVICE_DIR = Path(__file__).parent.parent.parent / "novel-checkpoint-service" / "scripts"
sys.path.insert(0, str(SERVICE_DIR))

from checkpoint_service import check_pause, is_pause, get_checkpoints, reload_rules

# 查询决策
decision = check_pause("writing_after_outline", "high")

# 布尔判断
if is_pause("writing_after_outline", "high"):
    # 暂停逻辑...
    pass
```

---

## 4. 完整内置检查点列表

参考 `scripts/default_rules.yaml` 中的完整清单，包括：

| 技能包 | 检查点 | 作用 |
|--------|--------|------|
| Ideation | `ideation_after_requirements` | 需求分析完成后 |
| Ideation | `ideation_after_concept` | 核心创意生成后 |
| Writing | `writing_after_requirements` | 写作需求分析后 |
| Writing | `writing_after_outline` | **大纲完成后（强制暂停）** |
| Quality | `quality_after_requirements` | 质量需求分析后 |
| Quality | `quality_after_full_evaluation` | 完整质量评估后（low 自动修复） |
| Project | `project_after_new` | 新建项目后 |
| ... | ... | ... |

完整列表请查看 `default_rules.yaml`。

---

## 5. 自检清单

- [ ] 规则文件中的 `checkpoints` 字段名是否正确？
- [ ] 决策值是否在 `pause` / `continue` / `auto_fix` 中？
- [ ] 项目覆盖规则的格式是否正确（`checkpoint_rules` 在 YAML 顶层）？
- [ ] 调用时使用的检查点名称是否与规则文件中一致？
- [ ] 当前工作目录是否在项目根目录？
