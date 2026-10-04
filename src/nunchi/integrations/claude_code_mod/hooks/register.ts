import type { EngineInterface, Register } from 'claude-code'

// Connects a dedicated Claude Code session to its Nunchi room gate.
//
// The gate starts the session with two variables: the path of its private
// socket and a per-launch secret. Without both, this module registers nothing
// and every hook passes straight through. With them, it:
//   - registers the room tools the gate declares;
//   - binds each model turn to the wake that started it;
//   - forwards room tool calls to the gate, which owns the room.

type Gate = { socket: string; secret: string }
type ToolSpec = { name: string; description: string; inputSchema: Record<string, unknown> }
type ToolAnswer = { ok: true; text: string } | { ok: false; error: string }

const WAKE = /^<nunchi_wake id="([A-Za-z0-9_-]{16,64})"\/>/
const RESERVED = new Set(['tool', 'tool_use_id', 'agentId'])

async function post<T>($: EngineInterface, gate: Gate, path: string, body: unknown): Promise<T> {
  const response = await $.http.fetch(`http://nunchi-gate${path}`, {
    method: 'POST',
    headers: { 'content-type': 'application/json', 'x-nunchi-session': gate.secret },
    body: JSON.stringify(body),
    socketPath: gate.socket,
  })
  if (!response.ok) throw new Error(`the Nunchi gate answered ${response.status}`)
  return JSON.parse(response.text) as T
}

export const register: Register = on => {
  let gate: Gate | undefined
  let turnId: string | undefined
  const tools = new Set<string>()

  on('session.start', async ($, e, next) => {
    const started = await next(e)
    const socket = await $.env.get('NUNCHI_CLAUDE_CODE_GATE_SOCKET')
    const secret = await $.env.get('NUNCHI_CLAUDE_CODE_GATE_SESSION')
    if (!socket || !secret) return started
    gate = { socket, secret }
    const attached = await post<{ tools: ToolSpec[] }>($, gate, '/v1/attach', {})
    for (const spec of attached.tools) {
      const { tool } = await $.tool.register(spec)
      tools.add(tool)
    }
    return started
  })

  on('turn.start', async ($, e, next) => {
    if (gate) {
      turnId = e.turnId
      const wake = WAKE.exec(e.text)?.[1] ?? null
      try {
        await post($, gate, '/v1/turn-start', { turn_id: e.turnId, wake_id: wake })
      } catch {
        // An unbound turn cannot act in the room; the gate reports it.
      }
    }
    return next(e)
  })

  on('tool.call', async ($, e, next) => {
    if (!gate || !tools.has(e.tool)) return next(e)
    if (e.agentId !== undefined) {
      return { deny: 'Only the main conversation can act in the room.' }
    }
    const input = Object.fromEntries(
      Object.entries(e).filter(([key]) => !RESERVED.has(key)),
    )
    try {
      const answer = await post<ToolAnswer>($, gate, '/v1/tool', {
        turn_id: turnId ?? null,
        tool: e.tool,
        input,
      })
      return answer.ok ? { result: answer.text } : { deny: answer.error }
    } catch {
      return { deny: 'The Nunchi gate is unreachable. Nothing was posted.' }
    }
  })
}
