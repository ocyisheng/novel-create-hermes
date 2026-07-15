import { tool } from "@opencode-ai/plugin"
import path from "path"
import { execSync } from "child_process"

const TOOL_SCRIPT = (worktree: string) =>
  `python "${path.join(worktree, ".opencode/shared/tools/novel_tool.py")}"`

function run(args: Record<string, unknown>, worktree: string): string {
  const script = TOOL_SCRIPT(worktree)
  if (args.project && typeof args.project === "string" && !path.isAbsolute(args.project)) {
    args.project = path.join(worktree, "novels", args.project)
  }
  try {
    // Windows cmd.exe 不识别单引号，需用双引号并转义内部双引号
    const isWin = process.platform === "win32"
    const json = JSON.stringify(args)
    const quoted = isWin
      ? `"${json.replace(/"/g, '\\"')}"`
      : `'${json}'`
    return execSync(`${script} ${quoted}`, {
      encoding: "utf-8",
      shell: true,
    }).toString().trim()
  } catch (e) {
    return JSON.stringify({ success: false, error: String(e) })
  }
}

export default tool({
  name: "novel-tool",
  description: "V2 小说创作统一工具, 涵盖 graph CRUD、项目管理、环境、知识库、可视化、导出等全部操作。返回 JSON。",
  args: {
    operation: tool.schema
      .enum([
        // graph reads
        "graph.get_unit", "graph.search", "graph.list_units", "graph.stats",
        "graph.get_neighbors", "graph.check", "graph.find_unit",
        "graph.list_relation_types", "graph.recent_events", "graph.get_modified_units",
        // graph writes
        "graph.create_unit", "graph.update_unit", "graph.add_relation",
        "graph.flush", "graph.fix_asymmetry", "graph.get_relations", "graph.remove_relation", "graph.batch_infer",
        "graph.archive_unit",
        // graph hierarchy queries
        "graph.find_descendants", "graph.find_ancestors",
        "graph.rebuild_structure_path", "graph.migrate_structure_to_edges",
        // graph exports
        "graph.export_docs", "graph.export_chunks",
        // graph viz & migrate
        "graph.viz", "graph.migrate",
        // project
        "project.new", "project.import", "project.status",
        "project.resume", "project.switch", "project.delete",
        "project.update_progress",
        // env
        "env.check", "env.fix", "env.force",
        // knowledge
        "knowledge.read", "knowledge.list_books",
        // session
        "session.start", "session.build_workspace", "session.info", "session.set_cycle", "session.set_phase",
        // deviation
        "deviation.merge", "deviation.list", "deviation.pending",
        "deviation.resolve", "deviation.retain", "deviation.delete", "deviation.stats",
      ])
      .describe("操作类型"),
    project: tool.schema.string().optional().describe("小说项目名（如 凡人之诡影重重）或绝对路径"),
    id: tool.schema.string().optional().describe("叙事单元 ID"),
    name: tool.schema.string().optional().describe("单元名称 / 项目名称"),
    keyword: tool.schema.string().optional().describe("搜索关键词"),
    pattern: tool.schema.string().optional().describe("正则模式"),
    unit_type: tool.schema.string().optional().describe("单元类型过滤 (SCENE/CHARACTER_ARC 等)"),
    limit: tool.schema.number().optional().describe("结果上限"),
    rel_type: tool.schema.string().optional().describe("关系类型过滤"),
    content: tool.schema.string().optional().describe("单元内容 (JSON 字符串)"),
    status: tool.schema.string().optional().describe("单元状态 (sprout/growing/mature/frozen/archived)"),
    file: tool.schema.string().optional().describe("从文件读取内容（优先于 content）"),
    type: tool.schema.string().optional().describe("类型（创建单元时的 UnitType / 关系类型 / 会话焦点类型）"),
    source: tool.schema.string().optional().describe("关系源 ID"),
    target: tool.schema.string().optional().describe("关系目标 ID"),
    bidirectional: tool.schema.boolean().optional().describe("是否自动建立反向关系"),
    tags: tool.schema.string().optional().describe("标签（逗号分隔）"),
    chapter: tool.schema.number().optional().describe("章节号"),
    volume: tool.schema.number().optional().describe("卷号"),
    parent_id: tool.schema.string().optional().describe("创建单元时的父级单元 ID（自动建 CONTAINS 边）"),
    max_depth: tool.schema.number().optional().describe("find_descendants 最大深度"),
    direction: tool.schema.string().optional().describe("方向 (outgoing/incoming/both，默认 both)"),
    actor: tool.schema.string().optional().describe("操作者标识"),
    character: tool.schema.string().optional().describe("可视化：角色名称/ID"),
    timeline: tool.schema.string().optional().describe("可视化：时间线角色"),
    output: tool.schema.string().optional().describe("输出路径"),
    open: tool.schema.boolean().optional().describe("生成后打开浏览器"),
    force: tool.schema.boolean().optional().describe("强制模式"),
    verbose: tool.schema.boolean().optional().describe("详细模式（显示完整内容）"),
    level: tool.schema.string().optional().describe("预热级别 (cold/warm/hot)"),
    slug: tool.schema.string().optional().describe("知识库标识 (如 fanren-xiuxian)"),
    topic: tool.schema.string().optional().describe("知识库查询主题 (支持 | OR 查询)"),
    genre: tool.schema.string().optional().describe("项目类型（玄幻/仙侠等）"),
    v2: tool.schema.boolean().optional().describe("创建 V2 原生项目"),
    volumes: tool.schema.number().optional().describe("卷数"),
    acts: tool.schema.number().optional().describe("幕数"),
    structure: tool.schema.string().optional().describe("结构类型"),
    source_path: tool.schema.string().optional().describe("导入源路径"),
    dry_run: tool.schema.boolean().optional().describe("试运行"),
    current_volume: tool.schema.number().optional().describe("更新写作进度：当前卷"),
    current_chapter: tool.schema.number().optional().describe("更新写作进度：当前章"),
    volume_outline_status: tool.schema.string().optional().describe("更新写作进度：卷大纲状态描述"),
    volume_outline_done: tool.schema.number().optional().describe("更新写作进度：已完成大纲的卷数"),
    scope: tool.schema.string().optional().describe("搜索范围（逗号分隔的类型）"),
    regex: tool.schema.boolean().optional().describe("启用正则搜索"),
    case_sensitive: tool.schema.boolean().optional().describe("区分大小写"),
    cycle_type: tool.schema.string().optional().describe("会话循环类型 (expansion/refinement/proofing/planning)"),
    phase: tool.schema.string().optional().describe("会话阶段 (ideation/planning/expansion/refinement/proofing)"),
    incremental: tool.schema.boolean().optional().describe("增量生成"),
    verify: tool.schema.boolean().optional().describe("迁移时验证"),
    report: tool.schema.boolean().optional().describe("迁移时输出报告"),
    since_version: tool.schema.number().optional().describe("起始版本号"),
    findings: tool.schema.string().optional().describe("偏差发现列表(JSON数组)"),
    scan_version: tool.schema.number().optional().describe("扫描版本号"),
    full_scan_version: tool.schema.number().optional().describe("全量扫描版本号"),
    out: tool.schema.string().optional().describe("导出目录"),
  },
  async execute(args, context) {
    return run(args, context.worktree)
  },
})
