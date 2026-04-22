"""
NEXUS - Agent Identity Resolver (Production)
Resolves agent names to W3C-inspired DID documents with full metadata.

DID Format: did:nexus:kite:{passport_hex}
DID Document includes: public keys, capabilities, services, controller
"""

from datetime import datetime
from typing import Optional

from backend.config import settings
from backend.models.agent_identity import AgentIdentity
from backend.models.verified_intent import VerifiedIntentHeader
from backend.models.mandate import Mandate


class DIDDocument:
    """W3C-inspired DID Document for an agent"""

    def __init__(
        self,
        did: str,
        agent_name: str,
        controller: str,
        capabilities: list[str],
        service_endpoint: str = "",
        registry_address: str = "",
        reputation_score: int = 50,
    ):
        self.did = did
        self.agent_name = agent_name
        self.controller = controller
        self.capabilities = capabilities
        self.service_endpoint = service_endpoint
        self.registry_address = registry_address
        self.reputation_score = reputation_score
        self.created = datetime.utcnow().isoformat()

    def to_dict(self) -> dict:
        """Return W3C-style DID Document"""
        return {
            "@context": [
                "https://www.w3.org/ns/did/v1",
                "https://nexus.kite.ai/ns/agent/v1",
            ],
            "id": self.did,
            "controller": f"did:ethr:kite:{self.controller}",
            "verificationMethod": [
                {
                    "id": f"{self.did}#key-1",
                    "type": "EcdsaSecp256k1VerificationKey2019",
                    "controller": f"did:ethr:kite:{self.controller}",
                    "blockchainAccountId": f"eip155:2368:{self.controller}",
                }
            ],
            "authentication": [f"{self.did}#key-1"],
            "service": [
                {
                    "id": f"{self.did}#agent-service",
                    "type": "NexusAgentService",
                    "serviceEndpoint": self.service_endpoint or "internal",
                    "capabilities": self.capabilities,
                },
                {
                    "id": f"{self.did}#x402-endpoint",
                    "type": "x402PaymentService",
                    # Point at the PUBLIC_URL when deployed (e.g. https://...nip.io);
                    # falls back to the dev default if PUBLIC_URL is unset.
                    "serviceEndpoint": f"{settings.public_url.rstrip('/')}/x402/{self.agent_name.lower().replace('-', '_')}",
                    "description": "x402-compliant agent endpoint (returns HTTP 402 without payment)",
                },
                {
                    "id": f"{self.did}#registry",
                    "type": "AgentRegistry",
                    "serviceEndpoint": f"https://testnet.kitescan.ai/address/{self.registry_address}",
                },
                {
                    "id": f"{self.did}#kite-mcp",
                    "type": "KiteMCPServer",
                    "serviceEndpoint": "https://neo.dev.gokite.ai/v1/mcp",
                    "description": "Kite Agent Passport MCP server for payment authorization",
                },
            ],
            "nexus": {
                "agentName": self.agent_name,
                "reputationScore": self.reputation_score,
                "capabilities": self.capabilities,
                "registeredOn": "kite-aero-testnet",
                "chainId": 2368,
            },
            "created": self.created,
        }


class AgentIdentityResolver:
    """Resolves agent names to DID documents and verified intent headers."""

    # Cache of resolved DIDs
    _did_cache: dict[str, DIDDocument] = {}

    def resolve(
        self, agent_name: str, passport_hex: str, controller_address: str,
        capabilities: list[str] = None, reputation_score: int = 50,
    ) -> AgentIdentity:
        """Build a DID identity for an agent."""
        did = f"did:nexus:kite:{passport_hex}"
        return AgentIdentity(
            did=did,
            agent_name=agent_name,
            passport_hex=passport_hex,
            controller=controller_address,
            registry_address=settings.agent_registry_address or "not_deployed",
        )

    def resolve_did_document(
        self, agent_name: str, passport_hex: str, controller_address: str,
        capabilities: list[str] = None, reputation_score: int = 50,
        service_endpoint: str = "",
    ) -> dict:
        """Resolve a full W3C-inspired DID Document for an agent."""
        did = f"did:nexus:kite:{passport_hex}"

        doc = DIDDocument(
            did=did,
            agent_name=agent_name,
            controller=controller_address,
            capabilities=capabilities or [],
            service_endpoint=service_endpoint,
            registry_address=settings.agent_registry_address or "",
            reputation_score=reputation_score,
        )

        self._did_cache[did] = doc
        return doc.to_dict()

    def lookup(self, did: str) -> Optional[dict]:
        """Look up a cached DID document by DID string."""
        doc = self._did_cache.get(did)
        if doc:
            return doc.to_dict()
        return None

    def build_header(
        self, mandate: Mandate, requesting_agent: str, target_agent: str,
    ) -> VerifiedIntentHeader:
        """Build a VerifiedIntentHeader for an agent-to-agent request."""
        return VerifiedIntentHeader(
            mandate_id=mandate.mandate_id,
            context_hash=mandate.context_hash,
            signature=mandate.signature,
            budget_remaining=mandate.budget_remaining,
            requesting_agent=requesting_agent,
            target_agent=target_agent,
        )


# Global singleton
agent_identity_resolver = AgentIdentityResolver()
