"""
PlayWebit Network — Plugin Manager
Loads and manages L2 plugins.
Notifies all registered plugins when L1 events happen.
"""

import logging
from typing import Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from playweb.plugin.base_plugin import BasePlugin
    from playweb.core.block         import Block
    from playweb.core.transaction   import Transaction

logger = logging.getLogger(__name__)


class PluginManager:

    def __init__(self):
        self._plugins: Dict[str, "BasePlugin"] = {}
        self._node = None

    def set_node(self, node):
        self._node = node

    # ─────────────────────────────────────────────────────────────
    # Register plugins
    # ─────────────────────────────────────────────────────────────

    def register(self, plugin: "BasePlugin"):
        """Register a L2 plugin with this node."""
        if plugin.plugin_id in self._plugins:
            logger.warning(
                f"Plugin {plugin.plugin_id} already registered — replacing"
            )

        plugin._set_node(self._node)
        self._plugins[plugin.plugin_id] = plugin
        logger.info(
            f"Plugin registered: {plugin.plugin_name} "
            f"(v{plugin.plugin_version})"
        )

    def get_plugin(self, plugin_id: str) -> Optional["BasePlugin"]:
        return self._plugins.get(plugin_id)

    def get_all_plugins(self) -> List["BasePlugin"]:
        return list(self._plugins.values())

    # ─────────────────────────────────────────────────────────────
    # Lifecycle notifications
    # ─────────────────────────────────────────────────────────────

    def notify_start(self, node):
        """Notify all plugins that the node has started."""
        for plugin in self._plugins.values():
            try:
                plugin.on_start(node)
            except Exception as e:
                logger.error(
                    f"Plugin {plugin.plugin_id} on_start error: {e}",
                    exc_info=True
                )

    def notify_stop(self):
        """Notify all plugins that the node is stopping."""
        for plugin in self._plugins.values():
            try:
                plugin.on_stop()
            except Exception as e:
                logger.error(f"Plugin {plugin.plugin_id} on_stop error: {e}")

    # ─────────────────────────────────────────────────────────────
    # Block / Transaction notifications
    # NVF: Cyclic re-entry
    # ─────────────────────────────────────────────────────────────

    def notify_block_finalised(self, block: "Block"):
        """
        Notify all plugins that a block has been finalised.
        NVF paper: Cyclic re-entry notification after ANCHOR phase.
        Each plugin processes transactions relevant to their platform.
        """
        for plugin in self._plugins.values():
            try:
                plugin.on_block_finalised(block)

                # Also notify per-transaction
                for tx in block.transactions:
                    plugin.on_transaction(tx)

                    # Special hooks for content events
                    if tx.tx_type == "content_register" and tx.cid:
                        plugin.on_content_registered(
                            cid      = tx.cid,
                            owner    = tx.to_addr,
                            platform = tx.data.get("platform_id", "unknown")
                            if tx.data else "unknown",
                        )

                    elif tx.tx_type == "edition_transfer" and tx.cid:
                        plugin.on_edition_transferred(
                            cid            = tx.cid,
                            edition_number = tx.edition_number or 0,
                            from_wallet    = tx.from_addr,
                            to_wallet      = tx.to_addr,
                        )

            except Exception as e:
                logger.error(
                    f"Plugin {plugin.plugin_id} block notification error: {e}",
                    exc_info=True,
                )
                # Never let a plugin crash the node

    def notify_transaction(self, tx: "Transaction"):
        """Notify all plugins of a new transaction (before block)."""
        for plugin in self._plugins.values():
            try:
                plugin.on_transaction(tx)
            except Exception as e:
                logger.error(
                    f"Plugin {plugin.plugin_id} tx notification error: {e}"
                )

    def get_status(self) -> Dict:
        return {
            "plugin_count": len(self._plugins),
            "plugins": [p.get_info() for p in self._plugins.values()],
        }
