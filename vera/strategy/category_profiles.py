from __future__ import annotations
from typing import Dict, List, Optional
from pydantic import BaseModel, Field


class CategoryStrategyProfile(BaseModel):
    slug: str
    display_name: str
    tone: str
    salutation_format: str
    customer_salutation_format: str
    vocab_allowed: List[str] = Field(default_factory=list)
    vocab_taboo: List[str] = Field(default_factory=list)
    preferred_emojis: List[str] = Field(default_factory=list)
    primary_compulsion_levers: List[str] = Field(default_factory=list)
    customer_voice_rules: str = ""
    merchant_voice_rules: str = ""


CATEGORY_PROFILES: Dict[str, CategoryStrategyProfile] = {
    "dentists": CategoryStrategyProfile(
        slug="dentists",
        display_name="Dentists",
        tone="peer_clinical",
        salutation_format="Dr. {owner_or_name}",
        customer_salutation_format="Hi {customer_name}, {clinic_name} here 🦷",
        vocab_allowed=[
            "fluoride varnish", "caries", "scaling", "occlusion", "bruxism",
            "endodontic", "periodontal", "aligner", "veneer", "IOPA", "RCT", "OPG",
            "clinical trial", "recall interval", "high-risk adult"
        ],
        vocab_taboo=[
            "guaranteed", "100% safe", "completely cure", "miracle", "best in city",
            "doctor approved", "flat 50% discount"
        ],
        preferred_emojis=["🦷", "📋"],
        primary_compulsion_levers=["source_citation", "clinical_specificity", "patient_retention", "reciprocity"],
        customer_voice_rules="Clinical, warm, never overclaim medical outcomes, clear slot choices, no shame.",
        merchant_voice_rules="Peer-to-peer collegial tone, cite relevant journals or clinical evidence, reference patient segments.",
    ),
    "salons": CategoryStrategyProfile(
        slug="salons",
        display_name="Salons & Beauty",
        tone="warm_operator",
        salutation_format="Hi {owner_or_name}",
        customer_salutation_format="Hi {customer_name} 💍 {owner_or_biz} here",
        vocab_allowed=[
            "keratin", "balayage", "bridal trial", "skin-prep", "haircut",
            "manicure", "pedicure", "threading", "facial", "slot", "grooming",
            "hair spa", "consultation"
        ],
        vocab_taboo=[
            "guaranteed look", "permanent magic", "cheap services"
        ],
        preferred_emojis=["💍", "✨", "💇‍♀️", "💅"],
        primary_compulsion_levers=["wedding_timing", "service_price", "effort_externalization", "curious_ask"],
        customer_voice_rules="Warm, enthusiastic, wedding prep timeline anchoring, low friction booking.",
        merchant_voice_rules="Operator-to-operator, practical marketing, curious asks about trending treatments.",
    ),
    "restaurants": CategoryStrategyProfile(
        slug="restaurants",
        display_name="Restaurants & Cafes",
        tone="operator_to_operator",
        salutation_format="Hi {owner_or_name}",
        customer_salutation_format="Hi {customer_name} 🍽️ {biz_name} here",
        vocab_allowed=[
            "covers", "match-night", "lunch thali", "delivery radius", "AOV",
            "corporate bulk", "BOGO", "Swiggy", "Zomato", "takeaway", "dine-in",
            "kitchen prep", "combo"
        ],
        vocab_taboo=[
            "world's best food", "unlimited free everything"
        ],
        preferred_emojis=["🍽️", "🍕", "🏏", "☕"],
        primary_compulsion_levers=["loss_aversion", "event_counter_timing", "tiered_pricing", "effort_cap"],
        customer_voice_rules="Appetizing, clear pricing, delivery radius clarity, limited-time combos.",
        merchant_voice_rules="Operator peer voice, focus on table turns, covers, delivery vs dine-in dynamics during IPL/events.",
    ),
    "gyms": CategoryStrategyProfile(
        slug="gyms",
        display_name="Gyms & Fitness Studios",
        tone="coach_operator",
        salutation_format="Hi {owner_or_name}",
        customer_salutation_format="Hi {customer_name} 👋 {owner_or_biz} here",
        vocab_allowed=[
            "HIIT", "strength conditioning", "acquisition lull", "retention challenge",
            "trial spot", "member churn", "conversion", "summer challenge", "PR",
            "weight loss", "hypertrophy", "cardio"
        ],
        vocab_taboo=[
            "lose 10kg in 3 days", "guaranteed six pack", "instant transformation"
        ],
        preferred_emojis=["💪", "👋", "🔥", "🏋️"],
        primary_compulsion_levers=["anxiety_preemption", "no_shame_winback", "member_retention", "binary_trial_cta"],
        customer_voice_rules="No-shame, welcoming, no commitment / no auto-charge guarantee, goal-aligned classes.",
        merchant_voice_rules="Coach-to-operator, data-informed reframe of seasonal drops, focus on member retention.",
    ),
    "pharmacies": CategoryStrategyProfile(
        slug="pharmacies",
        display_name="Pharmacies & Healthcare",
        tone="trustworthy_precise",
        salutation_format="{owner_or_name}",
        customer_salutation_format="Namaste — {biz_name} {locality} yahan",
        vocab_allowed=[
            "chronic-Rx", "molecule", "sub-potency", "refill", "voluntary recall",
            "home delivery", "senior discount", "maintenance medication", "dosage",
            "compliance circular"
        ],
        vocab_taboo=[
            "cure all diseases", "miracle pill", "discount on life-saving drugs"
        ],
        preferred_emojis=["💊", "🙏"],
        primary_compulsion_levers=["regulatory_compliance", "senior_respect", "exact_savings", "repeat_refill_timing"],
        customer_voice_rules="Namaste salutation, respectful of seniors, precise molecule names, total savings shown.",
        merchant_voice_rules="Trustworthy, precise compliance notes, patient batch recalls, repeat-Rx workflow assistance.",
    ),
}

GENERIC_PROFILE = CategoryStrategyProfile(
    slug="generic",
    display_name="Local Business",
    tone="respectful_peer",
    salutation_format="Hi {owner_or_name}",
    customer_salutation_format="Hi {customer_name}, {biz_name} here",
    vocab_allowed=["customers", "profile", "Google listing", "reviews", "walk-ins", "offers"],
    vocab_taboo=["guaranteed", "100% safe", "miracle"],
    preferred_emojis=["📍", "✨"],
    primary_compulsion_levers=["verifiable_specificity", "effort_externalization", "single_binary_cta"],
    customer_voice_rules="Clear, polite, service+price focus.",
    merchant_voice_rules="Helpful business assistant, clear numbers, immediate value.",
)


def get_category_profile(slug: Optional[str], category_ctx: Optional[Any] = None) -> CategoryStrategyProfile:
    if not slug:
        return GENERIC_PROFILE
    
    # If standard static profile exists, use it as baseline
    profile = CATEGORY_PROFILES.get(slug.lower().strip())
    
    # If dynamic CategoryContext was pushed, merge any custom fields
    if category_ctx:
        vp = getattr(category_ctx, "voice_profile", None) or (category_ctx.get("voice_profile") if isinstance(category_ctx, dict) else None)
        allowed = getattr(category_ctx, "allowed_vocabulary", None) or (category_ctx.get("allowed_vocabulary") if isinstance(category_ctx, dict) else None)
        taboos = getattr(category_ctx, "taboo_words", None) or (category_ctx.get("taboo_words") if isinstance(category_ctx, dict) else None)
        
        base_profile = profile or GENERIC_PROFILE
        return CategoryStrategyProfile(
            slug=slug,
            display_name=getattr(category_ctx, "display_name", None) or base_profile.display_name,
            tone=(vp.tone if vp and hasattr(vp, "tone") else (vp.get("tone") if isinstance(vp, dict) else base_profile.tone)),
            salutation_format=base_profile.salutation_format,
            customer_salutation_format=base_profile.customer_salutation_format,
            vocab_allowed=allowed if allowed is not None else base_profile.vocab_allowed,
            vocab_taboo=taboos if taboos is not None else base_profile.vocab_taboo,
            preferred_emojis=base_profile.preferred_emojis,
            primary_compulsion_levers=base_profile.primary_compulsion_levers,
            customer_voice_rules=base_profile.customer_voice_rules,
            merchant_voice_rules=base_profile.merchant_voice_rules,
        )

    return profile or GENERIC_PROFILE
