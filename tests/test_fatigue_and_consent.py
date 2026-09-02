from __future__ import annotations
import pytest
from vera.fatigue.model import MerchantFatigueModel
from vera.gate.consent import ConsentGate
from vera.models.context import MerchantContext, CustomerContext, TriggerContext


def test_merchant_fatigue_levels():
    merchant_base = MerchantContext(
        merchant_id="m_fatigue_test",
        category_slug="salons",
        identity={"name": "Test Salon", "city": "Delhi", "locality": "Saket"},
    )

    # Low fatigue
    low_f = MerchantFatigueModel.evaluate(
        merchant=merchant_base,
        recent_sends_count=0,
        unanswered_nudges=0,
        hours_since_last_touch=72.0,
    )
    assert low_f.level == "LOW"
    assert low_f.recommended_action == "PROCEED"

    # High fatigue
    high_f = MerchantFatigueModel.evaluate(
        merchant=merchant_base,
        recent_sends_count=4,
        unanswered_nudges=3,
        hours_since_last_touch=1.0,
    )
    assert high_f.level == "HIGH"
    assert high_f.recommended_action == "SUPPRESS_OR_WAIT"


def test_customer_consent_gate():
    customer_valid = CustomerContext(
        customer_id="c_valid",
        merchant_id="m_001",
        identity={"name": "Priya"},
        consent={"opted_in_at": "2026-01-01T00:00:00Z", "scope": ["recall_reminders"]},
    )
    trigger_recall = TriggerContext(
        id="trg_1",
        scope="customer",
        kind="recall_due",
        merchant_id="m_001",
        customer_id="c_valid",
    )

    # Valid consent for recall
    ok, reason = ConsentGate.verify_customer_consent(
        customer=customer_valid,
        trigger=trigger_recall,
        merchant_id="m_001",
    )
    assert ok is True

    # Missing promotional scope
    trigger_promo = TriggerContext(
        id="trg_2",
        scope="customer",
        kind="promotional_campaign",
        merchant_id="m_001",
        customer_id="c_valid",
    )
    ok_p, _ = ConsentGate.verify_customer_consent(
        customer=customer_valid,
        trigger=trigger_promo,
        merchant_id="m_001",
    )
    assert ok_p is False

    # Merchant mismatch
    ok_m, _ = ConsentGate.verify_customer_consent(
        customer=customer_valid,
        trigger=trigger_recall,
        merchant_id="m_002_other",
    )
    assert ok_m is False
