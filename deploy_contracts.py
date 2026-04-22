"""
NEXUS - Deploy Smart Contracts to Kite Aero Testnet using Python
No Hardhat needed - uses solcx (Solidity compiler) + web3.py directly.

Usage: python deploy_contracts.py
"""

import json
import os
import sys
from pathlib import Path
from web3 import Web3
from eth_account import Account
from dotenv import load_dotenv

# Load env
load_dotenv("backend/.env")

RPC_URL = os.getenv("KITE_RPC_URL", "https://rpc-testnet.gokite.ai/")
CHAIN_ID = int(os.getenv("KITE_CHAIN_ID", "2368"))
PRIVATE_KEY = os.getenv("DEPLOYER_PRIVATE_KEY", "")

if not PRIVATE_KEY:
    print("ERROR: Set DEPLOYER_PRIVATE_KEY in backend/.env")
    sys.exit(1)

# Connect
w3 = Web3(Web3.HTTPProvider(RPC_URL, request_kwargs={"timeout": 30}))
account = Account.from_key(PRIVATE_KEY)

print("=" * 60)
print("  NEXUS - Deploying to Kite Aero Testnet")
print("=" * 60)
print(f"  RPC: {RPC_URL}")
print(f"  Chain ID: {CHAIN_ID}")
print(f"  Deployer: {account.address}")
balance = w3.eth.get_balance(account.address)
print(f"  Balance: {w3.from_wei(balance, 'ether')} KITE")
print()

if balance == 0:
    print("ERROR: Zero balance! Get tokens from https://faucet.gokite.ai")
    sys.exit(1)

# Try to use solcx for compilation
try:
    from solcx import compile_standard, install_solc
    print("[Compiler] Installing solc 0.8.24...")
    install_solc("0.8.24")
    HAS_SOLCX = True
    print("[Compiler] solc 0.8.24 ready")
except ImportError:
    print("[Compiler] solcx not installed. Installing...")
    os.system(f"{sys.executable} -m pip install py-solc-x")
    from solcx import compile_standard, install_solc
    install_solc("0.8.24")
    HAS_SOLCX = True
    print("[Compiler] solc 0.8.24 ready")


def compile_contract(name: str, source_path: str) -> tuple:
    """Compile a Solidity contract, return (abi, bytecode)"""
    source = Path(source_path).read_text()

    compiled = compile_standard(
        {
            "language": "Solidity",
            "sources": {f"{name}.sol": {"content": source}},
            "settings": {
                "outputSelection": {
                    "*": {"*": ["abi", "evm.bytecode"]}
                },
                "optimizer": {"enabled": True, "runs": 200},
            },
        },
        solc_version="0.8.24",
    )

    contract_data = compiled["contracts"][f"{name}.sol"][name]
    abi = contract_data["abi"]
    bytecode = contract_data["evm"]["bytecode"]["object"]
    return abi, bytecode


def deploy_contract(name: str, abi: list, bytecode: str) -> str:
    """Deploy a contract and return its address"""
    contract = w3.eth.contract(abi=abi, bytecode=bytecode)

    nonce = w3.eth.get_transaction_count(account.address)
    gas_price = w3.eth.gas_price

    tx = contract.constructor().build_transaction({
        "from": account.address,
        "nonce": nonce,
        "gas": 3000000,
        "gasPrice": gas_price,
        "chainId": CHAIN_ID,
    })

    signed = w3.eth.account.sign_transaction(tx, PRIVATE_KEY)
    raw = signed.rawTransaction if hasattr(signed, 'rawTransaction') else signed.raw_transaction
    tx_hash = w3.eth.send_raw_transaction(raw)
    print(f"  TX sent: 0x{tx_hash.hex()}")

    receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)

    if receipt.status == 1:
        address = receipt.contractAddress
        print(f"  Deployed: {address}")
        print(f"  Gas used: {receipt.gasUsed}")
        print(f"  Explorer: https://testnet.kitescan.ai/address/{address}")
        return address
    else:
        print(f"  FAILED! TX: 0x{tx_hash.hex()}")
        return None


# ============================================================
# Deploy all 4 contracts
# ============================================================

contracts_dir = "contracts"
deployed = {}

contracts_to_deploy = [
    ("AgentRegistry", f"{contracts_dir}/AgentRegistry.sol"),
    ("ReputationTracker", f"{contracts_dir}/ReputationTracker.sol"),
    ("PaymentRouter", f"{contracts_dir}/PaymentRouter.sol"),
    ("GovernanceRules", f"{contracts_dir}/GovernanceRules.sol"),
]

for name, path in contracts_to_deploy:
    idx = contracts_to_deploy.index((name, path)) + 1
    total = len(contracts_to_deploy)
    print(f"\n[{idx}/{total}] Compiling {name}...")
    try:
        abi, bytecode = compile_contract(name, path)
        print(f"  Compiled OK (ABI: {len(abi)} functions)")

        print(f"  Deploying {name} to Kite Testnet...")
        address = deploy_contract(name, abi, bytecode)
        if address:
            deployed[name] = address

            # Save ABI for later use
            abi_dir = Path("backend/blockchain/abis")
            abi_dir.mkdir(parents=True, exist_ok=True)
            (abi_dir / f"{name}.json").write_text(json.dumps(abi, indent=2))
        else:
            print(f"  ERROR: {name} deployment failed!")
    except Exception as e:
        print(f"  ERROR: {e}")

# ============================================================
# Output results
# ============================================================

print("\n" + "=" * 60)

if len(deployed) == 4:
    print("  ALL 4 CONTRACTS DEPLOYED SUCCESSFULLY!")
    print("=" * 60)
    print()
    print("Add these to your backend/.env file:")
    print()
    print(f'AGENT_REGISTRY_ADDRESS={deployed.get("AgentRegistry", "")}')
    print(f'REPUTATION_TRACKER_ADDRESS={deployed.get("ReputationTracker", "")}')
    print(f'PAYMENT_ROUTER_ADDRESS={deployed.get("PaymentRouter", "")}')
    print(f'GOVERNANCE_RULES_ADDRESS={deployed.get("GovernanceRules", "")}')
    print()
    print("Verify on explorer: https://testnet.kitescan.ai/")
    print()

    # Auto-update .env file
    env_path = Path("backend/.env")
    env_content = env_path.read_text()
    env_content = env_content.replace(
        "AGENT_REGISTRY_ADDRESS=",
        f'AGENT_REGISTRY_ADDRESS={deployed.get("AgentRegistry", "")}'
    )
    env_content = env_content.replace(
        "REPUTATION_TRACKER_ADDRESS=",
        f'REPUTATION_TRACKER_ADDRESS={deployed.get("ReputationTracker", "")}'
    )
    env_content = env_content.replace(
        "PAYMENT_ROUTER_ADDRESS=",
        f'PAYMENT_ROUTER_ADDRESS={deployed.get("PaymentRouter", "")}'
    )
    env_content = env_content.replace(
        "GOVERNANCE_RULES_ADDRESS=",
        f'GOVERNANCE_RULES_ADDRESS={deployed.get("GovernanceRules", "")}'
    )
    env_path.write_text(env_content)
    print(".env file updated automatically!")
else:
    print(f"  PARTIAL DEPLOYMENT: {len(deployed)}/4 contracts")
    print("=" * 60)
    for name, addr in deployed.items():
        print(f"  {name}: {addr}")
