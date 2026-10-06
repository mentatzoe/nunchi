import { describe, expect, mock, test } from 'claude-code/testing'
import type { On } from 'claude-code'

const SOCKET = '/tmp/nunchi-cc-test/gate.sock'
const SECRET = 'per-launch-secret'
const WAKE_ID = 'abcdefghijklmnopqrstuvwx'
const SEND = 'mcp__nunchi__room_send'

type Call = { path: string; body: any; headers: Record<string, string>; socketPath?: string }

// Stands for the engine and the gate beneath the mod.
function world(
  on: On,
  answers: Record<string, unknown>,
  env: Record<string, string> = {
    NUNCHI_CLAUDE_CODE_GATE_SOCKET: SOCKET,
    NUNCHI_CLAUDE_CODE_GATE_SESSION: SECRET,
  },
): Call[] {
  const calls: Call[] = []
  mock.env(on, env)
  on('session.start', ($, e) => ({ cwd: e.cwd }))
  on('turn.start', ($, e) => ({ turnId: e.turnId }))
  on('tool.register', ($, e) => ({ value: { tool: `mcp__nunchi__${e.name}` } }))
  on('http.fetch', ($, e) => {
    const path = new URL(e.url).pathname
    calls.push({
      path,
      body: JSON.parse(e.init?.body ?? '{}'),
      headers: e.init?.headers ?? {},
      socketPath: e.init?.socketPath,
    })
    const answer = answers[path]
    if (answer === undefined) return { value: { status: 500, ok: false, headers: {}, text: '' } }
    return { value: { status: 200, ok: true, headers: {}, text: JSON.stringify(answer) } }
  })
  return calls
}

const ATTACH = {
  tools: [
    { name: 'room_send', description: 'Post one message.', inputSchema: { type: 'object' } },
  ],
}

async function begin($: any, wake: string | null = WAKE_ID) {
  await $.session.start({ cwd: '/work', surface: null, isInteractive: false })
  const prefix = wake === null ? '' : `<nunchi_wake id="${wake}"/>\n`
  await $.turn.start({ text: `${prefix}room facts`, turnId: 'turn-1' })
}

describe('outside a gated session', () => {
  test('registers nothing and calls nothing', async ($, on) => {
    const calls = world(on, {}, {})
    await begin($)
    expect(calls).toEqual([])
  })
})

describe('inside the gated session', () => {
  test('attaches over the private socket with the session secret', async ($, on) => {
    const calls = world(on, { '/v1/attach': ATTACH, '/v1/turn-start': { bound: true } })
    await begin($)
    expect(calls.map(call => call.path)).toEqual(['/v1/attach', '/v1/turn-start'])
    expect(calls[0]?.socketPath).toBe(SOCKET)
    expect(calls[0]?.headers['x-nunchi-session']).toBe(SECRET)
  })

  test('binds the turn to the wake that started it', async ($, on) => {
    const calls = world(on, { '/v1/attach': ATTACH, '/v1/turn-start': { bound: true } })
    await begin($)
    expect(calls[1]).toEqual(
      expect.objectContaining({
        path: '/v1/turn-start',
        body: { turn_id: 'turn-1', wake_id: WAKE_ID },
      }),
    )
  })

  test('a turn without a wake marker is reported unbound', async ($, on) => {
    const calls = world(on, { '/v1/attach': ATTACH, '/v1/turn-start': { bound: false } })
    await begin($, null)
    expect(calls[1]?.body).toEqual({ turn_id: 'turn-1', wake_id: null })
  })

  test('forwards a room tool call and returns the gate answer', async ($, on) => {
    const calls = world(on, {
      '/v1/attach': ATTACH,
      '/v1/turn-start': { bound: true },
      '/v1/tool': { ok: true, text: 'Done: the room accepted this action.' },
    })
    await begin($)
    const ran = await $.tool.call({ tool: SEND, text: 'hello room' })
    expect(calls[2]).toEqual(
      expect.objectContaining({
        path: '/v1/tool',
        body: { turn_id: 'turn-1', tool: SEND, input: { text: 'hello room' } },
      }),
    )
    expect(ran.isError).toBe(undefined)
    expect(ran.result).toBe('Done: the room accepted this action.')
  })

  test('a gate refusal reaches the model as a denial', async ($, on) => {
    world(on, {
      '/v1/attach': ATTACH,
      '/v1/turn-start': { bound: true },
      '/v1/tool': { ok: false, error: 'Refused: this action contains a secret.' },
    })
    await begin($)
    const ran = await $.tool.call({ tool: SEND, text: 'token' })
    expect(ran.deny).toBe('Refused: this action contains a secret.')
  })

  test('an unreachable gate posts nothing', async ($, on) => {
    world(on, { '/v1/attach': ATTACH, '/v1/turn-start': { bound: true } })
    await begin($)
    const ran = await $.tool.call({ tool: SEND, text: 'hello' })
    expect(ran.deny).toContain('Nothing was posted.')
  })
})

describe('steering (#94 step 6)', () => {
  const UPDATE = 'Room update: 1 new message(s) arrived while you were working.'

  test('what others posted rides the next tool result', async ($, on) => {
    const calls = world(on, {
      '/v1/attach': ATTACH,
      '/v1/turn-start': { bound: true },
      '/v1/news': { text: UPDATE },
    })
    on('tool.call', () => ({ result: 'README.md' }))
    await begin($)
    const ran = await $.tool.call({ tool: 'Bash', command: 'ls' })
    expect(ran.result).toBe('README.md')
    expect(ran.context).toEqual([UPDATE])
    expect(calls.at(-1)).toEqual(
      expect.objectContaining({ path: '/v1/news', body: { turn_id: 'turn-1' } }),
    )
  })

  test('a room tool answer carries it too', async ($, on) => {
    world(on, {
      '/v1/attach': ATTACH,
      '/v1/turn-start': { bound: true },
      '/v1/tool': { ok: true, text: 'Done: the room accepted this action.' },
      '/v1/news': { text: UPDATE },
    })
    await begin($)
    const ran = await $.tool.call({ tool: SEND, text: 'hello room' })
    expect(ran.result).toBe('Done: the room accepted this action.')
    expect(ran.context).toEqual([UPDATE])
  })

  test('nothing new, or an unreachable gate, adds nothing', async ($, on) => {
    world(on, { '/v1/attach': ATTACH, '/v1/turn-start': { bound: true }, '/v1/news': { text: null } })
    on('tool.call', () => ({ result: 'README.md' }))
    await begin($)
    const ran = await $.tool.call({ tool: 'Bash', command: 'ls' })
    expect(ran.result).toBe('README.md')
    expect(ran.context).toBe(undefined)
  })

  test('a subagent gets no room update', async ($, on) => {
    const calls = world(on, {
      '/v1/attach': ATTACH,
      '/v1/turn-start': { bound: true },
      '/v1/news': { text: UPDATE },
    })
    on('tool.call', () => ({ result: 'README.md' }))
    await begin($)
    const ran = await $.tool.call({ tool: 'Bash', command: 'ls', agentId: 'helper' })
    expect(ran.context).toBe(undefined)
    expect(calls.some(call => call.path === '/v1/news')).toBe(false)
  })
})
