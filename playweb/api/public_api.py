"""
PlayWebit Network — Public API
HTTP endpoints for dApps, clients, and the spiderweave-sdk.

spiderweave-sdk's PlayWebitAdapter calls:
  POST /api/anchor_spider_hash
  GET  /api/transaction/{tx_hash}
  GET  /api/spider_hashes/{chain_id}

All other endpoints are for general dApp use.
"""

import logging
from flask import Blueprint, request, jsonify

logger = logging.getLogger(__name__)


def create_public_api(node) -> Blueprint:
    """
    Factory — creates the public API blueprint bound to a node instance.
    Mount in Flask app: app.register_blueprint(create_public_api(node))
    """
    bp = Blueprint("public_api", __name__, url_prefix="/api")

    # ─────────────────────────────────────────────────────────────
    # Spider Hash Anchor
    # Called by spiderweave-sdk's PlayWebitAdapter
    # ─────────────────────────────────────────────────────────────

    @bp.route("/anchor_spider_hash", methods=["POST"])
    def anchor_spider_hash():
        """
        Anchor a SpiderWeave hash on the chain.
        L1 stores it, never interprets it.
        The hash can represent any database state on any platform.
        """
        data = request.get_json(silent=True)
        if not data:
            return jsonify({"success": False, "error": "Missing body"}), 400

        chain_name      = data.get("chain_id") or data.get("chain_name")
        spider_hash     = data.get("spider_hash")
        event_type      = data.get("event_type", "integrity_check")
        platform_wallet = data.get("platform_wallet") or data.get("wallet")
        signature       = data.get("signature")
        metadata        = data.get("metadata", {})

        if not chain_name or not spider_hash:
            return jsonify({
                "success": False,
                "error":   "Missing chain_id/chain_name and spider_hash",
            }), 400

        if not platform_wallet:
            return jsonify({
                "success": False,
                "error":   "Missing platform_wallet",
            }), 400

        from playweb.core.transaction import Transaction
        tx = Transaction(
            from_addr   = platform_wallet.lower(),
            to_addr     = platform_wallet.lower(),
            amount      = 0,
            tx_type     = "spider_hash_anchor",
            signature   = signature,
            spider_hash = spider_hash,
            chain_name  = chain_name,
            data        = {
                "event_type":  event_type,
                "platform":    data.get("platform_id", "unknown"),
                **metadata,
            },
        )

        success, result = node.blockchain.add_transaction(
            tx          = tx,
            node_wallet = node.node_wallet,
        )

        if not success:
            return jsonify({"success": False, "error": result}), 400

        # Broadcast to peers
        node.gossip.broadcast_transaction(
            tx    = tx,
            peers = node.peer_manager.get_active_peers(),
        )

        return jsonify({
            "success":  True,
            "tx_hash":  tx.hash,
            "chain_id": chain_name,
            "status":   "pending",
        })

    # ─────────────────────────────────────────────────────────────
    # Get transaction
    # Called by spiderweave-sdk to verify anchored hashes
    # ─────────────────────────────────────────────────────────────

    @bp.route("/transaction/<tx_hash>", methods=["GET"])
    def get_transaction(tx_hash):
        tx = node.blockchain.get_transaction(tx_hash)
        if not tx:
            return jsonify({"success": False, "error": "Transaction not found"}), 404
        return jsonify({
            "success":     True,
            "transaction": tx.to_dict(),
        })

    # ─────────────────────────────────────────────────────────────
    # Get spider hashes for a chain
    # Called by spiderweave-sdk to get all anchored hashes
    # ─────────────────────────────────────────────────────────────

    @bp.route("/spider_hashes/<chain_name>", methods=["GET"])
    def get_spider_hashes(chain_name):
        hashes = []

        # ── Confirmed (in blocks) ─────────────────────────────────
        length    = node.blockchain.get_chain_length()
        scan_from = max(0, length - 1000)
        blocks    = node.blockchain.get_blocks_from(scan_from, 1000)

        for block in blocks:
            for tx in block.transactions:
                if (
                    tx.tx_type == "spider_hash_anchor"
                    and tx.chain_name == chain_name
                ):
                    hashes.append({
                        "tx_hash":     tx.hash,
                        "spider_hash": tx.spider_hash,
                        "timestamp":   tx.timestamp,
                        "block_index": block.index,
                        "status":      "confirmed",
                        "event_type":  tx.data.get("event_type")
                                       if tx.data else None,
                    })

        # ── Pending (in mempool — not yet mined) ─────────────────
        for tx in node.blockchain.mempool.get_pending():
            if (
                tx.tx_type == "spider_hash_anchor"
                and tx.chain_name == chain_name
            ):
                hashes.append({
                    "tx_hash":     tx.hash,
                    "spider_hash": tx.spider_hash,
                    "timestamp":   tx.timestamp,
                    "block_index": None,
                    "status":      "pending",
                    "event_type":  tx.data.get("event_type")
                                   if tx.data else None,
                })

        return jsonify({
            "success":    True,
            "chain_name": chain_name,
            "count":      len(hashes),
            "confirmed":  len([h for h in hashes if h["status"] == "confirmed"]),
            "pending":    len([h for h in hashes if h["status"] == "pending"]),
            "hashes":     hashes,
        })

    # ─────────────────────────────────────────────────────────────
    # Balance
    # ─────────────────────────────────────────────────────────────

    @bp.route("/balance/<address>", methods=["GET"])
    def get_balance(address):
        balance = node.blockchain.get_balance(address)
        return jsonify({
            "success":  True,
            "address":  address.lower(),
            "balance":  balance,
            "currency": "PLWB",
        })

    # ─────────────────────────────────────────────────────────────
    # Submit transaction
    # ─────────────────────────────────────────────────────────────

    @bp.route("/transaction", methods=["POST"])
    def submit_transaction():
        data = request.get_json(silent=True)
        if not data:
            return jsonify({"success": False, "error": "Missing body"}), 400

        from playweb.core.transaction import Transaction
        try:
            tx = Transaction.from_dict(data)
        except Exception as e:
            return jsonify({"success": False, "error": f"Invalid tx: {e}"}), 400

        success, result = node.blockchain.add_transaction(
            tx          = tx,
            node_wallet = node.node_wallet,
        )

        if success:
            node.gossip.broadcast_transaction(
                tx    = tx,
                peers = node.peer_manager.get_active_peers(),
            )

        return jsonify({"success": success, "result": result})

    # ─────────────────────────────────────────────────────────────
    # PLWB Transfer between wallets
    # ─────────────────────────────────────────────────────────────

    @bp.route("/transfer", methods=["POST"])
    def transfer_plwb():
        data = request.get_json(silent=True) or {}
    
        # If full tx dict provided (pre-signed) — use it directly
        if "hash" in data and "signature" in data and "nonce" in data:
            from playweb.core.transaction import Transaction
            try:
                tx = Transaction.from_dict(data)
            except Exception as e:
                return jsonify({"success": False, "error": f"Invalid tx: {e}"}), 400
        else:
            # Build from individual fields
            from_addr = data.get("from_addr")
            to_addr   = data.get("to_addr")
            amount    = data.get("amount")
            signature = data.get("signature")
    
            if not all([from_addr, to_addr, amount, signature]):
                return jsonify({
                    "success": False,
                    "error":   "Missing: from_addr, to_addr, amount, signature",
                }), 400
    
            if float(amount) <= 0:
                return jsonify({
                    "success": False,
                    "error":   "Amount must be greater than 0",
                }), 400
    
            from playweb.core.transaction import Transaction
            tx = Transaction(
                from_addr = from_addr,
                to_addr   = to_addr,
                amount    = float(amount),
                tx_type   = "transfer",
                signature = signature,
            )
    
        success, result = node.blockchain.add_transaction(
            tx          = tx,
            node_wallet = node.node_wallet,
        )
        if not success:
            return jsonify({"success": False, "error": result}), 400
    
        node.gossip.broadcast_transaction(
            tx    = tx,
            peers = node.peer_manager.get_active_peers(),
        )
    
        return jsonify({
            "success": True,
            "tx_hash": tx.hash,
            "from":    tx.from_addr,
            "to":      tx.to_addr,
            "amount":  tx.amount,
            "fee":     1.0,
            "total":   tx.amount + 1.0,
            "status":  "pending",
        })

    # ─────────────────────────────────────────────────────────────
    # Content ownership
    # ─────────────────────────────────────────────────────────────

    @bp.route("/owner/<path:cid>", methods=["GET"])
    def get_owner(cid):
        """Who owns this CID across all platforms."""
        owner = node.content_registry.get_owner(cid)
        if not owner:
            return jsonify({
                "success": False,
                "error":   "CID not registered on PlayWebit Network",
            }), 404
        return jsonify({"success": True, **owner})

    @bp.route("/check_duplicate/<path:cid>", methods=["GET"])
    def check_duplicate(cid):
        """Is this CID already registered anywhere on the network?"""
        result = node.content_registry.check_duplicate(cid)
        return jsonify({"success": True, **result})

    @bp.route("/verify_ownership", methods=["POST"])
    def verify_ownership():
        data   = request.get_json(silent=True) or {}
        cid    = data.get("cid")
        wallet = data.get("wallet")
        if not cid or not wallet:
            return jsonify({
                "success": False,
                "error":   "Missing cid or wallet",
            }), 400
        owns = node.content_registry.verify_ownership(cid, wallet)
        return jsonify({
            "success": True,
            "owns":    owns,
            "cid":     cid,
            "wallet":  wallet,
        })

    # ─────────────────────────────────────────────────────────────
    # Editions
    # ─────────────────────────────────────────────────────────────

    @bp.route("/editions/<path:cid>", methods=["GET"])
    def get_editions(cid):
        """All editions, all owners, all platforms for a CID."""
        summary = node.edition_registry.get_edition_summary(cid)
        return jsonify({"success": True, **summary})

    @bp.route("/editions/<path:cid>/<int:edition_number>", methods=["GET"])
    def get_edition(cid, edition_number):
        edition = node.edition_registry.get_edition(cid, edition_number)
        if not edition:
            return jsonify({"success": False, "error": "Edition not found"}), 404
        return jsonify({"success": True, "edition": edition})

    @bp.route("/editions/<path:cid>/available", methods=["GET"])
    def get_available_editions(cid):
        """
        Editions still owned by original creator = not yet sold.
        Used by CipherVault creator tab to show available editions.
        """
        content = node.blockchain.storage.get_content_record(cid)
        if not content:
            return jsonify({"success": False, "error": "CID not found"}), 404

        creator      = content["creator_wallet"]
        all_editions = node.edition_registry.get_all_editions(cid)
        total        = content["total_editions"]

        available = [
            e for e in all_editions
            if e["current_owner"].lower() == creator.lower()
        ]
        sold = [
            e for e in all_editions
            if e["current_owner"].lower() != creator.lower()
        ]

        return jsonify({
            "success":   True,
            "cid":       cid,
            "total":     total,
            "available": len(available),
            "sold":      len(sold),
            "creator":   creator,
            "editions":  all_editions,
        })

    # ─────────────────────────────────────────────────────────────
    # Network stats
    # ─────────────────────────────────────────────────────────────

    @bp.route("/network/stats", methods=["GET"])
    def network_stats():
        tip   = node.blockchain.get_chain_tip()
        stats = node.blockchain.get_stats()
        return jsonify({
            "success":      True,
            "chain_id":     4968,
            "currency":     "PLWB",
            "block_height": tip.index if tip else 0,
            "chain_length": stats["chain_length"],
            "pending_txs":  stats["pending_tx_count"],
            "node_count":   node.peer_manager.peer_count() + 1,
            "node_wallet":  node.node_wallet,
            "consensus":    node.consensus.get_status(),
            "sync":         node.sync.get_sync_status(),
            "plugins":      node.plugin_manager.get_status(),
        })

    return bp  # ← always last, after ALL routes
