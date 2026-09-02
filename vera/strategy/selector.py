from __future__ import annotations
from enum import Enum
from typing import Optional
from ..models.context import TriggerContext
from ..models.evidence import EvidenceLedger
from ..models.state import MerchantDerivedState
from ..fatigue.model import FatigueAssessment


class StrategyKind(str, Enum):
    PROOF = "PROOF"
    BENCHMARK = "BENCHMARK"
    CURIOSITY = "CURIOSITY"
    TIMING = "TIMING"
    LOSS_AVERSION = "LOSS_AVERSION"
    OFFER_READY = "OFFER_READY"
    PERFORMANCE_INSIGHT = "PERFORMANCE_INSIGHT"
    CUSTOMER_RECALL = "CUSTOMER_RECALL"
    QUICK_WIN = "QUICK_WIN"
    EDUCATIONAL = "EDUCATIONAL"


class MessageStrategySelector:
    @classmethod
    def select_strategy(
        cls,
        trigger: TriggerContext,
        merchant_state: MerchantDerivedState,
        evidence_ledger: EvidenceLedger,
        fatigue: FatigueAssessment,
        is_customer: bool = False,
    ) -> StrategyKind:
        if is_customer:
            return StrategyKind.CUSTOMER_RECALL

        kind = trigger.kind.lower()

        # 1. Fatigue pressure overrides
        if fatigue.level == "HIGH":
            return StrategyKind.QUICK_WIN

        # 2. Research / Regulatory -> PROOF
        if "research" in kind or "digest" in kind or "regulation" in kind or "compliance" in kind or "supply" in kind:
            return StrategyKind.PROOF

        # 3. Performance / Benchmark
        if "dip" in kind or "seasonal" in kind:
            if merchant_state.ctr_state == "below_peer":
                return StrategyKind.BENCHMARK
            return StrategyKind.LOSS_AVERSION

        if "spike" in kind or "milestone" in kind:
            return StrategyKind.PERFORMANCE_INSIGHT

        # 4. Event / IPL / News / Weather
        if "ipl" in kind or "festival" in kind or "weather" in kind or "event" in kind:
            return StrategyKind.TIMING

        # 5. Curious asks / Planning
        if "curious" in kind:
            return StrategyKind.CURIOSITY

        if "planning" in kind or "active_planning" in kind:
            return StrategyKind.QUICK_WIN

        # 6. Active offer leverage
        if merchant_state.has_active_offer and merchant_state.ctr_state == "below_peer":
            return StrategyKind.OFFER_READY

        # 7. Renewal
        if "renewal" in kind or merchant_state.urgent_renewal:
            return StrategyKind.LOSS_AVERSION

        # 8. Educational
        if any(item.evidence_type == "content_library" for item in evidence_ledger.items):
            return StrategyKind.EDUCATIONAL

        return StrategyKind.QUICK_WIN
