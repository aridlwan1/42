import os
import json
import base64
import requests
import secrets
import time
import uuid
from web3 import Web3
from eth_account import Account
from dotenv import load_dotenv

load_dotenv(override=True)

def build_payment_signature(private_key, chain_id, usdc_name, usdc_version, usdc_address, accept):
    account = Account.from_key(private_key)
    nonce = "0x" + secrets.token_hex(32)
    valid_after = 0
    valid_before = int(time.time()) + int(accept["maxTimeoutSeconds"])

    typed_data = {
        "types": {
            "EIP712Domain": [
                {"name": "name", "type": "string"},
                {"name": "version", "type": "string"},
                {"name": "chainId", "type": "uint256"},
                {"name": "verifyingContract", "type": "address"},
            ],
            "ReceiveWithAuthorization": [
                {"name": "from", "type": "address"},
                {"name": "to", "type": "address"},
                {"name": "value", "type": "uint256"},
                {"name": "validAfter", "type": "uint256"},
                {"name": "validBefore", "type": "uint256"},
                {"name": "nonce", "type": "bytes32"},
            ],
        },
        "primaryType": "ReceiveWithAuthorization",
        "domain": {
            "name": usdc_name,
            "version": usdc_version,
            "chainId": chain_id,
            "verifyingContract": usdc_address,
        },
        "message": {
            "from": account.address,
            "to": accept["payTo"],
            "value": int(accept["amount"]),
            "validAfter": valid_after,
            "validBefore": valid_before,
            "nonce": nonce,
        },
    }

    signed = account.sign_typed_data(full_message=typed_data)
    r_hex = "0x" + signed.r.to_bytes(32, "big").hex()
    s_hex = "0x" + signed.s.to_bytes(32, "big").hex()

    payment_sig = {
        "x402Version": 2,
        "scheme": "exact",
        "network": accept["network"],
        "payload": {
            "client": account.address,
            "maxAmount": str(int(accept["amount"])),
            "validAfter": str(valid_after),
            "validBefore": str(valid_before),
            "nonce": nonce,
            "v": int(signed.v),
            "r": r_hex,
            "s": s_hex,
        },
    }
    return base64.b64encode(json.dumps(payment_sig, separators=(",", ":")).encode()).decode()

def test_full_session():
    MCP_URL = "https://mcp.fortytwo.network/mcp"
    s = requests.Session()
    
    init_res = s.post(MCP_URL, json={
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {"protocolVersion": "2025-11-25", "capabilities": {}, "clientInfo": {"name": "LootAgent", "version": "1.0"}}
    })
    print("INIT", init_res.status_code)

    query_text = "test session"
    payload = {
        "jsonrpc": "2.0", "id": 3, "method": "tools/call",
        "params": {"name": "ask_fortytwo_prime", "arguments": {"query": query_text}}
    }
    
    resp = s.post(MCP_URL, json=payload)
    print("CALL1", resp.status_code)
    if resp.status_code == 402:
        req_header_enc = resp.headers.get("payment-required")
        req_data = json.loads(base64.b64decode(req_header_enc).decode())
        accept = next((item for item in req_data.get("accepts", []) if item["network"] == "eip155:8453"), None)
        
        evm_private_key = os.getenv("evm_private_key")
        usdc_address = accept["asset"]
        payment_sig_b64 = build_payment_signature(evm_private_key, 8453, "USD Coin", "2", usdc_address, accept)
        
        print("TRYING WITH SESSION AND MAXAMOUNT")
        headers = {
            "payment-signature": payment_sig_b64,
            "x-idempotency-key": str(uuid.uuid4()),
            "Content-Type": "application/json"
        }
        res_final = s.post(MCP_URL, headers=headers, json=payload, timeout=30)
        print("FINAL STATUS", res_final.status_code)
        print("FINAL TEXT", res_final.text)

if __name__ == "__main__":
    test_full_session()
