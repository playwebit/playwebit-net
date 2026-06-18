"""
PlayWebit Network — Block
"""

import hashlib
import json
import time
import logging
from typing import List, Dict, Optional

from playweb.core.transaction import Transaction

logger = logging.getLogger(__name__)


class Block:

    def __init__(
        self,
        index:            int,
        transactions:     List[Transaction],
        previous_hash:    str,
        validator_wallet: str,
        timestamp:        float = None,
        nonce:            int   = 0,
        consensus_round:  int   = 0,
        votes:            List  = None,
    ):
        self.index            = index
        self.transactions     = transactions
        self.previous_hash    = previous_hash
        self.validator_wallet = validator_wallet.lower()
        self.timestamp        = timestamp or time.time()
        self.nonce            = nonce
        self.consensus_round  = consensus_round
        self.votes            = votes or []

        self.merkle_root = self.calculate_merkle_root()
        self.hash        = self.calculate_hash()

    # ─────────────────────────────────────────────────────────────
    # Merkle Tree
    # ─────────────────────────────────────────────────────────────

    def calculate_merkle_root(self) -> str:
        """Build merkle root from transaction hashes."""
        if not self.transactions:
            return hashlib.sha256(b"empty").hexdigest()

        hashes = [tx.hash for tx in self.transactions]

        while len(hashes) > 1:
            # Pad odd number of hashes
            if len(hashes) % 2 != 0:
                hashes.append(hashes[-1])

            hashes = [
                hashlib.sha256(
                    (hashes[i] + hashes[i + 1]).encode()
                ).hexdigest()
                for i in range(0, len(hashes), 2)
            ]

        return hashes[0]

    # ─────────────────────────────────────────────────────────────
    # Hashing
    # ─────────────────────────────────────────────────────────────

    def calculate_hash(self) -> str:
        block_data = {
            "index":            self.index,
            "previous_hash":    self.previous_hash,
            "merkle_root":      self.merkle_root,
            "timestamp":        self.timestamp,
            "nonce":            self.nonce,
            "validator_wallet": self.validator_wallet,
            "consensus_round":  self.consensus_round,
        }
        raw = json.dumps(block_data, sort_keys=True)
        return hashlib.sha256(raw.encode()).hexdigest()

    # ─────────────────────────────────────────────────────────────
    # Validation
    # ─────────────────────────────────────────────────────────────

    def validate(self, previous_block: Optional["Block"] = None) -> tuple[bool, str]:
        """
        Validate block integrity.
        Returns (is_valid, reason).
        """
        # Hash integrity
        if self.hash != self.calculate_hash():
            return False, "Block hash mismatch"

        # Merkle root integrity
        if self.merkle_root != self.calculate_merkle_root():
            return False, "Merkle root mismatch"

        # Chain linkage
        if previous_block:
            if self.previous_hash != previous_block.hash:
                return False, "Previous hash does not match"
            if self.index != previous_block.index + 1:
                return False, f"Block index gap: {previous_block.index} → {self.index}"

        # Validate each transaction
        for tx in self.transactions:
            valid, reason = tx.validate_fields()
            if not valid:
                return False, f"Invalid tx {tx.hash[:12]}: {reason}"

        return True, "Valid"

    # ─────────────────────────────────────────────────────────────
    # Serialisation
    # ─────────────────────────────────────────────────────────────

    def to_dict(self) -> Dict:
        return {
            "index":            self.index,
            "hash":             self.hash,
            "previous_hash":    self.previous_hash,
            "merkle_root":      self.merkle_root,
            "timestamp":        self.timestamp,
            "nonce":            self.nonce,
            "validator_wallet": self.validator_wallet,
            "consensus_round":  self.consensus_round,
            "votes":            self.votes,
            "transactions":     [tx.to_dict() for tx in self.transactions],
        }

    @classmethod
    def from_dict(cls, d: Dict) -> "Block":
        txs = [Transaction.from_dict(t) for t in d.get("transactions", [])]
        block = cls(
            index            = d["index"],
            transactions     = txs,
            previous_hash    = d["previous_hash"],
            validator_wallet = d["validator_wallet"],
            timestamp        = d["timestamp"],
            nonce            = d.get("nonce", 0),
            consensus_round  = d.get("consensus_round", 0),
            votes            = d.get("votes", []),
        )
        # Restore stored hash
        block.hash        = d["hash"]
        block.merkle_root = d["merkle_root"]
        return block

    def __repr__(self):
        return (
            f"Block(index={self.index}, "
            f"txs={len(self.transactions)}, "
            f"hash={self.hash[:12]}...)"
        )
