"""
NEXUS - Universal Invocation Envelope

Every agent call — in-process, HTTP marketplace, or any future transport —
goes through InvocationRequest in / InvocationResult out. Downstream code
branches on `status`, never on "which agent was this".

This is the core abstraction that makes the orchestrator dynamic: the same
code path handles success, failure, timeout, and unreachable cases for any
agent with any capability.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class InvocationStatus(str, Enum):
    SUCCESS = "success"
    PARTIAL = "partial"
    FAILED = "failed"
    TIMEOUT = "timeout"
    UNREACHABLE = "unreachable"
    INVALID_INPUT = "invalid_input"


class ErrorCode(str, Enum):
    """Canonical error codes. Agents may add vendor-specific codes in `error_message`."""
    INVALID_INPUT = "invalid_input"
    UNREACHABLE = "unreachable"
    UPSTREAM_4XX = "upstream_4xx"
    UPSTREAM_5XX = "upstream_5xx"
    TIMEOUT = "timeout"
    AGENT_ERROR = "agent_error"
    ORCHESTRATOR_ERROR = "orchestrator_error"


class InvocationRequest(BaseModel):
    """Request passed to the orchestrator's invoke() method."""
    request_id: str = Field(default_factory=lambda: uuid.uuid4().hex[:16])
    mandate_id: Optional[str] = None
    agent_id: str
    agent_name: str
    capability: str
    input: dict[str, Any] = Field(default_factory=dict)
    timeout_ms: int = 30_000
    emitted_at: datetime = Field(default_factory=datetime.utcnow)
    # Filled in by orchestrator after a successful probe + payment:
    payment_tx_hash: Optional[str] = None


class InvocationResult(BaseModel):
    """
    Uniform result from any agent invocation. Populated whether the call
    succeeded, failed, timed out, or was blocked at probe time.

    `output` is populated on success or partial; `error_*` populated on failure.
    Schema-level validation (input_schema/output_schema) happens inside the
    orchestrator; agents receive already-validated input.
    """
    request_id: str
    agent_id: str
    agent_name: str
    capability: str
    status: InvocationStatus

    # Success path
    output: Optional[dict[str, Any]] = None

    # Failure path
    error_code: Optional[ErrorCode] = None
    error_message: Optional[str] = None
    error_hint: Optional[str] = None

    # Bookkeeping
    duration_ms: float = 0.0
    payment_tx_hash: Optional[str] = None
    source: str = "builtin"  # "builtin" | "marketplace" | "in_process" | etc.
    completed_at: datetime = Field(default_factory=datetime.utcnow)

    def is_success(self) -> bool:
        return self.status == InvocationStatus.SUCCESS

    def model_dump_for_report(self) -> dict:
        """Serializer used when embedding an envelope inside report.sections."""
        d = self.model_dump(mode="json")
        # Keep only what the frontend needs; drop internal bookkeeping.
        d.pop("request_id", None)
        return d


def wrap_legacy_result(
    raw: Any,
    *,
    request: InvocationRequest,
    started_at: float,
    source: str,
    payment_tx_hash: Optional[str] = None,
) -> InvocationResult:
    """
    Back-compat wrapper. Takes whatever a legacy agent returned (dict with
    "error" key, raw data dict, random object) and produces a typed envelope.

    Rules:
    - dict with "error" -> FAILED (error_message=value, error_hint=result.get("hint"))
    - dict without "error" -> SUCCESS (output = the dict)
    - anything else -> SUCCESS (output = {"raw": <stringified>})
    - None -> FAILED (error_code=AGENT_ERROR)
    """
    import time
    duration_ms = (time.time() - started_at) * 1000

    base = {
        "request_id": request.request_id,
        "agent_id": request.agent_id,
        "agent_name": request.agent_name,
        "capability": request.capability,
        "duration_ms": round(duration_ms, 1),
        "payment_tx_hash": payment_tx_hash,
        "source": source,
    }

    if raw is None:
        return InvocationResult(
            **base,
            status=InvocationStatus.FAILED,
            error_code=ErrorCode.AGENT_ERROR,
            error_message="Agent returned no output.",
        )

    if isinstance(raw, dict):
        # If the envelope is already in our new shape, trust it.
        if "status" in raw and raw.get("status") in (s.value for s in InvocationStatus):
            try:
                return InvocationResult(**{**base, **raw})
            except Exception:
                pass  # fall through to legacy handling

        if "error" in raw and raw["error"]:
            return InvocationResult(
                **base,
                status=InvocationStatus.FAILED,
                error_code=ErrorCode.AGENT_ERROR,
                error_message=str(raw["error"]),
                error_hint=raw.get("hint"),
            )

        return InvocationResult(
            **base,
            status=InvocationStatus.SUCCESS,
            output=raw,
        )

    # Not a dict — stringify and succeed.
    return InvocationResult(
        **base,
        status=InvocationStatus.SUCCESS,
        output={"raw": str(raw)},
    )
