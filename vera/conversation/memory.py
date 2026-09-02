from __future__ import annotations
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set
from pydantic import BaseModel, Field
from .states import ConversationStateKind


class ConversationMemory(BaseModel):
    conversation_id: str
    merchant_id: str
    customer_id: Optional[str] = None
    
    current_state: ConversationStateKind = ConversationStateKind.NEW
    state_history: List[ConversationStateKind] = Field(default_factory=list)
    
    last_trigger_id: Optional[str] = None
    last_trigger_kind: Optional[str] = None
    last_message_body: Optional[str] = None
    last_cta_type: Optional[str] = None
    
    # Message turns
    turns: List[Dict[str, Any]] = Field(default_factory=list)
    
    # Memory and deduplication
    facts_presented: Set[str] = Field(default_factory=set)
    ctas_requested: List[str] = Field(default_factory=list)
    intents_detected: List[str] = Field(default_factory=list)
    
    # Dynamics
    fatigue_score: float = 0.0
    auto_reply_count: int = 0
    language_preferred: str = "en"
    is_suppressed: bool = False
    wait_until_iso: Optional[str] = None
    created_at_iso: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at_iso: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def record_turn(self, from_role: str, message: str, intent: Optional[str] = None) -> None:
        self.turns.append({
            "from": from_role,
            "message": message,
            "intent": intent,
            "ts": datetime.now(timezone.utc).isoformat(),
        })
        if intent:
            self.intents_detected.append(intent)
        self.updated_at_iso = datetime.now(timezone.utc).isoformat()

    def transition_to(self, new_state: ConversationStateKind) -> None:
        self.state_history.append(self.current_state)
        self.current_state = new_state
        self.updated_at_iso = datetime.now(timezone.utc).isoformat()

    def add_presented_facts(self, facts: List[str]) -> None:
        for f in facts:
            self.facts_presented.add(f.strip())

    def has_fact_been_presented(self, fact: str) -> bool:
        return fact.strip() in self.facts_presented
