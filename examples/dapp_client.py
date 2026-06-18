"""
PlayWebit Network — dApp Client Example
How a dApp connects to the network WITHOUT running a full node.
Just point at any validator node and call the SDK.

This is what CipherVault's app.py should look like after refactoring.
"""

import os
from dotenv import load_dotenv

load_dotenv()

from playweb import PlayWebitClient

# Connect to a validator node (your own or any trusted node)
client = PlayWebitClient(
    validator_url   = os.getenv("VALIDATOR_URL", "https://node1.playwebit.com"),
    platform_wallet = os.environ["PLATFORM_WALLET"],
)

# ── Check network health ──────────────────────────────────────────
print("Network health:", client.health_check())
print("Network stats:",  client.get_network_stats())

# ── Check if content is already registered ────────────────────────
cid    = "QmXyz123abc..."   # IPFS CID of the file
result = client.check_duplicate(cid)

if result["exists"]:
    print(f"Content already registered!")
    print(f"  First owner:    {result['first_owner']}")
    print(f"  First platform: {result['first_platform']}")
    print(f"  First seen:     {result['first_seen_human']}")
else:
    print("Content is new — registering...")

    # ── Register content ──────────────────────────────────────────
    success, reason, tx_hash = client.register_content(
        cid         = cid,
        owner       = "0xOwnerWalletAddress",
        editions    = 100,
        royalty_pct = 10,           # 10% royalty on every resale
        signature   = "0x...",      # MetaMask signature from user
        platform_id = "ciphervault",
    )

    if success:
        print(f"Registered! tx_hash: {tx_hash}")
    else:
        print(f"Failed: {reason}")

# ── Get owner ─────────────────────────────────────────────────────
owner_info = client.get_owner(cid)
if owner_info:
    print(f"Current owner: {owner_info['current_owner']}")
    print(f"Royalty: {owner_info['royalty_pct']}%")

# ── Get all editions across all platforms ─────────────────────────
editions = client.get_editions(cid)
print(f"Total editions: {editions.get('total_editions')}")
print(f"Editions found: {editions.get('editions_found')}")

# ── Anchor a SpiderWeave hash ────────────────────────────────────
# (spiderweave-sdk calls this internally via PlayWebitAdapter)
success, tx_hash = client.anchor_spider_hash(
    chain_name   = "ciphervault_vault_nfts",
    spider_hash  = "abc123def456...",
    event_type   = "file_linked",
    signature    = "0x...",
)
print(f"Hash anchored: {tx_hash}")

# ── Verify ownership ─────────────────────────────────────────────
owns = client.verify_ownership(cid, "0xOwnerWalletAddress")
print(f"Ownership verified: {owns}")

# ── Pay PLWB ─────────────────────────────────────────────────────
success, reason, tx_hash = client.pay(
    from_addr = "0xBuyerWallet",
    to_addr   = "0xSellerWallet",
    amount    = 50.0,
    signature = "0x...",
)
print(f"Payment: {success} — {reason}")
