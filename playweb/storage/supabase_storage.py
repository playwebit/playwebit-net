"""
PlayWebit Network — Supabase Storage
For nodes running on HuggingFace or anywhere without persistent disk.
Uses Supabase as the persistent layer.

Required Supabase tables (run this SQL in your Supabase SQL editor):

    CREATE TABLE IF NOT EXISTS pw_blocks (
        hash             TEXT PRIMARY KEY,
        idx              INTEGER UNIQUE,
        previous_hash    TEXT,
        merkle_root      TEXT,
        timestamp        FLOAT,
        nonce            INTEGER DEFAULT 0,
        validator_wallet TEXT,
        consensus_round  INTEGER DEFAULT 0,
        votes            JSONB DEFAULT '[]',
        transactions     JSONB DEFAULT '[]'
    );

    CREATE TABLE IF NOT EXISTS pw_transactions (
        hash  TEXT PRIMARY KEY,
        data  JSONB
    );

    CREATE TABLE IF NOT EXISTS pw_balances (
        address  TEXT PRIMARY KEY,
        balance  FLOAT DEFAULT 0.0,
        updated  FLOAT
    );

    CREATE TABLE IF NOT EXISTS pw_content_registry (
        cid              TEXT PRIMARY KEY,
        creator_wallet   TEXT,
        first_owner      TEXT,
        current_owner    TEXT,
        first_platform   TEXT,
        first_tx_hash    TEXT,
        first_block      INTEGER,
        timestamp        FLOAT,
        total_editions   INTEGER DEFAULT 1,
        royalty_pct      FLOAT DEFAULT 0,
        extra            JSONB DEFAULT '{}'
    );

    CREATE TABLE IF NOT EXISTS pw_edition_registry (
        cid             TEXT,
        edition_number  INTEGER,
        edition_of      INTEGER DEFAULT 1,
        current_owner   TEXT,
        platform        TEXT,
        tx_hash         TEXT,
        timestamp       FLOAT,
        provenance      JSONB DEFAULT '[]',
        PRIMARY KEY (cid, edition_number)
    );
"""

import json
import time
import logging
from typing import List, Optional, Dict

from playweb.storage.base import ChainStorage

logger = logging.getLogger(__name__)


class SupabaseStorage(ChainStorage):

    def __init__(self, url: str, key: str):
        try:
            from supabase import create_client
            self.sb = create_client(url, key)
            logger.info("SupabaseStorage initialised")
        except ImportError:
            raise ImportError(
                "supabase package not installed. "
                "Run: pip install supabase"
            )

    def _t(self, name: str):
        """Shorthand for table access."""
        return self.sb.table(name)

    # ─── Blocks ──────────────────────────────────────────────────

    def save_block(self, block) -> bool:
        try:
            data = {
                "hash":             block.hash,
                "idx":              block.index,
                "previous_hash":    block.previous_hash,
                "merkle_root":      block.merkle_root,
                "timestamp":        block.timestamp,
                "nonce":            block.nonce,
                "validator_wallet": block.validator_wallet,
                "consensus_round":  block.consensus_round,
                "votes":            block.votes,
                "transactions":     [tx.to_dict() for tx in block.transactions],
            }
            self._t("pw_blocks").upsert(data).execute()
            return True
        except Exception as e:
            logger.error(f"save_block error: {e}")
            return False

    def get_block(self, block_hash: str):
        try:
            res = self._t("pw_blocks").select("*").eq("hash", block_hash).execute()
            return self._row_to_block(res.data[0]) if res.data else None
        except Exception as e:
            logger.error(f"get_block error: {e}")
            return None

    def get_block_by_index(self, index: int):
        try:
            res = self._t("pw_blocks").select("*").eq("idx", index).execute()
            return self._row_to_block(res.data[0]) if res.data else None
        except Exception as e:
            logger.error(f"get_block_by_index error: {e}")
            return None

    def get_chain_tip(self):
        try:
            res = (
                self._t("pw_blocks")
                .select("*")
                .order("idx", desc=True)
                .limit(1)
                .execute()
            )
            return self._row_to_block(res.data[0]) if res.data else None
        except Exception as e:
            logger.error(f"get_chain_tip error: {e}")
            return None

    def get_chain_length(self) -> int:
        try:
            res = self._t("pw_blocks").select("idx", count="exact").execute()
            return res.count or 0
        except Exception as e:
            logger.error(f"get_chain_length error: {e}")
            return 0

    def get_blocks_from(self, from_index: int, limit: int = 50) -> List:
        try:
            res = (
                self._t("pw_blocks")
                .select("*")
                .gte("idx", from_index)
                .order("idx", desc=False)
                .limit(limit)
                .execute()
            )
            return [self._row_to_block(r) for r in (res.data or [])]
        except Exception as e:
            logger.error(f"get_blocks_from error: {e}")
            return []

    def _row_to_block(self, row: Dict):
        from playweb.core.block       import Block
        from playweb.core.transaction import Transaction

        txs_data = row.get("transactions", [])
        if isinstance(txs_data, str):
            txs_data = json.loads(txs_data)

        txs   = [Transaction.from_dict(t) for t in txs_data]
        votes = row.get("votes", [])
        if isinstance(votes, str):
            votes = json.loads(votes)

        block = Block(
            index            = row["idx"],
            transactions     = txs,
            previous_hash    = row["previous_hash"],
            validator_wallet = row["validator_wallet"],
            timestamp        = row["timestamp"],
            nonce            = row.get("nonce", 0),
            consensus_round  = row.get("consensus_round", 0),
            votes            = votes,
        )
        block.hash        = row["hash"]
        block.merkle_root = row["merkle_root"]
        return block

    # ─── Transactions ─────────────────────────────────────────────

    def save_transaction(self, tx) -> bool:
        try:
            self._t("pw_transactions").upsert({
                "hash": tx.hash,
                "data": tx.to_dict(),
            }).execute()
            return True
        except Exception as e:
            logger.error(f"save_transaction error: {e}")
            return False

    def get_transaction(self, tx_hash: str):
        try:
            res = (
                self._t("pw_transactions")
                .select("data")
                .eq("hash", tx_hash)
                .execute()
            )
            if not res.data:
                return None
            from playweb.core.transaction import Transaction
            data = res.data[0]["data"]
            if isinstance(data, str):
                data = json.loads(data)
            return Transaction.from_dict(data)
        except Exception as e:
            logger.error(f"get_transaction error: {e}")
            return None

    # ─── Balances ────────────────────────────────────────────────

    def get_balance(self, address: str) -> float:
        try:
            res = (
                self._t("pw_balances")
                .select("balance")
                .eq("address", address.lower())
                .execute()
            )
            return float(res.data[0]["balance"]) if res.data else 0.0
        except Exception as e:
            logger.error(f"get_balance error: {e}")
            return 0.0

    def save_balance(self, address: str, balance: float) -> bool:
        try:
            self._t("pw_balances").upsert({
                "address": address.lower(),
                "balance": max(0.0, balance),
                "updated": time.time(),
            }).execute()
            return True
        except Exception as e:
            logger.error(f"save_balance error: {e}")
            return False

    def get_all_addresses(self) -> List[str]:
        try:
            res = self._t("pw_balances").select("address").execute()
            return [r["address"] for r in (res.data or [])]
        except Exception as e:
            logger.error(f"get_all_addresses error: {e}")
            return []

    # ─── Content Registry ─────────────────────────────────────────

    def save_content_record(self, record: Dict) -> bool:
        try:
            extra = {k: v for k, v in record.items() if k not in (
                "cid", "creator_wallet", "first_owner", "current_owner",
                "first_platform", "first_tx_hash", "first_block",
                "timestamp", "total_editions", "royalty_pct"
            )}
            self._t("pw_content_registry").upsert({
                "cid":            record["cid"],
                "creator_wallet": record.get("creator_wallet"),
                "first_owner":    record.get("first_owner"),
                "current_owner":  record.get("current_owner", record.get("first_owner", "")).lower(),
                "first_platform": record.get("first_platform", "unknown"),
                "first_tx_hash":  record.get("first_tx_hash"),
                "first_block":    record.get("first_block"),
                "timestamp":      record.get("timestamp"),
                "total_editions": record.get("total_editions", 1),
                "royalty_pct":    record.get("royalty_pct", 0),
                "extra":          extra,
            }).execute()
            return True
        except Exception as e:
            logger.error(f"save_content_record error: {e}")
            return False

    def get_content_record(self, cid: str) -> Optional[Dict]:
        try:
            res = (
                self._t("pw_content_registry")
                .select("*")
                .eq("cid", cid)
                .execute()
            )
            if not res.data:
                return None
            record = res.data[0]
            extra  = record.pop("extra", {}) or {}
            if isinstance(extra, str):
                extra = json.loads(extra)
            record.update(extra)
            return record
        except Exception as e:
            logger.error(f"get_content_record error: {e}")
            return None

    def get_all_content_by_owner(self, address: str) -> List[Dict]:
        try:
            res = (
                self._t("pw_content_registry")
                .select("*")
                .eq("current_owner", address.lower())
                .execute()
            )
            return res.data or []
        except Exception as e:
            logger.error(f"get_all_content_by_owner error: {e}")
            return []
    
    def get_cid_by_int_id(self, int_id: int) -> Optional[str]:
        try:
            from playweb.api.erc721 import cid_to_int_id
            res = self._t("pw_content_registry").select("cid").execute()
            for r in (res.data or []):
                if cid_to_int_id(r["cid"]) == int_id:
                    return r["cid"]
            return None
        except Exception as e:
            logger.error(f"get_cid_by_int_id error: {e}")
            return None

    # ─── Edition Registry ─────────────────────────────────────────

    def save_edition_record(self, record: Dict) -> bool:
        try:
            self._t("pw_edition_registry").upsert({
                "cid":            record["cid"],
                "edition_number": record["edition_number"],
                "edition_of":     record.get("edition_of", 1),
                "current_owner":  record.get("current_owner", "").lower(),
                "platform":       record.get("platform", "unknown"),
                "tx_hash":        record.get("tx_hash"),
                "timestamp":      record.get("timestamp"),
                "provenance":     record.get("provenance", []),
            }).execute()
            return True
        except Exception as e:
            logger.error(f"save_edition_record error: {e}")
            return False

    def get_edition_record(self, cid: str, edition_number: int) -> Optional[Dict]:
        try:
            res = (
                self._t("pw_edition_registry")
                .select("*")
                .eq("cid", cid)
                .eq("edition_number", edition_number)
                .execute()
            )
            return res.data[0] if res.data else None
        except Exception as e:
            logger.error(f"get_edition_record error: {e}")
            return None

    def get_all_edition_records(self, cid: str) -> List[Dict]:
        try:
            res = (
                self._t("pw_edition_registry")
                .select("*")
                .eq("cid", cid)
                .order("edition_number")
                .execute()
            )
            return res.data or []
        except Exception as e:
            logger.error(f"get_all_edition_records error: {e}")
            return []
