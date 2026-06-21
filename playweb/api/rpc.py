"""
PlayWebit Network — Ethereum JSON-RPC Compatibility Layer
Allows MetaMask to connect to PlayWebit Network.

MetaMask setup:
  RPC URL:   https://your-node.com/rpc
  Chain ID:  4968
  Currency:  PLWB

Contract address = Node wallet address (for both ERC20 + ERC721)
No Solidity. No deployment. No gas fees to deploy.
"""

import logging
from flask import Blueprint, request, jsonify

logger = logging.getLogger(__name__)


def create_rpc(node) -> Blueprint:
    bp = Blueprint("rpc", __name__)

    @bp.route("/rpc", methods=["POST"])
    def rpc():
        data   = request.get_json(silent=True) or {}
        method = data.get("method", "")
        params = data.get("params", [])
        req_id = data.get("id", 1)

        def ok(val):
            return jsonify({
                "jsonrpc": "2.0",
                "id":      req_id,
                "result":  val,
            })

        def err(code, msg):
            return jsonify({
                "jsonrpc": "2.0",
                "id":      req_id,
                "error":   {"code": code, "message": msg},
            }), 400

        # ── Network identity ──────────────────────────────────
        if method == "eth_chainId":
            return ok("0x1368")   # 4968 in hex

        if method == "net_version":
            return ok("4968")

        if method == "eth_blockNumber":
            length = node.blockchain.get_chain_length()
            return ok(hex(max(0, length - 1)))

        if method == "eth_accounts":
            return ok([])

        if method == "eth_estimateGas":
            return ok("0x5208")   # 21000 fixed

        if method == "eth_gasPrice":
            return ok("0x1")      # 1 wei fixed

        if method == "eth_getTransactionCount":
            return ok("0x1")

        # ── PLWB native balance ───────────────────────────────
        if method == "eth_getBalance":
            addr    = params[0] if params else "0x0"
            balance = node.blockchain.get_balance(addr)
            wei     = int(balance * 10**18)
            return ok(hex(wei))

        # ── ERC20 + ERC721 via eth_call ───────────────────────
        if method == "eth_call":
            if not params or not isinstance(params[0], dict):
                return ok("0x")

            from playweb.api.erc20    import handle_erc20_call
            from playweb.api.erc721   import handle_erc721_call

            call_data = params[0].get("data", "0x")
            to_addr   = params[0].get("to", "").lower()

            # Both ERC20 + ERC721 use node wallet as contract address
            if to_addr == node.node_wallet.lower():
                # Try ERC20 first (PLWB token)
                result = handle_erc20_call(call_data, node)
                if result is not None:
                    return ok(result)

                # Then try ERC721 (NFT ownership)
                result = handle_erc721_call(call_data, node)
                if result is not None:
                    return ok(result)

            return ok("0x")

        # ── Transaction submission ────────────────────────────
        if method == "eth_sendRawTransaction":
            raw_tx = params[0] if params else None
            if not raw_tx:
                return err(-32602, "Missing raw transaction")
            try:
                from eth_account          import Account
                from eth_account.messages import encode_defunct
                from playweb.core.transaction import Transaction
                import time

                decoded   = Account.decode_transaction(raw_tx)
                from_addr = decoded.get("from", "")
                if not from_addr:
                    # recover from signature
                    from_addr = Account.recover_transaction(raw_tx)

                tx = Transaction(
                    from_addr = from_addr.lower(),
                    to_addr   = decoded["to"].lower(),
                    amount    = decoded["value"] / 10**18,
                    tx_type   = "transfer",
                    signature = raw_tx,
                    nonce     = decoded.get("nonce", int(time.time())),
                )

                success, result = node.blockchain.add_transaction(
                    tx          = tx,
                    node_wallet = node.node_wallet,
                )

                if success:
                    node.gossip.broadcast_transaction(
                        tx    = tx,
                        peers = node.peer_manager.get_active_peers(),
                    )
                    return ok(tx.hash)
                else:
                    return err(-32000, result)

            except Exception as e:
                logger.error(f"eth_sendRawTransaction error: {e}")
                return err(-32000, str(e))

        # ── Transaction queries ───────────────────────────────
        if method == "eth_getTransactionByHash":
            tx_hash = params[0] if params else None
            if not tx_hash:
                return ok(None)
            tx = node.blockchain.get_transaction(tx_hash)
            if not tx:
                return ok(None)
            return ok({
                "hash":             tx.hash,
                "from":             tx.from_addr,
                "to":               tx.to_addr,
                "value":            hex(int(tx.amount * 10**18)),
                "blockNumber":      None,
                "transactionIndex": "0x0",
                "gas":              "0x5208",
                "gasPrice":         "0x1",
                "nonce":            hex(tx.nonce or 0),
                "input":            "0x",
            })

        if method == "eth_getTransactionReceipt":
            tx_hash = params[0] if params else None
            if not tx_hash:
                return ok(None)
            tx = node.blockchain.get_transaction(tx_hash)
            if not tx:
                return ok(None)
            tip = node.blockchain.get_chain_tip()
            return ok({
                "transactionHash":  tx_hash,
                "status":           "0x1",
                "blockNumber":      hex(tip.index) if tip else "0x0",
                "blockHash":        tip.hash if tip else "0x0",
                "gasUsed":          "0x5208",
                "cumulativeGasUsed":"0x5208",
                "logs":             [],
                "logsBloom":        "0x" + "0" * 512,
            })

        if method == "eth_getBlockByNumber":
            block_param = params[0] if params else "latest"
            include_txs = params[1] if len(params) > 1 else False

            if block_param == "latest":
                block = node.blockchain.get_chain_tip()
            elif block_param == "earliest":
                block = node.blockchain.get_block_by_index(0)
            else:
                try:
                    block = node.blockchain.get_block_by_index(
                        int(block_param, 16)
                    )
                except:
                    block = node.blockchain.get_chain_tip()

            if not block:
                return ok(None)

            txs = (
                [tx.to_dict() for tx in block.transactions]
                if include_txs
                else [tx.hash for tx in block.transactions]
            )
            return ok({
                "number":           hex(block.index),
                "hash":             block.hash,
                "parentHash":       block.previous_hash,
                "timestamp":        hex(int(block.timestamp)),
                "transactions":     txs,
                "miner":            block.validator_wallet,
                "gasLimit":         "0x1c9c380",
                "gasUsed":          "0x0",
                "difficulty":       "0x1",
                "nonce":            "0x0000000000000000",
                "extraData":        "0x",
                "logsBloom":        "0x" + "0" * 512,
            })

        if method == "eth_getBlockByHash":
            block_hash  = params[0] if params else None
            include_txs = params[1] if len(params) > 1 else False
            if not block_hash:
                return ok(None)
            block = node.blockchain.get_block(block_hash)
            if not block:
                return ok(None)
            txs = (
                [tx.to_dict() for tx in block.transactions]
                if include_txs
                else [tx.hash for tx in block.transactions]
            )
            return ok({
                "number":      hex(block.index),
                "hash":        block.hash,
                "parentHash":  block.previous_hash,
                "timestamp":   hex(int(block.timestamp)),
                "transactions": txs,
            })

        # ── Unknown method ────────────────────────────────────
        logger.debug(f"Unknown RPC method: {method}")
        return ok("0x")

    return bp
