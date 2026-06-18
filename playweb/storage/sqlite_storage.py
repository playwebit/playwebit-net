"""
PlayWebit Network — SQLite Storage
Built into Python, no extra install needed.
Use for: VPS nodes, any server with persistent disk.
Fast reads/writes — standard blockchain approach.
"""

import json
import sqlite3
import logging
from typing import List, Optional, Dict
from contextlib import contextmanager

from playweb.storage.base import ChainStorage

logger = logging.getLogger(__name__)


class SQLiteStorage(ChainStorage):

    def __init__(self, db_path: str = "./chain.db"):
        self.db_path = db_path
        self._init_db()
        logger.info(f"SQLiteStorage initialised at {db_path}")

    @contextmanager
    def _conn(self):
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _init_db(self):
        with self._conn() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS blocks (
                    hash             TEXT PRIMARY KEY,
                    idx              INTEGER UNIQUE,
                    previous_hash    TEXT,
                    merkle_root      TEXT,
                    timestamp        REAL,
                    nonce            INTEGER,
                    validator_wallet TEXT,
                    consensus_round  INTEGER,
                    votes            TEXT,
                    transactions     TEXT
                );

                CREATE TABLE IF NOT EXISTS transactions (
                    hash        TEXT PRIMARY KEY,
                    block_hash  TEXT,
                    block_index INTEGER,
                    data        TEXT
                );

                CREATE TABLE IF NOT EXISTS balances (
                    address   TEXT PRIMARY KEY,
                    balance   REAL DEFAULT 0.0,
                    updated   REAL
                );

                CREATE TABLE IF NOT EXISTS content_registry (
                    cid              TEXT PRIMARY KEY,
                    creator_wallet   TEXT,
                    first_owner      TEXT,
                    current_owner    TEXT,
                    first_platform   TEXT,
                    first_tx_hash    TEXT,
                    first_block      INTEGER,
                    timestamp        REAL,
                    total_editions   INTEGER,
                    royalty_pct      REAL,
                    extra            TEXT
                );

                CREATE TABLE IF NOT EXISTS edition_registry (
                    cid             TEXT,
                    edition_number  INTEGER,
                    edition_of      INTEGER,
                    current_owner   TEXT,
                    platform        TEXT,
                    tx_hash         TEXT,
                    timestamp       REAL,
                    provenance      TEXT,
                    PRIMARY KEY (cid, edition_number)
                );

                CREATE INDEX IF NOT EXISTS idx_blocks_index
                    ON blocks(idx);
                CREATE INDEX IF NOT EXISTS idx_tx_block
                    ON transactions(block_hash);
                CREATE INDEX IF NOT EXISTS idx_editions_cid
                    ON edition_registry(cid);
            """)

    # ─── Blocks ──────────────────────────────────────────────────

    def save_block(self, block) -> bool:
        try:
            with self._conn() as conn:
                conn.execute("""
                    INSERT OR REPLACE INTO blocks
                    (hash, idx, previous_hash, merkle_root, timestamp,
                     nonce, validator_wallet, consensus_round, votes, transactions)
                    VALUES (?,?,?,?,?,?,?,?,?,?)
                """, (
                    block.hash,
                    block.index,
                    block.previous_hash,
                    block.merkle_root,
                    block.timestamp,
                    block.nonce,
                    block.validator_wallet,
                    block.consensus_round,
                    json.dumps(block.votes),
                    json.dumps([tx.to_dict() for tx in block.transactions]),
                ))
            return True
        except Exception as e:
            logger.error(f"save_block error: {e}")
            return False

    def get_block(self, block_hash: str):
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM blocks WHERE hash = ?", (block_hash,)
            ).fetchone()
        return self._row_to_block(row) if row else None

    def get_block_by_index(self, index: int):
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM blocks WHERE idx = ?", (index,)
            ).fetchone()
        return self._row_to_block(row) if row else None

    def get_chain_tip(self):
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM blocks ORDER BY idx DESC LIMIT 1"
            ).fetchone()
        return self._row_to_block(row) if row else None

    def get_chain_length(self) -> int:
        with self._conn() as conn:
            row = conn.execute("SELECT COUNT(*) as cnt FROM blocks").fetchone()
        return row["cnt"] if row else 0

    def get_blocks_from(self, from_index: int, limit: int = 50) -> List:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM blocks WHERE idx >= ? ORDER BY idx ASC LIMIT ?",
                (from_index, limit)
            ).fetchall()
        return [self._row_to_block(r) for r in rows if r]

    def _row_to_block(self, row):
        from playweb.core.block import Block
        txs_data = json.loads(row["transactions"])
        from playweb.core.transaction import Transaction
        txs   = [Transaction.from_dict(t) for t in txs_data]
        block = Block(
            index            = row["idx"],
            transactions     = txs,
            previous_hash    = row["previous_hash"],
            validator_wallet = row["validator_wallet"],
            timestamp        = row["timestamp"],
            nonce            = row["nonce"],
            consensus_round  = row["consensus_round"],
            votes            = json.loads(row["votes"] or "[]"),
        )
        block.hash        = row["hash"]
        block.merkle_root = row["merkle_root"]
        return block

    # ─── Transactions ─────────────────────────────────────────────

    def save_transaction(self, tx) -> bool:
        try:
            with self._conn() as conn:
                conn.execute("""
                    INSERT OR REPLACE INTO transactions (hash, data)
                    VALUES (?, ?)
                """, (tx.hash, json.dumps(tx.to_dict())))
            return True
        except Exception as e:
            logger.error(f"save_transaction error: {e}")
            return False

    def get_transaction(self, tx_hash: str):
        with self._conn() as conn:
            row = conn.execute(
                "SELECT data FROM transactions WHERE hash = ?", (tx_hash,)
            ).fetchone()
        if not row:
            return None
        from playweb.core.transaction import Transaction
        return Transaction.from_dict(json.loads(row["data"]))

    # ─── Balances ────────────────────────────────────────────────

    def get_balance(self, address: str) -> float:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT balance FROM balances WHERE address = ?",
                (address.lower(),)
            ).fetchone()
        return float(row["balance"]) if row else 0.0

    def save_balance(self, address: str, balance: float) -> bool:
        import time
        try:
            with self._conn() as conn:
                conn.execute("""
                    INSERT INTO balances (address, balance, updated)
                    VALUES (?, ?, ?)
                    ON CONFLICT(address) DO UPDATE SET
                        balance = excluded.balance,
                        updated = excluded.updated
                """, (address.lower(), max(0.0, balance), time.time()))
            return True
        except Exception as e:
            logger.error(f"save_balance error: {e}")
            return False

    def get_all_addresses(self) -> List[str]:
        with self._conn() as conn:
            rows = conn.execute("SELECT address FROM balances").fetchall()
        return [r["address"] for r in rows]

    # ─── Content Registry ─────────────────────────────────────────

    def save_content_record(self, record: Dict) -> bool:
        try:
            extra = {k: v for k, v in record.items() if k not in (
                "cid", "creator_wallet", "first_owner", "current_owner",
                "first_platform", "first_tx_hash", "first_block",
                "timestamp", "total_editions", "royalty_pct"
            )}
            with self._conn() as conn:
                conn.execute("""
                    INSERT INTO content_registry
                    (cid, creator_wallet, first_owner, current_owner,
                     first_platform, first_tx_hash, first_block,
                     timestamp, total_editions, royalty_pct, extra)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?)
                    ON CONFLICT(cid) DO UPDATE SET
                        current_owner = excluded.current_owner,
                        extra         = excluded.extra
                """, (
                    record["cid"],
                    record.get("creator_wallet"),
                    record.get("first_owner"),
                    record.get("current_owner", record.get("first_owner")),
                    record.get("first_platform", "unknown"),
                    record.get("first_tx_hash"),
                    record.get("first_block"),
                    record.get("timestamp"),
                    record.get("total_editions", 1),
                    record.get("royalty_pct", 0),
                    json.dumps(extra),
                ))
            return True
        except Exception as e:
            logger.error(f"save_content_record error: {e}")
            return False

    def get_content_record(self, cid: str) -> Optional[Dict]:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM content_registry WHERE cid = ?", (cid,)
            ).fetchone()
        if not row:
            return None
        record = dict(row)
        if record.get("extra"):
            record.update(json.loads(record.pop("extra")))
        return record

    # ─── Edition Registry ─────────────────────────────────────────

    def save_edition_record(self, record: Dict) -> bool:
        try:
            with self._conn() as conn:
                conn.execute("""
                    INSERT INTO edition_registry
                    (cid, edition_number, edition_of, current_owner,
                     platform, tx_hash, timestamp, provenance)
                    VALUES (?,?,?,?,?,?,?,?)
                    ON CONFLICT(cid, edition_number) DO UPDATE SET
                        current_owner = excluded.current_owner,
                        platform      = excluded.platform,
                        tx_hash       = excluded.tx_hash,
                        timestamp     = excluded.timestamp,
                        provenance    = excluded.provenance
                """, (
                    record["cid"],
                    record["edition_number"],
                    record.get("edition_of", 1),
                    record.get("current_owner"),
                    record.get("platform", "unknown"),
                    record.get("tx_hash"),
                    record.get("timestamp"),
                    json.dumps(record.get("provenance", [])),
                ))
            return True
        except Exception as e:
            logger.error(f"save_edition_record error: {e}")
            return False

    def get_edition_record(self, cid: str, edition_number: int) -> Optional[Dict]:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM edition_registry WHERE cid=? AND edition_number=?",
                (cid, edition_number)
            ).fetchone()
        if not row:
            return None
        record = dict(row)
        record["provenance"] = json.loads(record.get("provenance") or "[]")
        return record

    def get_all_edition_records(self, cid: str) -> List[Dict]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM edition_registry WHERE cid=? ORDER BY edition_number",
                (cid,)
            ).fetchall()
        records = []
        for row in rows:
            r = dict(row)
            r["provenance"] = json.loads(r.get("provenance") or "[]")
            records.append(r)
        return records
