"""
PlayWebit Network — CipherVault Plugin Stub
Shows how to refactor CipherVault as a L2 plugin.

This is a STUB — shows the structure.
The actual CipherVault logic moves into on_block_finalised
and the platform-specific Flask routes.
"""

import os
import logging
from typing import Dict

from playweb.plugin.base_plugin import BasePlugin

logger = logging.getLogger(__name__)


class CipherVaultPlugin(BasePlugin):

    plugin_id      = "ciphervault"
    plugin_name    = "CipherVault"
    plugin_version = "2.0.0"
    platform_wallet = os.getenv("CIPHERVAULT_PLATFORM_WALLET", "")

    def __init__(self, supabase_url: str, supabase_key: str):
        super().__init__()
        from supabase import create_client, ClientOptions
        import httpx
    
        httpx_client = httpx.Client(
            http2=False,
            timeout=httpx.Timeout(connect=10.0, read=30.0, write=30.0, pool=10.0),
            limits=httpx.Limits(max_connections=20, max_keepalive_connections=5, keepalive_expiry=15.0),
        )
        self.supabase = create_client(supabase_url, supabase_key, options=ClientOptions(httpx_client=httpx_client))

    # ─────────────────────────────────────────────────────────────
    # L1 lifecycle hooks
    # ─────────────────────────────────────────────────────────────

    def on_start(self, node):
        logger.info("CipherVault plugin started")

    def on_block_finalised(self, block):
        """
        Every confirmed block — update CipherVault's own state.
        Only process transactions relevant to CipherVault.
        """
        for tx in block.transactions:
            if tx.data and tx.data.get("platform_id") == "ciphervault":
                self._handle_ciphervault_tx(tx)

    def _handle_ciphervault_tx(self, tx):
        """Handle CipherVault-specific confirmed transactions."""
        if tx.tx_type == "content_register":
            # Update CipherVault's own vault_nfts table
            self._update_vault_nft(tx)
        elif tx.tx_type == "ownership_transfer":
            # Update CipherVault's ownership records
            self._update_ownership(tx)

    def on_content_registered(self, cid: str, owner: str, platform: str):
        if platform == "ciphervault":
            logger.info(f"CipherVault: content registered {cid[:16]}...")

    def on_edition_transferred(self, cid, edition_number, from_wallet, to_wallet):
        logger.info(
            f"CipherVault: edition #{edition_number} of {cid[:16]}... "
            f"→ {to_wallet[:8]}..."
        )

    # ─────────────────────────────────────────────────────────────
    # CipherVault L2 operations
    # These call L1 via the inherited SDK interface methods
    # ─────────────────────────────────────────────────────────────

    def link_file(
        self,
        cid:         str,
        owner_wallet: str,
        editions:    int   = 1,
        royalty_pct: float = 0,
        signature:   str   = None,
        metadata:    Dict  = None,
    ) -> tuple:
        """
        Link a file to the chain (CipherVault's cv_link action).
        Calls L1 register_content via the plugin SDK interface.
        """
        return self.register_content(
            cid         = cid,
            owner_wallet = owner_wallet,
            editions    = editions,
            royalty_pct = royalty_pct,
            signature   = signature,
            extra_data  = metadata,
        )

    def buy_file(
        self,
        cid:          str,
        buyer_wallet: str,
        seller_wallet: str,
        price:        float,
        signature:    str = None,
    ) -> tuple:
        """
        Buy a file — transfers ownership with royalty payment.
        L1 automatically enforces royalty split.
        """
        return self.transfer_ownership(
            cid         = cid,
            from_wallet = seller_wallet,
            to_wallet   = buyer_wallet,
            signature   = signature,
            sale_price  = price,
        )

    def anchor_integrity_hash(
        self,
        table_name:  str,
        spider_hash: str,
        event_type:  str = "table_update",
        signature:   str = None,
    ) -> tuple:
        """Anchor a SpiderWeave integrity hash for a CipherVault table."""
        return self.anchor_spider_hash(
            chain_name  = f"ciphervault_{table_name}",
            spider_hash = spider_hash,
            event_type  = event_type,
            signature   = signature,
        )

    # ─────────────────────────────────────────────────────────────
    # Internal Supabase updates (CipherVault's own L2 state)
    # ─────────────────────────────────────────────────────────────

    def _update_vault_nft(self, tx):
        try:
            self.supabase.table("cv_vault_nfts").upsert({
                "cid":           tx.cid,
                "owner_wallet":  tx.to_addr,
                "tx_hash":       tx.hash,
                "confirmed":     True,
            }).execute()
        except Exception as e:
            logger.error(f"CipherVault: _update_vault_nft error: {e}")

    def _update_ownership(self, tx):
        try:
            if tx.cid:
                self.supabase.table("cv_vault_nfts").update({
                    "owner_wallet": tx.to_addr,
                    "tx_hash":      tx.hash,
                }).eq("cid", tx.cid).execute()
        except Exception as e:
            logger.error(f"CipherVault: _update_ownership error: {e}")


# ── Usage ──────────────────────────────────────────────────────────
if __name__ == "__main__":
    import os
    from playweb import PlayWebitNode
    from playweb.storage.supabase_storage import SupabaseStorage

    # L1 storage (node's own chain storage)
    storage = SupabaseStorage(
        url = os.environ["SUPABASE_URL"],
        key = os.environ["SUPABASE_ANON_KEY"],
    )

    # L2 plugin (CipherVault's own state)
    plugin = CipherVaultPlugin(
        supabase_url = os.environ["SUPABASE_URL"],
        supabase_key = os.environ["SUPABASE_ANON_KEY"],
    )

    # Full node with CipherVault plugin attached
    node = PlayWebitNode(
        storage          = storage,
        node_wallet      = os.environ["NODE_WALLET_ADDRESS"],
        node_private_key = os.environ["NODE_WALLET_PRIVATE_KEY"],
        node_public_url  = os.environ["NODE_PUBLIC_URL"],
        platform         = "ciphervault",
        plugin           = plugin,
    )

    # Get Flask app and add CipherVault's own routes on top
    app = node.get_flask_app()

    @app.route("/cv/link", methods=["POST"])
    def cv_link():
        # CipherVault-specific route — not part of L1
        from flask import request, jsonify
        data    = request.get_json()
        success, reason, tx_hash = plugin.link_file(
            cid          = data["cid"],
            owner_wallet = data["wallet"],
            editions     = data.get("editions", 1),
            royalty_pct  = data.get("royalty_pct", 0),
            signature    = data.get("signature"),
        )
        return jsonify({"success": success, "reason": reason, "tx_hash": tx_hash})

    # Start node (non-blocking so Flask can serve routes above too)
    import threading
    t = threading.Thread(target=lambda: node.start(blocking=False), daemon=True)
    t.start()

    # Run Flask
    app.run(host="0.0.0.0", port=7860, debug=False)
