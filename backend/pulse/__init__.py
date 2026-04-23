"""
NEXUS - Market Pulse

A self-triggered query loop that drives the full orchestrator pipeline
(mandate + x402 payments + audit trail + reputation update) without human
involvement. The `/pulse` page exposes every autonomous run with a clickable
on-chain tx hash so judges can watch the economy run itself.

See backend/pulse/scheduler.py for the asyncio loop entry point.
"""
