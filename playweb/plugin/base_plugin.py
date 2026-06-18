"""
PlayWebit Network — Base Plugin Interface
L2 apps implement this to plug into a PlayWebit node.
CipherVault, MusicApp, ArtApp etc all implement BasePlugin.

The plugin gets:
  - Event hooks from L1 (on_block_finalised, on_transaction etc)
  - SDK interface to call L1 (submit_tx, get_balance etc)
  - Clean separation — plugin cannot touch L1 internals directly
"""

from abc import ABC, abstractmethod
from typing import Optional, Dict, TYPE_CHECKING

if TYPE_CHECKING:
    from playweb.core.block       import Block
    from playweb.core.transaction import Transaction


class BasePlugin(ABC):

    # ─────────────────────────────────────────────────────────────
    # Plugin identity — subclass must set these
    # ─────────────────────────────────────────────────────────────

    plugin_id:       str = "base"         # e.g. "ciphervault"
    plugin_name:     str = "Base Plugin"  # e.g. "CipherVault"
    plugin_version:  str = "1.0.0"
    platform_wallet: str = ""             # plugin's PLWB treasury wallet

    def __init__(self):
        self._node = None   # set by plugin_manager on register

    def _set_node(self, node):
        """Called by PluginManager when plugin is registered."""
        self._node = node

    # ─────────────────────────────────────────────────────────────
    # Lifecycle hooks — L1 calls these
    # ─────────────────────────────────────────────────────────────

    def on_start(self, node):
        """
        Called when the node starts up.
        Use this to initialise your plugin's own state.
        """
        pass

    def on_stop(self):
        """Called when the node shuts down gracefully."""
        pass

    def on_block_finalised(self, block: "Block"):
        """
        Called after every block is finalised by consensus.
        NVF: Cyclic re-entry notification.
        Use this to update your L2 state from confirmed transactions.
        """
        pass

    def on_transaction(self, tx: "Transaction"):
        """
        Called when a new transaction is confirmed on chain.
        Note: also fires via on_block_finalised for each tx in block.
        """
        pass

    def on_content_registered(self, cid: str, owner: str, platform: str):
        """Called when new content is registered on the network."""
        pass

    def on_edition_transferred(
        self,
        cid:            str,
        edition_number: int,
        from_wallet:    str,
        to_wallet:      str,
    ):
        """Called when an edition changes hands."""
        pass

    # ─────────────────────────────────────────────────────────────
    # SDK interface — plugin calls L1 via these
    # These are convenience wrappers around node methods
    # ─────────────────────────────────────────────────────────────

    def submit_transaction(self, tx: "Transaction") -> tuple:
        """Submit a transaction to L1. Returns (success, tx_hash_or_reason)."""
        if not self._node:
            return False, "Plugin not attached to node"
        return self._node.blockchain.add_transaction(
            tx          = tx,
            node_wallet = self._node.node_wallet,
        )

    def get_balance(self, address: str) -> float:
        """Get PLWB balance for any address."""
        if not self._node:
            return 0.0
        return self._node.blockchain.get_balance(address)

    def register_content(
        self,
        cid:          str,
        owner_wallet: str,
        editions:     int   = 1,
        royalty_pct:  float = 0,
        signature:    str   = None,
        extra_data:   Dict  = None,
    ) -> tuple:
        """Register a CID on the network. Returns (success, reason, tx_hash)."""
        if not self._node:
            return False, "Plugin not attached to node", None
        return self._node.content_registry.register(
            cid          = cid,
            owner_wallet = owner_wallet,
            platform_id  = self.plugin_id,
            editions     = editions,
            royalty_pct  = royalty_pct,
            signature    = signature,
            extra_data   = extra_data,
        )

    def transfer_ownership(
        self,
        cid:         str,
        from_wallet: str,
        to_wallet:   str,
        signature:   str   = None,
        sale_price:  float = 0,
    ) -> tuple:
        """Transfer ownership of a CID. Returns (success, reason, tx_hash)."""
        if not self._node:
            return False, "Plugin not attached to node", None
        return self._node.content_registry.transfer_ownership(
            cid         = cid,
            from_wallet = from_wallet,
            to_wallet   = to_wallet,
            signature   = signature,
            platform_id = self.plugin_id,
            sale_price  = sale_price,
        )

    def verify_ownership(self, cid: str, wallet: str) -> bool:
        """Verify wallet owns a CID."""
        if not self._node:
            return False
        return self._node.content_registry.verify_ownership(cid, wallet)

    def check_duplicate(self, cid: str) -> Dict:
        """Check if CID is already registered anywhere on the network."""
        if not self._node:
            return {"exists": False}
        return self._node.content_registry.check_duplicate(cid)

    def anchor_spider_hash(
        self,
        chain_name:  str,
        spider_hash: str,
        event_type:  str  = "integrity_check",
        metadata:    Dict = None,
        signature:   str  = None,
    ) -> tuple:
        """
        Anchor a SpiderWeave hash on the chain.
        This is what spiderweave-sdk calls internally.
        Returns (success, tx_hash).
        """
        if not self._node:
            return False, "Plugin not attached to node"

        from playweb.core.transaction import Transaction
        tx = Transaction(
            from_addr   = self.platform_wallet.lower(),
            to_addr     = self.platform_wallet.lower(),
            amount      = 0,
            tx_type     = "spider_hash_anchor",
            signature   = signature,
            spider_hash = spider_hash,
            chain_name  = chain_name,
            data        = {
                "event_type":  event_type,
                "platform_id": self.plugin_id,
                **(metadata or {}),
            },
        )
        success, result = self.submit_transaction(tx)
        return success, result

    def get_editions(self, cid: str) -> list:
        """Get all editions for a CID."""
        if not self._node:
            return []
        return self._node.edition_registry.get_all_editions(cid)

    # ─────────────────────────────────────────────────────────────
    # Plugin info
    # ─────────────────────────────────────────────────────────────

    def get_info(self) -> Dict:
        return {
            "plugin_id":      self.plugin_id,
            "plugin_name":    self.plugin_name,
            "plugin_version": self.plugin_version,
            "platform_wallet": self.platform_wallet,
        }

    def __repr__(self):
        return f"Plugin({self.plugin_id} v{self.plugin_version})"
