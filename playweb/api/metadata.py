"""
PlayWebit Network — NFT Metadata Endpoint
Generic metadata for any NFT on the network.
Platforms enrich via plugin get_nft_metadata() hook.

MetaMask fetches: GET /api/metadata/{cid}
Returns OpenSea-compatible metadata JSON.
"""

import logging
from flask import Blueprint, jsonify

logger = logging.getLogger(__name__)


def create_metadata_api(node) -> Blueprint:
    bp = Blueprint("metadata", __name__)

    @bp.route("/api/metadata/<path:cid>", methods=["GET"])
    def nft_metadata(cid):
        """
        Returns NFT metadata in OpenSea format.
        Reads base data from chain.
        Plugin can enrich with thumbnail, filename etc.
        """
        record = node.blockchain.storage.get_content_record(cid)
        if not record:
            return jsonify({"error": "CID not registered"}), 404

        # Base metadata from chain — always available
        metadata = {
            "name":        f"PlayWebit NFT — {cid[:12]}...",
            "description": (
                f"Registered on PlayWebit Network by "
                f"{record.get('first_platform', 'unknown')}. "
                f"CID: {cid}"
            ),
            "image":       "",
            "external_url": f"{node.node_url}/api/owner/{cid}",
            "attributes":  [
                {
                    "trait_type": "CID",
                    "value":      cid,
                },
                {
                    "trait_type": "Platform",
                    "value":      record.get("first_platform", "unknown"),
                },
                {
                    "trait_type": "Total Editions",
                    "value":      record.get("total_editions", 1),
                },
                {
                    "trait_type": "Royalty",
                    "value":      f"{record.get('royalty_pct', 0)}%",
                },
                {
                    "trait_type": "Current Owner",
                    "value":      record.get("current_owner", "unknown"),
                },
                {
                    "trait_type": "Registered Block",
                    "value":      record.get("first_block", 0),
                },
            ],
        }

        # Let plugin enrich metadata
        # (adds thumbnail, filename, custom attributes etc)
        if node.plugin_manager:
            for plugin in node.plugin_manager.get_all_plugins():
                if hasattr(plugin, "get_nft_metadata"):
                    try:
                        enriched = plugin.get_nft_metadata(cid, record)
                        if enriched:
                            metadata.update(enriched)
                            break
                    except Exception as e:
                        logger.error(
                            f"Plugin metadata error "
                            f"({plugin.plugin_id}): {e}"
                        )

        return jsonify(metadata)

    return bp
