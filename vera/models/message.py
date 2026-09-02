from __future__ import annotations
from typing import List, Optional
from pydantic import BaseModel, Field


class ComposedMessage(BaseModel):
    body: str
    cta: str  # "open_ended", "binary_yes_no", "multi_choice_slot", "binary_confirm_cancel", "none"
    send_as: str = "vera"  # "vera" or "merchant_on_behalf"
    suppression_key: str = ""
    rationale: str = ""
    template_name: str = "vera_generic_v1"
    template_params: List[str] = Field(default_factory=list)
    confidence: float = 1.0
    evidence_used: List[str] = Field(default_factory=list)


class MessageAction(BaseModel):
    conversation_id: str
    merchant_id: str
    customer_id: Optional[str] = None
    send_as: str = "vera"
    trigger_id: str
    template_name: str
    template_params: List[str] = Field(default_factory=list)
    body: str
    cta: str
    suppression_key: str
    rationale: str
