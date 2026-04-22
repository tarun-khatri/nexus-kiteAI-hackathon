"""
Tests for the expanded mandate payment-record state machine.

The orchestrator writes one of three statuses for each payment:
  - SUCCEEDED           : chain tx + agent output OK
  - FAILED_DOWNSTREAM   : chain tx OK, agent returned error/timeout
  - BLOCKED_UNREACHABLE : probe failed, NO chain tx fired (no debit)
"""

from backend.verified_intent.mandate_manager import MandateManager
from backend.models.mandate import PaymentRecordStatus


def _create(mm: MandateManager):
    return mm.create_mandate(
        query="test",
        allowed_agents=["A", "B"],
        agent_prices={"A": 0.0001, "B": 0.0002},
        budget_multiplier=3.0,
    )


def test_default_record_payment_is_succeeded():
    mm = MandateManager()
    m = _create(mm)
    mm.record_payment(m.mandate_id, "A", 0.0001, "task", tx_hash="0x1")
    rec = m.payment_log[-1]
    assert rec.status == PaymentRecordStatus.SUCCEEDED
    assert m.cumulative_spent == 0.0001


def test_blocked_unreachable_does_not_debit_budget():
    mm = MandateManager()
    m = _create(mm)
    mm.record_payment(
        m.mandate_id, "B", 0.0002, "task",
        tx_hash="",  # no chain tx
        status=PaymentRecordStatus.BLOCKED_UNREACHABLE,
        error_code="unreachable",
        error_message="probe failed",
    )
    rec = m.payment_log[-1]
    assert rec.status == PaymentRecordStatus.BLOCKED_UNREACHABLE
    assert rec.error_message == "probe failed"
    # Budget MUST NOT change when no chain tx fired
    assert m.cumulative_spent == 0.0


def test_mark_payment_failed_flips_existing_entry():
    mm = MandateManager()
    m = _create(mm)
    mm.record_payment(m.mandate_id, "A", 0.0001, "task", tx_hash="0xabc")
    assert m.payment_log[-1].status == PaymentRecordStatus.SUCCEEDED

    ok = mm.mark_payment_failed(
        m.mandate_id, "0xabc",
        error_code="agent_error", error_message="agent returned error",
    )
    assert ok
    rec = m.payment_log[-1]
    assert rec.status == PaymentRecordStatus.FAILED_DOWNSTREAM
    assert rec.error_code == "agent_error"
    # Budget was debited (chain tx fired); we don't refund on the mandate side —
    # reputation penalty is the accounting mechanism for failed downstream work.
    assert m.cumulative_spent == 0.0001


def test_mark_payment_failed_ignores_unknown_tx_hash():
    mm = MandateManager()
    m = _create(mm)
    mm.record_payment(m.mandate_id, "A", 0.0001, "task", tx_hash="0xreal")
    ok = mm.mark_payment_failed(m.mandate_id, "0xnope")
    assert ok is False
