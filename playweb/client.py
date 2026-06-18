"""
PlayWebit Network — PlayWebitClient
Lightweight client for dApps that connect to a validator node.
No local chain storage. No consensus participation.
Just calls a node's public API.

Use this for:
  - HuggingFace apps (CipherVault frontend)
  - Any app that doesn't want to run a full node
  - spiderweave-sdk integration without running a node

Usage:
    from playweb import PlayWebitClient

    client = PlayWebitClient(
        validator_url   = "https://node1.playwebit.com",
        platform_wallet = os.getenv("PLATFORM_WALLET"),
    )

    result = client.register_content(
        cid         = "QmXyz...",
        owner       = "0xabc...",
        editions    = 100,
        royalty_pct = 10,
        signature   = "0x...",
    )
"""

import logging
import requests
from typing import Optional, Dict, Tuple

from playweb.config import PEER_TIMEOUT, CHAIN_ID

logger = logging.getLogger(__name__)


class PlayWebitClient:

    def __init__(
        self,
        validator_url:   str,
        platform_wallet: str,
        timeout:         int = PEER_TIMEOUT,
    ):
        self.validator_url   = validator_url.rstrip("/")
        self.platform_wallet = platform_wallet.lower()
        self.timeout         = timeout

    # ─────────────────────────────────────────────────────────────
    # Internal HTTP helpers
    # ─────────────────────────────────────────────────────────────

    def _get(self, path: str) -> Dict:
        try:
            res = requests.get(
                f"{self.validator_url}{path}",
                timeout=self.timeout,
            )
            return res.json()
        except Exception as e:
            logger.error(f"Client GET {path} failed: {e}")
            return {"success": False, "error": str(e)}

    def _post(self, path: str, data: Dict) -> Dict:
        try:
            res = requests.post(
                f"{self.validator_url}{path}",
                json    = data,
                timeout = self.timeout,
            )
            return res.json()
        except Exception as e:
            logger.error(f"Client POST {path} failed: {e}")
            return {"success": False, "error": str(e)}

    # ─────────────────────────────────────────────────────────────
    # Content Registry
    # ─────────────────────────────────────────────────────────────

    def register_content(
        self,
        cid:         str,
        owner:       str,
        editions:    int   = 1,
        royalty_pct: float = 0,
        signature:   str   = None,
        platform_id: str   = None,
        extra_data:  Dict  = None,
    ) -> Tuple[bool, str, Optional[str]]:
        """
        Register a CID on the PlayWebit Network.
        Checks for duplicates automatically.
        Returns (success, reason, tx_hash).
        """
        res = self._post("/api/transaction", {
            "from_addr":   owner.lower(),
            "to_addr":     owner.lower(),
            "amount":      0,
            "tx_type":     "content_register",
            "signature":   signature,
            "chain_id":    CHAIN_ID,
            "cid":         cid,
            "editions":    editions,
            "royalty_pct": royalty_pct,
            "data": {
                "platform_id": platform_id or "unknown",
                **(extra_data or {}),
            },
        })
        success  = res.get("success", False)
        result   = res.get("result") or res.get("error", "Unknown error")
        tx_hash  = result if success else None
        return success, result, tx_hash

    def check_duplicate(self, cid: str) -> Dict:
        """
        Check if a CID is already registered anywhere on the network.
        Returns { exists, first_owner, first_platform, first_seen, ... }
        """
        return self._get(f"/api/check_duplicate/{cid}")

    def get_owner(self, cid: str) -> Optional[Dict]:
        """Get current owner of a CID."""
        res = self._get(f"/api/owner/{cid}")
        return res if res.get("success") else None

    def verify_ownership(self, cid: str, wallet: str) -> bool:
        """Verify a wallet owns a CID."""
        res = self._post("/api/verify_ownership", {
            "cid":    cid,
            "wallet": wallet,
        })
        return res.get("owns", False)

    def transfer_ownership(
        self,
        cid:         str,
        from_wallet: str,
        to_wallet:   str,
        signature:   str   = None,
        sale_price:  float = 0,
        platform_id: str   = None,
    ) -> Tuple[bool, str, Optional[str]]:
        """
        Transfer ownership of a CID.
        If sale_price > 0, royalty is automatically paid to creator.
        Returns (success, reason, tx_hash).
        """
        res = self._post("/api/transaction", {
            "from_addr": from_wallet.lower(),
            "to_addr":   to_wallet.lower(),
            "amount":    sale_price,
            "tx_type":   "ownership_transfer",
            "signature": signature,
            "chain_id":  CHAIN_ID,
            "cid":       cid,
            "data": {
                "platform_id":   platform_id or "unknown",
                "sale_price":    sale_price,
                "transfer_type": "sale" if sale_price > 0 else "gift",
            },
        })
        success = res.get("success", False)
        result  = res.get("result") or res.get("error", "Unknown error")
        return success, result, result if success else None

    # ─────────────────────────────────────────────────────────────
    # Edition Registry
    # ─────────────────────────────────────────────────────────────

    def get_editions(self, cid: str) -> Dict:
        """Get all editions for a CID across all platforms."""
        return self._get(f"/api/editions/{cid}")

    def get_edition(self, cid: str, edition_number: int) -> Optional[Dict]:
        """Get a specific edition."""
        res = self._get(f"/api/editions/{cid}/{edition_number}")
        return res.get("edition") if res.get("success") else None

    def transfer_edition(
        self,
        cid:            str,
        edition_number: int,
        from_wallet:    str,
        to_wallet:      str,
        signature:      str   = None,
        sale_price:     float = 0,
        platform_id:    str   = None,
    ) -> Tuple[bool, str, Optional[str]]:
        """Transfer a specific edition to a new owner."""
        res = self._post("/api/transaction", {
            "from_addr":      from_wallet.lower(),
            "to_addr":        to_wallet.lower(),
            "amount":         sale_price,
            "tx_type":        "edition_transfer",
            "signature":      signature,
            "chain_id":       CHAIN_ID,
            "cid":            cid,
            "edition_number": edition_number,
            "data": {
                "platform_id": platform_id or "unknown",
                "sale_price":  sale_price,
                "action":      "transfer",
            },
        })
        success = res.get("success", False)
        result  = res.get("result") or res.get("error", "Unknown error")
        return success, result, result if success else None

    # ─────────────────────────────────────────────────────────────
    # SpiderWeave hash anchoring
    # Called internally by spiderweave-sdk's PlayWebitAdapter
    # ─────────────────────────────────────────────────────────────

    def anchor_spider_hash(
        self,
        chain_name:      str,
        spider_hash:     str,
        event_type:      str  = "integrity_check",
        platform_wallet: str  = None,
        signature:       str  = None,
        metadata:        Dict = None,
    ) -> Tuple[bool, Optional[str]]:
        """
        Anchor a SpiderWeave hash on the chain.
        L1 stores it, never interprets it.
        Returns (success, tx_hash).
        """
        res = self._post("/api/anchor_spider_hash", {
            "chain_id":       chain_name,
            "chain_name":     chain_name,
            "spider_hash":    spider_hash,
            "event_type":     event_type,
            "platform_wallet": platform_wallet or self.platform_wallet,
            "signature":      signature,
            "metadata":       metadata or {},
        })
        success  = res.get("success", False)
        tx_hash  = res.get("tx_hash")
        return success, tx_hash

    def verify_spider_hash(self, tx_hash: str) -> Optional[Dict]:
        """Verify a previously anchored spider hash by tx_hash."""
        res = self._get(f"/api/transaction/{tx_hash}")
        if not res.get("success"):
            return None
        tx = res.get("transaction", {})
        if tx.get("tx_type") != "spider_hash_anchor":
            return None
        return {
            "tx_hash":     tx_hash,
            "spider_hash": tx.get("spider_hash"),
            "chain_name":  tx.get("chain_name"),
            "timestamp":   tx.get("timestamp"),
            "confirmed":   True,
        }

    def get_spider_hashes(self, chain_name: str) -> Dict:
        """Get all anchored hashes for a chain_name."""
        return self._get(f"/api/spider_hashes/{chain_name}")

    # ─────────────────────────────────────────────────────────────
    # Payments
    # ─────────────────────────────────────────────────────────────

    def pay(
        self,
        from_addr: str,
        to_addr:   str,
        amount:    float,
        signature: str,
    ) -> Tuple[bool, str, Optional[str]]:
        """
        Send PLWB from one wallet to another.
        Returns (success, reason, tx_hash).
        """
        res = self._post("/api/transaction", {
            "from_addr": from_addr.lower(),
            "to_addr":   to_addr.lower(),
            "amount":    amount,
            "tx_type":   "transfer",
            "signature": signature,
            "chain_id":  CHAIN_ID,
        })
        success = res.get("success", False)
        result  = res.get("result") or res.get("error", "Unknown error")
        return success, result, result if success else None

    def get_balance(self, address: str) -> float:
        """Get PLWB balance for an address."""
        res = self._get(f"/api/balance/{address}")
        return float(res.get("balance", 0.0))

    # ─────────────────────────────────────────────────────────────
    # Network info
    # ─────────────────────────────────────────────────────────────

    def get_network_stats(self) -> Dict:
        """Get network stats from the connected validator."""
        return self._get("/api/network/stats")

    def get_transaction(self, tx_hash: str) -> Optional[Dict]:
        """Get a transaction by hash."""
        res = self._get(f"/api/transaction/{tx_hash}")
        return res.get("transaction") if res.get("success") else None

    def health_check(self) -> bool:
        """Check if the connected validator is online."""
        res = self._get("/peer/health")
        return res.get("status") == "ok"

    def __repr__(self):
        return (
            f"PlayWebitClient("
            f"validator={self.validator_url}, "
            f"wallet={self.platform_wallet[:10]}...)"
        )
