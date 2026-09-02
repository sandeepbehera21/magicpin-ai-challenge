from __future__ import annotations
import pytest
from fastapi.testclient import TestClient

from bot import app, engine, compose, respond
from vera.models.context import CtxPushBody, TickBody, ReplyBody
from vera.evidence.builder import EvidenceBuilder
from vera.merchant_state.engine import MerchantStateEngine
from vera.auction.auction import OpportunityAuction
from vera.budget.attention_budget import AttentionBudget
from vera.gate.counterfactual import CounterfactualGate
from vera.critic.critic import EvidenceCritic
from vera.composer.realizer import MessageRealizer


@pytest.fixture(autouse=True)
def reset_engine():
    engine.context_store.clear()
    engine.attention_budget.clear()
    engine.conversation_handler.clear()


client = TestClient(app)


# -----------------------------------------------------------------------------
# 1. Healthz and Metadata Tests
# -----------------------------------------------------------------------------

def test_healthz_and_metadata():
    resp = client.get("/v1/healthz")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert "contexts_loaded" in data

    resp_meta = client.get("/v1/metadata")
    assert resp_meta.status_code == 200
    meta = resp_meta.json()
    assert meta["team_name"] == "Vera Decision Engine"
    assert meta["team_members"] == ["Sandeep Kumar Behera"]
    assert "deterministic" in meta["approach"].lower()


# -----------------------------------------------------------------------------
# 2. Context Store & Versioning Tests
# -----------------------------------------------------------------------------

def test_context_store_versioning_and_idempotency():
    payload = {"slug": "dentists", "peer_stats": {"avg_ctr": 0.030}}

    # Push v1 -> 200
    r1 = client.post("/v1/context", json={
        "scope": "category",
        "context_id": "dentists",
        "version": 1,
        "payload": payload,
    })
    assert r1.status_code == 200
    assert r1.json()["accepted"] is True

    # Re-push v1 -> 200 idempotent no-op
    r2 = client.post("/v1/context", json={
        "scope": "category",
        "context_id": "dentists",
        "version": 1,
        "payload": payload,
    })
    assert r2.status_code == 200
    assert r2.json()["accepted"] is True

    # Push v2 -> 200 replaces
    payload_v2 = {"slug": "dentists", "peer_stats": {"avg_ctr": 0.035}}
    r3 = client.post("/v1/context", json={
        "scope": "category",
        "context_id": "dentists",
        "version": 2,
        "payload": payload_v2,
    })
    assert r3.status_code == 200
    assert r3.json()["accepted"] is True
    assert engine.context_store.get_version("category", "dentists") == 2

    # Push lower version v1 after v2 -> 409 stale
    r3_stale = client.post("/v1/context", json={
        "scope": "category",
        "context_id": "dentists",
        "version": 1,
        "payload": payload,
    })
    assert r3_stale.status_code == 409
    assert r3_stale.json()["accepted"] is False
    assert r3_stale.json()["reason"] == "stale_version"

    # Malformed scope -> 400
    r4 = client.post("/v1/context", json={
        "scope": "invalid_scope",
        "context_id": "foo",
        "version": 1,
        "payload": {},
    })
    assert r4.status_code == 400


# -----------------------------------------------------------------------------
# 3. Evidence Builder & State Derivation Tests
# -----------------------------------------------------------------------------

def test_evidence_builder_and_merchant_state():
    merchant_data = {
        "merchant_id": "m_001_drmeera",
        "category_slug": "dentists",
        "identity": {
            "name": "Dr. Meera's Dental Clinic",
            "city": "Delhi",
            "locality": "Lajpat Nagar",
            "owner_first_name": "Meera",
        },
        "performance": {
            "window_days": 30,
            "views": 2410,
            "calls": 18,
            "ctr": 0.021,
            "delta_7d": {"views_pct": 0.18, "calls_pct": -0.05},
        },
        "offers": [{"id": "o1", "title": "Dental Cleaning @ ₹299", "status": "active"}],
        "customer_aggregate": {"high_risk_adult_count": 124, "lapsed_180d_plus": 78},
        "signals": ["ctr_below_peer_median"],
    }
    category_data = {
        "slug": "dentists",
        "peer_stats": {"avg_ctr": 0.030},
        "digest": [
            {
                "id": "d1",
                "title": "3-month fluoride recall cuts caries 38% better",
                "source": "JIDA Oct 2026, p.14",
                "trial_n": 2100,
            }
        ],
    }

    client.post("/v1/context", json={"scope": "category", "context_id": "dentists", "version": 1, "payload": category_data})
    client.post("/v1/context", json={"scope": "merchant", "context_id": "m_001_drmeera", "version": 1, "payload": merchant_data})

    cat = engine.context_store.get_category("dentists")
    m = engine.context_store.get_merchant("m_001_drmeera")

    ledger = EvidenceBuilder.build_ledger(category=cat, merchant=m)
    assert len(ledger.items) > 5
    assert ledger.get_by_field_path("merchant.performance.ctr").value == 0.021

    state = MerchantStateEngine.derive_state(m, cat)
    assert state.ctr_state == "below_peer"
    assert state.has_active_offer is True
    assert state.has_high_risk_cohort is True


# -----------------------------------------------------------------------------
# 4. Opportunity Auction & Gating Tests
# -----------------------------------------------------------------------------

def test_opportunity_auction_prioritizes_evidence_over_raw_urgency():
    merchant_data = {
        "merchant_id": "m_001_drmeera",
        "category_slug": "dentists",
        "identity": {"name": "Dr. Meera's Clinic", "city": "Delhi", "locality": "Lajpat Nagar", "owner_first_name": "Meera"},
        "performance": {"views": 2000, "calls": 20, "ctr": 0.021},
        "customer_aggregate": {"high_risk_adult_count": 124},
        "signals": ["high_risk_adult_cohort"],
    }
    category_data = {
        "slug": "dentists",
        "digest": [{"id": "d1", "title": "JIDA fluoride study", "source": "JIDA Oct 2026, p.14"}],
    }

    # Trigger A: generic trigger with high raw urgency
    trigger_generic = {
        "id": "trg_generic_urgency",
        "scope": "merchant",
        "kind": "weather_heatwave",
        "merchant_id": "m_001_drmeera",
        "payload": {"temp": 42},
        "urgency": 5,
        "suppression_key": "heatwave_1",
    }

    # Trigger B: clinical research digest directly matching Dr. Meera's cohort (lower raw urgency 2)
    trigger_research = {
        "id": "trg_research_meera",
        "scope": "merchant",
        "kind": "research_digest",
        "merchant_id": "m_001_drmeera",
        "payload": {"category": "dentists", "top_item_id": "d1"},
        "urgency": 2,
        "suppression_key": "research_1",
    }

    client.post("/v1/context", json={"scope": "category", "context_id": "dentists", "version": 1, "payload": category_data})
    client.post("/v1/context", json={"scope": "merchant", "context_id": "m_001_drmeera", "version": 1, "payload": merchant_data})
    client.post("/v1/context", json={"scope": "trigger", "context_id": "trg_generic_urgency", "version": 1, "payload": trigger_generic})
    client.post("/v1/context", json={"scope": "trigger", "context_id": "trg_research_meera", "version": 1, "payload": trigger_research})

    resp = client.post("/v1/tick", json={
        "now": "2026-04-26T10:35:00Z",
        "available_triggers": ["trg_generic_urgency", "trg_research_meera"],
    })
    assert resp.status_code == 200
    actions = resp.json()["actions"]

    # The engine should select the research trigger due to evidence strength and merchant relevance
    assert len(actions) == 1
    assert actions[0]["trigger_id"] == "trg_research_meera"
    assert "JIDA" in actions[0]["body"]
    assert "Dr. Meera" in actions[0]["body"]


# -----------------------------------------------------------------------------
# 5. Customer-Facing Composition Tests
# -----------------------------------------------------------------------------

def test_customer_facing_composition():
    merchant_data = {
        "merchant_id": "m_001_drmeera",
        "category_slug": "dentists",
        "identity": {"name": "Dr. Meera's Dental Clinic", "city": "Delhi", "locality": "Lajpat Nagar"},
        "offers": [{"id": "o1", "title": "Dental Cleaning @ ₹299", "status": "active"}],
    }
    customer_data = {
        "customer_id": "c_001_priya",
        "merchant_id": "m_001_drmeera",
        "identity": {"name": "Priya", "language_pref": "hi-en mix"},
        "relationship": {"visits_total": 4, "last_visit": "2026-05-12"},
        "state": "lapsed_soft",
        "preferences": {"preferred_slots": "weekday_evening"},
        "consent": {"opted_in_at": "2025-11-04", "scope": ["recall_reminders"]},
    }
    trigger_data = {
        "id": "trg_recall_priya",
        "scope": "customer",
        "kind": "recall_due",
        "merchant_id": "m_001_drmeera",
        "customer_id": "c_001_priya",
        "payload": {
            "available_slots": [{"label": "Wed 5 Nov, 6pm"}, {"label": "Thu 6 Nov, 5pm"}],
        },
        "urgency": 3,
        "suppression_key": "recall:c_001_priya",
    }

    client.post("/v1/context", json={"scope": "merchant", "context_id": "m_001_drmeera", "version": 1, "payload": merchant_data})
    client.post("/v1/context", json={"scope": "customer", "context_id": "c_001_priya", "version": 1, "payload": customer_data})
    client.post("/v1/context", json={"scope": "trigger", "context_id": "trg_recall_priya", "version": 1, "payload": trigger_data})

    resp = client.post("/v1/tick", json={
        "now": "2026-04-26T11:00:00Z",
        "available_triggers": ["trg_recall_priya"],
    })
    assert resp.status_code == 200
    actions = resp.json()["actions"]
    assert len(actions) == 1
    act = actions[0]
    assert act["send_as"] == "merchant_on_behalf"
    assert act["customer_id"] == "c_001_priya"
    assert "Priya" in act["body"]
    assert "₹299" in act["body"]
    assert "Wed 5 Nov, 6pm" in act["body"]


# -----------------------------------------------------------------------------
# 6. Multi-Turn Conversation Handler Tests
# -----------------------------------------------------------------------------

def test_multi_turn_auto_reply_handling():
    # Turn 1: initial canned auto-reply -> bot provides one prompt
    r1 = client.post("/v1/reply", json={
        "conversation_id": "conv_test_auto",
        "message": "Thank you for contacting us! Our team will respond shortly.",
        "turn_number": 2,
    })
    assert r1.status_code == 200
    assert r1.json()["action"] in ("send", "wait")

    # Turn 2: second repeated auto-reply -> bot waits 24h
    r2 = client.post("/v1/reply", json={
        "conversation_id": "conv_test_auto",
        "message": "Thank you for contacting us! Our team will respond shortly.",
        "turn_number": 3,
    })
    assert r2.status_code == 200
    assert r2.json()["action"] == "wait"
    assert r2.json()["wait_seconds"] == 86400

    # Turn 3: third auto-reply -> bot ends conversation gracefully
    r3 = client.post("/v1/reply", json={
        "conversation_id": "conv_test_auto",
        "message": "Thank you for contacting us! Our team will respond shortly.",
        "turn_number": 4,
    })
    assert r3.status_code == 200
    assert r3.json()["action"] == "end"


def test_multi_turn_intent_transition_to_action():
    resp = client.post("/v1/reply", json={
        "conversation_id": "conv_test_intent",
        "message": "Ok let's do it. What's next?",
        "turn_number": 2,
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["action"] == "send"
    body = data["body"].lower()
    # Must switch to action mode (contains action verbs and no qualifying questions)
    assert any(w in body for w in ["done", "sending", "draft", "here", "confirm", "proceed", "setup"])
    assert not any(w in body for w in ["would you say", "do you think", "can you tell us if"])


def test_multi_turn_hostile_opt_out():
    resp = client.post("/v1/reply", json={
        "conversation_id": "conv_test_hostile",
        "message": "Stop messaging me. This is useless spam.",
        "turn_number": 2,
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["action"] == "end"


# -----------------------------------------------------------------------------
# 7. Determinism Test
# -----------------------------------------------------------------------------

def test_determinism_across_runs():
    category_data = {"slug": "dentists", "peer_stats": {"avg_ctr": 0.030}}
    merchant_data = {
        "merchant_id": "m_001_drmeera",
        "category_slug": "dentists",
        "identity": {"name": "Dr. Meera's Dental Clinic", "city": "Delhi", "locality": "Lajpat Nagar", "owner_first_name": "Meera"},
        "performance": {"views": 2410, "calls": 18, "ctr": 0.021},
        "customer_aggregate": {"high_risk_adult_count": 124},
    }
    trigger_data = {
        "id": "trg_001_research_digest_dentists",
        "scope": "merchant",
        "kind": "research_digest",
        "merchant_id": "m_001_drmeera",
        "payload": {"category": "dentists", "top_item_id": "d_2026W17_jida_fluoride"},
        "urgency": 2,
        "suppression_key": "research:dentists:2026-W17",
    }

    outputs = []
    for _ in range(5):
        out = compose(category_data, merchant_data, trigger_data)
        outputs.append(out)

    # Verify all outputs are bit-for-bit identical
    for i in range(1, len(outputs)):
        assert outputs[i] == outputs[0]
