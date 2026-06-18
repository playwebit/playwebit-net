"""
PlayWebit Network — Peer Manager
Manages known peers in RAM. Lost on restart — rediscovered via bootstrap.
"""

import time
import threading
import logging
import requests
from typing import List, Optional, Dict
from dataclasses import dataclass, field

from playweb.config import MAX_PEERS, PEER_TIMEOUT

logger = logging.getLogger(__name__)


@dataclass
class Peer:
    url:       str
    wallet:    str
    platform:  str    = "unknown"
    role:      str    = "validator"
    last_seen: float  = field(default_factory=time.time)
    is_active: bool   = True
    latency_ms: float = 0.0

    def __hash__(self):
        return hash(self.url)

    def __eq__(self, other):
        return self.url == other.url


class PeerManager:

    def __init__(self, my_url: str, my_wallet: str):
        self.my_url    = my_url
        self.my_wallet = my_wallet.lower()
        self._peers:   Dict[str, Peer] = {}   # url → Peer
        self._lock     = threading.Lock()

    # ─────────────────────────────────────────────────────────────
    # Add / Remove
    # ─────────────────────────────────────────────────────────────

    def add_peer(
        self,
        url:      str,
        wallet:   str,
        platform: str = "unknown",
        role:     str = "validator",
    ) -> bool:
        """Add a new peer. Returns True if actually added (not duplicate)."""
        # Don't add self
        if url == self.my_url or wallet.lower() == self.my_wallet:
            return False

        with self._lock:
            if url in self._peers:
                # Update last_seen
                self._peers[url].last_seen = time.time()
                self._peers[url].is_active = True
                return False

            if len(self._peers) >= MAX_PEERS:
                # Remove oldest inactive peer first
                self._evict_one()

            self._peers[url] = Peer(
                url      = url,
                wallet   = wallet.lower(),
                platform = platform,
                role     = role,
            )
            logger.info(f"Peer added: {url} ({wallet[:8]}...)")
            return True

    def remove_peer(self, url: str):
        with self._lock:
            if url in self._peers:
                del self._peers[url]
                logger.info(f"Peer removed: {url}")

    def _evict_one(self):
        """Remove the least recently seen inactive peer."""
        inactive = [
            p for p in self._peers.values()
            if not p.is_active
        ]
        if inactive:
            oldest = min(inactive, key=lambda p: p.last_seen)
            del self._peers[oldest.url]

    # ─────────────────────────────────────────────────────────────
    # Query
    # ─────────────────────────────────────────────────────────────

    def get_active_peers(self) -> List[Peer]:
        with self._lock:
            return [p for p in self._peers.values() if p.is_active]

    def get_all_peers(self) -> List[Peer]:
        with self._lock:
            return list(self._peers.values())

    def get_peer(self, url: str) -> Optional[Peer]:
        return self._peers.get(url)

    def peer_count(self) -> int:
        return len([p for p in self._peers.values() if p.is_active])

    def get_peer_list_for_sharing(self) -> List[Dict]:
        """Return peer list to share with new nodes."""
        return [
            {"url": p.url, "wallet": p.wallet, "platform": p.platform}
            for p in self.get_active_peers()
        ]

    # ─────────────────────────────────────────────────────────────
    # Health check
    # ─────────────────────────────────────────────────────────────

    def ping_all(self):
        """Ping all peers and mark inactive ones."""
        peers = self.get_all_peers()
        for peer in peers:
            self._ping_peer(peer)

    def _ping_peer(self, peer: Peer):
        try:
            start = time.time()
            res   = requests.get(
                f"{peer.url}/peer/health",
                timeout=PEER_TIMEOUT
            )
            latency = (time.time() - start) * 1000

            if res.status_code == 200:
                with self._lock:
                    if peer.url in self._peers:
                        self._peers[peer.url].is_active  = True
                        self._peers[peer.url].last_seen  = time.time()
                        self._peers[peer.url].latency_ms = latency
            else:
                self._mark_inactive(peer.url)

        except Exception:
            self._mark_inactive(peer.url)

    def _mark_inactive(self, url: str):
        with self._lock:
            if url in self._peers:
                self._peers[url].is_active = False
                logger.debug(f"Peer marked inactive: {url}")

    def load_peers_from_list(self, peers: List[Dict]):
        """Load peers from a list (from bootstrap or another peer)."""
        for p in peers:
            self.add_peer(
                url      = p.get("url", ""),
                wallet   = p.get("wallet", ""),
                platform = p.get("platform", "unknown"),
            )
