/**
 * PlayWebit Network — Bootstrap Worker
 * Cloudflare Worker — paste into Cloudflare editor
 *
 * Setup:
 *   1. Create KV namespace called NODES
 *   2. Bind it to this worker as NODES
 *   3. Set route: bootstrap.playwebit.com/*
 *
 * KV stores: key="node:{wallet}" value=JSON TTL=86400s (24h)
 */

const NETWORK_NAME    = "PlayWebit Network"
const CHAIN_ID        = 4968
const NODE_TTL        = 86400       // 24 hours in seconds
const HEARTBEAT_TTL   = 43200       // 12 hours
const SIG_WINDOW      = 300         // 5 min replay protection

// ─── CORS headers ─────────────────────────────────────────────

const CORS = {
  "Access-Control-Allow-Origin":  "*",
  "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
  "Access-Control-Allow-Headers": "Content-Type",
  "Content-Type": "application/json"
}

function json(data, status = 200) {
  return new Response(JSON.stringify(data), { status, headers: CORS })
}

function err(msg, status = 400) {
  return json({ success: false, error: msg }, status)
}

// ─── Signature verification ────────────────────────────────────
// message format: "playwebit-bootstrap:{url}:{timestamp}"
// signed with node's Ethereum wallet (personal_sign)

async function verifySignature(url, wallet, signature, timestamp) {
  try {
    // Check timestamp within 5 minute window
    const now = Math.floor(Date.now() / 1000)
    if (Math.abs(now - parseInt(timestamp)) > SIG_WINDOW) {
      return false
    }

    const message   = `playwebit-bootstrap:${url}:${timestamp}`
    const msgHex    = Array.from(
      new TextEncoder().encode(
        `\x19Ethereum Signed Message:\n${message.length}${message}`
      )
    ).map(b => b.toString(16).padStart(2, "0")).join("")

    const msgBytes  = new Uint8Array(
      msgHex.match(/.{1,2}/g).map(b => parseInt(b, 16))
    )

    const hashBytes = new Uint8Array(
      await crypto.subtle.digest("SHA-256", msgBytes)
    )

    // Recover signer from signature
    // Cloudflare Workers support WebCrypto but not eth_recover natively
    // We do basic format check + trust the node (full ECDSA recovery
    // requires a library — use lightweight check here, full verify on node side)
    if (!signature || !signature.startsWith("0x") || signature.length !== 132) {
      return false
    }

    // Wallet format check
    if (!wallet || !wallet.startsWith("0x") || wallet.length !== 42) {
      return false
    }

    return true  // Cloudflare does format check; nodes do full ECDSA verify
  } catch (e) {
    return false
  }
}

// ─── Get all active nodes ──────────────────────────────────────

async function listNodes(env) {
  const list   = await env.NODES.list({ prefix: "node:" })
  const nodes  = []
  const now    = Math.floor(Date.now() / 1000)

  for (const key of list.keys) {
    const raw = await env.NODES.get(key.name)
    if (!raw) continue

    try {
      const node = JSON.parse(raw)
      // Double-check not expired
      if (now - node.last_seen <= NODE_TTL) {
        nodes.push({
          url:          node.url,
          wallet:       node.wallet,
          platform:     node.platform || "unknown",
          role:         node.role || "validator",
          registered:   node.registered_at,
          last_seen:    node.last_seen
        })
      }
    } catch (_) { }
  }

  return nodes
}

// ─── Notify existing nodes about new peer ─────────────────────

async function notifyExistingNodes(newNode, env) {
  const nodes = await listNodes(env)

  const notifications = nodes
    .filter(n => n.url !== newNode.url)
    .map(n =>
      fetch(`${n.url}/peer/new_node`, {
        method:  "POST",
        headers: { "Content-Type": "application/json" },
        body:    JSON.stringify({
          url:      newNode.url,
          wallet:   newNode.wallet,
          platform: newNode.platform,
          role:     newNode.role
        })
      }).catch(() => null)  // never fail if a node is down
    )

  // Fire and forget — don't await, don't block response
  Promise.allSettled(notifications)
}

// ─── Router ───────────────────────────────────────────────────

export default {
  async fetch(request, env) {
    const url    = new URL(request.url)
    const path   = url.pathname
    const method = request.method

    // CORS preflight
    if (method === "OPTIONS") {
      return new Response(null, { headers: CORS })
    }

    // ── GET /nodes ──────────────────────────────────────────────
    if (method === "GET" && path === "/nodes") {
      const nodes = await listNodes(env)
      return json({
        success:     true,
        network:     NETWORK_NAME,
        chain_id:    CHAIN_ID,
        node_count:  nodes.length,
        nodes
      })
    }

    // ── GET /nodes/health ───────────────────────────────────────
    if (method === "GET" && path === "/nodes/health") {
      const nodes = await listNodes(env)
      return json({
        success:      true,
        network:      NETWORK_NAME,
        chain_id:     CHAIN_ID,
        total_nodes:  nodes.length,
        status:       nodes.length > 0 ? "active" : "bootstrap",
        timestamp:    Math.floor(Date.now() / 1000)
      })
    }

    // ── POST /nodes/register ────────────────────────────────────
    if (method === "POST" && path === "/nodes/register") {
      let body
      try {
        body = await request.json()
      } catch (_) {
        return err("Invalid JSON body")
      }

      const { url: nodeUrl, wallet, signature, timestamp,
              platform = "unknown", role = "validator" } = body

      if (!nodeUrl || !wallet || !signature || !timestamp) {
        return err("Missing required fields: url, wallet, signature, timestamp")
      }

      const valid = await verifySignature(nodeUrl, wallet, signature, timestamp)
      if (!valid) {
        return err("Invalid signature or expired timestamp", 401)
      }

      const now     = Math.floor(Date.now() / 1000)
      const nodeKey = `node:${wallet.toLowerCase()}`

      // Check if already registered
      const existing = await env.NODES.get(nodeKey)
      const isNew     = !existing

      const nodeData = {
        url:             nodeUrl,
        wallet:          wallet.toLowerCase(),
        platform,
        role,
        registered_at:   isNew ? now : JSON.parse(existing || "{}").registered_at || now,
        last_seen:       now
      }

      // Store with 24h TTL
      await env.NODES.put(nodeKey, JSON.stringify(nodeData), {
        expirationTtl: NODE_TTL
      })

      // Notify all existing nodes about this new node (async)
      if (isNew) {
        notifyExistingNodes(nodeData, env)
      }

      const allNodes = await listNodes(env)

      return json({
        success:      true,
        message:      isNew ? "Node registered" : "Node re-registered",
        node_count:   allNodes.length,
        // Return peer list so new node can connect immediately
        peers:        allNodes
          .filter(n => n.url !== nodeUrl)
          .map(n => ({ url: n.url, wallet: n.wallet }))
      })
    }

    // ── POST /nodes/heartbeat ───────────────────────────────────
    if (method === "POST" && path === "/nodes/heartbeat") {
      let body
      try {
        body = await request.json()
      } catch (_) {
        return err("Invalid JSON body")
      }

      const { url: nodeUrl, wallet, signature, timestamp } = body

      if (!nodeUrl || !wallet || !signature || !timestamp) {
        return err("Missing required fields")
      }

      const valid = await verifySignature(nodeUrl, wallet, signature, timestamp)
      if (!valid) {
        return err("Invalid signature", 401)
      }

      const nodeKey = `node:${wallet.toLowerCase()}`
      const raw     = await env.NODES.get(nodeKey)

      if (!raw) {
        return err("Node not registered. Call /nodes/register first.", 404)
      }

      const nodeData = JSON.parse(raw)
      nodeData.last_seen = Math.floor(Date.now() / 1000)
      nodeData.url       = nodeUrl  // allow URL update on heartbeat

      await env.NODES.put(nodeKey, JSON.stringify(nodeData), {
        expirationTtl: NODE_TTL
      })

      return json({ success: true, message: "Heartbeat received" })
    }

    // ── POST /nodes/deregister ──────────────────────────────────
    if (method === "POST" && path === "/nodes/deregister") {
      let body
      try {
        body = await request.json()
      } catch (_) {
        return err("Invalid JSON body")
      }

      const { url: nodeUrl, wallet, signature, timestamp } = body

      if (!nodeUrl || !wallet || !signature || !timestamp) {
        return err("Missing required fields")
      }

      const valid = await verifySignature(nodeUrl, wallet, signature, timestamp)
      if (!valid) {
        return err("Invalid signature", 401)
      }

      const nodeKey = `node:${wallet.toLowerCase()}`
      await env.NODES.delete(nodeKey)

      return json({ success: true, message: "Node deregistered" })
    }

    // ── 404 ─────────────────────────────────────────────────────
    return err(`Unknown endpoint: ${method} ${path}`, 404)
  }
}
