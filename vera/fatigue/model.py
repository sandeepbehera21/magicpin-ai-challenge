from __future__ import annotations
from datetime import datetime, timezone
from typing import List, Optional, Tuple
from pydantic import BaseModel
from ..models.context import MerchantContext


class FatigueAssessment(BaseModel):
    level: str  # "LOW", "MEDIUM", "HIGH"
    score: float  # 0.0 to 10.0
    reason: str
    recommended_action: str  # "PROCEED", "SOFTEN_ANGLE", "SUPPRESS_OR_WAIT"


class MerchantFatigueModel:
    @classmethod
    def evaluate(
        cls,
        merchant: MerchantContext,
        recent_sends_count: int = 0,
        unanswered_nudges: int = 0,
        recent_opt_outs: int = 0,
        hours_since_last_touch: Optional[float] = None,
    ) -> FatigueAssessment:
        score = 0.0
        reasons: List[str] = []

        # 1. Unanswered nudges penalty
        if unanswered_nudges >= 3:
            score += 5.0
            reasons.append(f"{unanswered_nudges} consecutive unanswered touches")
        elif unanswered_nudges >= 1:
            score += 1.5 * unanswered_nudges

        # 2. Recency / frequency pressure
        if hours_since_last_touch is not None:
            if hours_since_last_touch < 4.0:
                score += 4.0
                reasons.append(f"Contacted very recently ({hours_since_last_touch:.1f}h ago)")
            elif hours_since_last_touch < 24.0:
                score += 1.5
        elif recent_sends_count >= 3:
            score += 3.5
            reasons.append(f"{recent_sends_count} messages sent in current window")

        # 3. Signals from context
        for sig in merchant.signals:
            sig_lower = sig.lower()
            if "dormant" in sig_lower:
                # Dormant merchants are sensitive to spam
                score += 1.0
            if "unsubscribed" in sig_lower:
                score += 6.0
                reasons.append("Historical unsubscription signal")

        # 4. Conversation history analysis
        if merchant.conversation_history:
            last_3 = merchant.conversation_history[-3:]
            ignored_count = sum(1 for t in last_3 if t.engagement == "merchant_no_reply")
            if ignored_count >= 2:
                score += 2.5
                reasons.append(f"{ignored_count} of last 3 turns ignored")

        # 5. Determine level
        score = min(10.0, max(0.0, score))
        if score >= 6.0 or recent_opt_outs > 0:
            level = "HIGH"
            rec = "SUPPRESS_OR_WAIT"
        elif score >= 3.0:
            level = "MEDIUM"
            rec = "SOFTEN_ANGLE"
        else:
            level = "LOW"
            rec = "PROCEED"

        reason_str = "; ".join(reasons) if reasons else "Healthy contact history with minimal fatigue pressure"
        return FatigueAssessment(
            level=level,
            score=round(score, 2),
            reason=reason_str,
            recommended_action=rec,
        )
