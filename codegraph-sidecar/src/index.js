'use strict'
/**
 * index.js — Express HTTP server for the codegraph sidecar.
 *
 * Exposes two surfaces:
 *   1. REST API  — repo lifecycle management (register, status, reindex, delete, query)
 *   2. MCP / SSE — per-repo MCP server bridged over SSE from `codegraph serve --mcp`
 *
 * Environment variables:
 *   PORT      (default 3001)
 *   HOST      (default 0.0.0.0)
 *   WORKSPACE (default /opt/codegraph_repos)
 */

const express = require('express')
const repoManager = require('./repoManager')
const mcpBridge = require('./mcpBridge')

const PORT = parseInt(process.env.PORT || '3001', 10)
const HOST = process.env.HOST || '0.0.0.0'

const app = express()
app.use(express.json())

// ── Health ────────────────────────────────────────────────────────────────────

app.get('/health', (_req, res) => {
  res.json({
    status: 'ok',
    repos: repoManager.listRepos().length,
    activeMcpSessions: mcpBridge.activeSessionCount()
  })
})

// ── Repo management REST API ──────────────────────────────────────────────────

/**
 * POST /repos
 * Register a repository and start indexing asynchronously.
 * Body: { name, repoUrl, cloneDepth? }
 * Returns 202 with the repo record immediately; poll GET /repos/:slug for status.
 */
app.post('/repos', (req, res) => {
  const { name, repoUrl, cloneDepth = 1 } = req.body || {}
  if (!name || !repoUrl) {
    return res.status(400).json({ error: '"name" and "repoUrl" are required' })
  }
  try {
    const repo = repoManager.addRepo({ name, repoUrl, cloneDepth: Number(cloneDepth) })
    res.status(202).json(repo)
  } catch (err) {
    res.status(500).json({ error: err.message })
  }
})

/**
 * GET /repos
 * List all registered repositories and their current status.
 */
app.get('/repos', (_req, res) => {
  res.json(repoManager.listRepos())
})

/**
 * GET /repos/:slug
 * Get a single repository by slug.
 */
app.get('/repos/:slug', (req, res) => {
  const repo = repoManager.getRepo(req.params.slug)
  if (!repo) return res.status(404).json({ error: `Repo '${req.params.slug}' not found` })
  res.json(repo)
})

/**
 * POST /repos/:slug/reindex
 * Trigger a re-index (git pull + codegraph index) for an existing repo.
 * Returns 202 immediately; poll GET /repos/:slug for completion.
 */
app.post('/repos/:slug/reindex', (req, res) => {
  const { cloneDepth = 1 } = req.body || {}
  try {
    repoManager.reindexRepo(req.params.slug, Number(cloneDepth))
    res.status(202).json({ slug: req.params.slug, status: 'pending' })
  } catch (err) {
    const status = err.message.includes('not found') ? 404 : 500
    res.status(status).json({ error: err.message })
  }
})

/**
 * DELETE /repos/:slug
 * Remove a repo record (and optionally its local checkout).
 * Query param: deleteLocal=true|false (default false)
 */
app.delete('/repos/:slug', (req, res) => {
  const deleteLocal = req.query.deleteLocal === 'true'
  try {
    repoManager.removeRepo(req.params.slug, deleteLocal)
    res.status(204).end()
  } catch (err) {
    const status = err.message.includes('not found') ? 404 : 500
    res.status(status).json({ error: err.message })
  }
})

/**
 * POST /repos/:slug/query
 * Run `codegraph <command> --json [args]` and return parsed JSON.
 * Body: { command, args? }
 * Repo must be in 'ready' status.
 */
app.post('/repos/:slug/query', async (req, res) => {
  const { command, args = [] } = req.body || {}
  if (!command) return res.status(400).json({ error: '"command" is required' })

  try {
    const result = await repoManager.queryRepo(req.params.slug, command, args)
    res.json(result)
  } catch (err) {
    const status = err.message.includes('not found')
      ? 404
      : err.message.includes('not ready')
        ? 409
        : 502
    res.status(status).json({ error: err.message })
  }
})

// ── MCP / SSE endpoints ───────────────────────────────────────────────────────

/**
 * GET /repos/:slug/sse
 * Open an MCP session for the given repository over Server-Sent Events.
 * The repo must be in 'ready' status.
 *
 * On connection, the sidecar spawns `codegraph serve --mcp` and bridges
 * its stdio to this SSE stream.  The first SSE event carries the POST
 * endpoint URL the MCP client must use for sending requests.
 */
app.get('/repos/:slug/sse', (req, res) => {
  const repo = repoManager.getRepo(req.params.slug)
  if (!repo) {
    return res.status(404).json({ error: `Repo '${req.params.slug}' not found` })
  }
  if (repo.status !== 'ready') {
    return res.status(409).json({
      error: `Repo '${req.params.slug}' is not ready (status: ${repo.status})`
    })
  }
  mcpBridge.handleSSEConnection(req.params.slug, repo.localPath, req, res)
})

/**
 * POST /repos/:slug/messages?sessionId=<id>
 * Deliver a JSON-RPC message to the MCP session identified by sessionId.
 * Used by the MCP client after receiving the endpoint URL from the SSE stream.
 */
app.post('/repos/:slug/messages', (req, res) => {
  const { sessionId } = req.query
  if (!sessionId) return res.status(400).json({ error: 'sessionId query param required' })
  mcpBridge.handleMessagePost(sessionId, req.body, res)
})

// ── Startup ───────────────────────────────────────────────────────────────────

repoManager.loadState()

app.listen(PORT, HOST, () => {
  console.log(`[codegraph-sidecar] Listening on http://${HOST}:${PORT}`)
  console.log(`[codegraph-sidecar] Workspace: ${process.env.WORKSPACE || '/opt/codegraph_repos'}`)
  console.log(`[codegraph-sidecar] Repos loaded: ${repoManager.listRepos().length}`)
})
