"""
PlayWebit Network — ERC20 Handler
PLWB token as ERC20 — reads from chain directly.
Contract address = Node wallet address.
No separate contract storage needed.
"""


def handle_erc20_call(call_data: str, node) -> str:
    """
    Handle ERC20 function calls from MetaMask.
    Returns ABI-encoded response or None if not ERC20.
    """

    # balanceOf(address) = 0x70a08231
    if call_data.startswith("0x70a08231"):
        addr    = "0x" + call_data[34:74]
        balance = node.blockchain.get_balance(addr)
        wei     = int(balance * 10**18)
        return "0x" + hex(wei)[2:].zfill(64)

    # totalSupply() = 0x18160ddd
    elif call_data.startswith("0x18160ddd"):
        addresses = node.blockchain.storage.get_all_addresses()
        total = sum(
            node.blockchain.get_balance(a)
            for a in addresses
        )
        wei = int(total * 10**18)
        return "0x" + hex(wei)[2:].zfill(64)

    # name() = 0x06fdde03
    elif call_data.startswith("0x06fdde03"):
        return _encode_string("PlayWebit Coin")

    # symbol() = 0x95d89b41
    elif call_data.startswith("0x95d89b41"):
        return _encode_string("PLWB")

    # decimals() = 0x313ce567
    elif call_data.startswith("0x313ce567"):
        return "0x" + hex(18)[2:].zfill(64)

    # allowance() = 0xdd62ed3e → always 0
    elif call_data.startswith("0xdd62ed3e"):
        return "0x" + "0" * 64

    # approve() = 0x095ea7b3 → always true
    elif call_data.startswith("0x095ea7b3"):
        return "0x" + "1".zfill(64)

    # supportsInterface = 0x01ffc9a7
    elif call_data.startswith("0x01ffc9a7"):
        return "0x" + "1".zfill(64)

    return None


def _encode_string(s: str) -> str:
    """ABI encode a string response."""
    b       = s.encode("utf-8")
    offset  = "0" * 63 + "20"
    length  = hex(len(b))[2:].zfill(64)
    padding = 32 - len(b) % 32
    pad     = b.hex() + "00" * (padding if padding != 32 else 0)
    return "0x" + offset + length + pad
