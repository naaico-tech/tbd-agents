'use strict'
/**
 * mcpBridge.js — bridges `codegraph serve --mcp` (stdio JSON-RPC) over
 * Server-Sent Events (SSE) so that tbd-agents can connect via the SSE
 * transport defined in the MCP specification.
 *
 * Protocol summary:
 *   Client → GET  /repos/:slug/sse
 *              ← SSE stream begins; first event is `event: endpoint`
 *                 carrying the POST URL the client must use for messages.
 *   Client → POST /repos/:slug/messages?sessionId=<id>  (JSON-RPC request)
 *              ← 202 Accepted  (response arrives asynchronously via SSE)
 *   Server → SSE `data: <json-rpc response>` events
 *
 * One `codegraph serve --mcp` child process is spawned per SSE session and
 * killed when the HTTP connection closes.
 */

const { spawn } = require('node:child_process')
const crypto = require('node:crypto')

/** Map<sessionId, { proc, res, slug }> — tracks active MCP sessions. */
const sessions = new Map()

// ── Internal helpers ──────────────────────────────────────────────────────────

function _setSSEHeaders (res) {
  res.setHeader('Content-Type', 'text/event-stream')
  res.setHeader('Cache-Control', 'no-cache')
  res.setHeader('Connection', 'keep-alive')
  res.setHeader('X-Accel-Buffering', 'no') // disable nginx/proxy buffering
  res.flushHeaders()
}

// ── Public handlers ───────────────────────────────────────────────────────────

/**
 * Handle GET /repos/:slug/sse
 *
 * Sets up the SSE stream, spawns `codegraph serve --mcp` in the repo's
 * working directory, and bridges stdout → SSE + stdin ← POST messages.
 */
function handleSSEConnection (slug, localPath, req, res) {
  const sessionId = crypto.randomUUID()

  _setSSEHeaders(res)

  // Tell the MCP client where to POST its requests (MCP SSE transport spec).
  const endpoint = `/repos/${slug}/messages?sessionId=${sessionId}`
  res.write(`event: endpoint\ndata: ${endpoint}\n\n`)

  // Spawn codegraph MCP stdio server for this session.
  const proc = spawn('codegraph', ['serve', '--mcp'], {
    cwd: localPath,
    stdio: ['pipe', 'pipe', 'pipe']
  })

  sessions.set(sessionId, { proc, res, slug })
  console.log(`[mcp:${slug}] Session ${sessionId} opened (pid=${proc.pid})`)

  // ── Bridge proc stdout → SSE ──────────────────────────────────────────────
  // codegraph outputs newline-delimited JSON-RPC messages.  We forward each
  // complete line as an SSE `data` event.
  let buffer = ''
  proc.stdout.on('data', chunk => {
    buffer += chunk.toString()
    const lines = buffer.split('\n')
    buffer = lines.pop() // keep any incomplete trailing line
    for (const line of lines) {
      const trimmed = line.trim()
      if (trimmed) {
        res.write(`data: ${trimmed}\n\n`)
      }
    }
  })

  proc.stderr.on('data', d => {
    process.stderr.write(`[mcp:${slug}] ${d.toString().trimEnd()}\n`)
  })

  proc.on('error', err => {
    console.error(`[mcp:${slug}] Process error: ${err.message}`)
    sessions.delete(sessionId)
    if (!res.writableEnded) res.end()
  })

  proc.on('exit', (code, signal) => {
    console.log(`[mcp:${slug}] Session ${sessionId} process exited code=${code} signal=${signal}`)
    sessions.delete(sessionId)
    if (!res.writableEnded) res.end()
  })

  // Clean up the child process when the HTTP connection drops.
  req.on('close', () => {
    console.log(`[mcp:${slug}] Session ${sessionId} closed by client`)
    sessions.delete(sessionId)
    proc.kill('SIGTERM')
  })
}

/**
 * Handle POST /repos/:slug/messages?sessionId=<id>
 *
 * Forwards the JSON-RPC message body to the corresponding codegraph process's
 * stdin.  The response will arrive asynchronously over the SSE stream.
 */
function handleMessagePost (sessionId, body, res) {
  const session = sessions.get(sessionId)
  if (!session) {
    return res.status(404).json({ error: 'Session not found or expired' })
  }

  const { proc } = session
  // Ensure the message is serialised to a single-line JSON string.
  const message = typeof body === 'string' ? body : JSON.stringify(body)
  proc.stdin.write(message + '\n')
  res.status(202).end()
}

/** Return the count of currently active MCP sessions (for health checks). */
function activeSessionCount () {
  return sessions.size
}

module.exports = { handleSSEConnection, handleMessagePost, activeSessionCount }
