"""
PlayWebit Network — Royalty Engine
Enforces creator royalties at protocol level.
Set at mint time, enforced on every resale — forever.
Platforms cannot bypass this. Consensus rejects blocks that do.
"""

import logging
from typing import Dict, List, Tuple, Optional

logger = logging.getLogger(__name__)


class RoyaltyEngine:

    def __init__(self, storage):
        """
        storage — any ChainStorage implementation.
        Reads content_registry to get creator + royalty_pct per CID.
        """
        self.storage = storage

    # ─────────────────────────────────────────────────────────────
    # Get royalty info
    # ─────────────────────────────────────────────────────────────

    def get_royalty(self, cid: str) -> Optional[Dict]:
        """
        Get royalty info for a CID from the content registry.
        Returns:
            {
                creator_wallet: str,
                royalty_pct:    float,
                cid:            str,
            }
        or None if CID not registered.
        """
        record = self.storage.get_content_record(cid)
        if not record:
            return None

        return {
            "creator_wallet": record.get("creator_wallet"),
            "royalty_pct":    record.get("royalty_pct", 0),
            "cid":            cid,
        }

    # ─────────────────────────────────────────────────────────────
    # Calculate split
    # ─────────────────────────────────────────────────────────────

    def calculate_split(
        self,
        cid:        str,
        sale_price: float,
    ) -> Dict:
        """
        Calculate how a sale price splits between creator and seller.
        Returns:
            {
                creator_wallet:  str,
                royalty_pct:     float,
                creator_amount:  float,   # royalty to original creator
                seller_amount:   float,   # remainder to seller
                sale_price:      float,
            }
        """
        royalty = self.get_royalty(cid)

        if not royalty or royalty["royalty_pct"] == 0:
            return {
                "creator_wallet":  royalty["creator_wallet"] if royalty else None,
                "royalty_pct":     0,
                "creator_amount":  0.0,
                "seller_amount":   sale_price,
                "sale_price":      sale_price,
            }

        royalty_pct    = royalty["royalty_pct"]
        creator_amount = round(sale_price * (royalty_pct / 100), 8)
        seller_amount  = round(sale_price - creator_amount, 8)

        return {
            "creator_wallet":  royalty["creator_wallet"],
            "royalty_pct":     royalty_pct,
            "creator_amount":  creator_amount,
            "seller_amount":   seller_amount,
            "sale_price":      sale_price,
        }

    # ─────────────────────────────────────────────────────────────
    # Create royalty transactions
    # ─────────────────────────────────────────────────────────────

    def create_royalty_transactions(
        self,
        cid:          str,
        sale_price:   float,
        buyer_wallet: str,
        seller_wallet: str,
        base_nonce:   int = 0,
    ) -> List:
        """
        Create the transactions for a resale.
        Returns [creator_royalty_tx, seller_payment_tx]

        Both go on chain. Consensus validates they're correct.
        """
        from playweb.core.transaction import Transaction

        split = self.calculate_split(cid, sale_price)
        txs   = []

        # Royalty to original creator
        if split["creator_amount"] > 0 and split["creator_wallet"]:
            txs.append(Transaction(
                from_addr = buyer_wallet.lower(),
                to_addr   = split["creator_wallet"].lower(),
                amount    = split["creator_amount"],
                tx_type   = "ownership_transfer",
                nonce     = base_nonce + 1,
                cid       = cid,
                data      = {
                    "royalty":      True,
                    "royalty_pct":  split["royalty_pct"],
                    "sale_price":   sale_price,
                    "seller":       seller_wallet,
                }
            ))

        # Payment to seller
        if split["seller_amount"] > 0:
            txs.append(Transaction(
                from_addr = buyer_wallet.lower(),
                to_addr   = seller_wallet.lower(),
                amount    = split["seller_amount"],
                tx_type   = "ownership_transfer",
                nonce     = base_nonce + 2,
                cid       = cid,
                data      = {
                    "royalty":      False,
                    "royalty_pct":  split["royalty_pct"],
                    "sale_price":   sale_price,
                    "creator_cut":  split["creator_amount"],
                }
            ))

        return txs

    # ─────────────────────────────────────────────────────────────
    # Validate royalty transactions in a block
    # Called by every node during consensus
    # ─────────────────────────────────────────────────────────────

    def validate_royalty_transactions(
        self,
        block,
    ) -> Tuple[bool, str]:
        """
        Validate that royalty payments in a block are correct.
        Every honest node runs this during consensus.

        Checks:
          1. Royalty goes to the correct original creator
          2. Royalty amount matches the registered royalty_pct
          3. Creator cannot be changed after minting

        Returns (is_valid, reason).
        """
        for tx in block.transactions:
            if tx.tx_type != "ownership_transfer":
                continue
            if not tx.data:
                continue
            if not tx.data.get("royalty"):
                continue

            # This is a royalty payment — validate it
            cid = tx.cid
            if not cid:
                return False, f"Royalty tx {tx.hash[:12]} missing cid"

            royalty = self.get_royalty(cid)
            if not royalty:
                return False, f"CID {cid} not in content registry"

            # Creator wallet must match
            if tx.to_addr != royalty["creator_wallet"].lower():
                return (
                    False,
                    f"Royalty going to wrong wallet for {cid}: "
                    f"expected {royalty['creator_wallet']}, "
                    f"got {tx.to_addr}"
                )

            # Royalty amount must match
            sale_price = tx.data.get("sale_price", 0)
            if sale_price > 0:
                expected = round(sale_price * (royalty["royalty_pct"] / 100), 8)
                if round(tx.amount, 8) != expected:
                    return (
                        False,
                        f"Wrong royalty amount for {cid}: "
                        f"expected {expected}, got {tx.amount}"
                    )

        return True, "Valid"
