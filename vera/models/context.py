from __future__ import annotations
from typing import Any, Dict, List, Literal, Optional, Union
from pydantic import BaseModel, ConfigDict, Field


# -----------------------------------------------------------------------------
# 1. Category Context Models
# -----------------------------------------------------------------------------

class OfferTemplate(BaseModel):
    id: Optional[str] = None
    title: str
    value: Optional[str] = None
    audience: Optional[str] = None
    type: Optional[str] = None


class VoiceProfile(BaseModel):
    tone: Optional[str] = None
    register: Optional[str] = None
    code_mix: Optional[str] = None
    vocab_allowed: List[str] = Field(default_factory=list)
    vocab_taboo: List[str] = Field(default_factory=list)
    salutation_examples: List[str] = Field(default_factory=list)
    tone_examples: List[str] = Field(default_factory=list)


class PeerStats(BaseModel):
    scope: Optional[str] = None
    avg_rating: Optional[float] = None
    avg_review_count: Optional[int] = None
    avg_views_30d: Optional[int] = None
    avg_calls_30d: Optional[int] = None
    avg_directions_30d: Optional[int] = None
    avg_ctr: Optional[float] = None
    avg_photos: Optional[int] = None
    avg_post_freq_days: Optional[int] = None
    retention_6mo_pct: Optional[float] = None


class DigestItem(BaseModel):
    id: str
    kind: Optional[str] = None  # research, compliance, cde, trend, tech, news
    title: str
    source: Optional[str] = None
    trial_n: Optional[int] = None
    patient_segment: Optional[str] = None
    summary: Optional[str] = None
    actionable: Optional[str] = None
    date: Optional[str] = None
    credits: Optional[int] = None


class ContentItem(BaseModel):
    id: str
    title: str
    channel: Optional[str] = "whatsapp"
    length_seconds: Optional[int] = None
    body: str


class SeasonalBeat(BaseModel):
    month_range: Optional[str] = None
    month: Optional[str] = None
    note: str


class TrendSignal(BaseModel):
    query: str
    delta_yoy: Optional[float] = None
    segment_age: Optional[str] = None
    skew: Optional[str] = None


class CategoryContext(BaseModel):
    slug: str
    display_name: Optional[str] = None
    voice: VoiceProfile = Field(default_factory=VoiceProfile)
    offer_catalog: List[OfferTemplate] = Field(default_factory=list)
    peer_stats: PeerStats = Field(default_factory=PeerStats)
    digest: List[DigestItem] = Field(default_factory=list)
    patient_content_library: List[ContentItem] = Field(default_factory=list)
    seasonal_beats: List[SeasonalBeat] = Field(default_factory=list)
    trend_signals: List[TrendSignal] = Field(default_factory=list)
    regulatory_authorities: List[str] = Field(default_factory=list)
    professional_journals: List[str] = Field(default_factory=list)


# -----------------------------------------------------------------------------
# 2. Merchant Context Models
# -----------------------------------------------------------------------------

class MerchantIdentity(BaseModel):
    name: str
    city: str
    locality: str
    place_id: Optional[str] = None
    verified: bool = False
    languages: List[str] = Field(default_factory=lambda: ["en", "hi"])
    owner_first_name: Optional[str] = None
    established_year: Optional[int] = None


class MerchantSubscription(BaseModel):
    status: str = "active"  # active, expired, trial
    plan: Optional[str] = "Pro"
    days_remaining: Optional[int] = 0
    days_since_expiry: Optional[int] = None
    renewed_at: Optional[str] = None


class PerformanceDelta(BaseModel):
    views_pct: Optional[float] = None
    calls_pct: Optional[float] = None
    ctr_pct: Optional[float] = None


class PerformanceSnapshot(BaseModel):
    window_days: int = 30
    views: int = 0
    calls: int = 0
    directions: Optional[int] = 0
    ctr: float = 0.0
    leads: Optional[int] = 0
    delta_7d: Optional[Union[PerformanceDelta, Dict[str, Any]]] = None


class MerchantOffer(BaseModel):
    id: Optional[str] = None
    title: str
    status: str = "active"  # active, expired, paused
    started: Optional[str] = None
    ended: Optional[str] = None


class ConversationTurn(BaseModel):
    ts: Optional[str] = None
    from_: Optional[str] = Field(None, alias="from")
    body: str = ""
    engagement: Optional[str] = None  # merchant_replied, merchant_no_reply, intent_action


class CustomerAggregate(BaseModel):
    model_config = ConfigDict(extra="allow")

    total_unique_ytd: Optional[int] = 0
    lapsed_180d_plus: Optional[int] = 0
    retention_6mo_pct: Optional[float] = None
    high_risk_adult_count: Optional[int] = None
    chronic_rx_count: Optional[int] = None


class ReviewTheme(BaseModel):
    theme: str
    sentiment: str = "neutral"  # pos, neg, neutral
    occurrences_30d: int = 1
    common_quote: Optional[str] = None


class MerchantContext(BaseModel):
    merchant_id: str
    category_slug: str
    identity: MerchantIdentity
    subscription: MerchantSubscription = Field(default_factory=MerchantSubscription)
    performance: PerformanceSnapshot = Field(default_factory=PerformanceSnapshot)
    offers: List[MerchantOffer] = Field(default_factory=list)
    conversation_history: List[ConversationTurn] = Field(default_factory=list)
    customer_aggregate: CustomerAggregate = Field(default_factory=CustomerAggregate)
    signals: List[str] = Field(default_factory=list)
    review_themes: List[ReviewTheme] = Field(default_factory=list)


# -----------------------------------------------------------------------------
# 3. Customer Context Models
# -----------------------------------------------------------------------------

class CustomerIdentity(BaseModel):
    name: str
    phone_redacted: Optional[str] = "<phone>"
    language_pref: Optional[str] = "en"
    age_band: Optional[str] = None


class CustomerRelationship(BaseModel):
    first_visit: Optional[str] = None
    last_visit: Optional[str] = None
    visits_total: int = 1
    services_received: List[str] = Field(default_factory=list)
    lifetime_value: Optional[float] = 0.0


class CustomerPreferences(BaseModel):
    preferred_slots: Optional[str] = None  # weekday_evening, weekend_morning, etc.
    channel: str = "whatsapp"
    reminder_opt_in: bool = True


class CustomerConsent(BaseModel):
    opted_in_at: Optional[str] = None
    scope: List[str] = Field(default_factory=lambda: ["promotional_offers", "recall_reminders"])


class CustomerContext(BaseModel):
    customer_id: str
    merchant_id: str
    identity: CustomerIdentity
    relationship: CustomerRelationship = Field(default_factory=CustomerRelationship)
    state: str = "active"  # new, active, lapsed_soft, lapsed_hard, churned
    preferences: CustomerPreferences = Field(default_factory=CustomerPreferences)
    consent: CustomerConsent = Field(default_factory=CustomerConsent)


# -----------------------------------------------------------------------------
# 4. Trigger Context Models
# -----------------------------------------------------------------------------

class TriggerContext(BaseModel):
    id: str
    scope: Literal["merchant", "customer"] = "merchant"
    kind: str
    source: Literal["external", "internal"] = "external"
    merchant_id: Optional[str] = None
    customer_id: Optional[str] = None
    payload: Dict[str, Any] = Field(default_factory=dict)
    urgency: int = 1
    suppression_key: str = ""
    expires_at: Optional[str] = None


# -----------------------------------------------------------------------------
# 5. API Endpoint Request / Response DTOs
# -----------------------------------------------------------------------------

class CtxPushBody(BaseModel):
    scope: str
    context_id: str
    version: int
    payload: Dict[str, Any]
    delivered_at: Optional[str] = None


class CtxPushResponse(BaseModel):
    accepted: bool
    ack_id: Optional[str] = None
    stored_at: Optional[str] = None
    reason: Optional[str] = None
    current_version: Optional[int] = None
    details: Optional[str] = None


class TickBody(BaseModel):
    now: Optional[str] = None
    available_triggers: List[str] = Field(default_factory=list)


class TickAction(BaseModel):
    conversation_id: str
    merchant_id: str
    customer_id: Optional[str] = None
    send_as: Literal["vera", "merchant_on_behalf"] = "vera"
    trigger_id: str
    template_name: str
    template_params: List[str] = Field(default_factory=list)
    body: str
    cta: str
    suppression_key: str
    rationale: str


class TickResponse(BaseModel):
    actions: List[TickAction] = Field(default_factory=list)


class ReplyBody(BaseModel):
    conversation_id: str
    merchant_id: Optional[str] = None
    customer_id: Optional[str] = None
    from_role: str = "merchant"
    message: str
    received_at: Optional[str] = None
    turn_number: int = 1


class ReplyResponse(BaseModel):
    action: Literal["send", "wait", "end"]
    body: Optional[str] = ""
    cta: Optional[str] = "none"
    wait_seconds: Optional[int] = None
    rationale: str


class HealthResponse(BaseModel):
    status: str = "ok"
    uptime_seconds: int
    contexts_loaded: Dict[str, int]


class MetadataResponse(BaseModel):
    team_name: str
    team_members: List[str]
    model: str
    approach: str
    contact_email: str
    version: str
    submitted_at: str
