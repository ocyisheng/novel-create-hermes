import { tool } from "@opencode-ai/plugin"
import path from "path"
import { execSync, spawn, ChildProcess } from "child_process"

// ── DaemonClient ─────────────────────────────────────────────────────

interface PendingRequest {
  resolve: (value: string) => void
  reject: (reason: Error) => void
  timer: NodeJS.Timeout
  startTime: number
}

class DaemonError extends Error {
  constructor(msg: string, public cause?: string) {
    super(msg)
    this.name = "DaemonError"
  }
}

class DaemonClient {
  private proc: ChildProcess | null = null
  private pending = new Map<string, PendingRequest>()
  private buffer = ""
  private nextId = 0
  private ready = false
  private readyResolve: (() => void) | null = null
  private readyReject: ((reason: Error) => void) | null = null
  private launchCount = 0
  private readonly MAX_RETRIES = 3
  private readonly LAUNCH_TIMEOUT = 5_000
  private readonly REQUEST_TIMEOUT = 30_000
  private readonly worktree: string

  constructor(worktree: string) {
    this.worktree = worktree
  }

  private get scriptPath(): string {
    return path.join(this.worktree, ".opencode/shared/tools/novel_tool.py")
  }

  private async ensureRunning(): Promise<void> {
    if (this.proc && !this.proc.killed && this.ready) return
    if (this.launchCount >= this.MAX_RETRIES) {
      throw new DaemonError(
        `Daemon crashed ${this.MAX_RETRIES} times, falling back to execSync`
      )
    }

    this.launchCount++
    this.ready = false
    this.buffer = ""

    this.proc = spawn("python", [this.scriptPath, "--daemon"], {
      stdio: ["pipe", "pipe", "pipe"],
    })

    // stdout 处理：按行解析 JSON
    this.proc.stdout!.on("data", (chunk: Buffer) => {
      this.buffer += chunk.toString()
      const lines = this.buffer.split("\n")
      this.buffer = lines.pop() || ""

      for (const line of lines) {
        const trimmed = line.trim()
        if (!trimmed) continue

        try {
          const msg = JSON.parse(trimmed)

          // 握手信号
          if (msg.ready === true) {
            this.ready = true
            this.launchCount = 0
            this.readyResolve?.()
            this.readyResolve = null
            this.readyReject = null
            continue
          }

          // 普通响应：按 _req_id 分发
          const reqId = msg._req_id
          if (reqId && this.pending.has(reqId)) {
            const p = this.pending.get(reqId)!
            clearTimeout(p.timer)
            p.resolve(trimmed)
            this.pending.delete(reqId)
          } else if (reqId) {
            // 未知 reqId（可能已超时），忽略
          }
        } catch {
          console.warn(`[daemon] unparseable stdout line: ${trimmed.slice(0, 200)}`)
        }
      }
    })

    // stderr → 日志
    this.proc.stderr!.on("data", (chunk: Buffer) => {
      const text = chunk.toString().trim()
      if (text) {
        console.warn(`[daemon:err] ${text}`)
      }
    })

    // 进程退出 → 拒绝所有待处理请求
    this.proc.on("exit", (code, signal) => {
      this.ready = false
      const wasReady = this.readyResolve === null
      this.proc = null

      // 如果正在等待 ready，拒绝
      if (this.readyReject) {
        this.readyReject(new DaemonError(`Daemon exited before ready (code=${code}, signal=${signal})`))
        this.readyResolve = null
        this.readyReject = null
      }

      // 拒绝所有待处理的请求
      if (wasReady && this.pending.size > 0) {
        const errMsg = `Daemon exited (code=${code}, signal=${signal})`
        for (const [reqId, p] of this.pending) {
          clearTimeout(p.timer)
          p.reject(new DaemonError(errMsg, `request ${reqId}`))
        }
        this.pending.clear()
      }
    })

    // 等待就绪信号（超时 LAUNCH_TIMEOUT ms）
    await new Promise<void>((resolve, reject) => {
      this.readyResolve = resolve
      this.readyReject = reject
      const timer = setTimeout(() => {
        if (!this.ready) {
          this.readyResolve = null
          this.readyReject = null
          this.kill()
          reject(new DaemonError("Daemon launch timeout"))
        }
      }, this.LAUNCH_TIMEOUT)

      // timer 清理：当 resolve/reject 被调用时覆盖原函数
      const origResolve = resolve
      const origReject = reject
      this.readyResolve = () => { clearTimeout(timer); origResolve() }
      this.readyReject = (e: Error) => { clearTimeout(timer); origReject(e) }
    })
  }

  async request(args: Record<string, unknown>): Promise<string> {
    if (this.launchCount >= this.MAX_RETRIES) {
      throw new DaemonError("Max retries exceeded, daemon permanently disabled")
    }

    await this.ensureRunning()

    const reqId = `req_${String(this.nextId++).padStart(4, "0")}`
    const payload = { ...args, _req_id: reqId }

    return new Promise<string>((resolve, reject) => {
      const timer = setTimeout(() => {
        this.pending.delete(reqId)
        reject(new DaemonError(`Request ${reqId} timed out (${this.REQUEST_TIMEOUT}ms)`))
      }, this.REQUEST_TIMEOUT)

      this.pending.set(reqId, { resolve, reject, timer, startTime: Date.now() })

      try {
        this.proc!.stdin!.write(JSON.stringify(payload) + "\n")
      } catch (e) {
        clearTimeout(timer)
        this.pending.delete(reqId)
        reject(new DaemonError(`Failed to write to daemon stdin: ${e}`))
      }
    })
  }

  async shutdown(): Promise<void> {
    if (this.proc && !this.proc.killed) {
      try {
        await this.request({ operation: "shutdown" })
      } catch {
        // daemon might already be dead
      }
      this.kill()
    }
  }

  private kill(): void {
    if (this.proc && !this.proc.killed) {
      this.proc.kill("SIGTERM")
      setTimeout(() => {
        if (this.proc && !this.proc.killed) {
          this.proc.kill("SIGKILL")
        }
      }, 2000)
    }
    this.proc = null
    this.ready = false
  }
}

// ── execSync 模式（原有逻辑，作为降级路径） ──────────────────────────

const TOOL_SCRIPT = (worktree: string) =>
  `python "${path.join(worktree, ".opencode/shared/tools/novel_tool.py")}"`

function runExecSync(args: Record<string, unknown>, worktree: string): string {
  const script = TOOL_SCRIPT(worktree)
  if (args.project && typeof args.project === "string" && !path.isAbsolute(args.project)) {
    args.project = path.join(worktree, "novels", args.project)
  }
  try {
    const json = JSON.stringify(args)
    return execSync(`${script}`, {
      input: json,
      encoding: "utf-8",
      shell: true,
    }).toString().trim()
  } catch (e) {
    return JSON.stringify({ success: false, error: String(e) })
  }
}

// ── 路由：daemon 优先，降级到 execSync ──────────────────────────────

// 模块级 daemon 实例（跨 execute 调用持久化）
let daemonClient: DaemonClient | null = null

async function run(args: Record<string, unknown>, worktree: string): Promise<string> {
  // 解析 project 为绝对路径
  if (args.project && typeof args.project === "string" && !path.isAbsolute(args.project)) {
    args.project = path.join(worktree, "novels", args.project)
  }

  // 环境变量或配置可禁用守护进程
  if (process.env.NOVEL_DAEMON_DISABLED) {
    return runExecSync(args, worktree)
  }

  // 尝试 daemon 模式
  if (!daemonClient) {
    daemonClient = new DaemonClient(worktree)
  }

  try {
    return await daemonClient.request(args)
  } catch (e) {
    if (e instanceof DaemonError) {
      console.warn(`[novel-tool] Daemon failed: ${e.message}. Falling back to execSync.`)
      return runExecSync(args, worktree)
    }
    // 非 DaemonError 的异常（如 JSON 序列化错误）也降级
    console.warn(`[novel-tool] Unexpected error in daemon path: ${e}. Falling back to execSync.`)
    return runExecSync(args, worktree)
  }
}

// 进程退出时清理 daemon
process.on("exit", () => {
  if (daemonClient) {
    // 同步 kill，不等待异步 shutdown
    try {
      daemonClient.shutdown()
    } catch {
      // ignore
    }
  }
})

// ── Tool 注册（数据部分完全不变） ────────────────────────────────────

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
        "graph.archive_unit", "graph.purge_archived",
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
    type: tool.schema.string().optional().describe("类型（向后兼容别名。新建用 unit_type/rel_type/focus_type）"),
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
    focus_type: tool.schema.string().optional().describe("会话焦点类型 (scene/character_arc 等)"),
    scope: tool.schema.string().optional().describe("搜索范围（逗号分隔的类型）"),
    regex: tool.schema.boolean().optional().describe("启用正则搜索"),
    case_sensitive: tool.schema.boolean().optional().describe("区分大小写"),
    cycle_type: tool.schema.string().optional().describe("会话循环类型 (ideation/expansion/refinement/proofing/planning)"),
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
