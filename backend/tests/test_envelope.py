"""
Tests for orchestration.envelope — the universal invocation wrapper that makes
success, failure, timeout, and unreachable cases structurally identical.
"""

from backend.orchestration.envelope import (
    InvocationRequest, InvocationResult, InvocationStatus, ErrorCode,
    wrap_legacy_result,
)


def test_legacy_error_dict_becomes_failed_envelope():
    req = InvocationRequest(
        agent_id="test", agent_name="TestAgent", capability="foo",
    )
    env = wrap_legacy_result(
        {"error": "boom", "hint": "try again"},
        request=req, started_at=0.0, source="marketplace",
    )
    assert env.status == InvocationStatus.FAILED
    assert env.error_code == ErrorCode.AGENT_ERROR
    assert env.error_message == "boom"
    assert env.error_hint == "try again"
    assert env.output is None


def test_legacy_success_dict_becomes_success_envelope():
    req = InvocationRequest(
        agent_id="test", agent_name="TestAgent", capability="foo",
    )
    env = wrap_legacy_result(
        {"risk_level": "LOW", "score": 95},
        request=req, started_at=0.0, source="marketplace",
    )
    assert env.is_success()
    assert env.output == {"risk_level": "LOW", "score": 95}


def test_none_becomes_failed_envelope():
    req = InvocationRequest(
        agent_id="test", agent_name="TestAgent", capability="foo",
    )
    env = wrap_legacy_result(None, request=req, started_at=0.0, source="builtin")
    assert env.status == InvocationStatus.FAILED
    assert env.error_code == ErrorCode.AGENT_ERROR


def test_envelope_shaped_passthrough():
    """If an agent already returns the new envelope shape, don't double-wrap."""
    req = InvocationRequest(
        agent_id="test", agent_name="TestAgent", capability="foo",
    )
    # A well-formed agent response using the new shape
    raw = {
        "request_id": req.request_id,
        "agent_id": "test",
        "agent_name": "TestAgent",
        "capability": "foo",
        "status": "success",
        "output": {"x": 1},
        "source": "marketplace",
    }
    env = wrap_legacy_result(raw, request=req, started_at=0.0, source="marketplace")
    assert env.is_success()
    assert env.output == {"x": 1}


def test_model_dump_for_report_strips_request_id():
    env = InvocationResult(
        request_id="abc123",
        agent_id="test",
        agent_name="TestAgent",
        capability="foo",
        status=InvocationStatus.SUCCESS,
        output={"x": 1},
    )
    d = env.model_dump_for_report()
    assert "request_id" not in d
    assert d["status"] == "success"
