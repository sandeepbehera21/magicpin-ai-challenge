from __future__ import annotations
import pytest
from bot import compose, respond


def test_20_run_determinism_compose():
    cat = {"slug": "pharmacies", "peer_stats": {"avg_ctr": 0.03}}
    merchant = {
        "merchant_id": "m_pharm_01",
        "category_slug": "pharmacies",
        "identity": {"name": "Apollo Pharmacy", "city": "Jaipur", "locality": "Malviya Nagar", "owner_first_name": "Ramesh"},
        "customer_aggregate": {"chronic_rx_count": 240},
    }
    trigger = {
        "id": "trg_pharm_supply",
        "scope": "merchant",
        "kind": "supply_alert",
        "merchant_id": "m_pharm_01",
        "payload": {"batches": ["AT2024-1102", "AT2024-1108"]},
        "urgency": 4,
        "suppression_key": "pharm_supp_01",
    }

    results = []
    for _ in range(20):
        res = compose(cat, merchant, trigger)
        results.append(res)

    for i in range(1, 20):
        assert results[i] == results[0]


def test_20_run_determinism_respond():
    results = []
    for i in range(20):
        res = respond(
            conversation_id=f"conv_det_test_{i}",
            merchant_message="Ok let's do it. What's next?",
            turn_number=2,
        )
        results.append(res)

    for i in range(1, 20):
        assert results[i] == results[0]
