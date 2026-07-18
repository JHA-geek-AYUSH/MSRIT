from __future__ import annotations

import os
from typing import Any, Dict


def publish_root(run_id: str, merkle_root: str) -> Dict[str, Any]:
    """Publish a Merkle root to the GemmaChain Notary contract.

    Falls back to a stub receipt when Web3 / contract config is absent so the
    server starts cleanly in development without a live subnet.
    """
    rpc_url = os.getenv("GEMMACHAIN_RPC_URL")
    contract_address = os.getenv("NOTARY_CONTRACT_ADDRESS")
    private_key = os.getenv("NOTARY_PRIVATE_KEY")

    if not all([rpc_url, contract_address, private_key]):
        # Dev stub – no blockchain configured
        return {
            "transactionHash": "0x" + "0" * 64,
            "blockNumber": 0,
            "status": 1,
        }

    try:
        from web3 import Web3

        w3 = Web3(Web3.HTTPProvider(rpc_url))

        NOTARY_ABI = [
            {
                "inputs": [
                    {"internalType": "bytes32", "name": "runId", "type": "bytes32"},
                    {"internalType": "bytes32", "name": "rootHash", "type": "bytes32"},
                ],
                "name": "publish",
                "outputs": [],
                "stateMutability": "nonpayable",
                "type": "function",
            }
        ]

        contract = w3.eth.contract(
            address=Web3.to_checksum_address(contract_address), abi=NOTARY_ABI
        )
        account = w3.eth.account.from_key(private_key)

        run_id_bytes = bytes.fromhex(run_id.replace("-", "").ljust(64, "0")[:64])
        root_bytes = bytes.fromhex(merkle_root.removeprefix("0x").ljust(64, "0")[:64])

        tx = contract.functions.publish(run_id_bytes, root_bytes).build_transaction(
            {
                "from": account.address,
                "nonce": w3.eth.get_transaction_count(account.address),
                "gas": 100_000,
                "gasPrice": w3.eth.gas_price,
            }
        )
        signed = account.sign_transaction(tx)
        tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=60)

        return {
            "transactionHash": receipt["transactionHash"].hex(),
            "blockNumber": receipt["blockNumber"],
            "status": receipt["status"],
        }
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"Blockchain publish failed: {exc}") from exc
