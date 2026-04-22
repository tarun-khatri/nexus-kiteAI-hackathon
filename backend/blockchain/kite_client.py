"""
NEXUS - Kite Blockchain Client (REAL ON-CHAIN)
Connects to Kite Aero Testnet and makes REAL transactions:
- Deploys and interacts with smart contracts
- Registers agents on-chain via AgentRegistry
- Makes real x402 payments via PaymentRouter
- Tracks reputation on-chain via ReputationTracker
- Enforces governance on-chain via GovernanceRules

Every transaction is verifiable at https://testnet.kitescan.ai/
"""

import json
import hashlib
import asyncio
from pathlib import Path
from typing import Optional
from web3 import Web3
from eth_account import Account

from backend.config import settings


# Load ABIs from compiled contract files
def _load_abi(name: str) -> list:
    abi_path = Path(__file__).parent / "abis" / f"{name}.json"
    if abi_path.exists():
        return json.loads(abi_path.read_text())
    return []


AGENT_REGISTRY_ABI = _load_abi("AgentRegistry")

REPUTATION_TRACKER_ABI = _load_abi("ReputationTracker")

PAYMENT_ROUTER_ABI = _load_abi("PaymentRouter")

GOVERNANCE_RULES_ABI = _load_abi("GovernanceRules")


class KiteClient:
    """
    REAL Kite Aero Testnet client.
    Every method makes actual on-chain transactions verifiable at:
    https://testnet.kitescan.ai/
    """

    def __init__(self):
        self.w3: Optional[Web3] = None
        self.account = None
        self.connected = False

        # Contract instances (set after deployment/loading)
        self.registry_contract = None
        self.reputation_contract = None
        self.payment_contract = None
        self.governance_contract = None

        # Track passport IDs for agents
        self.passport_ids: dict[str, bytes] = {}

        # Transaction log
        self.tx_hashes: list[str] = []

        # Serialize all outgoing txs so concurrent fire-and-forget background
        # tasks (reputation writes, audit-trail writes, mandate finalizes)
        # can't collide on the deployer wallet's nonce. Every on-chain tx
        # from this process goes through this lock.
        self._tx_lock: Optional[asyncio.Lock] = None

    async def connect(self) -> bool:
        """Connect to Kite Aero Testnet"""
        # Bind the tx-serialization lock to the running event loop exactly
        # once, here, so it's created synchronously before any concurrent
        # _send_tx calls can race to create competing locks.
        if self._tx_lock is None:
            self._tx_lock = asyncio.Lock()
        try:
            self.w3 = Web3(Web3.HTTPProvider(settings.kite_rpc_url, request_kwargs={"timeout": 30}))

            if self.w3.is_connected():
                chain_id = self.w3.eth.chain_id
                print(f"[Kite] Connected to Kite Aero Testnet (Chain ID: {chain_id})")

                # Load deployer account
                if settings.deployer_private_key:
                    self.account = Account.from_key(settings.deployer_private_key)
                    balance = self.w3.eth.get_balance(self.account.address)
                    balance_kite = self.w3.from_wei(balance, "ether")
                    print(f"[Kite] Deployer: {self.account.address}")
                    print(f"[Kite] Balance: {balance_kite:.4f} KITE")

                    if balance == 0:
                        print("[Kite] WARNING: Zero balance! Get tokens from https://faucet.gokite.ai")
                else:
                    print("[Kite] WARNING: No DEPLOYER_PRIVATE_KEY set. Read-only mode.")

                self.connected = True

                # Load existing contracts if addresses are configured
                await self._load_contracts()

                return True
            else:
                print("[Kite] Failed to connect to RPC")
        except Exception as e:
            print(f"[Kite] Connection error: {e}")

        self.connected = False
        return False

    async def _load_contracts(self):
        """Load deployed contract instances"""
        if settings.agent_registry_address:
            self.registry_contract = self.w3.eth.contract(
                address=Web3.to_checksum_address(settings.agent_registry_address),
                abi=AGENT_REGISTRY_ABI,
            )
            print(f"[Kite] AgentRegistry loaded: {settings.agent_registry_address}")

        if settings.reputation_tracker_address:
            self.reputation_contract = self.w3.eth.contract(
                address=Web3.to_checksum_address(settings.reputation_tracker_address),
                abi=REPUTATION_TRACKER_ABI,
            )
            print(f"[Kite] ReputationTracker loaded: {settings.reputation_tracker_address}")

        if settings.payment_router_address:
            self.payment_contract = self.w3.eth.contract(
                address=Web3.to_checksum_address(settings.payment_router_address),
                abi=PAYMENT_ROUTER_ABI,
            )
            print(f"[Kite] PaymentRouter loaded: {settings.payment_router_address}")

        if settings.governance_rules_address:
            self.governance_contract = self.w3.eth.contract(
                address=Web3.to_checksum_address(settings.governance_rules_address),
                abi=GOVERNANCE_RULES_ABI,
            )
            print(f"[Kite] GovernanceRules loaded: {settings.governance_rules_address}")

    def _get_passport_id(self, agent_name: str) -> bytes:
        """Generate a deterministic bytes32 passport ID from agent name"""
        if agent_name in self.passport_ids:
            return self.passport_ids[agent_name]
        passport = Web3.solidity_keccak(["string"], [agent_name])
        self.passport_ids[agent_name] = passport
        return passport

    async def _send_tx(self, func, description: str) -> Optional[str]:
        """Build, sign, and send a transaction. Returns tx hash or None.

        Serialized via `self._tx_lock` so concurrent background tasks
        (reputation write, audit-trail write, mandate finalization, etc.)
        don't race for the same nonce and produce
        `replacement transaction underpriced` or `nonce too low` errors.
        """
        if not self.connected or not self.account:
            print(f"[Kite] Cannot send tx ({description}): not connected or no account")
            return None

        # Defensive: if _send_tx is somehow called before connect() ran,
        # create the lock now. The double-check isn't atomic but is safe
        # on CPython for this simple branch (no awaits inside).
        if self._tx_lock is None:
            self._tx_lock = asyncio.Lock()

        async with self._tx_lock:
            # Two attempts: if the first trips on "nonce too low" or
            # "replacement transaction underpriced" (common right after a
            # restart when the old container left txs in the mempool), wait
            # 2s and retry once with a freshly-fetched nonce.
            for attempt in (1, 2):
                try:
                    nonce = self.w3.eth.get_transaction_count(self.account.address, "pending")
                    gas_price = self.w3.eth.gas_price
                    # Bump gas price slightly on retry to beat underpriced-replacement logic.
                    if attempt == 2:
                        gas_price = int(gas_price * 1.2) + 1

                    tx = func.build_transaction({
                        "from": self.account.address,
                        "nonce": nonce,
                        "gas": 500000,
                        "gasPrice": gas_price,
                        "chainId": settings.kite_chain_id,
                    })

                    signed = self.w3.eth.account.sign_transaction(tx, settings.deployer_private_key)
                    raw = signed.rawTransaction if hasattr(signed, 'rawTransaction') else signed.raw_transaction
                    tx_hash = self.w3.eth.send_raw_transaction(raw)
                    tx_hash_hex = tx_hash.hex()

                    receipt = await asyncio.to_thread(
                        self.w3.eth.wait_for_transaction_receipt, tx_hash, 60
                    )

                    if receipt.status == 1:
                        self.tx_hashes.append(tx_hash_hex)
                        print(f"[Kite] TX SUCCESS: {description}")
                        print(f"[Kite]   Hash: {tx_hash_hex}")
                        print(f"[Kite]   Gas used: {receipt.gasUsed}")
                        print(f"[Kite]   Explorer: https://testnet.kitescan.ai/tx/0x{tx_hash_hex}")
                        return tx_hash_hex
                    else:
                        print(f"[Kite] TX FAILED: {description} (status=0, attempt {attempt})")
                        if attempt == 1:
                            await asyncio.sleep(2)
                            continue
                        return None

                except Exception as e:
                    err_str = str(e).lower()
                    is_nonce_issue = (
                        "nonce too low" in err_str
                        or "replacement transaction underpriced" in err_str
                        or "already known" in err_str
                    )
                    if attempt == 1 and is_nonce_issue:
                        print(f"[Kite] TX transient ({description}): {e} — retrying in 2s")
                        await asyncio.sleep(2)
                        continue
                    print(f"[Kite] TX ERROR ({description}): {e}")
                    return None
            return None

    # ========================================================
    # Agent Registration (AgentRegistry contract)
    # ========================================================

    async def register_agent(self, agent_name: str, description: str,
                              capabilities: list[str], price_per_query: float) -> Optional[str]:
        """Register an agent on-chain in the AgentRegistry contract"""
        if not self.registry_contract:
            print(f"[Kite] AgentRegistry not deployed. Skipping registration for {agent_name}")
            return None

        passport_id = self._get_passport_id(agent_name)
        # Convert price to wei-like units (multiply by 10^6 for USDC-like precision)
        price_units = int(price_per_query * 1_000_000)

        tx_hash = await self._send_tx(
            self.registry_contract.functions.registerAgent(
                passport_id, agent_name, description, capabilities, price_units
            ),
            f"Register agent: {agent_name}",
        )
        return tx_hash

    async def get_agent_on_chain(self, agent_name: str) -> Optional[dict]:
        """Query agent details from on-chain registry"""
        if not self.registry_contract:
            return None

        try:
            passport_id = self._get_passport_id(agent_name)
            result = self.registry_contract.functions.getAgent(passport_id).call()
            return {
                "wallet": result[0],
                "name": result[1],
                "price": result[2],
                "reputation": result[3],
                "active": result[4],
                "jobs": result[5],
            }
        except Exception as e:
            print(f"[Kite] Error reading agent {agent_name}: {e}")
            return None

    async def increment_agent_jobs(self, agent_name: str) -> Optional[str]:
        """Increment job counter on-chain"""
        if not self.registry_contract:
            return None

        passport_id = self._get_passport_id(agent_name)
        return await self._send_tx(
            self.registry_contract.functions.incrementJobs(passport_id),
            f"Increment jobs for {agent_name}",
        )

    # ========================================================
    # Reputation (ReputationTracker contract)
    # ========================================================

    async def init_reputation(self, agent_name: str) -> Optional[str]:
        """Initialize reputation for an agent on-chain"""
        if not self.reputation_contract:
            return None

        passport_id = self._get_passport_id(agent_name)
        return await self._send_tx(
            self.reputation_contract.functions.initializeAgent(passport_id),
            f"Init reputation for {agent_name}",
        )

    async def record_success(self, agent_name: str, quality_score: int) -> Optional[str]:
        """Record successful job with quality score on-chain"""
        if not self.reputation_contract:
            return None

        passport_id = self._get_passport_id(agent_name)
        return await self._send_tx(
            self.reputation_contract.functions.recordSuccess(passport_id, quality_score),
            f"Record success for {agent_name} (quality: {quality_score})",
        )

    async def record_failure(self, agent_name: str) -> Optional[str]:
        """Record failed job on-chain"""
        if not self.reputation_contract:
            return None

        passport_id = self._get_passport_id(agent_name)
        return await self._send_tx(
            self.reputation_contract.functions.recordFailure(passport_id),
            f"Record failure for {agent_name}",
        )

    async def get_reputation(self, agent_name: str) -> Optional[int]:
        """Read reputation score from chain"""
        if not self.reputation_contract:
            return None

        try:
            passport_id = self._get_passport_id(agent_name)
            return self.reputation_contract.functions.getReputation(passport_id).call()
        except Exception:
            return None

    # ========================================================
    # Payments (PaymentRouter contract)
    # ========================================================

    async def fund_agent(self, agent_name: str, amount: float) -> Optional[str]:
        """Fund an agent's on-chain balance for payments"""
        if not self.payment_contract:
            return None

        passport_id = self._get_passport_id(agent_name)
        amount_units = int(amount * 1_000_000)
        return await self._send_tx(
            self.payment_contract.functions.fundAgent(passport_id, amount_units),
            f"Fund {agent_name} with ${amount}",
        )

    async def pay_for_service(self, from_agent: str, to_agent: str,
                               amount: float, purpose: str) -> Optional[str]:
        """
        Execute a REAL x402 payment between agents on Kite chain.
        This is the core of the agent economy - every payment is on-chain.
        """
        if not self.payment_contract:
            print(f"[Kite] PaymentRouter not deployed. Cannot execute payment.")
            return None

        from_id = self._get_passport_id(from_agent)
        to_id = self._get_passport_id(to_agent)
        amount_units = int(amount * 1_000_000)

        tx_hash = await self._send_tx(
            self.payment_contract.functions.payForService(from_id, to_id, amount_units, purpose),
            f"x402 Payment: {from_agent} -> {to_agent} ${amount} ({purpose})",
        )
        return tx_hash

    async def get_payment_count(self) -> int:
        """Get total payment count from on-chain"""
        if not self.payment_contract:
            return 0
        try:
            return self.payment_contract.functions.getPaymentCount().call()
        except Exception:
            return 0

    async def get_agent_balance(self, agent_name: str) -> float:
        """Read agent balance from chain"""
        if not self.payment_contract:
            return 0.0
        try:
            passport_id = self._get_passport_id(agent_name)
            balance = self.payment_contract.functions.getBalance(passport_id).call()
            return balance / 1_000_000
        except Exception:
            return 0.0

    async def get_agent_total_earned(self, agent_name: str) -> float:
        """Read total earnings for an agent from PaymentRouter contract."""
        if not self.payment_contract:
            return 0.0
        try:
            passport_id = self._get_passport_id(agent_name)
            raw = self.payment_contract.functions.getTotalEarned(passport_id).call()
            return float(raw) / 1_000_000
        except Exception:
            return 0.0

    async def get_agent_total_spent(self, agent_name: str) -> float:
        """Read total spending for an agent from PaymentRouter contract."""
        if not self.payment_contract:
            return 0.0
        try:
            passport_id = self._get_passport_id(agent_name)
            raw = self.payment_contract.functions.getTotalSpent(passport_id).call()
            return float(raw) / 1_000_000
        except Exception:
            return 0.0

    async def get_all_agents_on_chain(self) -> list[dict]:
        """
        Discover ALL agents registered in the AgentRegistry contract,
        regardless of whether we know about them locally.

        Reads the chain as the SOURCE OF TRUTH for who exists in this economy.

        Returns: [
            {"passport_id": "0x..hex..", "wallet": "0x...", "name": "...",
             "description": "...", "price": 0.0001, "reputation": 50,
             "active": True, "jobs": 5, "registered_at": 1234567890}
        ]

        Note: capabilities are NOT included (Solidity auto-getter doesn't return
        dynamic arrays). They're augmented from local metadata in agent_catalog.
        """
        if not self.registry_contract:
            return []

        agents: list[dict] = []
        try:
            count = self.registry_contract.functions.getAgentCount().call()
        except Exception as e:
            print(f"[Kite] get_all_agents_on_chain count failed: {e}")
            return []

        for idx in range(count):
            try:
                passport_bytes = self.registry_contract.functions.getAgentAt(idx).call()
                # getAgentFull returns: (wallet, name, description, price, reputation, active, jobs, registered_at)
                full = self.registry_contract.functions.getAgentFull(passport_bytes).call()
                wallet, name, description, price, reputation, active, jobs, registered_at = full

                agents.append({
                    "passport_id": passport_bytes.hex() if isinstance(passport_bytes, (bytes, bytearray)) else str(passport_bytes),
                    "wallet": wallet,
                    "name": name,
                    "description": description,
                    "price": float(price) / 1_000_000,
                    "reputation": int(reputation),
                    "active": bool(active),
                    "jobs": int(jobs),
                    "registered_at": int(registered_at),
                })
            except Exception as e:
                print(f"[Kite] get_all_agents_on_chain entry {idx} failed: {e}")
                continue

        return agents

    async def get_all_payments_from_chain(self, limit: int = 200) -> list[dict]:
        """
        Read ALL payment records from the PaymentRouter contract.
        This is the DECENTRALIZED payment history -- no SQLite, no cache,
        straight from the blockchain.

        Returns newest-first list of:
        [{"from_passport": "0x...", "to_passport": "0x...", "amount": 0.0001,
          "purpose": "data_collection", "mandate_id": "0x...", "timestamp": 1234567890}]
        """
        if not self.payment_contract:
            return []

        try:
            count = self.payment_contract.functions.getPaymentCount().call()
        except Exception as e:
            print(f"[Kite] get_all_payments_from_chain count failed: {e}")
            return []

        payments: list[dict] = []
        # Read from newest to oldest (most recent first)
        start = max(0, count - limit)
        for idx in range(count - 1, start - 1, -1):
            try:
                record = self.payment_contract.functions.payments(idx).call()
                from_agent, to_agent, amount, purpose, mandate_id, timestamp = record
                payments.append({
                    "from_passport": from_agent.hex() if isinstance(from_agent, (bytes, bytearray)) else str(from_agent),
                    "to_passport": to_agent.hex() if isinstance(to_agent, (bytes, bytearray)) else str(to_agent),
                    "amount": float(amount) / 1_000_000,
                    "purpose": purpose,
                    "mandate_id": mandate_id.hex() if isinstance(mandate_id, (bytes, bytearray)) else str(mandate_id),
                    "timestamp": int(timestamp),
                    "index": idx,
                })
            except Exception as e:
                print(f"[Kite] get_all_payments_from_chain entry {idx} failed: {e}")
                continue

        return payments

    # ========================================================
    # Governance (GovernanceRules contract)
    # ========================================================

    async def check_governance(self, agent_name: str, amount: float) -> tuple[bool, str]:
        """Check if payment is allowed by on-chain governance rules"""
        if not self.governance_contract:
            return True, "No governance contract (allowed by default)"

        try:
            passport_id = self._get_passport_id(agent_name)
            amount_units = int(amount * 1_000_000)
            allowed, reason = self.governance_contract.functions.checkAllowed(
                passport_id, amount_units
            ).call()
            return allowed, reason
        except Exception as e:
            return True, f"Governance check error: {e}"

    async def update_max_per_tx(self, new_max: float) -> Optional[str]:
        """Update max spend per transaction on-chain"""
        if not self.governance_contract:
            return None

        amount_units = int(new_max * 1_000_000)
        return await self._send_tx(
            self.governance_contract.functions.setGlobalMaxPerTx(amount_units),
            f"Update governance: max_per_tx = ${new_max}",
        )

    async def update_max_per_day(self, new_max: float) -> Optional[str]:
        """Update max spend per day on-chain (GovernanceRules.setGlobalMaxPerDay)"""
        if not self.governance_contract:
            return None

        amount_units = int(new_max * 1_000_000)
        return await self._send_tx(
            self.governance_contract.functions.setGlobalMaxPerDay(amount_units),
            f"Update governance: max_per_day = ${new_max}",
        )

    async def update_min_reputation(self, new_min: int) -> Optional[str]:
        """Update minimum reputation threshold on-chain (GovernanceRules.setMinReputation)"""
        if not self.governance_contract:
            return None

        return await self._send_tx(
            self.governance_contract.functions.setMinReputation(new_min),
            f"Update governance: min_reputation = {new_min}",
        )

    # ========================================================
    # Audit Trail (On-Chain Traceability)
    # ========================================================

    async def log_audit_trail(self, traceability_hash: str, mandate_id: str) -> Optional[str]:
        """
        Log a traceability hash on-chain as a data-bearing transaction.
        The hash is embedded in the transaction's calldata.
        Verifiable on block explorer by decoding the input data.

        Goes through the same `_tx_lock` used by `_send_tx` so it never
        races for a nonce with a concurrent reputation/payment write.
        """
        if not self.connected or not self.account:
            print("[Kite] Cannot log audit trail: not connected or no account")
            return None

        if self._tx_lock is None:
            self._tx_lock = asyncio.Lock()

        audit_data = f"NEXUS_AUDIT:{mandate_id}:{traceability_hash}"
        data_hex = "0x" + audit_data.encode().hex()

        async with self._tx_lock:
            for attempt in (1, 2):
                try:
                    nonce = self.w3.eth.get_transaction_count(self.account.address, "pending")
                    gas_price = self.w3.eth.gas_price
                    if attempt == 2:
                        gas_price = int(gas_price * 1.2) + 1

                    tx = {
                        "from": self.account.address,
                        "to": self.account.address,
                        "value": 0,
                        "data": data_hex,
                        "nonce": nonce,
                        "gas": 100000,
                        "gasPrice": gas_price,
                        "chainId": settings.kite_chain_id,
                    }

                    signed = self.w3.eth.account.sign_transaction(tx, settings.deployer_private_key)
                    raw = signed.rawTransaction if hasattr(signed, 'rawTransaction') else signed.raw_transaction
                    tx_hash = self.w3.eth.send_raw_transaction(raw)
                    tx_hash_hex = tx_hash.hex()

                    receipt = await asyncio.to_thread(
                        self.w3.eth.wait_for_transaction_receipt, tx_hash, 60
                    )
                    if receipt.status == 1:
                        self.tx_hashes.append(tx_hash_hex)
                        print(f"[Kite] AUDIT TRAIL on-chain: {tx_hash_hex}")
                        print(f"[Kite]   Explorer: https://testnet.kitescan.ai/tx/0x{tx_hash_hex}")
                        return tx_hash_hex
                    else:
                        print(f"[Kite] Audit trail TX failed (status=0, attempt {attempt})")
                        if attempt == 1:
                            await asyncio.sleep(2)
                            continue
                        return None

                except Exception as e:
                    err_str = str(e).lower()
                    is_nonce_issue = (
                        "nonce too low" in err_str
                        or "replacement transaction underpriced" in err_str
                        or "already known" in err_str
                    )
                    if attempt == 1 and is_nonce_issue:
                        print(f"[Kite] Audit trail transient: {e} — retrying in 2s")
                        await asyncio.sleep(2)
                        continue
                    print(f"[Kite] Audit trail TX error: {e}")
                    return None
            return None

    # ========================================================
    # Utility
    # ========================================================

    @property
    def is_connected(self) -> bool:
        return self.connected

    @property
    def contracts_deployed(self) -> bool:
        return all([
            self.registry_contract,
            self.reputation_contract,
            self.payment_contract,
            self.governance_contract,
        ])

    def get_usdt_balance(self) -> float:
        """Check Test USDT balance for x402 payments"""
        if not self.w3 or not self.account:
            return 0.0
        try:
            usdt_addr = settings.kite_test_usdt
            abi = [{"inputs":[{"name":"account","type":"address"}],"name":"balanceOf","outputs":[{"name":"","type":"uint256"}],"stateMutability":"view","type":"function"}]
            contract = self.w3.eth.contract(address=self.w3.to_checksum_address(usdt_addr), abi=abi)
            raw = contract.functions.balanceOf(self.account.address).call()
            return raw / 1e18
        except Exception:
            return 0.0

    @property
    def explorer_base(self) -> str:
        return "https://testnet.kitescan.ai"

    def get_tx_explorer_url(self, tx_hash: str) -> str:
        return f"{self.explorer_base}/tx/0x{tx_hash}" if not tx_hash.startswith("0x") else f"{self.explorer_base}/tx/{tx_hash}"

    def get_all_tx_hashes(self) -> list[dict]:
        """Return all transaction hashes with explorer URLs"""
        return [
            {"hash": h, "explorer": self.get_tx_explorer_url(h)}
            for h in self.tx_hashes
        ]


# Global Kite client
kite_client = KiteClient()
