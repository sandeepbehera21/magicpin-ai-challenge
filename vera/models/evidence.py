from __future__ import annotations
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class EvidenceItem(BaseModel):
    evidence_id: str
    source_scope: str  # "category", "merchant", "customer", "trigger"
    source_context_id: str
    field_path: str
    value: Any
    evidence_type: str  # "metric", "citation", "offer", "aggregate", "profile", "trigger_payload", "benchmark"
    freshness: float = 1.0  # 0.0 - 1.0
    relevance: float = 1.0  # 0.0 - 1.0
    confidence: float = 1.0  # 0.0 - 1.0
    display_fact: str  # human-readable verifiable fact representation (e.g., "views_pct: +18%")


class EvidenceLedger(BaseModel):
    items: List[EvidenceItem] = Field(default_factory=list)

    def add(self, item: EvidenceItem) -> None:
        self.items.append(item)

    def get_by_id(self, evidence_id: str) -> Optional[EvidenceItem]:
        for item in self.items:
            if item.evidence_id == evidence_id:
                return item
        return None

    def get_by_field_path(self, field_path: str) -> Optional[EvidenceItem]:
        for item in self.items:
            if item.field_path == field_path:
                return item
        return None

    def get_all_by_prefix(self, prefix: str) -> List[EvidenceItem]:
        return [item for item in self.items if item.field_path.startswith(prefix)]

    def extract_numbers_and_keywords(self) -> Dict[str, Any]:
        """Extract set of verifiable facts for criticism/validation."""
        facts = {}
        for item in self.items:
            facts[item.field_path] = item.value
        return facts
