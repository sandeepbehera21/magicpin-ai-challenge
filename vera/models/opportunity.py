from __future__ import annotations
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class Opportunity(BaseModel):
    trigger_id: str
    trigger_kind: str
    merchant_id: str
    customer_id: Optional[str] = None
    scope: str = "merchant"  # "merchant" or "customer"
    
    # Sub-scores (0.0 to 10.0 scale)
    urgency: float = 5.0
    freshness: float = 10.0
    evidence_strength: float = 5.0
    merchant_relevance: float = 5.0
    category_relevance: float = 5.0
    actionability: float = 5.0
    timing_fit: float = 5.0
    novelty: float = 5.0
    conversation_fit: float = 5.0
    offer_fit: float = 5.0
    customer_fit: float = 5.0
    
    # Penalties
    fatigue_penalty: float = 0.0
    repetition_penalty: float = 0.0
    uncertainty_penalty: float = 0.0
    
    # Final composite score (0.0 - 100.0)
    final_score: float = 0.0
    confidence: float = 1.0
    
    # Reason trace
    scoring_notes: List[str] = Field(default_factory=list)


class AuctionResult(BaseModel):
    ranked_opportunities: List[Opportunity] = Field(default_factory=list)
    winner: Optional[Opportunity] = None
    suppressed: List[Dict[str, Any]] = Field(default_factory=list)
    auction_timestamp: str = ""
