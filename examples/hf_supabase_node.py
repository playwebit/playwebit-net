"""
PlayWebit Network — HuggingFace Node Example
Running a full validator node on HuggingFace Spaces with Supabase storage.

Set these environment variables in your HuggingFace Space secrets:
  NODE_WALLET_PRIVATE_KEY
  NODE_PUBLIC_URL              (your HF Space URL)
  SUPABASE_URL
  SUPABASE_ANON_KEY
  PLAYWEBIT_AUTHORITY_WALLET   (only needed first time)

Run the Supabase SQL schema from supabase_storage.py docstring first.
"""

import os
from dotenv import load_dotenv

load_dotenv()

from playweb import PlayWebitNode
from playweb.storage.supabase_storage import SupabaseStorage

# ── Storage ──────────────────────────────────────────────────────
storage = SupabaseStorage(
    url = os.environ["SUPABASE_URL"],
    key = os.environ["SUPABASE_ANON_KEY"],
)

# ── Node ─────────────────────────────────────────────────────────
node = PlayWebitNode(
    storage           = storage,
    node_wallet       = os.environ["NODE_WALLET_ADDRESS"],
    node_private_key  = os.environ["NODE_WALLET_PRIVATE_KEY"],
    node_public_url   = os.environ["NODE_PUBLIC_URL"],
    platform          = os.getenv("PLATFORM_ID", "unknown"),
    port              = int(os.getenv("NODE_PORT", 7860)),
)

# ── Optional: attach a L2 plugin ─────────────────────────────────
# from my_plugin import MyCipherVaultPlugin
# node.register_plugin(MyCipherVaultPlugin())

# ── Start (blocking) ─────────────────────────────────────────────
if __name__ == "__main__":
    node.start(blocking=True)
