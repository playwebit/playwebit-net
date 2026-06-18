"""
PlayWebit Network — Edition Registry
Cross-platform edition tracking.
Edition #3 of 100 on MusicApp is visible and verifiable on ArtApp.
"""

import time
import logging
from typing import List, Dict, Optional, Tuple

logger = logging.getLogger(__name__)


class EditionRegistry:

    def __init__(self, blockchain, node_wallet: str):
        self.blockchain  = blockchain
        self.node_wallet = node_wallet

    # ─────────────────────────────────────────────────────────────
    # Create editions
    # ─────────────────────────────────────────────────────────────

    def create_editions(
        self,
        cid:          str,
        total:        int,
        owner_wallet: str,
        platform_id:  str,
        signature:    str = None,
    ) -> Tuple[bool, str]:
        """
        Create edition records for a registered CID.
        Called after content_register when editions > 1.
        Creates edition_transfer txs for each edition.
        Returns (success, reason).
        """
        # Verify CID is registered
        record = self.blockchain.storage.get_content_record(cid)
        if not record:
            return False, f"CID {cid[:16]}... not registered"

        if record.get("current_owner", "").lower() != owner_wallet.lower():
            return False, "Only the owner can create editions"

        from playweb.core.transaction import Transaction

        for edition_num in range(1, total + 1):
            tx = Transaction(
                from_addr      = owner_wallet.lower(),
                to_addr        = owner_wallet.lower(),
                amount         = 0,
                tx_type        = "edition_transfer",
                signature      = signature,
                cid            = cid,
                edition_number = edition_num,
                data           = {
                    "platform_id": platform_id,
                    "edition_of":  total,
                    "action":      "create",
                },
            )
            success, result = self.blockchain.add_transaction(
                tx          = tx,
                node_wallet = self.node_wallet,
            )
            if not success:
                logger.warning(
                    f"EditionRegistry: failed to create edition "
                    f"{edition_num}: {result}"
                )

        logger.info(
            f"EditionRegistry: created {total} editions for "
            f"{cid[:16]}... on {platform_id}"
        )
        return True, f"Created {total} editions"

    # ─────────────────────────────────────────────────────────────
    # Transfer edition
    # ─────────────────────────────────────────────────────────────

    def transfer_edition(
        self,
        cid:            str,
        edition_number: int,
        from_wallet:    str,
        to_wallet:      str,
        platform_id:    str,
        signature:      str  = None,
        sale_price:     float = 0,
    ) -> Tuple[bool, str, Optional[str]]:
        """
        Transfer a specific edition to a new owner.
        If sale_price > 0, royalty is paid to original creator.
        Returns (success, reason, tx_hash).
        """

        # Verify edition ownership
        if not self.verify_edition_owner(cid, edition_number, from_wallet):
            return (
                False,
                f"{from_wallet[:8]}... does not own edition "
                f"#{edition_number} of {cid[:16]}...",
                None,
            )

        from playweb.core.transaction import Transaction

        # Create the edition transfer tx
        tx = Transaction(
            from_addr      = from_wallet.lower(),
            to_addr        = to_wallet.lower(),
            amount         = sale_price,
            tx_type        = "edition_transfer",
            signature      = signature,
            cid            = cid,
            edition_number = edition_number,
            data           = {
                "platform_id": platform_id,
                "sale_price":  sale_price,
                "action":      "transfer",
            },
        )

        success, result = self.blockchain.add_transaction(
            tx          = tx,
            node_wallet = self.node_wallet,
        )
        if not success:
            return False, result, None

        # If sale, create royalty transactions
        if sale_price > 0:
            from playweb.core.royalty_engine import RoyaltyEngine
            royalty_engine = RoyaltyEngine(self.blockchain.storage)
            royalty_txs = royalty_engine.create_royalty_transactions(
                cid           = cid,
                sale_price    = sale_price,
                buyer_wallet  = to_wallet,
                seller_wallet = from_wallet,
            )
            for rtx in royalty_txs:
                rtx.signature = signature
                self.blockchain.add_transaction(
                    tx          = rtx,
                    node_wallet = self.node_wallet,
                )

        logger.info(
            f"EditionRegistry: transfer edition #{edition_number} "
            f"of {cid[:16]}... "
            f"from {from_wallet[:8]}... to {to_wallet[:8]}..."
        )
        return True, "Edition transfer queued", tx.hash

    # ─────────────────────────────────────────────────────────────
    # Queries
    # ─────────────────────────────────────────────────────────────

    def get_edition(self, cid: str, edition_number: int) -> Optional[Dict]:
        """
        Get a specific edition record.
        Returns None if not found.
        """
        return self.blockchain.storage.get_edition_record(cid, edition_number)

    def get_all_editions(self, cid: str) -> List[Dict]:
        """
        Get all editions for a CID across all platforms.
        Any platform can see all editions globally.
        """
        return self.blockchain.storage.get_all_edition_records(cid)

    def verify_edition_owner(
        self,
        cid:            str,
        edition_number: int,
        wallet:         str,
    ) -> bool:
        """
        Verify that a wallet owns a specific edition.
        Used by any platform to verify edition ownership claims.
        """
        record = self.blockchain.storage.get_edition_record(cid, edition_number)
        if not record:
            # If no edition record, check content record (edition 1 = content owner)
            if edition_number == 1:
                content = self.blockchain.storage.get_content_record(cid)
                if content:
                    return (
                        content.get("current_owner", "").lower()
                        == wallet.lower()
                    )
            return False

        return record.get("current_owner", "").lower() == wallet.lower()

    def get_edition_summary(self, cid: str) -> Dict:
        """
        Get a summary of all editions for a CID.
        Useful for marketplace displays.
        """
        content = self.blockchain.storage.get_content_record(cid)
        if not content:
            return {"cid": cid, "found": False}

        editions = self.get_all_editions(cid)
        total    = content.get("total_editions", 1)

        return {
            "cid":            cid,
            "found":          True,
            "total_editions": total,
            "editions_found": len(editions),
            "creator":        content.get("creator_wallet"),
            "royalty_pct":    content.get("royalty_pct", 0),
            "first_platform": content.get("first_platform"),
            "editions":       editions,
        }
