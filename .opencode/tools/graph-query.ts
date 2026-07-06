import { tool } from "@opencode-ai/plugin"
import path from "path"

const CLI = (worktree: string) => `python "${path.join(worktree, ".opencode/shared/cli.py")}" v2`
const projectPath = (worktree: string, project: string) => path.join(worktree, "novels", project)

export default tool({
  description: "查询 V2 叙事单元网络 (graph)。支持查单元详情、关键词搜索、按类型列举、获取关联关系、统计、一致性检查等。",
  args: {
    type: tool.schema
      .enum(["get-unit", "search", "list-units", "stats", "get-neighbors", "check", "find-unit", "read-knowledge"])
      .describe("查询类型"),
    project: tool.schema.string().describe("小说项目名，如 凡人之诡影重重"),
    id: tool.schema.string().optional().describe("叙事单元 ID (用于 get-unit/get-neighbors)"),
    name: tool.schema.string().optional().describe("单元名称 (用于 get-unit/find-unit/search)"),
    keyword: tool.schema.string().optional().describe("搜索关键词 (用于 search)"),
    unitType: tool.schema.string().optional().describe("单元类型过滤 (用于 list-units/search，如 SCENE/CHARACTER_ARC/NOTE)"),
    limit: tool.schema.number().optional().describe("最大返回条数"),
    slug: tool.schema.string().optional().describe("知识库标识 (用于 read-knowledge，如 fanren-xiuxian)"),
    topic: tool.schema.string().optional().describe("知识库查询主题 (用于 read-knowledge，如 鬼道|阴冥)"),
  },
  async execute(args, context) {
    const cli = CLI(context.worktree)
    const pPath = projectPath(context.worktree, args.project)

    try {
      switch (args.type) {
        case "get-unit": {
          if (args.id) {
            return (await Bun.$`${cli} get-unit --path "${pPath}" --id "${args.id}" --verbose`.text()).trim()
          }
          if (args.name) {
            const id = (await Bun.$`${cli} find-unit --path "${pPath}" --name "${args.name}"`.text()).trim()
            if (id === "NOT_FOUND") return "未找到匹配单元"
            return (await Bun.$`${cli} get-unit --path "${pPath}" --id "${id}" --verbose`.text()).trim()
          }
          return "请提供 id 或 name"
        }

        case "find-unit": {
          if (!args.name) return "find-unit 需要 name"
          return (await Bun.$`${cli} find-unit --path "${pPath}" --name "${args.name}"`.text()).trim()
        }

        case "search": {
          const kw = args.keyword || args.name || ""
          if (!kw) return "search 需要 keyword 或 name"
          const scope = args.unitType ? `--scope ${args.unitType}` : ""
          return (await Bun.$`${cli} search --path "${pPath}" --keyword "${kw}" ${scope} --limit ${args.limit || 10}`.text()).trim()
        }

        case "list-units": {
          const typeFlag = args.unitType ? `--type ${args.unitType}` : ""
          return (await Bun.$`${cli} list-units --path "${pPath}" ${typeFlag} --limit ${args.limit || 20}`.text()).trim()
        }

        case "stats":
          return (await Bun.$`${cli} stats --path "${pPath}"`.text()).trim()

        case "get-neighbors": {
          if (!args.id) return "get-neighbors 需要 id"
          const relFlag = args.unitType ? `--rel-type ${args.unitType}` : ""
          return (await Bun.$`${cli} get-neighbors --path "${pPath}" --id "${args.id}" ${relFlag}`.text()).trim()
        }

        case "check":
          return (await Bun.$`${cli} check --path "${pPath}"`.text()).trim()

        case "read-knowledge": {
          if (!args.slug) return "read-knowledge 需要 slug"
          return (await Bun.$`${cli} read-knowledge --path "${pPath}" --slug "${args.slug}" --topic "${args.topic || "概要"}"`.text()).trim()
        }

        default:
          return `不支持的查询类型: ${args.type}`
      }
    } catch (e) {
      return `查询失败: ${e}`
    }
  },
})
