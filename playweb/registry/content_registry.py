"""
PlayWebit Network — Content Registry
Cross-platform CID ownership. The core value of PlayWebit Network.

Any platform using IPFS CIDs gets duplicate detection for free —
IPFS CID format matches across all platforms automatically.

Register once → protected everywhere.
"""

import time
import logging
from typing import Dict, Optional, Tuple

logger = logging.getLogger(__name__)


class ContentRegistry:

    def __init__(self, blockchain, node_wallet: str):
        self.blockchain  = blockchain
        self.node_wallet = node_wallet

    # ─────────────────────────────────────────────────────────────
    # Register content
    # ─────────────────────────────────────────────────────────────

    def register(
        self,
        cid:           str,
        owner_wallet:  str,
        platform_id:   str,
        editions:      int   = 1,
        royalty_pct:   float = 0,
        signature:     str   = None,
        extra_data:    Dict  = None,
    ) -> Tuple[bool, str, Optional[str]]:
        """
        Register a CID on the network.
        Checks for duplicates first — rejects if already registered
        by ANY platform on the network.

        Returns (success, reason, tx_hash).
        tx_hash is None on failure.

        IPFS CIDs match automatically — a file registered on MusicApp
        cannot be registered again on ArtApp.
        """

        # Duplicate check — most important check
        existing = self.check_duplicate(cid)
        if existing["exists"]:
            return (
                False,
                f"CID already registered by {existing['first_platform']} "
                f"on {existing['first_seen_human']}. "
                f"Owner: {existing['first_owner']}",
                None,
            )

        # Validate inputs
        if not cid:
            return False, "CID is required", None
        if not owner_wallet:
            return False, "Owner wallet is required", None
        if editions < 1:
            return False, "Editions must be at least 1", None
        if not (0 <= royalty_pct <= 100):
            return False, "Royalty must be 0-100%", None

        from playweb.core.transaction import Transaction

        # Create the content_register transaction
        tx = Transaction(
            from_addr   = owner_wallet.lower(),
            to_addr     = owner_wallet.lower(),
            amount      = 0,
            tx_type     = "content_register",
            signature   = signature,
            cid         = cid,
            editions    = editions,
            royalty_pct = royalty_pct,
            data        = {
                "platform_id": platform_id,
                **(extra_data or {}),
            },
        )

        # Submit to blockchain (also creates cv_link fee tx)
        success, result = self.blockchain.add_transaction(
            tx          = tx,
            node_wallet = self.node_wallet,
        )

        if not success:
            return False, result, None

        logger.info(
            f"ContentRegistry: registered CID {cid[:16]}... "
            f"by {platform_id} owner={owner_wallet[:8]}..."
        )
        return True, "Registered", tx.hash

    # ─────────────────────────────────────────────────────────────
    # Duplicate detection
    # ─────────────────────────────────────────────────────────────

    def check_duplicate(self, cid: str) -> Dict:
        """
        Check if a CID is already registered on the network.
        Called by any platform before accepting a new upload.

        Returns:
        {
            exists:            bool,
            first_owner:       str or None,
            first_platform:    str or None,
            first_seen:        float or None,
            first_seen_human:  str or None,
            current_owner:     str or None,
            tx_hash:           str or None,
        }
        """
        record = self.blockchain.storage.get_content_record(cid)

        if not record:
            return {
                "exists":           False,
                "first_owner":      None,
                "first_platform":   None,
                "first_seen":       None,
                "first_seen_human": None,
                "current_owner":    None,
                "tx_hash":          None,
            }

        from datetime import datetime
        first_seen       = record.get("timestamp")
        first_seen_human = (
            datetime.fromtimestamp(first_seen).strftime("%Y-%m-%d %H:%M UTC")
            if first_seen else None
        )

        return {
            "exists":           True,
            "first_owner":      record.get("first_owner"),
            "first_platform":   record.get("first_platform"),
            "first_seen":       first_seen,
            "first_seen_human": first_seen_human,
            "current_owner":    record.get("current_owner"),
            "tx_hash":          record.get("first_tx_hash"),
        }

    # ─────────────────────────────────────────────────────────────
    # Ownership queries
    # ─────────────────────────────────────────────────────────────

    def get_owner(self, cid: str) -> Optional[Dict]:
        """
        Get current owner of a CID.
        Returns None if not registered.
        """
        record = self.blockchain.storage.get_content_record(cid)
        if not record:
            return None

        return {
            "cid":           cid,
            "current_owner": record.get("current_owner"),
            "creator":       record.get("creator_wallet"),
            "platform":      record.get("first_platform"),
            "royalty_pct":   record.get("royalty_pct", 0),
            "total_editions": record.get("total_editions", 1),
        }

    def verify_ownership(self, cid: str, wallet: str) -> bool:
        """
        Verify that a wallet is the current owner of a CID.
        Used by any platform to verify ownership claims.
        """
        record = self.blockchain.storage.get_content_record(cid)
        if not record:
            return False
        return (
            record.get("current_owner", "").lower() == wallet.lower()
        )

    # ─────────────────────────────────────────────────────────────
    # Transfer ownership
    # ─────────────────────────────────────────────────────────────

    def transfer_ownership(
        self,
        cid:          str,
        from_wallet:  str,
        to_wallet:    str,
        signature:    str = None,
        platform_id:  str = "unknown",
        sale_price:   float = 0,
    ) -> Tuple[bool, str, Optional[str]]:
        """
        Transfer ownership of a CID from one wallet to another.
        If sale_price > 0, royalty transactions are created automatically.
        Returns (success, reason, tx_hash).
        """

        # Verify current ownership
        if not self.verify_ownership(cid, from_wallet):
            return False, f"{from_wallet[:8]}... does not own {cid[:16]}...", None

        from playweb.core.transaction import Transaction

        # If this is a sale with price, use royalty engine
        if sale_price > 0:
            from playweb.core.royalty_engine import RoyaltyEngine
            royalty_engine = RoyaltyEngine(self.blockchain.storage)
            txs = royalty_engine.create_royalty_transactions(
                cid          = cid,
                sale_price   = sale_price,
                buyer_wallet = to_wallet,
                seller_wallet= from_wallet,
            )
            for tx in txs:
                tx.signature = signature
                success, result = self.blockchain.add_transaction(
                    tx          = tx,
                    node_wallet = self.node_wallet,
                )
                if not success:
                    return False, result, None

            main_tx_hash = txs[0].hash if txs else None
        else:
            # Simple transfer (gift, internal move)
            tx = Transaction(
                from_addr   = from_wallet.lower(),
                to_addr     = to_wallet.lower(),
                amount      = 0,
                tx_type     = "ownership_transfer",
                signature   = signature,
                cid         = cid,
                data        = {
                    "platform_id": platform_id,
                    "transfer_type": "gift",
                },
            )
            success, result = self.blockchain.add_transaction(
                tx          = tx,
                node_wallet = self.node_wallet,
            )
            if not success:
                return False, result, None
            main_tx_hash = tx.hash

        logger.info(
            f"ContentRegistry: transfer {cid[:16]}... "
            f"from {from_wallet[:8]}... to {to_wallet[:8]}..."
        )
        return True, "Transfer queued", main_tx_hash
