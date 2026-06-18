"""
PlayWebit Network — VPS / AWS Node Example
Running a validator node on any server with persistent disk.
Uses SQLite — no extra database needed.

Set these environment variables:
  NODE_WALLET_PRIVATE_KEY
  NODE_PUBLIC_URL
"""

import os
from dotenv import load_dotenv

load_dotenv()

from playweb import PlayWebitNode
from playweb.storage.sqlite_storage import SQLiteStorage

# ── Storage (persistent, local) ───────────────────────────────────
storage = SQLiteStorage(
    db_path = os.getenv("SQLITE_DB_PATH", "./chain.db")
)

# ── Node ─────────────────────────────────────────────────────────
node = PlayWebitNode(
    storage          = storage,
    node_wallet      = os.environ["NODE_WALLET_ADDRESS"],
    node_private_key = os.environ["NODE_WALLET_PRIVATE_KEY"],
    node_public_url  = os.environ["NODE_PUBLIC_URL"],
    platform         = os.getenv("PLATFORM_ID", "unknown"),
    port             = int(os.getenv("NODE_PORT", 7860)),
)

if __name__ == "__main__":
    node.start(blocking=True)
