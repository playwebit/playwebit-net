"""
PlayWebit Network — Leader Election
Rotating leader by block index. Deterministic — all nodes agree.
No randomness, no voting on who leads. Just math.
"""

import logging
from typing import List, Optional

logger = logging.getLogger(__name__)


class LeaderElection:

    def get_leader(
        self,
        block_index:  int,
        active_nodes: List[str],   # list of wallet addresses
    ) -> Optional[str]:
        """
        Get the leader wallet for a given block index.
        Deterministic: block_index % len(active_nodes)
        Every node on the network computes the same result.
        """
        if not active_nodes:
            return None

        sorted_nodes = sorted(active_nodes)   # sort for determinism
        leader_index = block_index % len(sorted_nodes)
        return sorted_nodes[leader_index]

    def is_leader(
        self,
        my_wallet:    str,
        block_index:  int,
        active_nodes: List[str],
    ) -> bool:
        """Check if this node is the leader for this block."""
        leader = self.get_leader(block_index, active_nodes)
        if not leader:
            return False
        return leader.lower() == my_wallet.lower()

    def get_next_leader(
        self,
        block_index:  int,
        active_nodes: List[str],
    ) -> Optional[str]:
        """Get the leader for the NEXT block — for planning ahead."""
        return self.get_leader(block_index + 1, active_nodes)
