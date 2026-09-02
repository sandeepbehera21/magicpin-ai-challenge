from __future__ import annotations
from typing import List, Optional, Tuple
from pydantic import BaseModel
from ..models.context import TriggerContext
from ..models.evidence import EvidenceLedger
from ..models.opportunity import Opportunity
from ..models.state import MerchantDerivedState
from ..models.decision import SendDecisionKind


class AttentionROI(BaseModel):
    score: float
    merchant_value: float
    evidence_strength: float
    actionability: float
    timing_value: float
    novelty: float
    interruption_cost: float
    fatigue_penalty: float
    rationale: str


class CounterfactualGate:
    @classmethod
    def calculate_attention_roi(
        cls,
        opportunity: Opportunity,
        trigger: TriggerContext,
        merchant_state: MerchantDerivedState,
        evidence_ledger: EvidenceLedger,
    ) -> AttentionROI:
        """
        Calculates deterministic Attention ROI:
        ROI = merchant_value + evidence_strength + actionability + timing_value + novelty
              - interruption_cost - fatigue_penalty - repetition_penalty
        """
        merchant_value = 5.0
        evidence_strength = getattr(opportunity, "evidence_strength", 5.0)
        actionability = 5.0
        timing_value = 5.0
        novelty = 7.0
        interruption_cost = 4.0
        fatigue_penalty = 0.0

        kind = trigger.kind.lower()
        payload = trigger.payload or {}

        # 1. Actionability & Merchant Value based on concrete payloads
        if "planning" in kind or "active_planning" in kind:
            merchant_value = 9.0
            actionability = 9.5
            timing_value = 9.0
        elif "supply" in kind or "recall" in kind or "regulation" in kind or "compliance" in kind:
            merchant_value = 9.0
            actionability = 8.5
            timing_value = 8.5
        elif "review_theme" in kind:
            merchant_value = 8.5
            actionability = 8.0
            timing_value = 8.0
        elif "winback" in kind:
            merchant_value = 8.0
            actionability = 8.5
            timing_value = 7.5
        elif "ipl" in kind or "event" in kind:
            merchant_value = 8.0
            actionability = 8.0
            timing_value = 9.0
        elif "research" in kind or "digest" in kind:
            merchant_value = 7.5
            actionability = 7.5
            timing_value = 7.0
        elif "curious" in kind:
            merchant_value = 7.0
            actionability = 8.0
            timing_value = 6.5
        elif "dip" in kind or "seasonal" in kind:
            merchant_value = 7.5
            actionability = 7.5
            timing_value = 7.5
        elif "renewal" in kind:
            merchant_value = 8.0
            actionability = 9.0
            timing_value = 8.0
        elif "festival" in kind:
            days = payload.get("days_until", 180)
            if days > 30:
                timing_value = 1.0  # Far away festival has very low timing value today
                interruption_cost = 7.0
            else:
                timing_value = 8.0
        elif "milestone" in kind:
            merchant_value = 6.0
            actionability = 6.0
            timing_value = 5.0

        # Penalize weak/empty payload
        if not payload or len(payload) == 0:
            if "curious" not in kind and "milestone" not in kind:
                actionability -= 3.0
                evidence_strength -= 3.0
                interruption_cost += 3.0

        total_roi = (
            merchant_value
            + evidence_strength
            + actionability
            + timing_value
            + novelty
            - interruption_cost
            - fatigue_penalty
        )

        return AttentionROI(
            score=round(total_roi, 2),
            merchant_value=merchant_value,
            evidence_strength=evidence_strength,
            actionability=actionability,
            timing_value=timing_value,
            novelty=novelty,
            interruption_cost=interruption_cost,
            fatigue_penalty=fatigue_penalty,
            rationale=f"ROI {total_roi:.1f}: mv={merchant_value}, ev={evidence_strength}, act={actionability}, tim={timing_value}, cost={interruption_cost}",
        )

    @classmethod
    def evaluate(
        cls,
        opportunity: Opportunity,
        trigger: TriggerContext,
        merchant_state: MerchantDerivedState,
        evidence_ledger: EvidenceLedger,
    ) -> Tuple[SendDecisionKind, str, Optional[int]]:
        """
        Deterministic Counterfactual Gate:
        Decides whether to SEND_NOW, WAIT, or SUPPRESS based on incremental value,
        timing delta, and attention ROI.
        """
        roi = cls.calculate_attention_roi(opportunity, trigger, merchant_state, evidence_ledger)
        kind = trigger.kind.lower()
        payload = trigger.payload or {}

        # ---------------------------------------------------------------------
        # 1. HARD SUPPRESSION RULES
        # ---------------------------------------------------------------------
        # A. Distant festivals (e.g. Diwali in 188 days) -> SUPPRESS
        if "festival" in kind and payload.get("days_until", 0) > 30:
            return (
                SendDecisionKind.SUPPRESS,
                f"Festival is {payload.get('days_until')} days away; too early to interrupt merchant without fatigue.",
                None,
            )

        # B. Weather heatwave or generic triggers with no category/merchant fit -> SUPPRESS
        if "weather" in kind or "heatwave" in kind:
            return (
                SendDecisionKind.SUPPRESS,
                "Generic external weather signal lacks actionable merchant-specific connection.",
                None,
            )

        # ---------------------------------------------------------------------
        # 2. INTELLIGENT WAIT RULES
        # ---------------------------------------------------------------------
        # A. Low overall Attention ROI (< 18.0) -> WAIT
        if roi.score < 18.0:
            return (
                SendDecisionKind.WAIT,
                f"Attention ROI ({roi.score:.1f}) is below threshold (18.0); waiting for stronger signal.",
                86400,
            )

        # B. Renewal trigger where expiry is > 14 days away -> WAIT
        if "renewal" in kind:
            days = payload.get("days_remaining", 30)
            if days > 14:
                return (
                    SendDecisionKind.WAIT,
                    f"Renewal is {days} days away; backing off until urgent 14-day window.",
                    86400 * 3,
                )

        # ---------------------------------------------------------------------
        # 3. SEND_NOW
        # ---------------------------------------------------------------------
        return (
            SendDecisionKind.SEND_NOW,
            f"High-conviction opportunity approved by Counterfactual Gate ({roi.rationale}).",
            None,
        )
