# PlayWebit Network — `playwebit-net`

> Public blockchain infrastructure for cross-platform digital ownership, royalty enforcement, and content integrity verification.

**Chain ID:** 4968 | **Currency:** PLWB | **Consensus:** NVF-BFT | **License:** Apache 2.0

---

## What is PlayWebit Network?

PlayWebit Network is a public, permissionless blockchain where any platform — marketplace, creator app, music platform, or content service — can register digital content, verify ownership, and enforce royalties across the entire network.

**Key properties:**

- **Any node that joins is automatically a validator** — no permission needed
- **Content registered on one platform cannot be duplicated on another** — enforced at protocol level using IPFS-compatible CIDs
- **Royalties enforced by L1** — creators set percentage at mint time, received on every resale, on every platform, forever
- **Node operators earn 50% of every network fee** they process
- **Platforms choose how users pay** — Model A (PLWB directly) or Model B (USD, platform handles crypto)
- **Storage agnostic** — Supabase, SQLite, LevelDB, or RAM — runs anywhere

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│  Layer 2 — Platform Apps (anyone builds these)           │
│                                                          │
│  CipherVault      MusicApp      ArtApp      ...          │
│                                                          │
│  Model A: users pay in PLWB directly                     │
│  Model B: users pay in USD, platform pays PLWB fees      │
│                                                          │
│              spiderweave-sdk (optional)                  │
│         (DB integrity hashes → L1 anchor)                │
└──────────────────────┬──────────────────────────────────┘
                       │  playweb-node SDK
┌──────────────────────▼──────────────────────────────────┐
│  Layer 1 — PlayWebit Network (this repo)                 │
│                                                          │
│  ✓ Block / Transaction / Merkle                          │
│  ✓ NVF-BFT Consensus (2/3 quorum, batch mining)         │
│  ✓ PLWB native token                                     │
│  ✓ Content Registry (cross-platform CID ownership)       │
│  ✓ Edition Registry (cross-platform edition tracking)    │
│  ✓ Royalty enforcement (creator % on every resale)       │
│  ✓ Fee split (50% authority / 50% node operator)         │
│  ✓ Bootstrap via Cloudflare Worker                       │
│  ✓ P2P gossip (HTTP webhooks — works everywhere)         │
│  ✓ Storage abstraction (Supabase / SQLite / LevelDB)     │
└─────────────────────────────────────────────────────────┘
```

---

## Payment Models

### Model A — PLWB Native
Users hold PLWB in their own MetaMask wallet and pay all fees directly.

```
User pays in PLWB:
  → content price to seller
  → royalty to creator (L1 enforced automatically)
  → network fee 1 PLWB (50/50 split)
  → CID link fee 5 PLWB (50/50 split)

Platform receives their charges in PLWB
Platform sets their own fees (L2 — their business)
```

### Model B — USD Native
Users pay in fiat. Platform manages all crypto behind the scenes.

```
User pays in USD:
  → never sees PLWB or MetaMask
  → owns content on-chain via custodial wallet

Platform pays from PLWB treasury:
  → network fee 1 PLWB (50/50 split)
  → CID link fee 5 PLWB (50/50 split)
  → everything else handled in USD — platform's business

PlayWebit gets: network fees only (50% split)
Platform gets:  all their USD charges directly
```

#### Model B — Wallet Options

| Option | Description |
|---|---|
| B | Pure custodial — platform holds key, user never knows wallet exists |
| C | Custodial with export — user can claim wallet anytime, import to MetaMask |

#### Model B — Royalty Options

| Option | How | On-Chain? |
|---|---|---|
| 1 | Platform pays creator in USD (trust-based) | No |
| 2 | Record on chain, pay USD separately | Partial |
| 3 | Convert royalty to PLWB, pay on chain | Yes ✓ (recommended) |

---

## Licence — Platform or Chain?

**Chain (universal, permanent):**
- Who owns which edition (source of truth)
- Full provenance / ownership history
- Royalty enforcement
- Duplicate detection globally
- Optional: licence terms in `data{}` field

**Platform (their business rules):**
- Licence type (personal / commercial / etc)
- Access control, downloads, expiry
- Licence certificate generation

```
Chain  = proof of OWNERSHIP (who owns it)
Platform = proof of RIGHTS (what they can do with it)
Both needed for full verification
```

---

## Fee Structure

| Fee | Amount | Split |
|---|---|---|
| Network fee | 1 PLWB per tx | 50% authority / 50% node |
| CID link fee | 5 PLWB per registration | 50% authority / 50% node |
| Redemption fee | 5% of amount | 100% authority |
| Royalty | Creator's % | 100% original creator |

Platform fees (listing, buying, cuts etc) — entirely platform's decision, go to platform wallet, PlayWebit has no involvement.

---

## Joining the Network

1. Visit PlayWebit Portal → register your platform
2. Connect MetaMask → verify treasury wallet
3. Get approved → API key + node registered on chain
4. Buy PLWB → fund treasury for network fees
5. Install SDK
6. Run your node → joins automatically, starts earning fees
7. Build your dApp using `PlayWebitClient`

---

## Installation

```bash
pip install git+https://github.com/playwebit/playwebit-net.git

# With Supabase (HuggingFace / no persistent disk)
pip install "playweb-node[supabase]"

# With LevelDB (VPS / AWS — fastest)
pip install "playweb-node[leveldb]"

# With signature verification (production)
pip install "playweb-node[eth]"

# Everything
pip install "playweb-node[all]"
```

---

## Quick Start

```python
# Full validator node (HuggingFace + Supabase)
from playweb import PlayWebitNode
from playweb.storage.supabase_storage import SupabaseStorage

node = PlayWebitNode(
    storage          = SupabaseStorage(url=..., key=...),
    node_wallet      = os.environ["NODE_WALLET_ADDRESS"],
    node_private_key = os.environ["NODE_WALLET_PRIVATE_KEY"],
    node_public_url  = os.environ["NODE_PUBLIC_URL"],
    platform         = "my_platform",
)
node.start()
```

```python
# Lightweight client (no local chain)
from playweb import PlayWebitClient

client = PlayWebitClient(
    validator_url   = "https://node1.playwebit.com",
    platform_wallet = os.environ["PLATFORM_WALLET"],
)

# Check duplicate across ALL platforms on the network
dup = client.check_duplicate("QmYourIPFSCID...")
if dup["exists"]:
    print(f"Already owned by {dup['first_owner']} on {dup['first_platform']}")
else:
    success, reason, tx_hash = client.register_content(
        cid         = "QmYourIPFSCID...",
        owner       = "0xOwnerWallet",
        editions    = 100,
        royalty_pct = 10,
        signature   = "0x...",
    )
```

---

## Environment Variables

Node operators only set these:

| Variable | Required | Description |
|---|---|---|
| `NODE_WALLET_PRIVATE_KEY` | ✓ | Node wallet private key |
| `NODE_WALLET_ADDRESS` | ✓ | Node wallet address |
| `NODE_PUBLIC_URL` | ✓ | Public URL reachable by other nodes |
| `SUPABASE_URL` | If using Supabase | Supabase project URL |
| `SUPABASE_ANON_KEY` | If using Supabase | Supabase anon key |
| `NODE_PORT` | No (default 7860) | API port |
| `PLATFORM_ID` | No | Your platform name |

Never set — hardcoded in SDK, enforced by consensus:
- `AUTHORITY_WALLET` → PlayWebIT wallet, 50% of all fees
- `BOOTSTRAP_URL` → `https://small-field-be1c.playwebit.workers.dev`
- `CHAIN_ID` → 4968
- `TRANSACTION_FEE` → 1 PLWB
- `CV_LINK_FEE` → 5 PLWB
- `FEE_SPLIT` → 50/50

---

## NVF-BFT Consensus + Batch Mining

Based on the NullVoid Framework paper.

```
Transaction arrives → added to mempool → batch timer starts
  ↓
  IF 10 transactions reached → mine immediately
  IF 5 minutes pass          → mine whatever is pending
  IF mempool empty           → no block, timer resets
  ↓
PROPOSE → PREPARE → VOTE → COMMIT → ANCHOR → NOTIFY
```

**Single node rules:**
- Authority node alone → can mine (bootstrapping phase)
- Non-authority node alone → must wait for peers (security)
- Multiple nodes → standard 2/3 quorum

---

## SpiderWeave (Optional)

[spiderweave-sdk](https://github.com/playwebit/spiderweave-sdk) is a separate optional tool for database integrity. Platforms install it independently if they want tamper-proof DB records anchored on chain.

Not required. Each platform configures their own hash strategy independently.

---

## Public API

### dApps and platforms

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/transaction` | Submit signed transaction |
| `POST` | `/api/anchor_spider_hash` | Anchor hash (no signature needed) |
| `GET` | `/api/transaction/:hash` | Get transaction |
| `GET` | `/api/spider_hashes/:chain_name` | Anchored hashes (confirmed + pending) |
| `GET` | `/api/balance/:address` | PLWB balance |
| `GET` | `/api/owner/:cid` | Current owner of CID |
| `GET` | `/api/check_duplicate/:cid` | Is CID registered anywhere? |
| `POST` | `/api/verify_ownership` | Verify wallet owns CID |
| `GET` | `/api/editions/:cid` | All editions across all platforms |
| `GET` | `/api/network/stats` | Network statistics |

### Peer-to-peer

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/peer/new_transaction` | Receive tx from peer |
| `POST` | `/peer/propose` | Block proposal |
| `POST` | `/peer/vote` | Consensus vote |
| `POST` | `/peer/new_block` | Finalised block |
| `POST` | `/peer/new_node` | New node joined |
| `GET` | `/peer/chain_tip` | Current chain tip |
| `GET` | `/peer/blocks/:from/:to` | Block range for sync |
| `GET` | `/peer/peers` | Peer list |
| `GET` | `/peer/health` | Health check |

---

## Transaction Types

| Type | Fee | Signature |
|---|---|---|
| `transfer` | 1 PLWB split | Required |
| `content_register` | 5 PLWB split | Required |
| `ownership_transfer` | 1 PLWB split | Required |
| `edition_transfer` | 1 PLWB split | Required |
| `spider_hash_anchor` | None | Not required |
| `plwb_redeem` | 5% authority | Not required |
| `plwb_purchase` | None | Not required |
| `node_register` | None | Not required |
| `genesis` / `reward` | None | Not required |

Every transaction has a free `data: {}` field — platforms store anything (licence type, platform ID, metadata). L1 carries it permanently without interpreting it.

---

## Supabase Schema

```sql
CREATE TABLE IF NOT EXISTS pw_blocks (
    hash TEXT PRIMARY KEY, idx INTEGER UNIQUE,
    previous_hash TEXT, merkle_root TEXT, timestamp FLOAT,
    nonce INTEGER DEFAULT 0, validator_wallet TEXT,
    consensus_round INTEGER DEFAULT 0,
    votes JSONB DEFAULT '[]', transactions JSONB DEFAULT '[]'
);
CREATE TABLE IF NOT EXISTS pw_transactions (hash TEXT PRIMARY KEY, data JSONB);
CREATE TABLE IF NOT EXISTS pw_balances (address TEXT PRIMARY KEY, balance FLOAT DEFAULT 0.0, updated FLOAT);
CREATE TABLE IF NOT EXISTS pw_content_registry (
    cid TEXT PRIMARY KEY, creator_wallet TEXT, first_owner TEXT,
    current_owner TEXT, first_platform TEXT, first_tx_hash TEXT,
    first_block INTEGER, timestamp FLOAT, total_editions INTEGER DEFAULT 1,
    royalty_pct FLOAT DEFAULT 0, extra JSONB DEFAULT '{}'
);
CREATE TABLE IF NOT EXISTS pw_edition_registry (
    cid TEXT, edition_number INTEGER, edition_of INTEGER DEFAULT 1,
    current_owner TEXT, platform TEXT, tx_hash TEXT, timestamp FLOAT,
    provenance JSONB DEFAULT '[]', PRIMARY KEY (cid, edition_number)
);
```

---

## Security Model

- **Fee manipulation** → rejected by consensus. Honest nodes earn 50%; cheaters earn nothing.
- **Content theft** → CID registered once, globally. IPFS CIDs match automatically.
- **Royalty bypass** → stored on-chain at mint time, validated by all nodes on every resale.
- **Node identity** → wallet signature. Authority wallet hardcoded in SDK — cannot be overridden.
- **Solo mining** → only authority node can mine alone. Non-authority single nodes must wait for peers.

---

## Related Repositories

| Repo | Description |
|---|---|
| [`playwebit/spiderweave-sdk`](https://github.com/playwebit/spiderweave-sdk) | Optional DB integrity hashing tool |
| [`playwebit/cloudflare-bootstrap`](https://github.com/playwebit/cloudflare-bootstrap) | Cloudflare Worker for peer discovery |

---

## License

Copyright 2026 PlayWebIT

Licensed under the Apache License, Version 2.0. You may obtain a copy at:
http://www.apache.org/licenses/LICENSE-2.0

---

*Built by [PlayWebIT](https://github.com/playwebit)*
