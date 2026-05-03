import os
import time
import uuid
import json
import base64
import secrets
import requests
from web3 import Web3
from eth_account import Account
from dotenv import load_dotenv
from datetime import datetime

load_dotenv(override=True)

def ts():
    """Timestamp helper: returns string [YYYY-MM-DD HH:MM:SS]"""
    return datetime.now().strftime('[%Y-%m-%d %H:%M:%S]')

# Configurations
evm_private_key = os.getenv("evm_private_key")
rpc_url = os.getenv("BASE_RPC_URL", "https://mainnet.base.org")
MCP_URL = "https://mcp.fortytwo.network/mcp"

# Error Handling
if not evm_private_key:
    print(f"{ts()} CRITICAL ERROR: evm_private_key not found in .env")
    exit(1)

ERC20_META_ABI = [
    {"name": "name", "outputs": [{"type": "string"}], "inputs": [], "stateMutability": "view", "type": "function"},
    {"name": "version", "outputs": [{"type": "string"}], "inputs": [], "stateMutability": "view", "type": "function"},
    {"name": "decimals", "outputs": [{"type": "uint8"}], "inputs": [], "stateMutability": "view", "type": "function"},
]

def load_token_metadata(rpc_url: str, usdc_address: str):
    w3 = Web3(Web3.HTTPProvider(rpc_url))
    token = w3.eth.contract(address=Web3.to_checksum_address(usdc_address), abi=ERC20_META_ABI)
    return (
        token.functions.name().call(),
        token.functions.version().call(),
        token.functions.decimals().call(),
    )

def get_usdc_balance(rpc_url: str, wallet_address: str, usdc_address: str):
    try:
        w3 = Web3(Web3.HTTPProvider(rpc_url))
        abi = [{"name": "balanceOf", "outputs": [{"type": "uint256"}], "inputs": [{"name": "account", "type": "address"}], "stateMutability": "view", "type": "function"}]
        token = w3.eth.contract(address=Web3.to_checksum_address(usdc_address), abi=abi)
        balance = token.functions.balanceOf(Web3.to_checksum_address(wallet_address)).call()
        return balance / 1e6 # USDC has 6 decimals
    except Exception as e:
        print(f"{ts()} Error checking balance: {e}")
        return 0.0

def build_payment_signature(private_key: str, chain_id: int, usdc_name: str, usdc_version: str, usdc_address: str, accept: dict):
    account = Account.from_key(private_key)
    nonce = "0x" + secrets.token_hex(32)
    valid_after = 0
    valid_before = int(time.time()) + 3600 # 1 hour expiry to ensure settlement (server only gave 90s)

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

def jalankan_mcp(grid):
    print(f"\n--- {ts()} Starting Fortytwo MCP (x402) ---")
    
    query_text = f"You are a Fortytwo Prime agent. Analyze the following grid data and provide a brief suggestion:\n\n{grid}"
    print(f"{ts()} Analyzing data on Fortytwo Prime network...")

    try:
        # Step 1: initialize
        requests.post(MCP_URL, json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {"protocolVersion": "2025-11-25", "capabilities": {}, "clientInfo": {"name": "LootAgent", "version": "1.0"}}
        })

        # Step 3: tools/call untuk nge-trigger 402 Payment Required
        payload = {
            "jsonrpc": "2.0", "id": 3, "method": "tools/call",
            "params": {"name": "ask_fortytwo_prime", "arguments": {"query": query_text}}
        }
        resp = requests.post(MCP_URL, json=payload)
        
        if resp.status_code == 200:
            jawaban_ai = resp.json().get('result', {}).get('content', [{}])[0].get('text', 'No answer')
            print(f"{ts()} AI Recommendation: {jawaban_ai}")
            return

        if resp.status_code != 402:
            print(f"{ts()} Server Error {resp.status_code}: {resp.text}")
            return

        print(f"{ts()} >> Received 402 Payment Required. Preparing x402 escrow signature...")
        
        # Ekstrak header payment-required
        req_header_enc = resp.headers.get("payment-required")
        if not req_header_enc:
            print(f"{ts()} ERROR: 'payment-required' header not found.")
            return

        req_data = json.loads(base64.b64decode(req_header_enc).decode())
        
        # Kita pakai Base network secara default (eip155:8453)
        accept = next((item for item in req_data.get("accepts", []) if item["network"] == "eip155:8453"), None)
        if not accept:
            print(f"{ts()} ERROR: No Base network option (eip155:8453) from server.")
            return
            
        usdc_address = accept["asset"]
        usdc_name, usdc_version, _ = load_token_metadata(rpc_url, usdc_address)

        # Buat signature
        payment_sig_b64 = build_payment_signature(evm_private_key, 8453, usdc_name, usdc_version, usdc_address, accept)
        idemp_key = str(uuid.uuid4())

        # Step 5: Retry call with payment-signature (with retry logic for 502/504)
        print(f"{ts()} >> Signature successful! Executing query to Prime with escrow ceiling {int(accept['amount'])/1e6} USDC...")
        headers = {
            "payment-signature": payment_sig_b64,
            "x-idempotency-key": idemp_key,
            "Content-Type": "application/json"
        }
        
        max_retries = 3
        for attempt in range(max_retries):
            try:
                res_final = requests.post(MCP_URL, headers=headers, json=payload, timeout=600)
                
                if res_final.status_code == 200:
                    result_data = res_final.json()
                    if "result" in result_data and "content" in result_data["result"] and len(result_data["result"]["content"]) > 0:
                        jawaban_ai = result_data["result"]["content"][0]["text"]
                    else:
                        jawaban_ai = str(result_data)
                        
                    print(f"\n{ts()} AI Recommendation:\n{jawaban_ai}")
                    print(f"\n{ts()} >>> x402 Activity Recorded! FOR points increased.")
                    return
                elif res_final.status_code in [502, 504]:
                    print(f"{ts()} Error {res_final.status_code} detected (Network Timeout). Attempt {attempt+1}/{max_retries}...")
                    if attempt < max_retries - 1:
                        time.sleep(10) # Wait 10 seconds before retrying
                        continue
                
                print(f"{ts()} Escrow Failed! HTTP {res_final.status_code}: {res_final.text}")
                break
                
            except Exception as e:
                print(f"{ts()} Error during final execution: {e}")
                if attempt < max_retries - 1:
                    time.sleep(10)
                    continue
                break

    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"{ts()} System error: {e}")

if __name__ == "__main__":
    print(f"{ts()} Smart Heuristic Mode (New Round Check) ENABLED.")
    
    # Verify and print active wallet address
    account = Account.from_key(evm_private_key)
    print(f"{ts()} Active Wallet: {account.address}")
    
    print(f"{ts()} Bot will check Mineloot API for free and only pay USDC when a new round starts.")
    last_round_id = None
    last_execution_time = 0
    COOLDOWN_SECONDS = 1800  # Hemat: 1800 detik (30 menit sekali) — ~$4/hari max
    
    # Batas pengeluaran harian (dalam USDC)
    DAILY_SPEND_LIMIT = 5.0  # Max $5/hari
    daily_spend = 0.0
    day_start = time.time()
    
    # Berdasarkan bukti transaksi: Escrow $2.0 tapi di-refund $1.5
    # Jadi biaya asli per query cuma $0.5
    ESTIMATED_COST_PER_CALL = 0.5 
    MIN_BALANCE_REQUIRED = 2.0 # Tetap butuh $2 di wallet untuk buka escrow
    
    USDC_ADDRESS_BASE = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
    
    while True:
        try:
            # 1. Cek Saldo Sebelum Apapun
            saldo_sekarang = get_usdc_balance(rpc_url, account.address, USDC_ADDRESS_BASE)
            if saldo_sekarang < MIN_BALANCE_REQUIRED:
                print(f"\r{ts()} [PAUSED] Saldo USDC Kurang ({saldo_sekarang:.2f}/2.00). Menunggu deposit... (Cek tiap 60s)", end="")
                time.sleep(60)
                continue

            req = requests.get("https://api.mineloot.app/api/round/current", timeout=10)
            if req.status_code == 200:
                grid = req.json()
                current_round = grid.get("roundId", "unknown")
                current_time = time.time()
                
                if current_round != last_round_id:
                    # Cek juga apakah sudah lewat batas cooldown USDC
                    waktu_tersisa = COOLDOWN_SECONDS - (current_time - last_execution_time)
                    
                    # Reset budget harian jika sudah ganti hari
                    if current_time - day_start >= 86400:
                        daily_spend = 0.0
                        day_start = current_time
                        print(f"\n{ts()} [BUDGET] Daily spend reset.")

                    if last_round_id is None:
                        # First run
                        print(f"\n\n{ts()} Bot started (Initial Round: {current_round}). Calling MCP...")
                        last_round_id = current_round
                        last_execution_time = current_time
                        if daily_spend + ESTIMATED_COST_PER_CALL <= DAILY_SPEND_LIMIT:
                            daily_spend += ESTIMATED_COST_PER_CALL
                            jalankan_mcp(grid)
                        else:
                            print(f"\n{ts()} [BUDGET] Daily limit ${DAILY_SPEND_LIMIT} reached (spent ~${daily_spend:.1f}). Skipping.")
                    elif waktu_tersisa <= 0:
                        # New round & cooldown finished
                        if daily_spend + ESTIMATED_COST_PER_CALL <= DAILY_SPEND_LIMIT:
                            print(f"\n\n{ts()} NEW round detected! (Old ID: {last_round_id} -> New ID: {current_round}). Recalling AI MCP... [Budget: ${daily_spend:.1f}/${DAILY_SPEND_LIMIT}]")
                            last_round_id = current_round
                            last_execution_time = current_time
                            daily_spend += ESTIMATED_COST_PER_CALL
                            jalankan_mcp(grid)
                        else:
                            print(f"\n{ts()} [BUDGET] Daily limit ${DAILY_SPEND_LIMIT} reached (spent ~${daily_spend:.1f}). SKIP round {current_round}.")
                            last_round_id = current_round
                    else:
                        # Round changed, but USDC cooldown not yet reached
                        last_round_id = current_round
                        print(f"\n{ts()} Round changed to {current_round}, but SKIP (Cooldown: {int(waktu_tersisa)}s left)", end="")
                else:
                    # No changes at all
                    waktu_tersisa = max(0, COOLDOWN_SECONDS - (current_time - last_execution_time))
                    print(f"\r{ts()} Round {current_round} | Cooldown: {int(waktu_tersisa)}s | Budget: ${daily_spend:.1f}/${DAILY_SPEND_LIMIT} | Re-checking in 15s...", end="")
            else:
                print(f"\r{ts()} API check failed (HTTP {req.status_code}). Waiting 15 seconds...", end="")
        except Exception as e:
            print(f"\r{ts()} Waiting/Searching for Mineloot game server...", end="")
            
        time.sleep(5)
