"""
NEXUS - Configuration
Loads all environment variables and provides app-wide settings.
All services used are FREE tier.
"""

from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    """Application settings loaded from .env file"""

    # --- Free LLM APIs ---
    groq_api_key: Optional[str] = None
    gemini_api_key: Optional[str] = None
    ollama_enabled: bool = True
    ollama_model: str = "llama3.1:8b"

    # LLM priority order
    llm_primary: str = "groq"
    llm_fallback: str = "gemini"
    llm_emergency: str = "ollama"

    # --- Free Data APIs ---
    newsapi_key: Optional[str] = None
    cryptopanic_key: Optional[str] = None
    coingecko_api_key: Optional[str] = None
    helius_api_key: Optional[str] = None
    twitter_api_key: Optional[str] = None

    # --- Kite Blockchain (Testnet = FREE) ---
    kite_rpc_url: str = "https://rpc-testnet.gokite.ai"
    kite_chain_id: int = 2368
    deployer_private_key: Optional[str] = None

    # Kite x402 Protocol
    kite_test_usdt: str = "0x0fF5393387ad2f9f691FD6Fd28e07E3969e27e63"
    facilitator_url: str = "https://facilitator.pieverse.io"
    facilitator_address: str = "0x12343e649e6b2b2b77649DFAb88f103c02F3C78b"
    kite_mcp_url: str = "https://neo.dev.gokite.ai/v1/mcp"

    # Deployed contract addresses
    agent_registry_address: Optional[str] = None
    reputation_tracker_address: Optional[str] = None
    payment_router_address: Optional[str] = None
    governance_rules_address: Optional[str] = None

    # --- Server Config ---
    backend_host: str = "0.0.0.0"
    backend_port: int = 8000
    frontend_url: str = "http://localhost:3000"
    public_url: str = "http://localhost:8000"  # Public base URL for x402 resource fields

    class Config:
        env_file = "backend/.env"
        env_file_encoding = "utf-8"
        extra = "ignore"


# Try multiple .env locations
import os
_env_paths = ["backend/.env", ".env", os.path.join(os.path.dirname(__file__), ".env")]
for _p in _env_paths:
    if os.path.exists(_p):
        settings = Settings(_env_file=_p)
        break
else:
    settings = Settings()


# --- Agent Configuration ---
AGENTS_CONFIG = {
    "data_agent": {
        "name": "Nexus-DataAgent-v1",
        "capabilities": ["twitter_data", "price_data", "whale_data", "news_data"],
        "price_per_query": 0.0001,  # USDC
        "description": "Collects real-time data from Twitter, markets, news, and on-chain sources",
    },
    "analyst_agent": {
        "name": "Nexus-AnalystAgent-v1",
        "capabilities": ["sentiment_analysis", "price_trend", "whale_analysis", "news_summary"],
        "price_per_query": 0.0002,
        "description": "Analyzes raw data to produce sentiment scores, price trends, and insights",
    },
    "report_agent": {
        "name": "Nexus-ReportAgent-v1",
        "capabilities": ["report_generation", "orchestration"],
        "price_per_query": 0.0005,
        "description": "Orchestrates other agents and compiles comprehensive reports",
    },
    "alert_agent": {
        "name": "Nexus-AlertAgent-v1",
        "capabilities": ["price_alerts", "sentiment_alerts", "whale_alerts"],
        "price_per_query": 0.0001,
        "description": "Monitors thresholds and sends real-time notifications",
    },
    "audit_agent": {
        "name": "Nexus-AuditAgent-v1",
        "capabilities": ["quality_audit", "data_verification", "consistency_check"],
        "price_per_query": 0.0001,
        "description": "Verifies other agents outputs for accuracy and quality",
    },
}

# --- Governance Defaults ---
DEFAULT_GOVERNANCE = {
    "max_spend_per_tx": 0.001,       # $0.001 USDC max per transaction
    "max_spend_per_day": 0.01,        # $0.01 USDC max per day
    "max_spend_per_agent": 0.005,     # $0.005 USDC max per agent per day
    "min_reputation_to_hire": 20,     # Minimum reputation score to hire an agent
    "audit_threshold": 70,            # Minimum audit score to pass
    "mandate_ttl_seconds": 300,       # Default mandate TTL (5 minutes)
    "mandate_budget_multiplier": 3.0, # Budget = sum(agent prices) * multiplier
}
