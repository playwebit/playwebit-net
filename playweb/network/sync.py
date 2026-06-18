"""
PlayWebit Network — Chain Sync
Syncs chain from peers when a node starts or restarts.
Downloads missing blocks in chunks, verifies each one.
After sync completes, node joins consensus normally.
"""

import logging
import requests
from typing import List, Optional, Tuple, TYPE_CHECKING

from playweb.config import SYNC_CHUNK_SIZE, PEER_TIMEOUT

if TYPE_CHECKING:
    from playweb.network.peer_manager import Peer

logger = logging.getLogger(__name__)


class ChainSync:

    def __init__(self, blockchain, peer_manager):
        self.blockchain   = blockchain
        self.peer_manager = peer_manager
        self._syncing     = False
        self._progress    = {"current": 0, "target": 0, "synced": False}

    # ─────────────────────────────────────────────────────────────
    # Main sync entry point
    # ─────────────────────────────────────────────────────────────

    def sync(self) -> bool:
        """
        Sync chain from peers.
        1. Find canonical chain tip from peers
        2. Download missing blocks in chunks
        3. Verify and apply each block
        Returns True if fully synced.
        """
        peers = self.peer_manager.get_active_peers()
        if not peers:
            logger.info("Sync: no peers available — running as solo node")
            return True

        self._syncing = True

        # Step 1: Find the canonical chain tip
        target_index, best_peer = self._find_canonical_tip(peers)
        if target_index is None:
            logger.info("Sync: could not determine canonical tip from peers")
            self._syncing = False
            return False

        my_index = self.blockchain.get_chain_length() - 1
        self._progress["target"]  = target_index
        self._progress["current"] = my_index

        if my_index >= target_index:
            logger.info(
                f"Sync: already up to date (block {my_index})"
            )
            self._syncing         = False
            self._progress["synced"] = True
            return True

        logger.info(
            f"Sync: need blocks {my_index + 1} → {target_index} "
            f"({target_index - my_index} blocks)"
        )

        # Step 2: Download blocks in chunks
        success = self._download_blocks(
            from_index  = my_index + 1,
            to_index    = target_index,
            peers       = peers,
        )

        self._syncing            = False
        self._progress["synced"] = success
        return success

    # ─────────────────────────────────────────────────────────────
    # Find canonical chain tip
    # ─────────────────────────────────────────────────────────────

    def _find_canonical_tip(
        self,
        peers: List["Peer"],
    ) -> Tuple[Optional[int], Optional["Peer"]]:
        """
        Ask each peer for their chain tip.
        The canonical chain is the one with the highest valid index.
        Returns (target_block_index, best_peer).
        """
        tips = []

        for peer in peers:
            try:
                res = requests.get(
                    f"{peer.url}/peer/chain_tip",
                    timeout=PEER_TIMEOUT,
                )
                if res.status_code == 200:
                    data  = res.json()
                    index = data.get("block_index", -1)
                    hash_ = data.get("block_hash", "")
                    if index >= 0:
                        tips.append((index, hash_, peer))
            except Exception as e:
                logger.debug(f"Sync: could not get tip from {peer.url}: {e}")

        if not tips:
            return None, None

        # Pick highest index — canonical chain
        tips.sort(key=lambda t: t[0], reverse=True)
        best_index, best_hash, best_peer = tips[0]

        logger.info(
            f"Sync: canonical tip is block {best_index} "
            f"({best_hash[:12]}...) from {best_peer.url}"
        )
        return best_index, best_peer

    # ─────────────────────────────────────────────────────────────
    # Download blocks
    # ─────────────────────────────────────────────────────────────

    def _download_blocks(
        self,
        from_index: int,
        to_index:   int,
        peers:      List["Peer"],
    ) -> bool:
        """
        Download blocks in chunks from peers.
        Tries each peer in sequence — falls back if one fails.
        Verifies each block before adding to chain.
        """
        current = from_index

        while current <= to_index:
            chunk_end = min(current + SYNC_CHUNK_SIZE - 1, to_index)
            success   = False

            # Try each peer until one works
            for peer in peers:
                blocks = self._fetch_chunk(peer, current, chunk_end)
                if blocks:
                    applied = self._apply_chunk(blocks)
                    if applied:
                        current += len(blocks)
                        self._progress["current"] = current
                        logger.info(
                            f"Sync: applied blocks "
                            f"{current - len(blocks)} → {current - 1}"
                        )
                        success = True
                        break

            if not success:
                logger.error(
                    f"Sync: failed to download blocks "
                    f"{current} → {chunk_end} from any peer"
                )
                return False

        logger.info(f"Sync: complete. Chain at block {to_index}")
        return True

    def _fetch_chunk(
        self,
        peer:       "Peer",
        from_index: int,
        to_index:   int,
    ) -> List:
        """Fetch a chunk of blocks from a peer."""
        try:
            res = requests.get(
                f"{peer.url}/peer/blocks/{from_index}/{to_index}",
                timeout=PEER_TIMEOUT * 3,  # longer timeout for bulk fetch
            )
            if res.status_code != 200:
                return []

            data   = res.json()
            blocks_data = data.get("blocks", [])
            blocks = []

            from playweb.core.block import Block
            for bd in blocks_data:
                try:
                    block = Block.from_dict(bd)
                    blocks.append(block)
                except Exception as e:
                    logger.warning(f"Sync: failed to parse block: {e}")
                    return []

            return blocks

        except Exception as e:
            logger.debug(f"Sync: fetch failed from {peer.url}: {e}")
            return []

    def _apply_chunk(self, blocks: List) -> bool:
        """Verify and apply a chunk of blocks to local chain."""
        for block in blocks:
            # Verify block integrity
            tip = self.blockchain.get_chain_tip()
            valid, reason = block.validate(previous_block=tip)

            if not valid:
                logger.warning(f"Sync: invalid block {block.index}: {reason}")
                return False

            # Add to chain (skip fee validation during sync —
            # we trust the chain has been validated by consensus already)
            success, reason = self.blockchain.add_block(block)
            if not success:
                logger.warning(
                    f"Sync: failed to add block {block.index}: {reason}"
                )
                return False

        return True

    # ─────────────────────────────────────────────────────────────
    # Status
    # ─────────────────────────────────────────────────────────────

    def get_sync_status(self) -> dict:
        return {
            "syncing":  self._syncing,
            "current":  self._progress["current"],
            "target":   self._progress["target"],
            "synced":   self._progress["synced"],
            "percent":  (
                round(
                    self._progress["current"] /
                    max(self._progress["target"], 1) * 100, 1
                )
                if self._progress["target"] > 0 else 100
            ),
        }
