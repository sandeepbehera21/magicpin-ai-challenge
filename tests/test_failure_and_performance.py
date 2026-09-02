from __future__ import annotations
import time
import pytest
from fastapi.testclient import TestClient
from bot import app, engine, compose, respond


@pytest.fixture(autouse=True)
def reset_engine():
    engine.context_store.clear()
    engine.attention_budget.clear()
    engine.state_machine.clear()


client = TestClient(app)


def test_failure_injection_missing_merchant():
    resp = client.post("/v1/tick", json={
        "now": "2026-04-26T10:00:00Z",
        "available_triggers": ["trg_non_existent"],
    })
    assert resp.status_code == 200
    assert resp.json()["actions"] == []


def test_failure_injection_empty_triggers():
    resp = client.post("/v1/tick", json={
        "now": "2026-04-26T10:00:00Z",
        "available_triggers": [],
    })
    assert resp.status_code == 200
    assert resp.json()["actions"] == []


def test_failure_injection_malformed_context_scope():
    resp = client.post("/v1/context", json={
        "scope": "unknown_invalid_scope",
        "context_id": "test_01",
        "version": 1,
        "payload": {},
    })
    assert resp.status_code == 400
    assert resp.json()["accepted"] is False


def test_dynamic_unseen_category_synthesis():
    cat_data = {
        "slug": "car_detailing",
        "display_name": "Premium Auto Spa",
        "voice_profile": {"tone": "technical_enthusiast"},
        "allowed_vocabulary": ["ceramic coating", "paint correction", "PPF"],
        "taboo_words": ["cheap wash"],
    }
    merchant_data = {
        "merchant_id": "m_auto_spa_01",
        "category_slug": "car_detailing",
        "identity": {"name": "Speed Detailing", "city": "Pune", "locality": "Baner", "owner_first_name": "Rohan"},
        "performance": {"views": 1800, "calls": 22, "ctr": 0.024},
    }
    trigger_data = {
        "id": "trg_detailing_curious",
        "scope": "merchant",
        "kind": "curious_ask_due",
        "merchant_id": "m_auto_spa_01",
        "payload": {},
        "urgency": 1,
        "suppression_key": "curious:m_auto_spa_01",
    }

    client.post("/v1/context", json={"scope": "category", "context_id": "car_detailing", "version": 1, "payload": cat_data})
    client.post("/v1/context", json={"scope": "merchant", "context_id": "m_auto_spa_01", "version": 1, "payload": merchant_data})
    client.post("/v1/context", json={"scope": "trigger", "context_id": "trg_detailing_curious", "version": 1, "payload": trigger_data})

    resp = client.post("/v1/tick", json={
        "now": "2026-04-26T10:00:00Z",
        "available_triggers": ["trg_detailing_curious"],
    })
    assert resp.status_code == 200
    actions = resp.json()["actions"]
    assert len(actions) == 1
    assert "Speed Detailing" in actions[0]["body"]


def test_api_performance_benchmarks():
    merchant_data = {
        "merchant_id": "m_perf_bench",
        "category_slug": "salons",
        "identity": {"name": "Test Salon", "city": "Delhi", "locality": "Saket", "owner_first_name": "Pooja"},
    }

    # Measure /v1/context latency
    t0 = time.perf_counter()
    r_ctx = client.post("/v1/context", json={"scope": "merchant", "context_id": "m_perf_bench", "version": 1, "payload": merchant_data})
    t_ctx = (time.perf_counter() - t0) * 1000
    assert r_ctx.status_code == 200
    assert t_ctx < 50.0  # under 50ms

    # Measure /v1/reply latency
    t0 = time.perf_counter()
    r_rep = client.post("/v1/reply", json={"conversation_id": "c_bench", "merchant_id": "m_perf_bench", "message": "Let's do it", "turn_number": 2})
    t_rep = (time.perf_counter() - t0) * 1000
    assert r_rep.status_code == 200
    assert t_rep < 50.0  # comfortably under 30-second judge limit
