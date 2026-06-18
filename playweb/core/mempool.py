"""
PlayWebit Network — Mempool
Pending transactions — lives in RAM only.
Lost on restart — peers will resend. That's fine.
"""

import time
import logging
from typing import Dict, List, Optional

from playweb.core.transaction import Transaction
from playweb.config import MAX_TX_PER_BLOCK

logger = logging.getLogger(__name__)

# Max age of a pending transaction before it's dropped (10 minutes)
TX_MAX_AGE = 600


class Mempool:

    def __init__(self):
        # tx_hash → Transaction
        self._pool: Dict[str, Transaction] = {}

    # ─────────────────────────────────────────────────────────────
    # Add
    # ─────────────────────────────────────────────────────────────

    def add(self, tx: Transaction) -> tuple[bool, str]:
        """
        Add a transaction to the mempool.
        Returns (success, reason).
        """
        if tx.hash in self._pool:
            return False, "Transaction already in mempool"

        valid, reason = tx.validate_fields()
        if not valid:
            return False, reason

        self._pool[tx.hash] = tx
        logger.debug(f"Mempool: added {tx.hash[:12]} ({tx.tx_type})")
        return True, "Added"

    # ─────────────────────────────────────────────────────────────
    # Get
    # ─────────────────────────────────────────────────────────────

    def get_pending(self, limit: int = MAX_TX_PER_BLOCK) -> List[Transaction]:
        """
        Return pending transactions sorted by timestamp (oldest first).
        Automatically drops expired transactions.
        """
        self._drop_expired()
        txs = sorted(self._pool.values(), key=lambda tx: tx.timestamp)
        return txs[:limit]

    def get(self, tx_hash: str) -> Optional[Transaction]:
        return self._pool.get(tx_hash)

    def contains(self, tx_hash: str) -> bool:
        return tx_hash in self._pool

    def size(self) -> int:
        return len(self._pool)

    # ─────────────────────────────────────────────────────────────
    # Remove
    # ─────────────────────────────────────────────────────────────

    def remove(self, tx_hash: str):
        """Remove a transaction after it's been included in a block."""
        if tx_hash in self._pool:
            del self._pool[tx_hash]
            logger.debug(f"Mempool: removed {tx_hash[:12]}")

    def remove_batch(self, tx_hashes: List[str]):
        """Remove multiple transactions at once after block is finalised."""
        for h in tx_hashes:
            self.remove(h)

    def clear(self):
        self._pool.clear()
        logger.debug("Mempool: cleared")

    # ─────────────────────────────────────────────────────────────
    # Maintenance
    # ─────────────────────────────────────────────────────────────

    def _drop_expired(self):
        """Drop transactions older than TX_MAX_AGE seconds."""
        now     = time.time()
        expired = [
            h for h, tx in self._pool.items()
            if now - tx.timestamp > TX_MAX_AGE
        ]
        for h in expired:
            del self._pool[h]
            logger.debug(f"Mempool: expired {h[:12]}")

    def get_stats(self) -> Dict:
        return {
            "pending_count": self.size(),
            "oldest_tx":     min(
                (tx.timestamp for tx in self._pool.values()),
                default=None
            ),
        }

    def __repr__(self):
        return f"Mempool(pending={self.size()})"
