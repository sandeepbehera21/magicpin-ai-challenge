from __future__ import annotations
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
from .opportunity import Opportunity
from .state import MerchantDerivedState, CustomerDerivedState


class SendDecisionKind(str, Enum):
    SEND_NOW = "SEND_NOW"
    WAIT = "WAIT"
    SUPPRESS = "SUPPRESS"


class CTAConfig(BaseModel):
    cta_type: str  # "open_ended", "binary_yes_no", "binary_confirm_cancel", "multi_choice_slot", "none"
    text: str
    target_action: str


class Decision(BaseModel):
    action_type: SendDecisionKind = SendDecisionKind.SEND_NOW
    winning_opportunity: Optional[Opportunity] = None
    merchant_state: Optional[MerchantDerivedState] = None
    customer_state: Optional[CustomerDerivedState] = None
    
    send_as: str = "vera"  # "vera" or "merchant_on_behalf"
    message_objective: str = ""
    tone: str = "peer_clinical"
    cta: CTAConfig
    suppression_key: str = ""
    wait_seconds: Optional[int] = None
    rationale: str = ""
    
    selected_evidence_ids: List[str] = Field(default_factory=list)
    template_name: str = "vera_standard_v1"
    template_params: List[str] = Field(default_factory=list)
