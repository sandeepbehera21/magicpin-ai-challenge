from __future__ import annotations
import pytest
from fastapi.testclient import TestClient

from bot import app, engine, compose, respond
from vera.evidence.builder import EvidenceBuilder
from vera.merchant_state.engine import MerchantStateEngine
from vera.auction.auction import OpportunityAuction
from vera.budget.attention_budget import AttentionBudget
from vera.gate.counterfactual import CounterfactualGate
from vera.critic.critic import EvidenceCritic
from vera.models.message import ComposedMessage
from vera.models.evidence import EvidenceLedger


@pytest.fixture(autouse=True)
def reset_engine():
    engine.context_store.clear()
    engine.attention_budget.clear()
    engine.conversation_handler.clear()


client = TestClient(app)


def test_stale_lower_version_rejected():
    # Push version 5
    r1 = client.post("/v1/context", json={
        "scope": "merchant",
        "context_id": "m_test_01",
        "version": 5,
        "payload": {
            "merchant_id": "m_test_01",
            "category_slug": "salons",
            "identity": {"name": "Test Salon", "city": "Mumbai", "locality": "Bandra"},
        },
    })
    assert r1.status_code == 200

    # Try to push version 3 -> rejected with 409
    r2 = client.post("/v1/context", json={
        "scope": "merchant",
        "context_id": "m_test_01",
        "version": 3,
        "payload": {"merchant_id": "m_test_01"},
    })
    assert r2.status_code == 409
    assert r2.json()["accepted"] is False
    assert r2.json()["current_version"] == 5


def test_attention_budget_throttles_per_merchant():
    budget = AttentionBudget(max_actions_per_tick=5, max_per_merchant_per_tick=1)

    # Push 3 triggers for the SAME merchant
    merchant_data = {
        "merchant_id": "m_solo",
        "category_slug": "gyms",
        "identity": {"name": "Power Gym", "city": "Bangalore", "locality": "HSR Layout"},
        "performance": {"views": 1000, "calls": 10, "ctr": 0.03},
    }
    client.post("/v1/context", json={"scope": "merchant", "context_id": "m_solo", "version": 1, "payload": merchant_data})

    for i in range(3):
        client.post("/v1/context", json={
            "scope": "trigger",
            "context_id": f"trg_m_solo_{i}",
            "version": 1,
            "payload": {
                "id": f"trg_m_solo_{i}",
                "scope": "merchant",
                "kind": "curious_ask_due",
                "merchant_id": "m_solo",
                "urgency": 2,
                "suppression_key": f"supp_key_{i}",
            },
        })

    resp = client.post("/v1/tick", json={
        "now": "2026-04-26T10:00:00Z",
        "available_triggers": [f"trg_m_solo_{i}" for i in range(3)],
    })
    assert resp.status_code == 200
    actions = resp.json()["actions"]

    # Only 1 action should be returned for this merchant in this tick
    assert len(actions) == 1
    assert actions[0]["merchant_id"] == "m_solo"


def test_evidence_critic_removes_urls_and_taboos():
    raw_msg = ComposedMessage(
        body="Dr. Meera, this 100% safe miracle treatment is guaranteed to completely cure tooth decay! Check it out: https://magicpin.com/dentists. Want me to draft a post?",
        cta="open_ended",
        send_as="vera",
        suppression_key="test_supp",
        rationale="Test message",
    )
    ledger = EvidenceLedger()

    is_valid, repaired, notes = EvidenceCritic.review_and_repair(
        message=raw_msg,
        category_slug="dentists",
        evidence_ledger=ledger,
    )

    assert is_valid is True
    # Verify URLs are stripped
    assert "https://" not in repaired.body
    assert "magicpin.com" not in repaired.body
    # Verify taboo terms replaced
    assert "100% safe" not in repaired.body
    assert "completely cure" not in repaired.body
    assert "guaranteed" not in repaired.body
    assert len(notes) >= 2


def test_all_five_category_verticals_composition():
    categories = ["dentists", "salons", "restaurants", "gyms", "pharmacies"]

    for cat_slug in categories:
        cat_data = {"slug": cat_slug, "peer_stats": {"avg_ctr": 0.030}}
        m_data = {
            "merchant_id": f"m_{cat_slug}_test",
            "category_slug": cat_slug,
            "identity": {
                "name": f"Top {cat_slug.title()} Store",
                "city": "Delhi",
                "locality": "Saket",
                "owner_first_name": "Ravi",
            },
            "performance": {"views": 1500, "calls": 25, "ctr": 0.028},
            "offers": [{"title": f"Special {cat_slug.title()} Deal @ ₹499", "status": "active"}],
        }
        trg_data = {
            "id": f"trg_{cat_slug}_test",
            "scope": "merchant",
            "kind": "curious_ask_due",
            "merchant_id": f"m_{cat_slug}_test",
            "urgency": 2,
            "suppression_key": f"curious:{cat_slug}",
        }

        composed = compose(cat_data, m_data, trg_data)
        assert composed is not None
        assert "body" in composed
        assert len(composed["body"]) > 20
        assert composed["send_as"] == "vera"
        assert "Ravi" in composed["body"] or "Top" in composed["body"]
