from __future__ import annotations
import pytest
from fastapi.testclient import TestClient
from bot import app, engine


@pytest.fixture(autouse=True)
def reset_engine():
    engine.context_store.clear()
    engine.attention_budget.clear()
    engine.state_machine.clear()


client = TestClient(app)


def test_adversarial_flow_action_handoff():
    merchant_data = {
        "merchant_id": "m_test_handoff",
        "category_slug": "restaurants",
        "identity": {"name": "Biryani Express", "city": "Hyderabad", "locality": "Madhapur", "owner_first_name": "Karim"},
    }
    client.post("/v1/context", json={"scope": "merchant", "context_id": "m_test_handoff", "version": 1, "payload": merchant_data})

    # Merchant says "I want to join" -> must switch to action immediately without qualifying
    resp = client.post("/v1/reply", json={
        "conversation_id": "conv_handoff_1",
        "merchant_id": "m_test_handoff",
        "message": "I want to join. Let's start.",
        "turn_number": 2,
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["action"] == "send"
    body_lower = data["body"].lower()
    assert any(w in body_lower for w in ["done", "activated", "initialized", "welcome", "confirm"])
    # Ensure no qualifying interrogation
    assert not any(w in body_lower for w in ["what is your budget", "how many tables", "do you have"])


def test_adversarial_flow_answer_first_pricing():
    merchant_data = {
        "merchant_id": "m_test_pricing",
        "category_slug": "salons",
        "identity": {"name": "Glow Studio", "city": "Delhi", "locality": "Saket", "owner_first_name": "Anita"},
        "offers": [{"title": "Keratin Spa @ ₹1,999", "status": "active"}],
    }
    client.post("/v1/context", json={"scope": "merchant", "context_id": "m_test_pricing", "version": 1, "payload": merchant_data})

    resp = client.post("/v1/reply", json={
        "conversation_id": "conv_pricing_1",
        "merchant_id": "m_test_pricing",
        "message": "How much does it cost?",
        "turn_number": 2,
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["action"] == "send"
    assert "₹1,999" in data["body"] or "Keratin" in data["body"]


def test_adversarial_flow_later_postponement():
    resp = client.post("/v1/reply", json={
        "conversation_id": "conv_later_1",
        "message": "Baad mein baat karte hain, abhi customer hai.",
        "turn_number": 2,
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["action"] == "wait"
    assert data["wait_seconds"] == 86400


def test_adversarial_flow_stop_opt_out():
    resp = client.post("/v1/reply", json={
        "conversation_id": "conv_stop_1",
        "message": "Nahi chahiye, please mat bhejo.",
        "turn_number": 2,
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["action"] == "end"
