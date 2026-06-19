"""
PlayWebit Network — L1 Configuration
All constants hardcoded here. Never in .env.
Node operators cannot override these — consensus enforces them.
"""

import os

# ─────────────────────────────────────────────
# NETWORK IDENTITY
# ─────────────────────────────────────────────

NETWORK_NAME  = "PlayWebit Network"
CHAIN_ID      = 4968
CURRENCY      = "PLWB"
DECIMALS      = 18

# ─────────────────────────────────────────────
# AUTHORITY WALLET
# Hardcoded — public and intentional.
# Every node enforces fees go here.
# Changing this = your blocks get rejected by network.
# ─────────────────────────────────────────────

AUTHORITY_WALLET = "0x101A249DE184ECdA4b9D3B2c8844eaB8102bB378"

# ─────────────────────────────────────────────
# L1 FEES — enforced by consensus
# These are the ONLY fees L1 knows about.
# Platform fees (list, buy, delist etc) are L2 territory.
# ─────────────────────────────────────────────

TRANSACTION_FEE      = 1       # PLWB — every tx on the network
CV_LINK_FEE          = 5       # PLWB — linking a CID to the chain
PLWB_REDEMPTION_FEE  = 0.05   # 5%   — fee on PLWB redemption (100% authority)
PLWB_RATE_USD        = 0.10   # $0.10 per 1 PLWB
PLWB_MIN_PURCHASE    = 10     # minimum PLWB per purchase
PLWB_MIN_REDEMPTION  = 50     # minimum PLWB to redeem

# ─────────────────────────────────────────────
# FEE SPLIT — enforced by consensus
# Every node validates this on every block.
# Wrong split = block rejected.
# ─────────────────────────────────────────────

FEE_SPLIT_AUTHORITY  = 0.50   # 50% → AUTHORITY_WALLET
FEE_SPLIT_NODE       = 0.50   # 50% → node operator wallet

# Which fee tx_types get the 50/50 split
SPLITTABLE_FEE_TYPES = [
    "fee",        # base network tx fee (1 PLWB)
    "cv_link",    # CID link fee (5 PLWB)
]

# Which fee tx_types go 100% to authority
AUTHORITY_ONLY_FEE_TYPES = [
    "plwb_redeem",   # redemption fee
]

# ─────────────────────────────────────────────
# TRANSACTION TYPES — L1 knows only these
# Everything else is L2 / plugin territory.
# ─────────────────────────────────────────────

L1_TX_TYPES = [
    "transfer",            # PLWB transfer between wallets
    "fee",                 # network fee (auto-split 50/50)
    "cv_link",             # link CID to chain (content registration fee)
    "content_register",    # register CID ownership on chain
    "ownership_transfer",  # transfer CID ownership
    "edition_transfer",    # transfer specific edition
    "spider_hash_anchor",  # anchor a spider hash (L2 integrity proof)
    "plwb_redeem",         # user redeems PLWB for fiat
    "plwb_purchase",       # user purchases PLWB
    "genesis",             # chain genesis transaction
    "reward",              # block reward
    "node_register",       # node registers on chain
]

# These tx types skip signature verification (authority only)
AUTHORITY_TX_TYPES = [
    "genesis",
    "reward",
    "plwb_purchase",
    "plwb_redeem",
    "spider_hash_anchor",
]

# ─────────────────────────────────────────────
# CONSENSUS — NVF-BFT
# ─────────────────────────────────────────────

CONSENSUS_QUORUM       = 0.667   # 2/3 of active nodes must vote
BLOCK_TIME             = 30      # seconds between blocks
CONSENSUS_TIMEOUT      = 15      # seconds before round times out
CONSENSUS_ROUND_PHASES = [
    "PROPOSE",   # leader broadcasts block candidate
    "PREPARE",   # peers verify + sign
    "VOTE",      # peers broadcast votes
    "COMMIT",    # 2/3 quorum reached → finalise
    "ANCHOR",    # write to storage
    "NOTIFY",    # notify plugins
]

# ─────────────────────────────────────────────
# BOOTSTRAP — Cloudflare Worker
# ─────────────────────────────────────────────

BOOTSTRAP_URL = os.getenv(
    "PLAYWEBIT_BOOTSTRAP_URL",
    "https://small-field-be1c.playwebit.workers.dev"
)

BOOTSTRAP_ENDPOINTS = {
    "nodes":       "/nodes",
    "register":    "/nodes/register",
    "heartbeat":   "/nodes/heartbeat",
    "deregister":  "/nodes/deregister",
    "health":      "/nodes/health",
}

# Fallback — your own permanent nodes
# Used if Cloudflare is unreachable
BOOTSTRAP_FALLBACK_NODES = [
    "https://node1.playwebit.com",
    "https://node2.playwebit.com",
]

BOOTSTRAP_HEARTBEAT_INTERVAL = 43200   # 12 hours in seconds
NODE_TTL                     = 86400   # 24 hours — auto-expire dead nodes

# ─────────────────────────────────────────────
# MINING
# ─────────────────────────────────────────────

MINING_MODE       = "nvf_bft"
WRITE_DELAY       = 5   # seconds between storage writes (rate limiting)
BATCH_TIMEOUT      = 300  # 5 minutes — mine after this regardless
MAX_TX_PER_BLOCK   = 10

# ─────────────────────────────────────────────
# NETWORK / P2P
# ─────────────────────────────────────────────

# Default port nodes listen on for peer-to-peer communication
# Node operators can override via NODE_PORT env var
NODE_PORT         = int(os.getenv("NODE_PORT", 7860))

# How many peers to maintain connections with
MAX_PEERS         = 20
MIN_PEERS         = 3

# Gossip — how many peers to forward to
GOSSIP_FANOUT     = 5

# Sync chunk size when downloading chain
SYNC_CHUNK_SIZE   = 50   # blocks per request

# Peer timeout
PEER_TIMEOUT      = 10   # seconds

# ─────────────────────────────────────────────
# LOGGING
# ─────────────────────────────────────────────

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
DEBUG     = os.getenv("DEBUG", "False").lower() == "true"
