"""
PlayWebit Network — Gossip Protocol
P2P block and transaction propagation via HTTP webhooks.
Works on ALL cloud platforms — HuggingFace, AWS, VPS, anywhere.
No persistent connections needed. Fire and forget to peers.
"""

import logging
import threading
import requests
from typing import List, TYPE_CHECKING

from playweb.config import GOSSIP_FANOUT, PEER_TIMEOUT

if TYPE_CHECKING:
    from playweb.network.peer_manager import Peer
    from playweb.consensus.vote       import Vote
    from playweb.core.block           import Block
    from playweb.core.transaction     import Transaction

logger = logging.getLogger(__name__)


class GossipProtocol:

    def __init__(self, node_wallet: str):
        self.node_wallet = node_wallet

    # ─────────────────────────────────────────────────────────────
    # Internal helpers
    # ─────────────────────────────────────────────────────────────

    def _post(self, url: str, data: dict, timeout: int = PEER_TIMEOUT):
        """Fire-and-forget HTTP POST to a peer endpoint."""
        try:
            requests.post(url, json=data, timeout=timeout)
        except Exception:
            pass   # peer may be down — that's fine

    def _broadcast(
        self,
        peers:    List["Peer"],
        endpoint: str,
        payload:  dict,
        fanout:   int = GOSSIP_FANOUT,
    ):
        """
        Broadcast payload to up to GOSSIP_FANOUT peers in parallel.
        Each peer then forwards to their peers.
        This is how messages propagate through the whole network.
        """
        # Limit fanout but prefer low-latency peers
        targets = sorted(peers, key=lambda p: p.latency_ms)[:fanout]

        threads = []
        for peer in targets:
            t = threading.Thread(
                target=self._post,
                args=(f"{peer.url}{endpoint}", payload),
                daemon=True,
            )
            t.start()
            threads.append(t)

        # Don't wait — fire and forget
        # Peers will propagate further themselves

    # ─────────────────────────────────────────────────────────────
    # Broadcast: new transaction
    # ─────────────────────────────────────────────────────────────

    def broadcast_transaction(
        self,
        tx:    "Transaction",
        peers: List["Peer"],
    ):
        """
        Broadcast a new transaction to peers.
        Called when a node receives a tx from an API client.
        """
        if not peers:
            return

        payload = {
            "transaction": tx.to_dict(),
            "from_node":   self.node_wallet,
        }
        self._broadcast(peers, "/peer/new_transaction", payload)
        logger.debug(f"Gossip: broadcast tx {tx.hash[:12]}... to {len(peers)} peers")

    # ─────────────────────────────────────────────────────────────
    # Broadcast: block proposal (from consensus leader)
    # ─────────────────────────────────────────────────────────────

    def broadcast_block_proposal(
        self,
        block:        "Block",
        round_number: int,
        peers:        List["Peer"],
    ):
        """
        Broadcast a block proposal during PROPOSE phase.
        Only the consensus leader calls this.
        """
        if not peers:
            return

        payload = {
            "block":        block.to_dict(),
            "round_number": round_number,
            "from_node":    self.node_wallet,
            "message_type": "proposal",
        }
        # Send to ALL peers for proposals (not just fanout)
        # Every peer needs to receive the proposal to vote
        threads = []
        for peer in peers:
            t = threading.Thread(
                target=self._post,
                args=(f"{peer.url}/peer/propose", payload),
                daemon=True,
            )
            t.start()
            threads.append(t)

        logger.info(
            f"Gossip: broadcast proposal block {block.index} "
            f"to {len(peers)} peers"
        )

    # ─────────────────────────────────────────────────────────────
    # Broadcast: vote
    # ─────────────────────────────────────────────────────────────

    def broadcast_vote(
        self,
        vote:  "Vote",
        peers: List["Peer"],
    ):
        """
        Broadcast a consensus vote to all peers.
        Every validator calls this after validating a proposal.
        """
        if not peers:
            return

        payload = {
            "vote":      vote.to_dict(),
            "from_node": self.node_wallet,
        }
        # Send votes to ALL peers — every node needs to collect them
        threads = []
        for peer in peers:
            t = threading.Thread(
                target=self._post,
                args=(f"{peer.url}/peer/vote", payload),
                daemon=True,
            )
            t.start()
            threads.append(t)

        logger.debug(
            f"Gossip: broadcast vote for block "
            f"{vote.block_hash[:12]}... to {len(peers)} peers"
        )

    # ─────────────────────────────────────────────────────────────
    # Broadcast: finalised block
    # ─────────────────────────────────────────────────────────────

    def broadcast_finalised_block(
        self,
        block:  "Block",
        votes:  list,
        peers:  List["Peer"],
    ):
        """
        Broadcast a finalised block after consensus.
        Nodes that missed the consensus round catch up via this.
        """
        if not peers:
            return

        payload = {
            "block":        block.to_dict(),
            "votes":        votes,
            "from_node":    self.node_wallet,
            "message_type": "finalised",
        }
        self._broadcast(peers, "/peer/new_block", payload)
        logger.info(
            f"Gossip: broadcast finalised block "
            f"{block.index} to {len(peers)} peers"
        )

    # ─────────────────────────────────────────────────────────────
    # Broadcast: new node joined
    # ─────────────────────────────────────────────────────────────

    def broadcast_new_node(
        self,
        new_node_url:    str,
        new_node_wallet: str,
        peers:           List["Peer"],
    ):
        """
        Tell all existing peers about a new node.
        Called when Cloudflare notifies us of a new registration.
        """
        if not peers:
            return

        payload = {
            "url":       new_node_url,
            "wallet":    new_node_wallet,
            "from_node": self.node_wallet,
        }
        self._broadcast(peers, "/peer/new_node", payload)
        logger.info(
            f"Gossip: broadcast new node "
            f"{new_node_url} to {len(peers)} peers"
        )
