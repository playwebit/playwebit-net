"""
PlayWebit Network — Transaction
Clean L1 transaction. No CipherVault logic. No Supabase.
"""

import hashlib
import json
import time
import logging
from typing import Optional, Dict, Any

from playweb.config import CHAIN_ID, L1_TX_TYPES, AUTHORITY_TX_TYPES

logger = logging.getLogger(__name__)


class Transaction:
    """
    L1 Transaction.

    MANDATORY fields — L1 validates all of these:
        from_addr, to_addr, amount, tx_type,
        timestamp, signature, nonce, chain_id

    CONDITIONAL fields — required for specific tx_types:
        cid            → required for content_register, cv_link,
                         ownership_transfer, edition_transfer
        editions       → required for content_register
        royalty_pct    → required for content_register
        edition_number → required for edition_transfer
        spider_hash    → required for spider_hash_anchor
        chain_name     → required for spider_hash_anchor

    OPTIONAL free field — L1 carries it, never reads it:
        data: {}       → platform stores anything here
                         license_type, song_title, platform_id,
                         spider_hash metadata, custom fields etc
    """

    def __init__(
        self,
        from_addr:      str,
        to_addr:        str,
        amount:         float,
        tx_type:        str,
        signature:      str   = None,
        nonce:          int   = None,
        timestamp:      float = None,

        # Conditional fields
        cid:            Optional[str]   = None,
        editions:       Optional[int]   = None,
        royalty_pct:    Optional[float] = None,
        edition_number: Optional[int]   = None,
        spider_hash:    Optional[str]   = None,
        chain_name:     Optional[str]   = None,

        # Free optional data field — L1 never reads this
        data:           Optional[Dict[str, Any]] = None,
    ):
        # ── Mandatory fields ──────────────────────────────────
        self.from_addr  = from_addr.lower() if from_addr else from_addr
        self.to_addr    = to_addr.lower()   if to_addr   else to_addr
        self.amount     = float(amount)
        self.tx_type    = tx_type
        self.timestamp  = timestamp or time.time()
        self.nonce      = nonce if nonce is not None else int(self.timestamp * 1000)
        self.chain_id   = CHAIN_ID
        self.signature  = signature

        # ── Conditional fields ────────────────────────────────
        self.cid            = cid
        self.editions       = editions
        self.royalty_pct    = royalty_pct
        self.edition_number = edition_number
        self.spider_hash    = spider_hash
        self.chain_name     = chain_name

        # ── Optional free data field ──────────────────────────
        self.data = data or {}

        # ── Computed ──────────────────────────────────────────
        self.hash = self.calculate_hash()

    # ─────────────────────────────────────────────────────────────
    # Hashing
    # ─────────────────────────────────────────────────────────────

    def get_signable_data(self) -> Dict:
        """
        Returns the canonical dict that gets hashed and signed.
        Only mandatory + conditional fields — not data{} field
        because platforms may add data after signing.
        """
        d = {
            "from_addr":  self.from_addr,
            "to_addr":    self.to_addr,
            "amount":     self.amount,
            "tx_type":    self.tx_type,
            "timestamp":  self.timestamp,
            "nonce":      self.nonce,
            "chain_id":   self.chain_id,
        }

        # Include conditional fields only if set
        if self.cid            is not None: d["cid"]            = self.cid
        if self.editions       is not None: d["editions"]       = self.editions
        if self.royalty_pct    is not None: d["royalty_pct"]    = self.royalty_pct
        if self.edition_number is not None: d["edition_number"] = self.edition_number
        if self.spider_hash    is not None: d["spider_hash"]    = self.spider_hash
        if self.chain_name     is not None: d["chain_name"]     = self.chain_name

        return d

    def calculate_hash(self) -> str:
        """SHA256 of canonical signable data."""
        raw = json.dumps(self.get_signable_data(), sort_keys=True)
        return hashlib.sha256(raw.encode()).hexdigest()

    # ─────────────────────────────────────────────────────────────
    # Validation
    # ─────────────────────────────────────────────────────────────

    def validate_fields(self) -> tuple[bool, str]:
        """
        Validate mandatory and conditional fields.
        Returns (is_valid, reason).
        """

        # Mandatory checks
        if not self.from_addr:
            return False, "Missing from_addr"
        if not self.to_addr:
            return False, "Missing to_addr"
        if self.amount < 0:
            return False, "Amount cannot be negative"
        if self.tx_type not in L1_TX_TYPES:
            return False, f"Unknown tx_type: {self.tx_type}"
        if self.chain_id != CHAIN_ID:
            return False, f"Wrong chain_id: {self.chain_id}, expected {CHAIN_ID}"
        if not self.nonce:
            return False, "Missing nonce"

        # Conditional checks
        if self.tx_type == "content_register":
            if not self.cid:
                return False, "content_register requires cid"
            if self.editions is None:
                return False, "content_register requires editions"
            if self.royalty_pct is None:
                return False, "content_register requires royalty_pct"
            if not (0 <= self.royalty_pct <= 100):
                return False, "royalty_pct must be 0-100"

        if self.tx_type in ("cv_link", "ownership_transfer"):
            if not self.cid:
                return False, f"{self.tx_type} requires cid"

        if self.tx_type == "edition_transfer":
            if not self.cid:
                return False, "edition_transfer requires cid"
            if self.edition_number is None:
                return False, "edition_transfer requires edition_number"

        if self.tx_type == "spider_hash_anchor":
            if not self.spider_hash:
                return False, "spider_hash_anchor requires spider_hash"
            if not self.chain_name:
                return False, "spider_hash_anchor requires chain_name"

        return True, "Valid"

    def verify_signature(self, public_key: str = None) -> bool:
        """
        Verify the transaction signature.
        Authority transactions skip verification.
        MetaMask personal_sign compatible.
        """
        # Authority txs don't need signature verification
        if self.tx_type in AUTHORITY_TX_TYPES:
            return True

        if not self.signature:
            logger.warning(f"Transaction {self.hash} missing signature")
            return False

        try:
            from eth_account import Account
            from eth_account.messages import encode_defunct

            signable  = json.dumps(self.get_signable_data(), sort_keys=True)
            message   = encode_defunct(text=signable)
            recovered = Account.recover_message(message, signature=self.signature)

            return recovered.lower() == self.from_addr.lower()

        except ImportError:
            # eth_account not installed — basic format check only
            logger.warning(
                "eth_account not installed. "
                "Skipping full signature verification. "
                "Install: pip install eth-account"
            )
            return bool(self.signature and self.signature.startswith("0x"))

        except Exception as e:
            logger.error(f"Signature verification failed: {e}")
            return False

    # ─────────────────────────────────────────────────────────────
    # Serialisation
    # ─────────────────────────────────────────────────────────────

    def to_dict(self) -> Dict:
        d = {
            # Mandatory
            "hash":       self.hash,
            "from_addr":  self.from_addr,
            "to_addr":    self.to_addr,
            "amount":     self.amount,
            "tx_type":    self.tx_type,
            "timestamp":  self.timestamp,
            "nonce":      self.nonce,
            "chain_id":   self.chain_id,
            "signature":  self.signature,
            # Optional free field
            "data":       self.data,
        }

        # Conditional — only include if set
        if self.cid            is not None: d["cid"]            = self.cid
        if self.editions       is not None: d["editions"]       = self.editions
        if self.royalty_pct    is not None: d["royalty_pct"]    = self.royalty_pct
        if self.edition_number is not None: d["edition_number"] = self.edition_number
        if self.spider_hash    is not None: d["spider_hash"]    = self.spider_hash
        if self.chain_name     is not None: d["chain_name"]     = self.chain_name

        return d

    @classmethod
    def from_dict(cls, d: Dict) -> "Transaction":
        tx = cls(
            from_addr      = d["from_addr"],
            to_addr        = d["to_addr"],
            amount         = d["amount"],
            tx_type        = d["tx_type"],
            signature      = d.get("signature"),
            nonce          = d.get("nonce"),
            timestamp      = d.get("timestamp"),
            cid            = d.get("cid"),
            editions       = d.get("editions"),
            royalty_pct    = d.get("royalty_pct"),
            edition_number = d.get("edition_number"),
            spider_hash    = d.get("spider_hash"),
            chain_name     = d.get("chain_name"),
            data           = d.get("data", {}),
        )
        # Restore original hash (don't recalculate — it was stored)
        if "hash" in d:
            tx.hash = d["hash"]
        return tx

    def __repr__(self):
        return (
            f"Transaction(type={self.tx_type}, "
            f"from={self.from_addr[:8]}..., "
            f"to={self.to_addr[:8]}..., "
            f"amount={self.amount}, "
            f"hash={self.hash[:12]}...)"
        )
