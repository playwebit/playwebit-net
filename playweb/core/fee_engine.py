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
                total:          float,  # total fee in PLWB
                authority_cut:  float,  # goes to AUTHORITY_WALLET
                node_cut:       float,  # goes to node operator
                fee_type:       str,    # "split" | "authority_only" | "none"
            }
        """
        if tx_type == "fee":
            total = TRANSACTION_FEE
            return self._split(total)

        if tx_type == "cv_link":
            total = CV_LINK_FEE
            return self._split(total)

        if tx_type in ("transfer", "content_register", "ownership_transfer",
                   "edition_transfer", "spider_hash_anchor", "node_register"):
            total = TRANSACTION_FEE
            return self._split(total)

        if tx_type == "plwb_redeem":
            # Redemption fee = 5% of redemption amount, 100% to authority
            total = amount * PLWB_REDEMPTION_FEE
            return {
                "total":         total,
                "authority_cut": total,
                "node_cut":      0.0,
                "fee_type":      "authority_only",
            }

        # No L1 fee for other tx types
        # (platform fees are L2 territory)
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
        original_tx,          # the Transaction that triggered this fee
        node_wallet: str,     # node operator's wallet
    ) -> List:
        """
        Create the fee transactions for a given original transaction.
        Returns a list of Transaction objects to be added to the block.

        For split fees: returns 2 transactions
            → 0.5 PLWB to AUTHORITY_WALLET
            → 0.5 PLWB to node_wallet

        For authority-only fees: returns 1 transaction
            → fee to AUTHORITY_WALLET

        For no-fee tx types: returns []
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
                        "fee_for":    original_tx.hash,
                        "fee_split":  "authority",
                        "split_pct":  FEE_SPLIT_AUTHORITY,
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
                        "fee_for":    original_tx.hash,
                        "fee_split":  "node",
                        "split_pct":  FEE_SPLIT_NODE,
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
    # Called by every node during block validation
    # This is what prevents fee manipulation
    # ─────────────────────────────────────────────────────────────

    def validate_fee_transactions(
        self,
        block,
        node_wallet: str,
    ) -> Tuple[bool, str]:
        """
        Validate that all fee transactions in a block are correct.
        Called during consensus — every honest node runs this.

        Checks:
          1. Fee goes to correct wallets (AUTHORITY_WALLET + node_wallet)
          2. Split is exactly 50/50
          3. Redemption fee goes 100% to AUTHORITY_WALLET
          4. No extra fee transactions that shouldn't be there

        Returns (is_valid, reason).
        """
        transactions = block.transactions

        # Build a map of fee transactions keyed by the tx they're paying for
        fee_map: Dict[str, List] = {}
        for tx in transactions:
            if tx.tx_type == "fee":
                fee_for = tx.data.get("fee_for") if tx.data else None
                if fee_for:
                    fee_map.setdefault(fee_for, []).append(tx)

        # For each non-fee transaction, validate its fees
        for tx in transactions:
            if tx.tx_type == "fee":
                continue  # skip fee txs themselves

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
                # Must have exactly 2 fee transactions
                if len(fees) != 2:
                    return (
                        False,
                        f"Expected 2 fee txs for {tx.hash[:12]}, "
                        f"got {len(fees)}"
                    )

                # Find authority and node fee txs
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

                # Validate amounts
                expected_auth = round(fee_info["total"] * FEE_SPLIT_AUTHORITY, 8)
                expected_node = round(fee_info["total"] * FEE_SPLIT_NODE, 8)

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
                # Must have exactly 1 fee transaction to authority
                if len(fees) != 1:
                    return (
                        False,
                        f"Expected 1 fee tx for {tx.hash[:12]}, got {len(fees)}"
                    )
                if fees[0].to_addr != AUTHORITY_WALLET.lower():
                    return (
                        False,
                        f"Authority-only fee going to wrong wallet: {fees[0].to_addr}"
                    )

        return True, "Valid"

    def get_required_balance_for_tx(self, tx_type: str, amount: float) -> float:
        """
        How much PLWB does a user need to submit this transaction?
        amount + all fees.
        """
        fee_info = self.calculate_fee(tx_type, amount)
        return amount + fee_info["total"]
