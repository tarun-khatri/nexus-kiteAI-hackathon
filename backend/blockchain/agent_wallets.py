"""
NEXUS - Agent Wallet Manager
Creates deterministic wallets for each agent.

Each agent gets its own Ethereum-compatible wallet address derived from:
  wallet = keccak256(deployer_address + agent_passport_id)

This gives each agent a unique, deterministic address that:
1. Can be funded independently
2. Can be verified on the block explorer
3. Is derived from the agent's on-chain identity

Wallets are deterministic EOAs derived from the deployer key -- a Python-native
approach since Kite's AA SDK (gokite-aa-sdk) is JavaScript/npm only.
"""

from web3 import Web3
from eth_account import Account
from typing import Optional

from backend.config import settings


class AgentWalletManager:
    """
    Manages deterministic wallets for each agent.
    Each agent gets a unique address derived from its passport.
    """

    def __init__(self):
        self.wallets: dict[str, dict] = {}  # agent_name -> wallet info
        self._deployer_address = ""

    def initialize(self, deployer_address: str):
        """Set deployer address for wallet derivation"""
        self._deployer_address = deployer_address

    def derive_wallet(self, agent_name: str, passport_hex: str) -> dict:
        """
        Derive a deterministic wallet address for an agent.
        Uses keccak256(deployer + passport) as a seed.
        """
        if agent_name in self.wallets:
            return self.wallets[agent_name]

        # Derive a deterministic private key from deployer + passport
        seed = Web3.solidity_keccak(
            ["address", "bytes32"],
            [
                Web3.to_checksum_address(self._deployer_address) if self._deployer_address else "0x0000000000000000000000000000000000000000",
                bytes.fromhex(passport_hex) if len(passport_hex) == 64 else Web3.solidity_keccak(["string"], [passport_hex]),
            ]
        )

        # Create account from derived key
        account = Account.from_key(seed)

        wallet_info = {
            "agent_name": agent_name,
            "address": account.address,
            "passport_hex": passport_hex,
            "derived_from": self._deployer_address,
            "type": "derived_eoa",
            "balance_kite": 0.0,
            "funded": False,
        }

        self.wallets[agent_name] = wallet_info
        print(f"[Wallet] Derived wallet for {agent_name}: {account.address}")
        return wallet_info

    def get_wallet(self, agent_name: str) -> Optional[dict]:
        """Get wallet info for an agent"""
        return self.wallets.get(agent_name)

    def get_all_wallets(self) -> list[dict]:
        """Get all agent wallets"""
        return list(self.wallets.values())

    async def fund_wallet(self, agent_name: str, amount_kite: float) -> Optional[str]:
        """
        Fund an agent's derived wallet with KITE from the deployer.
        Returns tx hash if successful.
        """
        wallet = self.wallets.get(agent_name)
        if not wallet or not settings.deployer_private_key:
            return None

        try:
            w3 = Web3(Web3.HTTPProvider(settings.kite_rpc_url, request_kwargs={"timeout": 30}))
            deployer = Account.from_key(settings.deployer_private_key)

            nonce = w3.eth.get_transaction_count(deployer.address)
            tx = {
                "from": deployer.address,
                "to": Web3.to_checksum_address(wallet["address"]),
                "value": w3.to_wei(amount_kite, "ether"),
                "nonce": nonce,
                "gas": 21000,
                "gasPrice": w3.eth.gas_price,
                "chainId": settings.kite_chain_id,
            }

            signed = w3.eth.account.sign_transaction(tx, settings.deployer_private_key)
            raw = signed.rawTransaction if hasattr(signed, 'rawTransaction') else signed.raw_transaction
            tx_hash = w3.eth.send_raw_transaction(raw)
            receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=60)

            if receipt.status == 1:
                wallet["funded"] = True
                wallet["balance_kite"] = amount_kite
                print(f"[Wallet] Funded {agent_name} with {amount_kite} KITE: {tx_hash.hex()}")
                return tx_hash.hex()

        except Exception as e:
            print(f"[Wallet] Fund error for {agent_name}: {e}")

        return None


# Global singleton
agent_wallet_manager = AgentWalletManager()
