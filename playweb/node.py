"""
PlayWebit Network — PlayWebitNode
Main entry point for running a full validator node.
Wires all components together.

Usage:
    from playweb import PlayWebitNode
    from playweb.storage.supabase_storage import SupabaseStorage

    storage = SupabaseStorage(url=..., key=...)
    node = PlayWebitNode(
        storage          = storage,
        node_wallet      = "0xYourWallet",
        node_private_key = os.getenv("NODE_WALLET_PRIVATE_KEY"),
        node_public_url  = "https://your-node.com",
    )
    node.start()
"""

import os
import time
import logging
import threading
from typing import Optional, TYPE_CHECKING

from playweb.core.blockchain          import Blockchain
from playweb.core.fee_engine          import FeeEngine
from playweb.core.royalty_engine      import RoyaltyEngine
from playweb.consensus.nvf_bft        import NVFBFTConsensus
from playweb.network.peer_manager     import PeerManager
from playweb.network.bootstrap        import Bootstrap
from playweb.network.gossip           import GossipProtocol
from playweb.network.sync             import ChainSync
from playweb.registry.content_registry import ContentRegistry
from playweb.registry.edition_registry import EditionRegistry
from playweb.plugin.plugin_manager    import PluginManager
from playweb.config                   import LOG_LEVEL, NODE_PORT

if TYPE_CHECKING:
    from playweb.plugin.base_plugin import BasePlugin
    from playweb.storage.base       import ChainStorage

logging.basicConfig(
    level   = getattr(logging, LOG_LEVEL, logging.INFO),
    format  = "%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger(__name__)


class PlayWebitNode:

    def __init__(
        self,
        storage,
        node_wallet:      str,
        node_private_key: str,
        node_public_url:  str,
        platform:         str           = "unknown",
        plugin:           Optional["BasePlugin"] = None,
        port:             int           = NODE_PORT,
    ):
        self.node_wallet     = node_wallet.lower()
        self.node_private_key = node_private_key
        self.node_url        = node_public_url.rstrip("/")
        self.platform        = platform
        self.port            = port

        # ── Core ────────────────────────────────────────────────
        self.blockchain = Blockchain(storage)

        # ── Registries ──────────────────────────────────────────
        self.content_registry = ContentRegistry(self.blockchain, self.node_wallet)
        self.edition_registry = EditionRegistry(self.blockchain, self.node_wallet)

        # ── Network ─────────────────────────────────────────────
        self.peer_manager = PeerManager(self.node_url, self.node_wallet)
        self.gossip       = GossipProtocol(self.node_wallet)
        self.bootstrap    = Bootstrap(
            node_url         = self.node_url,
            node_wallet      = self.node_wallet,
            node_private_key = self.node_private_key,
            platform         = self.platform,
        )
        self.sync = ChainSync(self.blockchain, self.peer_manager)

        # ── Plugins ─────────────────────────────────────────────
        self.plugin_manager = PluginManager()
        self.plugin_manager.set_node(self)

        # ── Consensus ───────────────────────────────────────────
        self.consensus = NVFBFTConsensus(
            blockchain         = self.blockchain,
            peer_manager       = self.peer_manager,
            gossip             = self.gossip,
            node_wallet        = self.node_wallet,
            node_private_key   = self.node_private_key,
            plugin_manager     = self.plugin_manager,
            on_block_finalised = self._on_block_finalised,
        )

        # Register plugin if provided
        if plugin:
            self.register_plugin(plugin)

        self._flask_app  = None
        self._flask_thread: Optional[threading.Thread] = None
        self._running    = False

        logger.info(
            f"PlayWebitNode initialised: "
            f"wallet={self.node_wallet[:12]}... "
            f"url={self.node_url}"
        )

    # ─────────────────────────────────────────────────────────────
    # Plugin registration
    # ─────────────────────────────────────────────────────────────

    def register_plugin(self, plugin: "BasePlugin"):
        """Register a L2 plugin with this node."""
        self.plugin_manager.register(plugin)

    # ─────────────────────────────────────────────────────────────
    # Start
    # ─────────────────────────────────────────────────────────────

    def start(self, blocking: bool = True):
        """
        Start the node:
          1. Discover peers via Cloudflare bootstrap
          2. Register self with bootstrap directory
          3. Sync chain from peers
          4. Start Flask API server
          5. Start NVF-BFT consensus loop
          6. Start heartbeat
          7. Notify plugins
        """
        self._running = True
        logger.info("=" * 50)
        logger.info("PlayWebit Network Node Starting...")
        logger.info(f"  Wallet:   {self.node_wallet}")
        logger.info(f"  URL:      {self.node_url}")
        logger.info(f"  Platform: {self.platform}")
        logger.info("=" * 50)

        # Step 1: Discover peers
        logger.info("Step 1/6: Discovering peers via bootstrap...")
        peers = self.bootstrap.discover_peers()
        self.peer_manager.load_peers_from_list(peers)
        logger.info(f"  Found {len(peers)} peers")

        # Step 2: Register with Cloudflare bootstrap
        logger.info("Step 2/6: Registering with bootstrap directory...")
        self.bootstrap.register_node()

        # Step 3: Sync chain
        logger.info("Step 3/6: Syncing chain from peers...")
        self.sync.sync()
        tip = self.blockchain.get_chain_tip()
        logger.info(
            f"  Chain synced. Height: {tip.index if tip else 0}"
        )

        # Step 4: Start Flask API
        logger.info(f"Step 4/6: Starting API server on port {self.port}...")
        self._start_flask()

        # Step 5: Start consensus
        logger.info("Step 5/6: Starting NVF-BFT consensus...")
        self.consensus.start()

        # Step 6: Start heartbeat
        logger.info("Step 6/6: Starting bootstrap heartbeat...")
        self.bootstrap.start_heartbeat()

        # Notify plugins
        self.plugin_manager.notify_start(self)

        logger.info("=" * 50)
        logger.info("Node is live and participating in consensus!")
        logger.info("=" * 50)

        if blocking:
            try:
                while self._running:
                    time.sleep(1)
            except KeyboardInterrupt:
                self.stop()

    def stop(self):
        """Graceful shutdown."""
        logger.info("Node shutting down...")
        self._running = False
        self.consensus.stop()
        self.bootstrap.deregister()
        self.plugin_manager.notify_stop()
        logger.info("Node stopped.")

    # ─────────────────────────────────────────────────────────────
    # Flask API server
    # ─────────────────────────────────────────────────────────────

    def _start_flask(self):
        """Start Flask in a background thread."""
        from flask import Flask
        from playweb.api.node_api   import create_node_api
        from playweb.api.public_api import create_public_api
        from playweb.api.rpc      import create_rpc
        from playweb.api.metadata import create_metadata_api

        app = Flask(__name__)
        app.register_blueprint(create_node_api(self))
        app.register_blueprint(create_public_api(self))
        app.register_blueprint(create_rpc(self))
        app.register_blueprint(create_metadata_api(self))

        self._flask_app = app

        self._flask_thread = threading.Thread(
            target=lambda: app.run(
                host    = "0.0.0.0",
                port    = self.port,
                debug   = False,
                use_reloader = False,
            ),
            daemon = True,
            name   = "flask-api",
        )
        self._flask_thread.start()
        logger.info(f"API server started on port {self.port}")

    def get_flask_app(self):
        """
        Get the Flask app for external mounting.
        Use this if you want to add your own routes on top.
        Returns the Flask app instance.
        """
        if not self._flask_app:
            from flask import Flask
            from playweb.api.node_api   import create_node_api
            from playweb.api.public_api import create_public_api

            app = Flask(__name__)
            app.register_blueprint(create_node_api(self))
            app.register_blueprint(create_public_api(self))
            self._flask_app = app

        return self._flask_app

    # ─────────────────────────────────────────────────────────────
    # Consensus callback
    # ─────────────────────────────────────────────────────────────

    def _on_block_finalised(self, block, votes):
        """
        Called by consensus after a block is finalised.
        Broadcasts to peers so they can add it to their chain.
        NVF: Cyclic re-entry notification complete.
        """
        self.gossip.broadcast_finalised_block(
            block = block,
            votes = votes,
            peers = self.peer_manager.get_active_peers(),
        )

    # ─────────────────────────────────────────────────────────────
    # Convenience methods
    # ─────────────────────────────────────────────────────────────

    def submit_transaction(self, tx, broadcast: bool = True):
        """Submit a transaction and optionally broadcast to peers."""
        success, result = self.blockchain.add_transaction(
            tx          = tx,
            node_wallet = self.node_wallet,
        )
        if success and broadcast:
            self.gossip.broadcast_transaction(
                tx    = tx,
                peers = self.peer_manager.get_active_peers(),
            )
        return success, result

    def get_balance(self, address: str) -> float:
        return self.blockchain.get_balance(address)

    def get_block(self, block_hash: str):
        return self.blockchain.get_block(block_hash)

    def get_chain_tip(self):
        return self.blockchain.get_chain_tip()

    def get_status(self) -> dict:
        tip = self.blockchain.get_chain_tip()
        return {
            "node_wallet":  self.node_wallet,
            "node_url":     self.node_url,
            "platform":     self.platform,
            "block_height": tip.index if tip else 0,
            "peer_count":   self.peer_manager.peer_count(),
            "consensus":    self.consensus.get_status(),
            "sync":         self.sync.get_sync_status(),
            "plugins":      self.plugin_manager.get_status(),
        }
