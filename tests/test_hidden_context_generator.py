from __future__ import annotations
import pytest
from fastapi.testclient import TestClient
from bot import app, engine, compose


@pytest.fixture(autouse=True)
def reset_engine():
    engine.context_store.clear()
    engine.attention_budget.clear()
    engine.state_machine.clear()


client = TestClient(app)


def test_hidden_context_injected_digest():
    category_base = {
        "slug": "dentists",
        "peer_stats": {"avg_ctr": 0.030},
        "digest": [
            {
                "id": "d_injected_2026",
                "kind": "research",
                "title": "New orthodontic aligner study reveals 45% faster tooth movement",
                "source": "Indian Journal of Dental Research Nov 2026, p.88",
                "trial_n": 1500,
            }
        ],
    }
    merchant_data = {
        "merchant_id": "m_injected_dentist",
        "category_slug": "dentists",
        "identity": {"name": "Apex Dental", "city": "Bangalore", "locality": "Indiranagar", "owner_first_name": "Karthik"},
        "performance": {"views": 3100, "calls": 35, "ctr": 0.029},
    }
    trigger_data = {
        "id": "trg_injected_aligner",
        "scope": "merchant",
        "kind": "research_digest",
        "merchant_id": "m_injected_dentist",
        "payload": {"category": "dentists", "top_item_id": "d_injected_2026"},
        "urgency": 2,
        "suppression_key": "injected_research_w45",
    }

    client.post("/v1/context", json={"scope": "category", "context_id": "dentists", "version": 1, "payload": category_base})
    client.post("/v1/context", json={"scope": "merchant", "context_id": "m_injected_dentist", "version": 1, "payload": merchant_data})
    client.post("/v1/context", json={"scope": "trigger", "context_id": "trg_injected_aligner", "version": 1, "payload": trigger_data})

    resp = client.post("/v1/tick", json={
        "now": "2026-11-15T10:00:00Z",
        "available_triggers": ["trg_injected_aligner"],
    })
    assert resp.status_code == 200
    actions = resp.json()["actions"]
    assert len(actions) == 1
    # Check that message dynamically uses the injected citation
    assert "Dr. Karthik" in actions[0]["body"]
    assert "JIDA" in actions[0]["body"] or "Dental" in actions[0]["body"]


def test_concurrent_auction_5_triggers_single_winner():
    merchant_data = {
        "merchant_id": "m_multi_trigger",
        "category_slug": "dentists",
        "identity": {"name": "Smile Clinic", "city": "Delhi", "locality": "Saket", "owner_first_name": "Neha"},
        "performance": {"views": 2000, "calls": 20, "ctr": 0.020},
        "customer_aggregate": {"high_risk_adult_count": 100},
        "signals": ["high_risk_adult_cohort"],
    }
    category_data = {
        "slug": "dentists",
        "digest": [{"id": "d_trial", "title": "Trial Caries", "source": "JIDA Oct 2026"}],
    }

    client.post("/v1/context", json={"scope": "category", "context_id": "dentists", "version": 1, "payload": category_data})
    client.post("/v1/context", json={"scope": "merchant", "context_id": "m_multi_trigger", "version": 1, "payload": merchant_data})

    # 5 triggers of varying urgency and relevance
    triggers = [
        {"id": "trg_heatwave", "scope": "merchant", "kind": "weather_heatwave", "urgency": 5, "suppression_key": "k1", "payload": {}},
        {"id": "trg_festival_far", "scope": "merchant", "kind": "festival_upcoming", "urgency": 4, "suppression_key": "k2", "payload": {"days_until": 180}},
        {"id": "trg_research_match", "scope": "merchant", "kind": "research_digest", "urgency": 2, "suppression_key": "k3", "payload": {"category": "dentists", "top_item_id": "d_trial"}},
        {"id": "trg_curious", "scope": "merchant", "kind": "curious_ask_due", "urgency": 1, "suppression_key": "k4", "payload": {}},
        {"id": "trg_milestone", "scope": "merchant", "kind": "milestone_reached", "urgency": 1, "suppression_key": "k5", "payload": {}},
    ]

    for t in triggers:
        t["merchant_id"] = "m_multi_trigger"
        client.post("/v1/context", json={"scope": "trigger", "context_id": t["id"], "version": 1, "payload": t})

    resp = client.post("/v1/tick", json={
        "now": "2026-04-26T10:00:00Z",
        "available_triggers": [t["id"] for t in triggers],
    })
    assert resp.status_code == 200
    actions = resp.json()["actions"]
    # Single winning action chosen based on evidence strength + cohort match
    assert len(actions) == 1
    assert actions[0]["trigger_id"] == "trg_research_match"
