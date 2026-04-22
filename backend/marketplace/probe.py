"""
NEXUS - Generic Agent Probe

Health check any marketplace agent before paying it. Same code works for
every agent regardless of who registered it or what capability it offers.

Cache window: default 30 seconds per agent_id to avoid probe-storms.
In-process built-ins always probe True (no network hop).
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Optional

import httpx


@dataclass
class ProbeResult:
    reachable: bool
    status_code: Optional[int] = None
    latency_ms: Optional[float] = None
    error: Optional[str] = None
    checked_at: float = 0.0


class AgentProber:
    """Probes agents' /health endpoints. Results cached per (agent_id, url).

    Performance note: on Windows, every `httpx.AsyncClient(...)` constructor
    call pays ~1.5-2 seconds for proxy-env-var detection via winreg. So we
    keep ONE persistent client, created lazily inside the first async call
    (so it binds to the running loop), with trust_env=False to skip the
    Windows proxy-detection slow path entirely. Result: probes go from
    ~2000ms to ~10ms.

    If the event loop is swapped (uvicorn --reload), the whole process
    restarts so the lazy client is recreated too.
    """

    def __init__(self, ttl_seconds: float = 30.0, timeout_seconds: float = 2.0):
        self.ttl = ttl_seconds
        self.timeout = timeout_seconds
        self._cache: dict[str, ProbeResult] = {}
        self._client: Optional[httpx.AsyncClient] = None

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=self.timeout,
                trust_env=False,  # skip winreg proxy detection (~1.8s on Windows)
            )
        return self._client

    async def probe(
        self,
        agent_id: str,
        callback_url: Optional[str] = None,
        force: bool = False,
    ) -> ProbeResult:
        """Check reachability of `callback_url`. In-process = always reachable."""
        if not callback_url:
            return ProbeResult(reachable=True, status_code=200, latency_ms=0.0, checked_at=time.time())

        cache_key = f"{agent_id}|{callback_url}"
        if not force:
            cached = self._cache.get(cache_key)
            if cached and (time.time() - cached.checked_at) < self.ttl:
                return cached

        # Prefer the IPv4 loopback explicitly to avoid Windows IPv6 slow-path
        # fallback for agents that only listen on 0.0.0.0 / 127.0.0.1.
        health_url = self._health_url_from(callback_url)
        if "://localhost:" in health_url:
            health_url = health_url.replace("://localhost:", "://127.0.0.1:", 1)

        client = self._get_client()
        t0 = time.time()
        try:
            resp = await client.get(health_url, timeout=self.timeout)
            latency = (time.time() - t0) * 1000
            result = ProbeResult(
                reachable=(200 <= resp.status_code < 300),
                status_code=resp.status_code,
                latency_ms=round(latency, 1),
                error=None if resp.status_code < 300 else f"HTTP {resp.status_code}",
                checked_at=time.time(),
            )
        except httpx.TimeoutException:
            result = ProbeResult(reachable=False, error="timeout", latency_ms=self.timeout * 1000, checked_at=time.time())
        except (httpx.ConnectError, httpx.RemoteProtocolError, httpx.HTTPError) as e:
            result = ProbeResult(reachable=False, error=f"{type(e).__name__}: {e}", checked_at=time.time())
        except Exception as e:
            result = ProbeResult(reachable=False, error=str(e), checked_at=time.time())

        self._cache[cache_key] = result
        return result

    def invalidate(self, agent_id: Optional[str] = None):
        """Clear the cache (all or one agent)."""
        if agent_id is None:
            self._cache.clear()
            return
        for key in list(self._cache.keys()):
            if key.startswith(f"{agent_id}|"):
                del self._cache[key]

    @staticmethod
    def _health_url_from(callback_url: str) -> str:
        """Convert `http://host:port/invoke` to `http://host:port/health`.

        Falls back to probing the callback URL itself if it doesn't end in /invoke
        (many agents return 200/405 to a bare GET on their base URL, which is
        enough to prove the process is alive)."""
        if callback_url.endswith("/invoke"):
            return callback_url[: -len("/invoke")] + "/health"
        return callback_url.rstrip("/") + "/health"


# Global singleton used by the orchestrator.
agent_prober = AgentProber()
