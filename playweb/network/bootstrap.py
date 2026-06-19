"""
PlayWebit Network — Bootstrap
First peer discovery via Cloudflare Worker.
After first connection, pure P2P gossip takes over.
Cloudflare is never needed again until node restarts.
"""

import time
import json
import hashlib
import logging
import threading
import requests
from typing import List, Dict, Optional

from playweb.config import (
    BOOTSTRAP_URL,
    BOOTSTRAP_ENDPOINTS,
    BOOTSTRAP_FALLBACK_NODES,
    BOOTSTRAP_HEARTBEAT_INTERVAL,
    PEER_TIMEOUT,
)

logger = logging.getLogger(__name__)


class Bootstrap:

    def __init__(
        self,
        node_url:         str,
        node_wallet:      str,
        node_private_key: str,
        platform:         str = "unknown",
        role:             str = "validator",
    ):
        self.node_url         = node_url
        self.node_wallet      = node_wallet.lower()
        self.node_private_key = node_private_key
        self.platform         = platform
        self.role             = role
        self._heartbeat_thread: Optional[threading.Thread] = None
        self._running          = False

    # ─────────────────────────────────────────────────────────────
    # Signature for Cloudflare verification
    # ─────────────────────────────────────────────────────────────

    def _sign(self, timestamp: int) -> str:
        """
        Sign the bootstrap message with node's wallet.
        message = "playwebit-bootstrap:{url}:{timestamp}"
        """
        try:
            from eth_account import Account
            from eth_account.messages import encode_defunct

            message = f"playwebit-bootstrap:{self.node_url}:{timestamp}"
            msg     = encode_defunct(text=message)
            signed  = Account.sign_message(msg, private_key=self.node_private_key)
            sig = signed.signature.hex()
            # ensure 0x prefix — Worker requires it
            return sig if sig.startswith("0x") else "0x" + sig
        except ImportError:
            # Fallback placeholder signature (format-valid)
            raw = f"{self.node_url}:{timestamp}:{self.node_wallet}"
            return "0x" + hashlib.sha256(raw.encode()).hexdigest() + "0" * 66
        except Exception as e:
            logger.error(f"Bootstrap signing failed: {e}")
            return "0x" + "0" * 130

    # ─────────────────────────────────────────────────────────────
    # Discover peers
    # ─────────────────────────────────────────────────────────────

    def discover_peers(self) -> List[Dict]:
        """
        Get list of active nodes from Cloudflare Worker.
        Falls back to hardcoded nodes if Cloudflare unreachable.
        Returns list of { url, wallet, platform } dicts.
        """
        url = BOOTSTRAP_URL + BOOTSTRAP_ENDPOINTS["nodes"]
        try:
            res = requests.get(url, timeout=PEER_TIMEOUT)
            if res.status_code == 200:
                data  = res.json()
                nodes = data.get("nodes", [])
                # Filter out self
                nodes = [
                    n for n in nodes
                    if n.get("url") != self.node_url
                    and n.get("wallet", "").lower() != self.node_wallet
                ]
                logger.info(
                    f"Bootstrap: discovered {len(nodes)} peers "
                    f"from Cloudflare"
                )
                return nodes
            else:
                logger.warning(
                    f"Bootstrap Cloudflare returned {res.status_code}"
                )
        except Exception as e:
            logger.warning(f"Bootstrap Cloudflare unreachable: {e}")

        # Fallback to hardcoded nodes
        logger.info("Bootstrap: using fallback nodes")
        return [
            {"url": url, "wallet": "unknown", "platform": "playwebit"}
            for url in BOOTSTRAP_FALLBACK_NODES
            if url != self.node_url
        ]

    # ─────────────────────────────────────────────────────────────
    # Register node
    # ─────────────────────────────────────────────────────────────

    def register_node(self) -> bool:
        """
        Register this node with the Cloudflare bootstrap directory.
        Cloudflare will notify all existing nodes about us.
        """
        timestamp = int(time.time())
        signature = self._sign(timestamp)
        url       = BOOTSTRAP_URL + BOOTSTRAP_ENDPOINTS["register"]

        try:
            res = requests.post(url, json={
                "url":       self.node_url,
                "wallet":    self.node_wallet,
                "signature": signature,
                "timestamp": timestamp,
                "platform":  self.platform,
                "role":      self.role,
            }, timeout=PEER_TIMEOUT)

            if res.status_code == 200:
                data = res.json()
                logger.info(
                    f"Bootstrap: node registered. "
                    f"Network has {data.get('node_count', '?')} nodes"
                )
                # Cloudflare returns peer list in registration response
                # — use it to seed peer manager immediately
                return True
            else:
                logger.warning(
                    f"Bootstrap registration failed: "
                    f"{res.status_code} {res.text}"
                )
                return False

        except Exception as e:
            logger.warning(f"Bootstrap registration error: {e}")
            return False

    # ─────────────────────────────────────────────────────────────
    # Heartbeat — keeps node listed in Cloudflare KV
    # ─────────────────────────────────────────────────────────────

    def start_heartbeat(self):
        """Start background heartbeat thread (every 12 hours)."""
        self._running = True
        self._heartbeat_thread = threading.Thread(
            target = self._heartbeat_loop,
            daemon = True,
            name   = "bootstrap-heartbeat",
        )
        self._heartbeat_thread.start()
        logger.info("Bootstrap heartbeat started (every 12h)")

    def stop_heartbeat(self):
        self._running = False

    def _heartbeat_loop(self):
        while self._running:
            time.sleep(BOOTSTRAP_HEARTBEAT_INTERVAL)
            self._send_heartbeat()

    def _send_heartbeat(self):
        timestamp = int(time.time())
        signature = self._sign(timestamp)
        url       = BOOTSTRAP_URL + BOOTSTRAP_ENDPOINTS["heartbeat"]
        try:
            res = requests.post(url, json={
                "url":       self.node_url,
                "wallet":    self.node_wallet,
                "signature": signature,
                "timestamp": timestamp,
            }, timeout=PEER_TIMEOUT)
            if res.status_code == 200:
                logger.debug("Bootstrap heartbeat sent")
            else:
                logger.warning(f"Bootstrap heartbeat failed: {res.status_code}")
        except Exception as e:
            logger.warning(f"Bootstrap heartbeat error: {e}")

    # ─────────────────────────────────────────────────────────────
    # Deregister
    # ─────────────────────────────────────────────────────────────

    def deregister(self):
        """Clean removal when node shuts down gracefully."""
        self.stop_heartbeat()
        timestamp = int(time.time())
        signature = self._sign(timestamp)
        url       = BOOTSTRAP_URL + BOOTSTRAP_ENDPOINTS["deregister"]
        try:
            requests.post(url, json={
                "url":       self.node_url,
                "wallet":    self.node_wallet,
                "signature": signature,
                "timestamp": timestamp,
            }, timeout=PEER_TIMEOUT)
            logger.info("Bootstrap: node deregistered")
        except Exception as e:
            logger.warning(f"Bootstrap deregistration error: {e}")
