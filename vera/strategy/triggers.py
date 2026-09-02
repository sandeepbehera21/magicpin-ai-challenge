from __future__ import annotations
from typing import Any, Callable, Dict, List, Optional
from pydantic import BaseModel
from ..models.context import CategoryContext, MerchantContext, CustomerContext, TriggerContext
from ..models.state import MerchantDerivedState, CustomerDerivedState


class TriggerStrategy(BaseModel):
    kind: str
    default_scope: str = "merchant"  # "merchant" or "customer"
    base_urgency: float = 5.0
    actionability_score: float = 7.0
    compulsion_type: str = "curiosity"  # "curiosity", "loss_aversion", "social_proof", "compliance", "retention", "reciprocity"
    default_cta_type: str = "open_ended"  # "open_ended", "binary_yes_no", "binary_confirm_cancel", "multi_choice_slot", "none"


TRIGGER_REGISTRY: Dict[str, TriggerStrategy] = {
    "research_digest": TriggerStrategy(
        kind="research_digest",
        base_urgency=6.0,
        actionability_score=8.5,
        compulsion_type="curiosity",
        default_cta_type="open_ended",
    ),
    "category_research_digest_release": TriggerStrategy(
        kind="category_research_digest_release",
        base_urgency=6.0,
        actionability_score=8.5,
        compulsion_type="curiosity",
        default_cta_type="open_ended",
    ),
    "regulation_change": TriggerStrategy(
        kind="regulation_change",
        base_urgency=8.5,
        actionability_score=9.0,
        compulsion_type="compliance",
        default_cta_type="open_ended",
    ),
    "supply_alert": TriggerStrategy(
        kind="supply_alert",
        base_urgency=9.0,
        actionability_score=9.5,
        compulsion_type="compliance",
        default_cta_type="open_ended",
    ),
    "recall_due": TriggerStrategy(
        kind="recall_due",
        default_scope="customer",
        base_urgency=7.5,
        actionability_score=9.5,
        compulsion_type="retention",
        default_cta_type="multi_choice_slot",
    ),
    "chronic_refill_due": TriggerStrategy(
        kind="chronic_refill_due",
        default_scope="customer",
        base_urgency=8.5,
        actionability_score=9.5,
        compulsion_type="retention",
        default_cta_type="binary_confirm_cancel",
    ),
    "customer_lapsed_soft": TriggerStrategy(
        kind="customer_lapsed_soft",
        default_scope="customer",
        base_urgency=6.5,
        actionability_score=8.0,
        compulsion_type="retention",
        default_cta_type="binary_yes_no",
    ),
    "customer_lapsed_hard": TriggerStrategy(
        kind="customer_lapsed_hard",
        default_scope="customer",
        base_urgency=6.0,
        actionability_score=8.0,
        compulsion_type="retention",
        default_cta_type="binary_yes_no",
    ),
    "wedding_package_followup": TriggerStrategy(
        kind="wedding_package_followup",
        default_scope="customer",
        base_urgency=7.0,
        actionability_score=9.0,
        compulsion_type="retention",
        default_cta_type="binary_yes_no",
    ),
    "bridal_followup": TriggerStrategy(
        kind="bridal_followup",
        default_scope="customer",
        base_urgency=7.0,
        actionability_score=9.0,
        compulsion_type="retention",
        default_cta_type="binary_yes_no",
    ),
    "perf_dip": TriggerStrategy(
        kind="perf_dip",
        base_urgency=7.5,
        actionability_score=8.0,
        compulsion_type="loss_aversion",
        default_cta_type="binary_yes_no",
    ),
    "seasonal_perf_dip": TriggerStrategy(
        kind="seasonal_perf_dip",
        base_urgency=6.0,
        actionability_score=8.5,
        compulsion_type="anxiety_preemption",
        default_cta_type="binary_yes_no",
    ),
    "perf_spike": TriggerStrategy(
        kind="perf_spike",
        base_urgency=5.5,
        actionability_score=7.5,
        compulsion_type="reciprocity",
        default_cta_type="binary_yes_no",
    ),
    "milestone_reached": TriggerStrategy(
        kind="milestone_reached",
        base_urgency=5.0,
        actionability_score=7.0,
        compulsion_type="reciprocity",
        default_cta_type="binary_yes_no",
    ),
    "curious_ask_due": TriggerStrategy(
        kind="curious_ask_due",
        base_urgency=4.5,
        actionability_score=8.0,
        compulsion_type="asking_the_merchant",
        default_cta_type="open_ended",
    ),
    "dormant_with_vera": TriggerStrategy(
        kind="dormant_with_vera",
        base_urgency=6.5,
        actionability_score=7.5,
        compulsion_type="curiosity",
        default_cta_type="open_ended",
    ),
    "festival_upcoming": TriggerStrategy(
        kind="festival_upcoming",
        base_urgency=5.5,
        actionability_score=8.0,
        compulsion_type="loss_aversion",
        default_cta_type="binary_yes_no",
    ),
    "weather_heatwave": TriggerStrategy(
        kind="weather_heatwave",
        base_urgency=5.0,
        actionability_score=7.5,
        compulsion_type="loss_aversion",
        default_cta_type="binary_yes_no",
    ),
    "competitor_opened": TriggerStrategy(
        kind="competitor_opened",
        base_urgency=7.0,
        actionability_score=8.0,
        compulsion_type="loss_aversion",
        default_cta_type="binary_yes_no",
    ),
    "review_theme_emerged": TriggerStrategy(
        kind="review_theme_emerged",
        base_urgency=7.0,
        actionability_score=8.5,
        compulsion_type="reputation_management",
        default_cta_type="binary_yes_no",
    ),
    "renewal_due": TriggerStrategy(
        kind="renewal_due",
        base_urgency=8.0,
        actionability_score=9.0,
        compulsion_type="loss_aversion",
        default_cta_type="binary_confirm_cancel",
    ),
    "active_planning_intent": TriggerStrategy(
        kind="active_planning_intent",
        base_urgency=8.5,
        actionability_score=9.5,
        compulsion_type="effort_externalization",
        default_cta_type="binary_confirm_cancel",
    ),
    "appointment_tomorrow": TriggerStrategy(
        kind="appointment_tomorrow",
        default_scope="customer",
        base_urgency=8.0,
        actionability_score=9.0,
        compulsion_type="retention",
        default_cta_type="binary_confirm_cancel",
    ),
}

DEFAULT_TRIGGER_STRATEGY = TriggerStrategy(
    kind="generic_trigger",
    base_urgency=5.0,
    actionability_score=6.0,
    compulsion_type="curiosity",
    default_cta_type="open_ended",
)


def get_trigger_strategy(kind: str) -> TriggerStrategy:
    return TRIGGER_REGISTRY.get(kind.lower().strip(), DEFAULT_TRIGGER_STRATEGY)
