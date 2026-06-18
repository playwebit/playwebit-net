"""
PlayWebit Network — Blockchain
Storage-agnostic. No Supabase imports. No CipherVault logic.
Works with any ChainStorage implementation.
"""

import time
import logging
from typing import List, Optional, Tuple, Dict

from playweb.core.block       import Block
from playweb.core.transaction import Transaction
from playweb.core.mempool     import Mempool
from playweb.core.fee_engine  import FeeEngine
from playweb.config           import (
    CHAIN_ID,
    AUTHORITY_WALLET,
    AUTHORITY_TX_TYPES,
    L1_TX_TYPES,
    MAX_TX_PER_BLOCK,
    TRANSACTION_FEE,
    CV_LINK_FEE,
)

logger = logging.getLogger(__name__)


class Blockchain:

    def __init__(self, storage):
        """
        storage — any ChainStorage implementation.
        LevelDBStorage, SQLiteStorage, SupabaseStorage, RAMStorage.
        """
        self.storage    = storage
        self.mempool    = Mempool()
        self.fee_engine = FeeEngine()
        self._ensure_genesis()

    # ─────────────────────────────────────────────────────────────
    # Genesis
    # ─────────────────────────────────────────────────────────────

    def _ensure_genesis(self):
        """Create genesis block if chain is empty."""
        if self.storage.get_chain_length() == 0:
            logger.info("Chain is empty — creating genesis block")
            genesis_tx = Transaction(
                from_addr = AUTHORITY_WALLET,
                to_addr   = AUTHORITY_WALLET,
                amount    = 0,
                tx_type   = "genesis",
                nonce     = 0,
                timestamp = 0,
                data      = {
                    "chain_id":   CHAIN_ID,
                    "message":    "PlayWebit Network Genesis",
                    "created_at": time.time(),
                }
            )
            genesis_block = Block(
                index            = 0,
                transactions     = [genesis_tx],
                previous_hash    = "0" * 64,
                validator_wallet = AUTHORITY_WALLET,
                timestamp        = 0,
            )
            self.storage.save_block(genesis_block)
            logger.info(f"Genesis block created: {genesis_block.hash[:16]}...")

    # ─────────────────────────────────────────────────────────────
    # Transactions
    # ─────────────────────────────────────────────────────────────

    def add_transaction(
        self,
        tx:          Transaction,
        node_wallet: str = None,
    ) -> Tuple[bool, str]:
        """
        Validate and add a transaction to the mempool.
        Also creates and queues the required fee transactions.
        Returns (success, reason).
        """
        # Field validation
        valid, reason = tx.validate_fields()
        if not valid:
            return False, reason

        # Signature verification (skipped for authority txs)
        if tx.tx_type not in AUTHORITY_TX_TYPES:
            if not tx.verify_signature():
                return False, "Invalid signature"

        # Balance check (skip for authority txs)
        if tx.tx_type not in AUTHORITY_TX_TYPES:
            fee_info     = self.fee_engine.calculate_fee(tx.tx_type, tx.amount)
            total_needed = tx.amount + fee_info["total"]
            balance      = self.get_balance(tx.from_addr)

            if balance < total_needed:
                return (
                    False,
                    f"Insufficient balance: need {total_needed} PLWB, "
                    f"have {balance} PLWB"
                )

        # Duplicate check
        if self.mempool.contains(tx.hash):
            return False, "Transaction already in mempool"

        if self.storage.get_transaction(tx.hash):
            return False, "Transaction already on chain"

        # Add to mempool
        success, reason = self.mempool.add(tx)
        if not success:
            return False, reason

        # Create and queue fee transactions
        if node_wallet and tx.tx_type not in AUTHORITY_TX_TYPES:
            fee_txs = self.fee_engine.create_fee_transactions(tx, node_wallet)
            for fee_tx in fee_txs:
                self.mempool.add(fee_tx)

        logger.info(f"Transaction added to mempool: {tx.hash[:16]} ({tx.tx_type})")
        return True, tx.hash

    def get_transaction(self, tx_hash: str) -> Optional[Transaction]:
        """Get a transaction by hash — checks mempool first, then chain."""
        # Check mempool first
        tx = self.mempool.get(tx_hash)
        if tx:
            return tx
        # Then check storage
        return self.storage.get_transaction(tx_hash)

    def validate_transaction(
        self,
        tx:          Transaction,
        node_wallet: str = None,
    ) -> Tuple[bool, str]:
        """
        Full transaction validation.
        Used during consensus when receiving blocks from peers.
        """
        valid, reason = tx.validate_fields()
        if not valid:
            return False, reason

        if tx.tx_type not in AUTHORITY_TX_TYPES:
            if not tx.verify_signature():
                return False, "Invalid signature"

        return True, "Valid"

    # ─────────────────────────────────────────────────────────────
    # Blocks
    # ─────────────────────────────────────────────────────────────

    def create_block(self, validator_wallet: str) -> Optional[Block]:
        """
        Create a new block from pending mempool transactions.
        Called by the consensus leader before proposing.
        """
        pending = self.mempool.get_pending(MAX_TX_PER_BLOCK)
        if not pending:
            logger.debug("No pending transactions — skipping block creation")
            return None

        tip = self.storage.get_chain_tip()
        if not tip:
            logger.error("No chain tip found — chain may be corrupt")
            return None

        block = Block(
            index            = tip.index + 1,
            transactions     = pending,
            previous_hash    = tip.hash,
            validator_wallet = validator_wallet,
        )

        logger.info(
            f"Block created: index={block.index}, "
            f"txs={len(pending)}, "
            f"hash={block.hash[:16]}..."
        )
        return block

    def add_block(
        self,
        block:       Block,
        votes:       List = None,
        node_wallet: str  = None,
    ) -> Tuple[bool, str]:
        """
        Add a finalised block to the chain.
        Called after consensus (2/3 votes received).
        Validates block then writes to storage.
        """
        # Get previous block for chain validation
        tip = self.storage.get_chain_tip()

        # Validate block integrity
        valid, reason = block.validate(previous_block=tip)
        if not valid:
            return False, f"Block validation failed: {reason}"

        # Validate fee transactions (50/50 split enforced)
        if node_wallet:
            fee_valid, fee_reason = self.fee_engine.validate_fee_transactions(
                block, node_wallet
            )
            if not fee_valid:
                return False, f"Fee validation failed: {fee_reason}"

        # Attach votes
        if votes:
            block.votes = votes

        # Save to storage
        self.storage.save_block(block)

        # Update balances
        self._apply_block_to_balances(block)

        # Update content registry for content_register transactions
        self._apply_content_registry(block)

        # Remove confirmed transactions from mempool
        self.mempool.remove_batch([tx.hash for tx in block.transactions])

        logger.info(
            f"Block finalised: index={block.index}, "
            f"txs={len(block.transactions)}, "
            f"hash={block.hash[:16]}..."
        )
        return True, block.hash

    def _apply_block_to_balances(self, block: Block):
        """Update balance records for all transactions in a block."""
        for tx in block.transactions:
            if tx.amount <= 0:
                continue

            # Deduct from sender (not for authority/genesis txs)
            if tx.tx_type not in AUTHORITY_TX_TYPES:
                from_bal = self.storage.get_balance(tx.from_addr)
                self.storage.save_balance(tx.from_addr, from_bal - tx.amount)

            # Credit receiver
            to_bal = self.storage.get_balance(tx.to_addr)
            self.storage.save_balance(tx.to_addr, to_bal + tx.amount)

            # Save transaction record
            self.storage.save_transaction(tx)

    def _apply_content_registry(self, block: Block):
        """Register CIDs and editions from content_register transactions."""
        for tx in block.transactions:
            if tx.tx_type == "content_register" and tx.cid:
                record = {
                    "cid":            tx.cid,
                    "creator_wallet": tx.from_addr,
                    "first_owner":    tx.to_addr,
                    "first_platform": tx.data.get("platform_id", "unknown"),
                    "first_tx_hash":  tx.hash,
                    "first_block":    block.index,
                    "timestamp":      tx.timestamp,
                    "total_editions": tx.editions or 1,
                    "royalty_pct":    tx.royalty_pct or 0,
                }
                self.storage.save_content_record(record)

            elif tx.tx_type == "ownership_transfer" and tx.cid:
                # Update current owner
                existing = self.storage.get_content_record(tx.cid)
                if existing:
                    existing["current_owner"] = tx.to_addr
                    self.storage.save_content_record(existing)

            elif tx.tx_type == "edition_transfer" and tx.cid:
                edition_record = {
                    "cid":            tx.cid,
                    "edition_number": tx.edition_number,
                    "current_owner":  tx.to_addr,
                    "platform":       tx.data.get("platform_id", "unknown"),
                    "tx_hash":        tx.hash,
                    "timestamp":      tx.timestamp,
                }
                self.storage.save_edition_record(edition_record)

    # ─────────────────────────────────────────────────────────────
    # Balances
    # ─────────────────────────────────────────────────────────────

    def get_balance(self, address: str) -> float:
        """Get PLWB balance for an address."""
        return self.storage.get_balance(address.lower())

    # ─────────────────────────────────────────────────────────────
    # Chain queries
    # ─────────────────────────────────────────────────────────────

    def get_block(self, block_hash: str) -> Optional[Block]:
        return self.storage.get_block(block_hash)

    def get_block_by_index(self, index: int) -> Optional[Block]:
        return self.storage.get_block_by_index(index)

    def get_chain_tip(self) -> Optional[Block]:
        return self.storage.get_chain_tip()

    def get_chain_length(self) -> int:
        return self.storage.get_chain_length()

    def get_pending_transactions(self) -> List[Transaction]:
        return self.mempool.get_pending()

    def get_blocks_from(self, from_index: int, limit: int = 50) -> List[Block]:
        """Get a range of blocks — used for chain sync."""
        return self.storage.get_blocks_from(from_index, limit)

    # ─────────────────────────────────────────────────────────────
    # Chain validation
    # ─────────────────────────────────────────────────────────────

    def validate_chain(self) -> Tuple[bool, str]:
        """
        Validate entire chain integrity.
        Used during sync to verify downloaded chain from peers.
        """
        length = self.storage.get_chain_length()
        if length == 0:
            return False, "Empty chain"

        previous_block = None
        for i in range(length):
            block = self.storage.get_block_by_index(i)
            if not block:
                return False, f"Missing block at index {i}"

            valid, reason = block.validate(previous_block)
            if not valid:
                return False, f"Block {i} invalid: {reason}"

            previous_block = block

        return True, f"Chain valid ({length} blocks)"

    def get_stats(self) -> Dict:
        tip = self.get_chain_tip()
        return {
            "chain_length":      self.get_chain_length(),
            "chain_tip":         tip.hash if tip else None,
            "pending_tx_count":  self.mempool.size(),
            "chain_id":          CHAIN_ID,
        }
