"""
PlayWebit Network — Node API (Peer-to-Peer)
HTTP endpoints for node-to-node communication.
Every node exposes these. Peers call these directly.
Works on all cloud platforms — no WebSocket needed.
"""

import logging
from flask import Blueprint, request, jsonify

logger = logging.getLogger(__name__)


def create_node_api(node) -> Blueprint:
    """
    Factory — creates the peer API blueprint bound to a node instance.
    Mount in Flask app: app.register_blueprint(create_node_api(node))
    """
    bp = Blueprint("node_api", __name__, url_prefix="/peer")

    # ─────────────────────────────────────────────────────────────
    # Health check
    # ─────────────────────────────────────────────────────────────

    @bp.route("/health", methods=["GET"])
    def health():
        tip = node.blockchain.get_chain_tip()
        return jsonify({
            "status":       "ok",
            "node_wallet":  node.node_wallet,
            "block_height": tip.index if tip else 0,
            "peer_count":   node.peer_manager.peer_count(),
            "chain_id":     4968,
            "synced":       node.sync.get_sync_status()["synced"],
        })

    # ─────────────────────────────────────────────────────────────
    # Chain tip — used by new nodes to find canonical chain
    # ─────────────────────────────────────────────────────────────

    @bp.route("/chain_tip", methods=["GET"])
    def chain_tip():
        tip = node.blockchain.get_chain_tip()
        if not tip:
            return jsonify({"block_index": -1, "block_hash": None})
        return jsonify({
            "block_index": tip.index,
            "block_hash":  tip.hash,
            "timestamp":   tip.timestamp,
        })

    # ─────────────────────────────────────────────────────────────
    # Block range — used during chain sync
    # ─────────────────────────────────────────────────────────────

    @bp.route("/blocks/<int:from_index>/<int:to_index>", methods=["GET"])
    def get_blocks(from_index, to_index):
        limit  = min(to_index - from_index + 1, 50)   # max 50 per request
        blocks = node.blockchain.get_blocks_from(from_index, limit)
        return jsonify({
            "blocks":     [b.to_dict() for b in blocks],
            "from_index": from_index,
            "to_index":   to_index,
            "count":      len(blocks),
        })

    # ─────────────────────────────────────────────────────────────
    # Peer list — new nodes get peers from existing nodes
    # ─────────────────────────────────────────────────────────────

    @bp.route("/peers", methods=["GET"])
    def get_peers():
        return jsonify({
            "peers": node.peer_manager.get_peer_list_for_sharing(),
            "my_url": node.node_url,
        })

    # ─────────────────────────────────────────────────────────────
    # Receive new transaction from peer
    # ─────────────────────────────────────────────────────────────

    @bp.route("/new_transaction", methods=["POST"])
    def new_transaction():
        data = request.get_json(silent=True)
        if not data or "transaction" not in data:
            return jsonify({"success": False, "error": "Missing transaction"}), 400

        from playweb.core.transaction import Transaction
        try:
            tx = Transaction.from_dict(data["transaction"])
        except Exception as e:
            return jsonify({"success": False, "error": f"Invalid tx: {e}"}), 400

        # Skip if already in mempool or chain
        if node.blockchain.mempool.contains(tx.hash):
            return jsonify({"success": True, "status": "already_known"})

        success, result = node.blockchain.add_transaction(
            tx          = tx,
            node_wallet = node.node_wallet,
        )

        if success:
            # Forward to our peers (gossip propagation)
            node.gossip.broadcast_transaction(
                tx    = tx,
                peers = node.peer_manager.get_active_peers(),
            )

        return jsonify({
            "success": success,
            "result":  result,
        })

    # ─────────────────────────────────────────────────────────────
    # Receive block proposal from consensus leader
    # NVF: Spacetime Fabric activation received
    # ─────────────────────────────────────────────────────────────

    @bp.route("/propose", methods=["POST"])
    def propose():
        data = request.get_json(silent=True)
        if not data or "block" not in data:
            return jsonify({"success": False, "error": "Missing block"}), 400

        from playweb.core.block import Block
        try:
            block        = Block.from_dict(data["block"])
            round_number = data.get("round_number", block.index)
            from_peer    = data.get("from_node", "unknown")
        except Exception as e:
            return jsonify({"success": False, "error": f"Invalid block: {e}"}), 400

        # Hand off to consensus engine
        node.consensus.on_propose(block, round_number, from_peer)

        return jsonify({"success": True, "status": "proposal_received"})

    # ─────────────────────────────────────────────────────────────
    # Receive consensus vote
    # NVF: Planck Threshold approach
    # ─────────────────────────────────────────────────────────────

    @bp.route("/vote", methods=["POST"])
    def receive_vote():
        data = request.get_json(silent=True)
        if not data or "vote" not in data:
            return jsonify({"success": False, "error": "Missing vote"}), 400

        from playweb.consensus.vote import Vote
        try:
            vote = Vote.from_dict(data["vote"])
        except Exception as e:
            return jsonify({"success": False, "error": f"Invalid vote: {e}"}), 400

        node.consensus.on_vote(vote)
        return jsonify({"success": True, "status": "vote_received"})

    # ─────────────────────────────────────────────────────────────
    # Receive finalised block from peer
    # For nodes that missed consensus round
    # ─────────────────────────────────────────────────────────────

    @bp.route("/new_block", methods=["POST"])
    def new_block():
        data = request.get_json(silent=True)
        if not data or "block" not in data:
            return jsonify({"success": False, "error": "Missing block"}), 400

        from playweb.core.block import Block
        try:
            block = Block.from_dict(data["block"])
            votes = data.get("votes", [])
        except Exception as e:
            return jsonify({"success": False, "error": f"Invalid block: {e}"}), 400

        # Check if we already have this block
        existing = node.blockchain.get_block(block.hash)
        if existing:
            return jsonify({"success": True, "status": "already_known"})

        # Add to chain
        success, result = node.blockchain.add_block(
            block       = block,
            votes       = votes,
            node_wallet = node.node_wallet,
        )

        return jsonify({"success": success, "result": result})

    # ─────────────────────────────────────────────────────────────
    # New node joined the network
    # Cloudflare calls this when a new node registers
    # ─────────────────────────────────────────────────────────────

    @bp.route("/new_node", methods=["POST"])
    def new_node():
        data = request.get_json(silent=True)
        if not data or "url" not in data or "wallet" not in data:
            return jsonify({"success": False, "error": "Missing url or wallet"}), 400

        added = node.peer_manager.add_peer(
            url      = data["url"],
            wallet   = data["wallet"],
            platform = data.get("platform", "unknown"),
            role     = data.get("role", "validator"),
        )

        if added:
            logger.info(f"New peer joined: {data['url']}")
            # Forward new node info to our peers
            node.gossip.broadcast_new_node(
                new_node_url    = data["url"],
                new_node_wallet = data["wallet"],
                peers           = node.peer_manager.get_active_peers(),
            )

        return jsonify({
            "success":    True,
            "added":      added,
            "peer_count": node.peer_manager.peer_count(),
        })

    return bp
