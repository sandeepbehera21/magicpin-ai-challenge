from __future__ import annotations
from typing import List, Optional
from pydantic import BaseModel, Field


class MerchantDerivedState(BaseModel):
    merchant_id: str
    category_slug: str
    
    # Trajectory & Health
    health: str = "healthy"  # "healthy", "growing", "declining", "underperforming", "dormant"
    ctr_state: str = "normal"  # "above_peer", "at_peer", "below_peer"
    views_trend: str = "stable"  # "spiking", "growing", "stable", "dipping", "declining"
    calls_trend: str = "stable"  # "spiking", "growing", "stable", "dipping", "declining"
    
    # Readiness & Assets
    has_active_offer: bool = False
    active_offer_titles: List[str] = Field(default_factory=list)
    has_high_risk_cohort: bool = False
    has_chronic_rx_cohort: bool = False
    high_lapsed_rate: bool = False
    has_negative_review_spike: bool = False
    urgent_renewal: bool = False
    days_to_sub_expiry: Optional[int] = None
    
    # Engagement State
    engagement_level: str = "moderate"  # "highly_engaged", "moderately_engaged", "dormant", "disengaged"
    last_touch_hours_ago: Optional[float] = None
    hours_since_merchant_reply: Optional[float] = None
    derived_signals: List[str] = Field(default_factory=list)


class CustomerDerivedState(BaseModel):
    customer_id: str
    merchant_id: str
    lifecycle_stage: str = "active"  # "new", "active", "lapsed_soft", "lapsed_hard", "churned"
    months_since_last_visit: Optional[float] = None
    is_recall_eligible: bool = False
    preferred_timing: str = "weekday_evening"
    language_code_mix: str = "hi-en mix"
    consent_valid: bool = True
