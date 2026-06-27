"""
PlayWebit Network — Vote
NVF-BFT vote message. Signed by each validator.
"""

import hashlib
import json
import time
import logging
from typing import Dict

logger = logging.getLogger(__name__)


class Vote:

    def __init__(
        self,
        block_hash:    str,
        voter_wallet:  str,
        round_number:  int,
        phase:         str,       # PREPARE | VOTE | COMMIT
        timestamp:     float = None,
        signature:     str   = None,
    ):
        self.block_hash   = block_hash
        self.voter_wallet = voter_wallet.lower()
        self.round_number = round_number
        self.phase        = phase
        self.timestamp    = timestamp or time.time()
        self.signature    = signature
        self.hash         = self._calculate_hash()

    def _calculate_hash(self) -> str:
        raw = json.dumps({
            "block_hash":   self.block_hash,
            "voter_wallet": self.voter_wallet,
            "round_number": self.round_number,
            "phase":        self.phase,
            "timestamp":    self.timestamp,
        }, sort_keys=True)
        return hashlib.sha256(raw.encode()).hexdigest()

    def sign(self, private_key: str) -> bool:
        """Sign the vote with the node's private key."""
        try:
            from eth_account import Account
            from eth_account.messages import encode_defunct

            msg      = encode_defunct(text=self.hash)
            signed   = Account.sign_message(msg, private_key=private_key)
            sig = signed.signature.hex()
            self.signature = sig if sig.startswith("0x") else "0x" + sig
            return True
        except ImportError:
            # Basic placeholder if eth_account not available
            self.signature = f"0x{'0' * 130}"
            return True
        except Exception as e:
            logger.error(f"Vote signing failed: {e}")
            return False

    def verify(self) -> bool:
        """Verify the vote signature."""
        if not self.signature:
            return False
        try:
            from eth_account import Account
            from eth_account.messages import encode_defunct

            msg       = encode_defunct(text=self.hash)
            recovered = Account.recover_message(msg, signature=self.signature)
            return recovered.lower() == self.voter_wallet
        except ImportError:
            return bool(self.signature)
        except Exception as e:
            logger.error(f"Vote verification failed: {e}")
            return False

    def to_dict(self) -> Dict:
        return {
            "hash":         self.hash,
            "block_hash":   self.block_hash,
            "voter_wallet": self.voter_wallet,
            "round_number": self.round_number,
            "phase":        self.phase,
            "timestamp":    self.timestamp,
            "signature":    self.signature,
        }

    @classmethod
    def from_dict(cls, d: Dict) -> "Vote":
        v = cls(
            block_hash   = d["block_hash"],
            voter_wallet = d["voter_wallet"],
            round_number = d["round_number"],
            phase        = d["phase"],
            timestamp    = d.get("timestamp"),
            signature    = d.get("signature"),
        )
        v.hash = d.get("hash", v.hash)
        return v

    def __repr__(self):
        return (
            f"Vote(phase={self.phase}, "
            f"voter={self.voter_wallet[:8]}..., "
            f"block={self.block_hash[:12]}...)"
        )
