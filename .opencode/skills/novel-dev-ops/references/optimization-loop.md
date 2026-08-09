# 优化闭环流程（附录 C）

聚合分析产出改进清单后，编排层将其映射到具体可操作的改进任务，覆盖项目的各个层面。

## C.1 改进维度映射

聚类线索按类型自动映射到项目中的改进目标：

| 线索类型 | 改进维度 | 具体目标 | 执行方式（含多步可执行清单） |
|---------|---------|---------|---------|
| `schema` | Graph 数据模型 | 单元字段、关系类型、edge 定义 | ① 定位缺失/错误的字段定义 ② 修改 `graph_store.py` schema 校验 ③ 更新 skill 文档中的单元类型说明 ④ 运行 `novel-tool(operation="graph.check")` 验证 |
| `prompt` | Agent 调度逻辑 | `novel-writer.md` 路由表、§3 焦点路由、§5 调度模板 | ① 定位缺失/错误的判断分支（从「过程回放」的根因反推具体行号） ② 写出修正后的分支条件 ③ 更新对应路由表单元格 ④ 关联触发场景的描述（防止同类误判再现） |
| `handler` | 业务逻辑 | `handlers_*.py` 中的处理函数 | ① 定位函数 + 有问题的代码行 ② 写出修正后的逻辑 ③ 添加/更新测试用例 |
| `skill` | 创作能力 | `.opencode/skills/*/SKILL.md` 操作指南 | ① 定位缺失/错误的操作步骤 ② 更新 skill 文档 ③ 同步更新触发词列表（如有） |
| `workflow` | 编排流程 | `novel-writer.md` 主循环、§3 决策树、§5 调度模板 | ① 从「过程回放」的第 1 轮根因提取"缺了哪步前置判断" ② 在主循环路由树中插入新分支/检查点 ③ 更新对应的调度模板或注入规则 ④ 在 A.1 迭代过程的说明中新增"触发条件"描述 |
| `tool` | 工具层 | `novel-tool` 参数、返回格式 | ① 定位参数/返回值问题 ② 修改 `novel_tool.py` 适配层或 `__init__.py` 注册 ③ 更新 handlers 对应函数签名 |

## C.2 生成改进任务清单

编排层通过 `novel-tool(operation="analysis.read")` 读取改进清单后，将聚类线索转化为具体改进任务：

```markdown
## 改进任务清单（来自优化线索聚合分析）

### critical
1. **[schema] graph_store.py**：为 timeline_event 单元增加 `location` 和 `volume_ref` 字段
   - 来源线索：时间线事件缺少位置信息 × 3 次
   - 过程回放：3 次都是创建 timeline_event 时发现没有位置字段可用
   - 改动范围：① graph_store.py schema 校验 → ② novel-v2 skill §3 操作指南 → ③ 存量数据补 migration
   - 验证方式：创建 timeline_event 时强制要求 location 字段

2. **[workflow] 编排层·跨卷角色路径规划**：缺前置关键事件列表检查
   - 来源线索：吕风路径 3 轮修正才收敛（2026-07-24）
   - 过程回放：
     · 第1轮：凭单卷数据规划 → 用户纠正→根因：未加载关键事件列表
     · 第2轮：改走散 → 用户纠正→根因：漏了中间过渡节点
     · 第3轮：补过渡再重逢 → 用户纠正→根因：忽略地理约束
   - 改动范围：① 主循环处理跨卷角色路径前插入 event_list 检查点 → ② `novel-tool(operation="graph.get_neighbors")` 调用 → ③ distance 元数据约束校验步骤
   - 验证方式：下次跨卷角色路径规划 ≤1 轮收敛

### high
3. **[prompt] novel-writer.md**：路由表增加"时间线/位置查询"分支
   - 来源线索：简单位置查询走了 cross-ref 深度诊断 × 2 次
   - 过程回放：
     · 第1次：用户问"韩致在哪出现过" → 走了 cross-ref → 实际 `novel-tool(operation="graph.search")` 即可
     · 第2次：同类查询再次走错 → 根因：路由表没有"位置查询"分支
   - 改动范围：① 主循环「搜索分析?」下新增"位置查询"子分支 → ② 路由到 `novel-tool(operation="graph.search")` 直接 tool
```

## C.3 执行策略

- **用户确认后执行**：改进任务清单输出后，等待用户确认再逐项修改代码/文档
- **按维度并行**：不同维度的改进（如 schema + prompt）可并行执行
- **最小改动原则**：每次改进只改必要的文件，不顺带重构
- **改进后重分析**：执行完 critical 任务后，可重新触发聚合分析流程，验证线索是否消除

## C.4 反馈验证

- 改进任务执行后，**用 `analysis.resolve` 标记对应线索已修复**（写入 index.json 的 resolved 列表），下一轮聚合自动跳过/标注，避免重复报告：

  ```text
  novel-tool(operation="analysis.resolve", clue="{线索标识}", note="{修复说明}")   # 默认标记最新清单
  novel-tool(operation="analysis.resolve", file="{清单文件名}", clue="{线索标识}", note="{修复说明}")
  ```

- 新一轮聚合前调用 `analysis.list` 读取 `entries[].resolved` 收集已修复线索集合，聚类时对已 resolve 线索标注 `✅ 已修复` 或跳过（详见 aggregate-analysis.md B.4.2）
- 重新触发聚合分析后，通过版本对比区分线索演进：
  - `analysis.list` 查看全部版本（含各自线索与修复状态）→ `analysis.read(file=...)` 读取指定版本
  - **遗留线索**：上轮与本轮都出现且未 resolve（未消除，继续追踪）
  - **新线索**：仅本轮出现（本轮开发模式流程新发现）
  - **已消除线索**：已通过 `analysis.resolve` 标记（改进生效）
- 未消除的线索保留在聚类中，下次分析时继续追踪
