# PlayWebit Network — `playwebit-net`

> Public blockchain infrastructure for cross-platform digital ownership, royalty enforcement, and content integrity verification.

**Chain ID:** 4968 | **Currency:** PLWB | **Consensus:** NVF-BFT | **License:** MIT

---

## What is PlayWebit Network?

PlayWebit Network is a public, permissionless blockchain where:

- **Any node** that joins automatically becomes a validator
- **Any platform** (marketplace, creator app, music platform) can register content and verify ownership
- **No platform can duplicate content** registered by another — cross-platform duplicate detection is enforced at the protocol level using IPFS-compatible CIDs
- **Royalties are enforced by L1** — creators set their percentage at mint time and receive it on every resale, on every platform, forever
- **Platforms pay in USD** — their users never need to hold PLWB directly; platforms maintain a PLWB treasury and pay network fees on behalf of their users
- **Node operators earn 50%** of every network fee processed through their node

---

## Architecture

```
┌─────────────────────────────────────────────────────┐
│  Layer 2 — Platform Apps (anyone builds these)       │
│                                                      │
│  CipherVault      MusicApp      ArtApp      ...      │
│  (NFT vault)   (song licenses) (editions)            │
│       │               │              │               │
│       └───────────────┴──────────────┘               │
│                  spiderweave-sdk                      │
│         (DB integrity hashes → L1 anchor)            │
└──────────────────────┬──────────────────────────────┘
                       │  playweb-node SDK
                       │  register_content(), transfer_ownership(),
                       │  anchor_spider_hash(), get_balance() ...
┌──────────────────────▼──────────────────────────────┐
│  Layer 1 — PlayWebit Network (this repo)             │
│                                                      │
│  ✓ Block / Transaction / Merkle                      │
│  ✓ NVF-BFT Consensus (2/3 quorum)                    │
│  ✓ PLWB native token                                 │
│  ✓ Content Registry (cross-platform CID ownership)   │
│  ✓ Edition Registry (cross-platform edition tracking)│
│  ✓ Royalty enforcement (creator % on every resale)   │
│  ✓ Fee split (50% authority / 50% node operator)     │
│  ✓ Bootstrap via Cloudflare Worker                   │
│  ✓ P2P gossip (HTTP webhooks — works everywhere)     │
│  ✓ Storage abstraction (Supabase / SQLite / LevelDB) │
└──────────────────────┬──────────────────────────────┘
                       │  Supabase (Layer 0 — permanent anchor)
```

---

## Key Features

### Cross-Platform Duplicate Detection
Any file registered on one platform cannot be registered again on any other platform. Uses IPFS-compatible CIDs — if your platform uses IPFS, duplicate detection works automatically with zero extra configuration.

### Royalty Enforcement
Creators set their royalty percentage (0–100%) at registration time. Every resale on any platform — regardless of which platform processes the transaction — pays the creator their cut. Platforms cannot bypass this. Consensus rejects blocks that violate it.

### Storage Agnostic
Run a node with whatever storage fits your infrastructure:
- **Supabase** — for HuggingFace Spaces or any platform without persistent disk
- **SQLite** — for VPS/AWS, built into Python, no extra setup
- **LevelDB** — fastest option for dedicated validator nodes
- **RAM** — for testing and development

### Works Everywhere
HTTP-based P2P gossip means the network works on HuggingFace, AWS, DigitalOcean, Render, Railway — any platform that can receive HTTP requests. No WebSocket requirement, no persistent connections.

### Fee Economics
```
Every network transaction pays 1 PLWB
  → 0.5 PLWB to PlayWebit authority (hardcoded)
  → 0.5 PLWB to node operator (incentive to run nodes)

CID link fee: 5 PLWB (same split)
Redemption fee: 5% of amount (100% to authority)
Royalty: X% of sale (100% to original creator)
```

---

## Installation

```bash
pip install playweb-node

# With Supabase storage (HuggingFace nodes)
pip install "playweb-node[supabase]"

# With LevelDB storage (VPS nodes)
pip install "playweb-node[leveldb]"

# With signature verification (recommended for production)
pip install "playweb-node[eth]"

# Everything
pip install "playweb-node[all]"
```

---

## Quick Start

### Run a full validator node (HuggingFace + Supabase)

```python
import os
from playweb import PlayWebitNode
from playweb.storage.supabase_storage import SupabaseStorage

storage = SupabaseStorage(
    url = os.environ["SUPABASE_URL"],
    key = os.environ["SUPABASE_ANON_KEY"],
)

node = PlayWebitNode(
    storage          = storage,
    node_wallet      = os.environ["NODE_WALLET_ADDRESS"],
    node_private_key = os.environ["NODE_WALLET_PRIVATE_KEY"],
    node_public_url  = os.environ["NODE_PUBLIC_URL"],
    platform         = "my_platform",
)

node.start()  # blocking — discovers peers, syncs chain, joins consensus
```

### Run a full validator node (VPS + SQLite)

```python
from playweb import PlayWebitNode
from playweb.storage.sqlite_storage import SQLiteStorage

node = PlayWebitNode(
    storage          = SQLiteStorage("./chain.db"),
    node_wallet      = os.environ["NODE_WALLET_ADDRESS"],
    node_private_key = os.environ["NODE_WALLET_PRIVATE_KEY"],
    node_public_url  = "https://your-vps.com",
)

node.start()
```

### Connect as a lightweight client (no local chain)

```python
from playweb import PlayWebitClient

client = PlayWebitClient(
    validator_url   = "https://node1.playwebit.com",
    platform_wallet = os.environ["PLATFORM_WALLET"],
)

# Check if content is already registered anywhere on the network
result = client.check_duplicate("QmYourIPFSCID...")
if result["exists"]:
    print(f"Already owned by {result['first_owner']} on {result['first_platform']}")
else:
    # Register it
    success, reason, tx_hash = client.register_content(
        cid         = "QmYourIPFSCID...",
        owner       = "0xOwnerWallet",
        editions    = 100,
        royalty_pct = 10,       # 10% royalty on every resale, forever
        signature   = "0x...",  # MetaMask signature
    )
```

---

## Environment Variables

Copy `.env.example` to `.env` and fill in your values.

| Variable | Required | Description |
|---|---|---|
| `NODE_WALLET_PRIVATE_KEY` | ✓ | Node's wallet private key (MetaMask export) |
| `NODE_PUBLIC_URL` | ✓ | Public URL of this node (reachable by peers) |
| `NODE_WALLET_ADDRESS` | ✓ | Node's wallet address |
| `SUPABASE_URL` | If using Supabase | Your Supabase project URL |
| `SUPABASE_ANON_KEY` | If using Supabase | Your Supabase anon key |
| `NODE_PORT` | No (default: 7860) | Port to run the API on |
| `PLATFORM_ID` | No | Name of your platform/dApp |
| `LOG_LEVEL` | No (default: INFO) | Logging level |

> **Note:** `AUTHORITY_WALLET`, `BOOTSTRAP_URL`, `CHAIN_ID`, `TRANSACTION_FEE`, and `FEE_SPLIT` are hardcoded in `playweb/config.py`. They are **not** configurable by node operators — consensus enforces them network-wide.

---

## Building a L2 Plugin

Any platform can plug into a PlayWebit node by implementing `BasePlugin`:

```python
from playweb.plugin.base_plugin import BasePlugin

class MyPlatformPlugin(BasePlugin):
    plugin_id       = "myplatform"
    plugin_name     = "My Platform"
    plugin_version  = "1.0.0"
    platform_wallet = "0xMyPlatformWallet"

    def on_block_finalised(self, block):
        # Called after every confirmed block
        # Update your platform's own state here
        for tx in block.transactions:
            if tx.data and tx.data.get("platform_id") == "myplatform":
                self.handle_my_tx(tx)

    def on_content_registered(self, cid, owner, platform):
        # New content registered on the network
        pass

    def link_file(self, cid, owner, royalty_pct, signature):
        # Call L1 via inherited SDK methods
        return self.register_content(
            cid         = cid,
            owner_wallet = owner,
            royalty_pct = royalty_pct,
            signature   = signature,
        )

# Attach to node
node = PlayWebitNode(storage=..., ..., plugin=MyPlatformPlugin())
```

The plugin gets lifecycle hooks from L1 (`on_block_finalised`, `on_transaction`, `on_content_registered`, `on_edition_transferred`) and a clean SDK interface to submit transactions, verify ownership, anchor hashes, and check balances — without touching L1 internals.

---

## Public API Endpoints

Every node exposes these endpoints. The `spiderweave-sdk` `PlayWebitAdapter` calls them automatically.

### Public (for dApps and platforms)

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/transaction` | Submit a signed transaction |
| `POST` | `/api/anchor_spider_hash` | Anchor a SpiderWeave integrity hash |
| `GET` | `/api/transaction/:hash` | Get transaction by hash |
| `GET` | `/api/spider_hashes/:chain_name` | Get all anchored hashes for a chain |
| `GET` | `/api/balance/:address` | Get PLWB balance |
| `GET` | `/api/owner/:cid` | Get current owner of a CID |
| `GET` | `/api/check_duplicate/:cid` | Check if CID is registered anywhere |
| `POST` | `/api/verify_ownership` | Verify wallet owns a CID |
| `GET` | `/api/editions/:cid` | Get all editions across all platforms |
| `GET` | `/api/editions/:cid/:number` | Get a specific edition |
| `GET` | `/api/network/stats` | Network statistics |

### Peer-to-peer (node-to-node)

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/peer/new_transaction` | Receive transaction from peer |
| `POST` | `/peer/propose` | Receive block proposal (NVF-BFT PROPOSE) |
| `POST` | `/peer/vote` | Receive consensus vote (NVF-BFT VOTE) |
| `POST` | `/peer/new_block` | Receive finalised block |
| `POST` | `/peer/new_node` | New node joined network |
| `GET` | `/peer/chain_tip` | Get current chain tip |
| `GET` | `/peer/blocks/:from/:to` | Get block range (for sync) |
| `GET` | `/peer/peers` | Get peer list |
| `GET` | `/peer/health` | Node health check |

---

## NVF-BFT Consensus

Based on the NullVoid Framework paper. Each block goes through 6 phases:

```
PROPOSE  →  Leader broadcasts block candidate
            (NVF: Spacetime Fabric activation)

PREPARE  →  Peers verify block integrity + spider hash
            (NVF: Six Directional Progressions)

VOTE     →  Valid peers sign and broadcast their vote
            (NVF: Planck Threshold approach)

COMMIT   →  ≥ 2/3 of active nodes voted → block committed
            (NVF: False Vacuum → True Vacuum finality)

ANCHOR   →  Block written to node's storage permanently
            (NVF: Null Void Layer 0 anchoring)

NOTIFY   →  All plugins + peers notified of new block
            (NVF: Cyclic re-entry notification)
```

Leader rotates deterministically: `block_index % active_node_count`. Every node computes the same leader — no election messages needed.

Tolerates up to `f < n/3` faulty nodes (standard BFT guarantee).

---

## Bootstrap — How New Nodes Join

```
New node starts
    ↓
GET bootstrap.playwebit.com/nodes
    ↓  (Cloudflare Worker — always online)
Gets list of active peers
    ↓
POST bootstrap.playwebit.com/nodes/register
    ↓  (Cloudflare notifies all existing nodes about new node)
Connects directly to peers (P2P from here)
    ↓
Finds canonical chain tip (highest valid block)
    ↓
Downloads missing blocks from peers in chunks
    ↓
Verifies chain integrity locally
    ↓
Joins NVF-BFT consensus as a validator
    ↓
Sends heartbeat every 12h to stay listed
```

Cloudflare is only used for the initial peer discovery. After that, all communication is pure P2P between nodes. The network continues functioning even if Cloudflare is unreachable — nodes use hardcoded fallback nodes as a last resort.

---

## Supabase Schema

If using `SupabaseStorage`, run this SQL in your Supabase SQL editor:

```sql
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
    hash TEXT PRIMARY KEY,
    data JSONB
);

CREATE TABLE IF NOT EXISTS pw_balances (
    address TEXT PRIMARY KEY,
    balance FLOAT DEFAULT 0.0,
    updated FLOAT
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
```

---

## Repository Structure

```
playwebit-net/
├── playweb/
│   ├── config.py               # L1 constants (authority wallet, fees, chain ID)
│   ├── node.py                 # PlayWebitNode — full validator entry point
│   ├── client.py               # PlayWebitClient — lightweight dApp client
│   ├── core/
│   │   ├── transaction.py      # Transaction (mandatory + conditional + data{} fields)
│   │   ├── block.py            # Block + Merkle tree
│   │   ├── blockchain.py       # Blockchain (storage-agnostic)
│   │   ├── mempool.py          # Pending transaction pool (RAM)
│   │   ├── fee_engine.py       # 50/50 fee split enforcement
│   │   └── royalty_engine.py   # Creator royalty enforcement
│   ├── storage/
│   │   ├── base.py             # ChainStorage interface
│   │   ├── supabase_storage.py # Supabase adapter
│   │   ├── sqlite_storage.py   # SQLite adapter
│   │   └── ram_storage.py      # RAM adapter (testing)
│   ├── consensus/
│   │   ├── nvf_bft.py          # NVF-BFT consensus engine
│   │   ├── leader.py           # Rotating leader election
│   │   └── vote.py             # Vote message
│   ├── network/
│   │   ├── bootstrap.py        # Cloudflare peer discovery
│   │   ├── gossip.py           # P2P HTTP broadcast
│   │   ├── peer_manager.py     # Peer list management
│   │   └── sync.py             # Chain sync for new nodes
│   ├── registry/
│   │   ├── content_registry.py # Cross-platform CID ownership
│   │   └── edition_registry.py # Cross-platform edition tracking
│   ├── plugin/
│   │   ├── base_plugin.py      # L2 plugin interface
│   │   └── plugin_manager.py   # Plugin lifecycle manager
│   └── api/
│       ├── node_api.py         # Peer-to-peer HTTP endpoints
│       └── public_api.py       # dApp + spiderweave-sdk endpoints
├── examples/
│   ├── hf_supabase_node.py     # HuggingFace node setup
│   ├── vps_sqlite_node.py      # VPS/AWS node setup
│   ├── dapp_client.py          # Lightweight dApp usage
│   └── ciphervault_plugin_stub.py  # L2 plugin example
├── cloudflare_worker.js        # Bootstrap Worker (deploy to Cloudflare)
├── requirements.txt
├── setup.py
├── .env.example
└── .gitignore
```

---

## Transaction Types

L1 understands only these transaction types. Everything else is L2 territory stored in the optional `data: {}` field.

| Type | Description | Fee |
|---|---|---|
| `transfer` | PLWB transfer between wallets | 1 PLWB (split) |
| `fee` | Network fee transaction (auto-created) | — |
| `content_register` | Register CID ownership on chain | 5 PLWB cv_link (split) |
| `ownership_transfer` | Transfer CID to new owner | 1 PLWB (split) |
| `edition_transfer` | Transfer specific edition | 1 PLWB (split) |
| `spider_hash_anchor` | Anchor a SpiderWeave integrity hash | 1 PLWB (split) |
| `plwb_redeem` | User redeems PLWB for fiat | 5% of amount (authority) |
| `plwb_purchase` | User purchases PLWB | — |
| `genesis` | Chain genesis | — |
| `reward` | Block reward | — |
| `node_register` | Node registers on chain | — |

Every transaction has a mandatory `data: {}` field where platforms store anything they need (license type, song title, platform ID, custom metadata). L1 carries this data on chain without interpreting it.

---

## Related Repositories

| Repo | Description |
|---|---|
| [`playwebit/spiderweave-sdk`](https://github.com/playwebit/spiderweave-sdk) | Cross-table hash architecture for tamper-proof DB integrity. Anchors hashes on PlayWebit Network. |
| [`playwebit/cloudflare-bootstrap`](https://github.com/playwebit/cloudflare-bootstrap) | Cloudflare Worker for bootstrap peer discovery. |

---

## Security Model

**Fee manipulation is impossible** — every honest node validates the 50/50 split on every block. A modified node that routes fees to a different wallet produces blocks that get rejected by the network. Honest nodes earn by being honest; cheating earns nothing.

**Content theft is impossible** — once a CID is registered, no other platform on the network can register the same CID. This is enforced at the protocol level, not at the application level.

**Royalty bypass is impossible** — royalty percentage is stored on-chain at mint time. Every resale transaction is validated by all nodes. A block missing the royalty payment is rejected by consensus.

**Node identity is wallet-based** — each node signs all messages with its wallet private key. Node operators earn 50% of fees through their registered wallet. Fake node identities can join the network but they cannot produce valid blocks or earn fees.

---

## License

MIT — see [LICENSE](LICENSE)

---

*Built by [PlayWebIT](https://github.com/playwebit)*
