"""
PlayWebit Network — ChainStorage Interface
Any storage backend implements this.
Blockchain core only calls these methods — never touches DB directly.
"""

from abc import ABC, abstractmethod
from typing import List, Optional, Dict


class ChainStorage(ABC):

    # ─────────────────────────────────────────────────────────────
    # Blocks
    # ─────────────────────────────────────────────────────────────

    @abstractmethod
    def save_block(self, block) -> bool:
        """Save a block to storage. Returns True on success."""
        ...

    @abstractmethod
    def get_block(self, block_hash: str):
        """Get a block by hash. Returns Block or None."""
        ...

    @abstractmethod
    def get_block_by_index(self, index: int):
        """Get a block by index. Returns Block or None."""
        ...

    @abstractmethod
    def get_chain_tip(self):
        """Get the latest block. Returns Block or None."""
        ...

    @abstractmethod
    def get_chain_length(self) -> int:
        """Get total number of blocks in the chain."""
        ...

    @abstractmethod
    def get_blocks_from(self, from_index: int, limit: int = 50) -> List:
        """
        Get blocks from from_index up to limit.
        Used for chain sync between nodes.
        Returns List[Block].
        """
        ...

    # ─────────────────────────────────────────────────────────────
    # Transactions
    # ─────────────────────────────────────────────────────────────

    @abstractmethod
    def save_transaction(self, tx) -> bool:
        """Save a confirmed transaction. Returns True on success."""
        ...

    @abstractmethod
    def get_transaction(self, tx_hash: str):
        """Get a transaction by hash. Returns Transaction or None."""
        ...

    # ─────────────────────────────────────────────────────────────
    # Balances
    # ─────────────────────────────────────────────────────────────

    @abstractmethod
    def get_balance(self, address: str) -> float:
        """Get PLWB balance for an address. Returns 0.0 if not found."""
        ...

    @abstractmethod
    def save_balance(self, address: str, balance: float) -> bool:
        """Update balance for an address. Returns True on success."""
        ...

    @abstractmethod
    def get_all_addresses(self) -> List[str]:
        """Get all addresses that have ever had a balance."""
        ...

    # ─────────────────────────────────────────────────────────────
    # Content Registry
    # Cross-platform CID ownership — the core value of the network
    # ─────────────────────────────────────────────────────────────

    @staticmethod
    def normalise_record(record: Dict) -> Dict:
        """Normalise wallet addresses to lowercase before saving."""
        normalised = dict(record)
        for key in ("creator_wallet", "first_owner", "current_owner"):
            if normalised.get(key):
                normalised[key] = normalised[key].lower()
        return normalised

    @abstractmethod
    def save_content_record(self, record: Dict) -> bool:
        record = self.normalise_record(record)
        """
        Save a content registration record.
        record keys:
            cid, creator_wallet, first_owner, first_platform,
            first_tx_hash, first_block, timestamp,
            total_editions, royalty_pct, current_owner
        """
        ...

    @abstractmethod
    def get_content_record(self, cid: str) -> Optional[Dict]:
        """Get content record by CID. Returns dict or None."""
        ...

    # ─────────────────────────────────────────────────────────────
    # Edition Registry
    # ─────────────────────────────────────────────────────────────

    @abstractmethod
    def save_edition_record(self, record: Dict) -> bool:
        """
        Save an edition record.
        record keys:
            cid, edition_number, edition_of, current_owner,
            platform, tx_hash, timestamp, provenance (list)
        """
        ...

    @abstractmethod
    def get_edition_record(self, cid: str, edition_number: int) -> Optional[Dict]:
        """Get a specific edition record."""
        ...

    @abstractmethod
    def get_all_edition_records(self, cid: str) -> List[Dict]:
        """Get all edition records for a CID."""
        ...

    @abstractmethod
    def get_all_content_by_owner(self, address: str) -> List[Dict]:
        """
        Get all content records where current_owner = address.
        Used by ERC721 balanceOf() to count NFTs.
        """
        ...
    
    @abstractmethod
    def get_cid_by_int_id(self, int_id: int) -> Optional[str]:
        """
        Get CID string from integer token ID.
        Integer IDs are used by MetaMask (uint256).
        Computed as: sha256(cid)[:16] as int.
        """
        ...
