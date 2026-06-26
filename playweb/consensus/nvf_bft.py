"""
PlayWebit Network — NVF-BFT Consensus Engine
Based on NullVoid Framework paper concepts.

Round phases mapped to NVF paper:
  PROPOSE → Spacetime Fabric activation (leader broadcasts)
  PREPARE → Six Directional Progressions (peers validate)
  VOTE    → Planck Threshold approach (peers sign + broadcast)
  COMMIT  → False Vacuum → True Vacuum (2/3 quorum = finalised)
  ANCHOR  → Null Void Layer 0 anchoring (write to storage)
  NOTIFY  → Cyclic re-entry notification (plugins + peers notified)

Tolerates up to f < n/3 faulty nodes (standard BFT guarantee).

Sybil Resistance — Option A (Authority Whitelist):
  Only nodes with a node_register tx signed by AUTHORITY_WALLET
  can participate in consensus voting.
  Attacker nodes are silently ignored even if connected.
"""

import time
import threading
import logging
from typing import Dict, List, Optional, Callable, Set

from playweb.consensus.leader import LeaderElection
from playweb.consensus.vote   import Vote
from playweb.config           import (
    CONSENSUS_QUORUM,
    BLOCK_TIME,
    CONSENSUS_TIMEOUT,
    BATCH_TIMEOUT,
    MAX_TX_PER_BLOCK,
    AUTHORITY_WALLET,
)

logger = logging.getLogger(__name__)


class ConsensusRound:
    """State for a single consensus round."""

    def __init__(self, block_index: int, block):
        self.block_index        = block_index
        self.block              = block
        self.phase              = "PROPOSE"
        self.votes: Dict[str, Vote] = {}   # voter_wallet → Vote
        self.started_at         = time.time()
        self.finalised          = False
        self.failed             = False

    def add_vote(self, vote: Vote) -> bool:
        """Add a vote. Returns True if new vote added."""
        if vote.voter_wallet in self.votes:
            return False
        if not vote.verify():
            logger.warning(
                f"Invalid vote signature from {vote.voter_wallet[:8]}"
            )
            return False
        self.votes[vote.voter_wallet] = vote
        return True

    def has_quorum(
        self,
        active_node_count: int,
        node_wallet: str = "",
    ) -> bool:
        """
        Check if 2/3 quorum has been reached.

        Single node rules:
          - Authority node alone → can mine (bootstrapping phase)
          - Non-authority node alone → must wait for peers (security)
        """
        if active_node_count == 0:
            return False

        # Single node special case
        if active_node_count == 1:
            if node_wallet.lower() == AUTHORITY_WALLET.lower():
                return len(self.votes) >= 1
            else:
                return False

        # Multiple nodes — standard 2/3 quorum
        return len(self.votes) / active_node_count >= CONSENSUS_QUORUM

    def is_timed_out(self) -> bool:
        return time.time() - self.started_at > CONSENSUS_TIMEOUT


class NVFBFTConsensus:

    def __init__(
        self,
        blockchain,
        peer_manager,
        gossip,
        node_wallet:        str,
        node_private_key:   str,
        plugin_manager      = None,
        on_block_finalised: Optional[Callable] = None,
    ):
        self.blockchain         = blockchain
        self.peer_manager       = peer_manager
        self.gossip             = gossip
        self.node_wallet        = node_wallet.lower()
        self.node_private_key   = node_private_key
        self.plugin_manager     = plugin_manager
        self.on_block_finalised = on_block_finalised

        self.leader_election    = LeaderElection()
        self.current_round:     Optional[ConsensusRound] = None
        self._lock              = threading.Lock()
        self._running           = False
        self._thread:           Optional[threading.Thread] = None

        # Batch mining timer
        self._batch_timer_start: Optional[float] = None

        # Sybil resistance — registered node wallet cache
        # Loaded from chain on startup, updated on each new block
        self._registered_nodes:        Set[str] = set()
        self._registered_nodes_loaded: bool     = False

    # ─────────────────────────────────────────────────────────────
    # Lifecycle
    # ─────────────────────────────────────────────────────────────

    def start(self):
        """Start the consensus loop in a background thread."""
        # Load registered nodes from chain before starting
        self._load_registered_nodes()

        self._running = True
        self._thread  = threading.Thread(
            target = self._consensus_loop,
            daemon = True,
            name   = "nvf-bft-consensus",
        )
        self._thread.start()
        logger.info(
            f"NVF-BFT consensus started — "
            f"{len(self._registered_nodes)} registered validators"
        )

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
        logger.info("NVF-BFT consensus stopped")

    # ─────────────────────────────────────────────────────────────
    # Sybil Resistance — Registered Node Registry
    # ─────────────────────────────────────────────────────────────

    def _load_registered_nodes(self):
        """
        Load all registered validator wallets from chain.
        Scans for node_register transactions signed by AUTHORITY_WALLET.
        Authority wallet is always included (bootstrapping).
        Called on startup and when new blocks arrive.
        """
        registered = {AUTHORITY_WALLET.lower()}

        try:
            length    = self.blockchain.get_chain_length()
            scan_from = max(0, length - 100000)
            blocks    = self.blockchain.get_blocks_from(scan_from, 100000)

            for block in blocks:
                for tx in block.transactions:
                    if (
                        tx.tx_type   == "node_register"
                        and tx.from_addr == AUTHORITY_WALLET.lower()
                    ):
                        registered.add(tx.to_addr.lower())

        except Exception as e:
            logger.error(f"Error loading registered nodes: {e}")

        self._registered_nodes        = registered
        self._registered_nodes_loaded = True
        logger.info(
            f"Registered validators: {len(registered)} "
            f"({', '.join(list(registered)[:3])}...)"
        )

    def _is_registered_node(self, wallet: str) -> bool:
        """
        Check if a wallet is a registered validator.
        Authority wallet is always registered.
        Other nodes must have a node_register tx on chain.
        """
        if not self._registered_nodes_loaded:
            self._load_registered_nodes()
        return wallet.lower() in self._registered_nodes

    def _update_registered_nodes(self, block):
        """
        Update registered nodes cache from a newly finalised block.
        Called after ANCHOR phase so new validators take effect
        from the very next block.
        """
        for tx in block.transactions:
            if (
                tx.tx_type   == "node_register"
                and tx.from_addr == AUTHORITY_WALLET.lower()
            ):
                self._registered_nodes.add(tx.to_addr.lower())
                logger.info(
                    f"New validator registered on chain: "
                    f"{tx.to_addr[:12]}... "
                    f"(platform: {tx.data.get('platform_id', 'unknown') if tx.data else 'unknown'})"
                )

    # ─────────────────────────────────────────────────────────────
    # Main consensus loop — Batch Mining
    # ─────────────────────────────────────────────────────────────

    def _consensus_loop(self):
        """
        Batch mining loop:
        - Never mines empty blocks
        - Starts timer when first tx hits mempool
        - Mines immediately at MAX_TX_PER_BLOCK
        - Mines with pending txs when BATCH_TIMEOUT expires
        """
        while self._running:
            try:
                pending = self.blockchain.mempool.size()

                if pending == 0:
                    # No transactions — reset timer, wait
                    self._batch_timer_start = None
                    time.sleep(5)
                    continue

                # First tx arrived — start timer
                if self._batch_timer_start is None:
                    self._batch_timer_start = time.time()
                    logger.info(
                        f"Batch timer started — "
                        f"{pending} tx(s) in mempool, "
                        f"mining in {BATCH_TIMEOUT}s "
                        f"or at {MAX_TX_PER_BLOCK} txs"
                    )

                elapsed     = time.time() - self._batch_timer_start
                should_mine = (
                    pending >= MAX_TX_PER_BLOCK   # max txs → mine now
                    or elapsed >= BATCH_TIMEOUT    # timeout → mine now
                )

                if should_mine:
                    reason = (
                        "max_txs" if pending >= MAX_TX_PER_BLOCK
                        else "timeout"
                    )
                    logger.info(
                        f"Mining: {pending} txs | "
                        f"elapsed={elapsed:.0f}s | "
                        f"reason={reason}"
                    )
                    self._run_round()
                    self._batch_timer_start = None  # reset after mining

            except Exception as e:
                logger.error(f"Consensus error: {e}", exc_info=True)
                self._batch_timer_start = None

            time.sleep(5)   # check every 5 seconds

    def _run_round(self):
        """Execute one consensus round."""
        tip        = self.blockchain.get_chain_tip()
        next_index = (tip.index + 1) if tip else 1

        # Only registered nodes count as active validators
        active_nodes = [
            p.wallet
            for p in self.peer_manager.get_active_peers()
            if self._is_registered_node(p.wallet)
        ]

        # Include self if registered
        if self._is_registered_node(self.node_wallet):
            if self.node_wallet not in active_nodes:
                active_nodes.append(self.node_wallet)

        if not active_nodes:
            logger.warning("No registered validators available")
            return

        # PHASE: PROPOSE — NVF: Spacetime Fabric activation
        am_leader = self.leader_election.is_leader(
            self.node_wallet, next_index, active_nodes
        )

        if am_leader:
            logger.info(
                f"Round {next_index}: I am leader "
                f"({self.node_wallet[:8]}...) "
                f"[{len(active_nodes)} validators]"
            )
            self._propose(next_index)
        else:
            leader = self.leader_election.get_leader(next_index, active_nodes)
            logger.debug(
                f"Round {next_index}: waiting for leader "
                f"{leader[:8] if leader else 'unknown'}..."
            )

    # ─────────────────────────────────────────────────────────────
    # Phase: PROPOSE — NVF: Spacetime Fabric activation
    # ─────────────────────────────────────────────────────────────

    def _propose(self, block_index: int):
        """Leader creates and broadcasts a block proposal."""
        block = self.blockchain.create_block(self.node_wallet)
        if not block:
            logger.debug(f"Round {block_index}: no transactions to propose")
            return

        with self._lock:
            self.current_round       = ConsensusRound(block_index, block)
            self.current_round.phase = "PREPARE"

        logger.info(
            f"PROPOSE: block {block_index}, "
            f"{len(block.transactions)} txs, "
            f"hash={block.hash[:12]}..."
        )

        # Broadcast to all peers
        self.gossip.broadcast_block_proposal(
            block        = block,
            round_number = block_index,
            peers        = self.peer_manager.get_active_peers(),
        )

        # Vote for own proposal
        self._prepare_and_vote(block, block_index)

    # ─────────────────────────────────────────────────────────────
    # Phase: PREPARE — NVF: Six Directional Progressions
    # ─────────────────────────────────────────────────────────────

    def on_propose(self, block, round_number: int, from_peer: str):
        """
        Called when we receive a block proposal from the leader.
        Validates and moves to VOTE phase.
        """
        # Only accept proposals from registered nodes
        if not self._is_registered_node(from_peer):
            logger.warning(
                f"Proposal from unregistered node "
                f"{from_peer[:8]}... ignored (Sybil protection)"
            )
            return

        logger.info(
            f"PREPARE: received proposal for block {round_number} "
            f"from {from_peer[:8]}..."
        )

        tip           = self.blockchain.get_chain_tip()
        valid, reason = block.validate(previous_block=tip)

        if not valid:
            logger.warning(f"Proposal rejected: {reason}")
            return

        with self._lock:
            self.current_round       = ConsensusRound(round_number, block)
            self.current_round.phase = "VOTE"

        self._prepare_and_vote(block, round_number)

    def _prepare_and_vote(self, block, round_number: int):
        """Create and broadcast our vote for this block."""
        vote = Vote(
            block_hash   = block.hash,
            voter_wallet = self.node_wallet,
            round_number = round_number,
            phase        = "VOTE",
        )
        vote.sign(self.node_private_key)

        self.gossip.broadcast_vote(
            vote  = vote,
            peers = self.peer_manager.get_active_peers(),
        )

        self.on_vote(vote)

    # ─────────────────────────────────────────────────────────────
    # Phase: VOTE → COMMIT
    # NVF: False Vacuum → True Vacuum (quorum = finality)
    # ─────────────────────────────────────────────────────────────

    def on_vote(self, vote: Vote):
        """
        Called when we receive a vote from any peer (or self).
        If 2/3 quorum reached → COMMIT.
        """
        with self._lock:
            if not self.current_round:
                return

            # Sybil resistance — only registered nodes can vote
            if not self._is_registered_node(vote.voter_wallet):
                logger.warning(
                    f"Vote ignored — unregistered node: "
                    f"{vote.voter_wallet[:12]}... (Sybil protection)"
                )
                return

            if vote.block_hash != self.current_round.block.hash:
                logger.debug(
                    f"Vote for unknown block "
                    f"{vote.block_hash[:12]}... ignored"
                )
                return

            added = self.current_round.add_vote(vote)
            if not added:
                return

            # Count only registered active nodes
            registered_peers = [
                p for p in self.peer_manager.get_active_peers()
                if self._is_registered_node(p.wallet)
            ]
            active_count = len(registered_peers) + 1  # +1 for self
            vote_count   = len(self.current_round.votes)

            logger.debug(
                f"VOTE: {vote_count}/{active_count} registered votes "
                f"for block {self.current_round.block_index}"
            )

            if self.current_round.has_quorum(active_count, self.node_wallet):
                if not self.current_round.finalised:
                    self.current_round.finalised = True
                    self._commit(
                        self.current_round.block,
                        list(self.current_round.votes.values()),
                    )

    # ─────────────────────────────────────────────────────────────
    # Phase: COMMIT → ANCHOR → NOTIFY
    # NVF: True Vacuum → Null Void anchoring → Cyclic re-entry
    # ─────────────────────────────────────────────────────────────

    def _commit(self, block, votes: List[Vote]):
        """
        2/3 quorum reached. Finalise the block.
        COMMIT → ANCHOR → NOTIFY
        """
        logger.info(
            f"COMMIT: block {block.index} finalised with "
            f"{len(votes)} votes"
        )

        # ANCHOR — NVF Layer 0
        vote_dicts      = [v.to_dict() for v in votes]
        success, reason = self.blockchain.add_block(
            block       = block,
            votes       = vote_dicts,
            node_wallet = self.node_wallet,
        )

        if not success:
            logger.error(f"Block commit failed: {reason}")
            return

        logger.info(
            f"ANCHOR: block {block.index} written "
            f"({block.hash[:16]}...)"
        )

        # Update registered nodes cache from this block
        # New node_register txs take effect immediately
        self._update_registered_nodes(block)

        # NOTIFY — Cyclic re-entry
        # 1. Notify plugins
        if self.plugin_manager:
            self.plugin_manager.notify_block_finalised(block)

        # 2. Notify node (broadcasts to peers)
        if self.on_block_finalised:
            self.on_block_finalised(block, vote_dicts)

        logger.info(
            f"NOTIFY: block {block.index} notifications sent"
        )

    # ─────────────────────────────────────────────────────────────
    # Timeout handling
    # ─────────────────────────────────────────────────────────────

    def check_timeout(self):
        """Check if current round timed out and reset if so."""
        with self._lock:
            if (
                self.current_round
                and self.current_round.is_timed_out()
            ):
                logger.warning(
                    f"Consensus round {self.current_round.block_index} "
                    f"timed out — resetting"
                )
                self.current_round = None

    # ─────────────────────────────────────────────────────────────
    # Status
    # ─────────────────────────────────────────────────────────────

    def get_status(self) -> Dict:
        with self._lock:
            base = {
                "registered_validators": len(self._registered_nodes),
            }
            if not self.current_round:
                return {**base, "status": "idle"}
            return {
                **base,
                "status":      "in_round",
                "block_index": self.current_round.block_index,
                "phase":       self.current_round.phase,
                "votes":       len(self.current_round.votes),
                "finalised":   self.current_round.finalised,
            }

    def get_registered_validators(self) -> List[str]:
        """Get list of all registered validator wallets."""
        return list(self._registered_nodes)
