'use strict'
/**
 * repoManager.js — manages the git clone + codegraph indexing lifecycle.
 *
 * State is persisted to a JSON file in the workspace volume so repos survive
 * container restarts.  All indexing runs asynchronously in the background;
 * callers poll GET /repos/:slug for status.
 */

const { execFile } = require('node:child_process')
const fs = require('node:fs')
const path = require('node:path')

const WORKSPACE = process.env.WORKSPACE || '/opt/codegraph_repos'
const STATE_FILE = path.join(WORKSPACE, '.sidecar-state.json')

/** In-memory state — persisted to STATE_FILE on every change. */
let state = { repos: {} }

// ── Helpers ───────────────────────────────────────────────────────────────────

/**
 * Convert a repo name to a filesystem-safe slug.
 * Spaces, slashes, and backslashes become underscores; all other non-word
 * characters are stripped.
 */
function slugify (name) {
  return name.replace(/[\s/\\]+/g, '_').replace(/[^a-zA-Z0-9_.-]/g, '')
}

function runCommand (cmd, args, cwd) {
  return new Promise((resolve, reject) => {
    execFile(cmd, args, { cwd, maxBuffer: 100 * 1024 * 1024 }, (err, stdout, stderr) => {
      if (err) {
        reject(new Error(`${cmd} ${args.join(' ')} failed: ${(stderr || err.message).trim()}`))
      } else {
        resolve(stdout)
      }
    })
  })
}

// ── State persistence ─────────────────────────────────────────────────────────

function loadState () {
  try {
    fs.mkdirSync(WORKSPACE, { recursive: true })
    if (fs.existsSync(STATE_FILE)) {
      state = JSON.parse(fs.readFileSync(STATE_FILE, 'utf8'))
    }
  } catch (err) {
    console.error('[repoManager] Failed to load state:', err.message)
    state = { repos: {} }
  }
}

function saveState () {
  try {
    fs.writeFileSync(STATE_FILE, JSON.stringify(state, null, 2), 'utf8')
  } catch (err) {
    console.error('[repoManager] Failed to save state:', err.message)
  }
}

// ── Core indexing logic ───────────────────────────────────────────────────────

async function _indexAsync (slug, repoUrl, localPath, cloneDepth) {
  const repo = state.repos[slug]
  if (!repo) return

  try {
    // ── Step 1: clone or pull ─────────────────────────────────────────────
    repo.status = 'cloning'
    repo.error = null
    saveState()

    if (!fs.existsSync(localPath)) {
      console.log(`[${slug}] Cloning ${repoUrl} → ${localPath}`)
      const cloneArgs = ['clone']
      if (cloneDepth > 0) cloneArgs.push('--depth', String(cloneDepth))
      cloneArgs.push(repoUrl, localPath)
      await runCommand('git', cloneArgs, WORKSPACE)
    } else {
      console.log(`[${slug}] Local path exists — pulling latest changes`)
      try {
        const pullArgs = ['pull']
        if (cloneDepth > 0) pullArgs.push('--depth', String(cloneDepth))
        await runCommand('git', pullArgs, localPath)
      } catch (pullErr) {
        // Warn but continue: existing checkout may still be indexable
        console.warn(`[${slug}] git pull failed (will still re-index): ${pullErr.message}`)
      }
    }

    // ── Step 2: codegraph init + index ────────────────────────────────────
    repo.status = 'indexing'
    saveState()

    console.log(`[${slug}] Running codegraph init`)
    await runCommand('codegraph', ['init'], localPath)

    console.log(`[${slug}] Running codegraph index`)
    await runCommand('codegraph', ['index'], localPath)

    repo.status = 'ready'
    repo.indexedAt = new Date().toISOString()
    repo.error = null
    saveState()
    console.log(`[${slug}] Indexing complete ✓`)
  } catch (err) {
    repo.status = 'error'
    repo.error = err.message
    saveState()
    console.error(`[${slug}] Indexing failed: ${err.message}`)
  }
}

// ── Public API ────────────────────────────────────────────────────────────────

function getRepo (slug) {
  return state.repos[slug] || null
}

function listRepos () {
  return Object.values(state.repos)
}

/**
 * Register a repo and start indexing asynchronously.
 * Calling again for the same slug resets status and re-indexes (git pull).
 */
function addRepo ({ name, repoUrl, cloneDepth = 1 }) {
  const slug = slugify(name)
  const localPath = path.join(WORKSPACE, slug)
  const existing = state.repos[slug]
  const now = new Date().toISOString()

  state.repos[slug] = {
    slug,
    name,
    repoUrl,
    localPath,
    status: 'pending',
    error: null,
    createdAt: existing ? existing.createdAt : now,
    indexedAt: existing ? existing.indexedAt : null
  }
  saveState()

  // Fire-and-forget — callers poll for status
  _indexAsync(slug, repoUrl, localPath, cloneDepth).catch(err =>
    console.error(`[${slug}] Unhandled indexing error: ${err.message}`)
  )

  return state.repos[slug]
}

/**
 * Trigger a re-index for an already-registered repo.
 * Equivalent to calling addRepo again — does git pull + codegraph index.
 */
function reindexRepo (slug, cloneDepth = 1) {
  const repo = state.repos[slug]
  if (!repo) throw new Error(`Repo '${slug}' not found`)

  repo.status = 'pending'
  repo.error = null
  saveState()

  _indexAsync(slug, repo.repoUrl, repo.localPath, cloneDepth).catch(err =>
    console.error(`[${slug}] Unhandled reindex error: ${err.message}`)
  )
}

/**
 * Remove a repo record and optionally delete its local directory.
 */
function removeRepo (slug, deleteLocal = false) {
  const repo = state.repos[slug]
  if (!repo) throw new Error(`Repo '${slug}' not found`)

  if (deleteLocal && fs.existsSync(repo.localPath)) {
    fs.rmSync(repo.localPath, { recursive: true, force: true })
    console.log(`[${slug}] Deleted local path ${repo.localPath}`)
  }

  delete state.repos[slug]
  saveState()
}

/**
 * Run `codegraph <command> --json [args]` in the repo's local path and return
 * the parsed JSON output.
 */
async function queryRepo (slug, command, args = []) {
  const repo = state.repos[slug]
  if (!repo) throw new Error(`Repo '${slug}' not found`)
  if (repo.status !== 'ready') throw new Error(`Repo '${slug}' is not ready (status: ${repo.status})`)

  const stdout = await runCommand('codegraph', [command, '--json', ...args], repo.localPath)
  try {
    return JSON.parse(stdout)
  } catch {
    throw new Error(`codegraph ${command} returned non-JSON output: ${stdout.slice(0, 200)}`)
  }
}

module.exports = { loadState, getRepo, listRepos, addRepo, reindexRepo, removeRepo, queryRepo, slugify }
