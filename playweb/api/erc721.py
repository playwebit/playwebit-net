"""
PlayWebit Network — ERC721 Handler
NFT ownership reads from L1 chain directly.
Contract address = Node wallet address.

Ownership is ALREADY on chain in content_registry
and edition_registry. This just exposes it as ERC721.
"""

import hashlib


def handle_erc721_call(call_data: str, node) -> str:
    """
    Handle ERC721 function calls from MetaMask.
    Returns ABI-encoded response or None if not ERC721.
    """

    # balanceOf(address) = 0x70a08231
    if call_data.startswith("0x70a08231"):
        addr    = "0x" + call_data[34:74]
        records = node.blockchain.storage.get_all_content_by_owner(addr)
        count   = len(records)
        return "0x" + hex(count)[2:].zfill(64)

    # ownerOf(uint256) = 0x6352211e
    elif call_data.startswith("0x6352211e"):
        int_id = int(call_data[10:], 16)
        cid    = node.blockchain.storage.get_cid_by_int_id(int_id)
        if cid:
            record = node.blockchain.storage.get_content_record(cid)
            if record:
                owner = record.get("current_owner", "0x" + "0" * 40)
                return "0x" + owner[2:].zfill(64)
        return "0x" + "0" * 64

    # tokenURI(uint256) = 0xc87b56dd
    elif call_data.startswith("0xc87b56dd"):
        int_id = int(call_data[10:], 16)
        cid    = node.blockchain.storage.get_cid_by_int_id(int_id)
        if cid:
            uri = f"{node.node_url}/api/metadata/{cid}"
            return _encode_string(uri)
        return "0x"

    # name() = 0x06fdde03
    elif call_data.startswith("0x06fdde03"):
        return _encode_string("PlayWebit NFT")

    # symbol() = 0x95d89b41
    elif call_data.startswith("0x95d89b41"):
        return _encode_string("PLWB-NFT")

    # supportsInterface(bytes4) = 0x01ffc9a7
    elif call_data.startswith("0x01ffc9a7"):
        iface     = call_data[10:18].lower()
        # ERC721=80ac58cd, ERC721Metadata=5b5e139f, ERC165=01ffc9a7
        supported = iface in ["80ac58cd", "5b5e139f", "01ffc9a7"]
        return "0x" + ("1" if supported else "0").zfill(64)

    # getApproved(uint256) = 0x081812fc → always zero address
    elif call_data.startswith("0x081812fc"):
        return "0x" + "0" * 64

    # isApprovedForAll = 0xe985e9c5 → always false
    elif call_data.startswith("0xe985e9c5"):
        return "0x" + "0" * 64

    return None


def _encode_string(s: str) -> str:
    """ABI encode a string response."""
    b       = s.encode("utf-8")
    offset  = "0" * 63 + "20"
    length  = hex(len(b))[2:].zfill(64)
    padding = 32 - len(b) % 32
    pad     = b.hex() + "00" * (padding if padding != 32 else 0)
    return "0x" + offset + length + pad


def cid_to_int_id(cid: str) -> int:
    """
    Convert CID string to integer token ID for MetaMask.
    Deterministic — same CID always gives same int.
    """
    hash_obj = hashlib.sha256(cid.encode())
    return int(hash_obj.hexdigest()[:16], 16)
