"""
PlayWebit Network — RAM Storage
Everything in Python dicts. Lost on restart.
Use for: testing, development, light nodes.
"""

import logging
from typing import List, Optional, Dict

from playweb.storage.base import ChainStorage

logger = logging.getLogger(__name__)


class RAMStorage(ChainStorage):

    def __init__(self):
        self._blocks_by_hash:   Dict[str, object] = {}
        self._blocks_by_index:  Dict[int, object] = {}
        self._transactions:     Dict[str, object] = {}
        self._balances:         Dict[str, float]  = {}
        self._content_registry: Dict[str, Dict]   = {}
        self._edition_registry: Dict[str, Dict]   = {}
        self._chain_length:     int               = 0
        logger.info("RAMStorage initialised (data lost on restart)")

    # ─── Blocks ──────────────────────────────────────────────────

    def save_block(self, block) -> bool:
        self._blocks_by_hash[block.hash]   = block
        self._blocks_by_index[block.index] = block
        self._chain_length = max(self._chain_length, block.index + 1)
        return True

    def get_block(self, block_hash: str):
        return self._blocks_by_hash.get(block_hash)

    def get_block_by_index(self, index: int):
        return self._blocks_by_index.get(index)

    def get_chain_tip(self):
        if self._chain_length == 0:
            return None
        return self._blocks_by_index.get(self._chain_length - 1)

    def get_chain_length(self) -> int:
        return self._chain_length

    def get_blocks_from(self, from_index: int, limit: int = 50) -> List:
        blocks = []
        for i in range(from_index, min(from_index + limit, self._chain_length)):
            block = self._blocks_by_index.get(i)
            if block:
                blocks.append(block)
        return blocks

    # ─── Transactions ─────────────────────────────────────────────

    def save_transaction(self, tx) -> bool:
        self._transactions[tx.hash] = tx
        return True

    def get_transaction(self, tx_hash: str):
        return self._transactions.get(tx_hash)

    # ─── Balances ────────────────────────────────────────────────

    def get_balance(self, address: str) -> float:
        return self._balances.get(address.lower(), 0.0)

    def save_balance(self, address: str, balance: float) -> bool:
        self._balances[address.lower()] = max(0.0, balance)
        return True

    def get_all_addresses(self) -> List[str]:
        return list(self._balances.keys())

    # ─── Content Registry ─────────────────────────────────────────

    def save_content_record(self, record: Dict) -> bool:
        # Normalise wallet addresses to lowercase
        normalised = dict(record)
        for key in ("creator_wallet", "first_owner", "current_owner"):
            if normalised.get(key):
                normalised[key] = normalised[key].lower()
        self._content_registry[normalised["cid"]] = normalised
        return True

    def get_content_record(self, cid: str) -> Optional[Dict]:
        return self._content_registry.get(cid)

    def get_all_content_by_owner(self, address: str) -> List[Dict]:
        addr = address.lower()
        return [
            r for r in self._content_registry.values()
            if r.get("current_owner", "").lower() == addr
        ]
    
    def get_cid_by_int_id(self, int_id: int) -> Optional[str]:
        from playweb.api.erc721 import cid_to_int_id
        for cid in self._content_registry:
            if cid_to_int_id(cid) == int_id:
                return cid
        return None

    # ─── Edition Registry ─────────────────────────────────────────

    def save_edition_record(self, record: Dict) -> bool:
        normalised = dict(record)
        if normalised.get("current_owner"):
            normalised["current_owner"] = normalised["current_owner"].lower()
        key = f"{normalised['cid']}:{normalised['edition_number']}"
        self._edition_registry[key] = normalised
        return True

    def get_edition_record(self, cid: str, edition_number: int) -> Optional[Dict]:
        return self._edition_registry.get(f"{cid}:{edition_number}")

    def get_all_edition_records(self, cid: str) -> List[Dict]:
        return [
            v for k, v in self._edition_registry.items()
            if k.startswith(f"{cid}:")
        ]
