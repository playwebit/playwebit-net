"""
PlayWebit Network — Fee Engine
Handles all L1 fee logic.
50/50 split enforced here — no node operator can override.
Every block is validated against these rules.
"""

import logging
from typing import List, Tuple, Dict

from playweb.config import (
    AUTHORITY_WALLET,
    TRANSACTION_FEE,
    CV_LINK_FEE,
    PLWB_REDEMPTION_FEE,
    FEE_SPLIT_AUTHORITY,
    FEE_SPLIT_NODE,
    SPLITTABLE_FEE_TYPES,
    AUTHORITY_ONLY_FEE_TYPES,
    AUTHORITY_TX_TYPES,
)

logger = logging.getLogger(__name__)


class FeeEngine:

    def __init__(self):
        pass

    # ─────────────────────────────────────────────────────────────
    # Calculate
    # ─────────────────────────────────────────────────────────────

    def calculate_fee(self, tx_type: str, amount: float = 0) -> Dict:
        """
        Calculate the fee for a given transaction type.
        Returns:
            {
                total:          float,
                authority_cut:  float,
                node_cut:       float,
                fee_type:       str,   "split" | "authority_only" | "none"
            }
        """
        # ── Authority tx types never have fees ───────────────────
        # genesis, reward, plwb_purchase, plwb_redeem,
        # spider_hash_anchor — all free
        if tx_type in AUTHORITY_TX_TYPES:
            return {
                "total":         0.0,
                "authority_cut": 0.0,
                "node_cut":      0.0,
                "fee_type":      "none",
            }

        # ── Base network fee (50/50 split) ────────────────────────
        if tx_type == "fee":
            return self._split(TRANSACTION_FEE)

        # ── CID link fee (50/50 split) ────────────────────────────
        if tx_type == "cv_link":
            return self._split(CV_LINK_FEE)

        # ── All standard user-facing tx types → 1 PLWB network fee
        if tx_type in (
            "transfer",             # PLWB transfer between any wallets
            "content_register",     # register CID ownership
            "ownership_transfer",   # transfer content (1:1 model)
            "edition_transfer",     # transfer edition (creator model)
            "node_register",        # platform registers on network
        ):
            return self._split(TRANSACTION_FEE)

        # ── Redemption fee → 100% authority ──────────────────────
        if tx_type == "plwb_redeem":
            total = amount * PLWB_REDEMPTION_FEE
            return {
                "total":         total,
                "authority_cut": total,
                "node_cut":      0.0,
                "fee_type":      "authority_only",
            }

        # ── No fee for unknown/other tx types ────────────────────
        return {
            "total":         0.0,
            "authority_cut": 0.0,
            "node_cut":      0.0,
            "fee_type":      "none",
        }

    def _split(self, total: float) -> Dict:
        """50/50 split between authority and node operator."""
        authority_cut = round(total * FEE_SPLIT_AUTHORITY, 8)
        node_cut      = round(total * FEE_SPLIT_NODE, 8)
        return {
            "total":         total,
            "authority_cut": authority_cut,
            "node_cut":      node_cut,
            "fee_type":      "split",
        }

    # ─────────────────────────────────────────────────────────────
    # Create fee transactions
    # ─────────────────────────────────────────────────────────────

    def create_fee_transactions(
        self,
        original_tx,
        node_wallet: str,
    ) -> List:
        """
        Create the fee transactions for a given original transaction.
        Returns list of Transaction objects to add to the block.

        Split fees → 2 transactions (authority + node)
        Authority-only fees → 1 transaction (authority only)
        No fee → []
        """
        from playweb.core.transaction import Transaction

        fee_info = self.calculate_fee(original_tx.tx_type, original_tx.amount)

        if fee_info["fee_type"] == "none":
            return []

        fee_txs = []

        if fee_info["fee_type"] == "split":
            # Authority cut
            if fee_info["authority_cut"] > 0:
                fee_txs.append(Transaction(
                    from_addr = original_tx.from_addr,
                    to_addr   = AUTHORITY_WALLET.lower(),
                    amount    = fee_info["authority_cut"],
                    tx_type   = "fee",
                    nonce     = original_tx.nonce + 1,
                    data      = {
                        "fee_for":   original_tx.hash,
                        "fee_split": "authority",
                        "split_pct": FEE_SPLIT_AUTHORITY,
                    }
                ))

            # Node operator cut
            if fee_info["node_cut"] > 0 and node_wallet:
                fee_txs.append(Transaction(
                    from_addr = original_tx.from_addr,
                    to_addr   = node_wallet.lower(),
                    amount    = fee_info["node_cut"],
                    tx_type   = "fee",
                    nonce     = original_tx.nonce + 2,
                    data      = {
                        "fee_for":   original_tx.hash,
                        "fee_split": "node",
                        "split_pct": FEE_SPLIT_NODE,
                    }
                ))

        elif fee_info["fee_type"] == "authority_only":
            if fee_info["authority_cut"] > 0:
                fee_txs.append(Transaction(
                    from_addr = original_tx.from_addr,
                    to_addr   = AUTHORITY_WALLET.lower(),
                    amount    = fee_info["authority_cut"],
                    tx_type   = "fee",
                    nonce     = original_tx.nonce + 1,
                    data      = {
                        "fee_for":   original_tx.hash,
                        "fee_split": "authority_only",
                    }
                ))

        return fee_txs

    # ─────────────────────────────────────────────────────────────
    # Validate fee transactions in a block
    # Called by every node during consensus
    # This prevents fee manipulation
    # ─────────────────────────────────────────────────────────────

    def validate_fee_transactions(
        self,
        block,
        node_wallet: str,
    ) -> Tuple[bool, str]:
        """
        Validate that all fee transactions in a block are correct.
        Every honest node runs this during consensus.
        Returns (is_valid, reason).
        """
        transactions = block.transactions

        # Build map of fee txs keyed by the tx they're paying for
        fee_map: Dict[str, List] = {}
        for tx in transactions:
            if tx.tx_type == "fee":
                fee_for = tx.data.get("fee_for") if tx.data else None
                if fee_for:
                    fee_map.setdefault(fee_for, []).append(tx)

        # Validate each non-fee transaction
        for tx in transactions:
            if tx.tx_type == "fee":
                continue

            # Authority tx types never have fee transactions
            if tx.tx_type in AUTHORITY_TX_TYPES:
                continue

            fee_info = self.calculate_fee(tx.tx_type, tx.amount)

            if fee_info["fee_type"] == "none":
                # Should have no fee transactions
                if tx.hash in fee_map:
                    return False, f"Unexpected fee for tx {tx.hash[:12]}"
                continue

            fees = fee_map.get(tx.hash, [])

            if fee_info["fee_type"] == "split":
                if len(fees) != 2:
                    return (
                        False,
                        f"Expected 2 fee txs for {tx.hash[:12]}, "
                        f"got {len(fees)}"
                    )

                auth_fees = [
                    f for f in fees
                    if f.to_addr == AUTHORITY_WALLET.lower()
                ]
                node_fees = [
                    f for f in fees
                    if f.to_addr == node_wallet.lower()
                ]

                if len(auth_fees) != 1:
                    return (
                        False,
                        f"Missing authority fee for tx {tx.hash[:12]}"
                    )
                if len(node_fees) != 1:
                    return (
                        False,
                        f"Missing node fee for tx {tx.hash[:12]}"
                    )

                expected_auth = round(
                    fee_info["total"] * FEE_SPLIT_AUTHORITY, 8
                )
                expected_node = round(
                    fee_info["total"] * FEE_SPLIT_NODE, 8
                )

                if round(auth_fees[0].amount, 8) != expected_auth:
                    return (
                        False,
                        f"Wrong authority fee: expected {expected_auth}, "
                        f"got {auth_fees[0].amount}"
                    )
                if round(node_fees[0].amount, 8) != expected_node:
                    return (
                        False,
                        f"Wrong node fee: expected {expected_node}, "
                        f"got {node_fees[0].amount}"
                    )

            elif fee_info["fee_type"] == "authority_only":
                if len(fees) != 1:
                    return (
                        False,
                        f"Expected 1 fee tx for {tx.hash[:12]}, "
                        f"got {len(fees)}"
                    )
                if fees[0].to_addr != AUTHORITY_WALLET.lower():
                    return (
                        False,
                        f"Authority-only fee going to wrong wallet: "
                        f"{fees[0].to_addr}"
                    )

        return True, "Valid"

    def get_required_balance_for_tx(
        self,
        tx_type: str,
        amount: float,
    ) -> float:
        """How much PLWB does sender need? amount + all fees."""
        fee_info = self.calculate_fee(tx_type, amount)
        return amount + fee_info["total"]
