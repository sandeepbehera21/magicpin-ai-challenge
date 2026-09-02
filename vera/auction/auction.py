from __future__ import annotations
from datetime import datetime, timezone
from typing import Dict, List, Optional
from ..models.context import CategoryContext, MerchantContext, CustomerContext, TriggerContext
from ..models.evidence import EvidenceLedger
from ..models.opportunity import Opportunity, AuctionResult
from ..models.state import MerchantDerivedState
from ..strategy.triggers import get_trigger_strategy


class OpportunityAuction:
    @staticmethod
    def evaluate_opportunity(
        trigger: TriggerContext,
        merchant: MerchantContext,
        category: Optional[CategoryContext],
        customer: Optional[CustomerContext],
        merchant_state: MerchantDerivedState,
        evidence_ledger: EvidenceLedger,
    ) -> Opportunity:
        strategy = get_trigger_strategy(trigger.kind)
        notes = []
        payload = trigger.payload or {}
        kind = trigger.kind.lower()

        # 1. Urgency (Scale 0-10)
        raw_urgency = float(trigger.urgency) * 2.0
        urgency_score = (raw_urgency * 0.6) + (strategy.base_urgency * 0.4)

        # 2. Evidence Strength (Scale 0-10)
        has_citation = any(item.evidence_type == "citation" for item in evidence_ledger.items)
        has_metrics = any(item.evidence_type == "metric" for item in evidence_ledger.items)
        has_active_offer = any(item.evidence_type == "offer" for item in evidence_ledger.items)
        has_aggregate = any(item.evidence_type == "aggregate" for item in evidence_ledger.items)

        evidence_score = 4.0
        if has_citation:
            evidence_score += 2.5
        if has_metrics:
            evidence_score += 1.5
        if has_active_offer:
            evidence_score += 1.0
        if has_aggregate:
            evidence_score += 1.0
        evidence_score = min(10.0, evidence_score)

        # 3. Category Relevance (Scale 0-10)
        category_rel = 8.5
        if category:
            cat_payload = payload.get("category")
            if cat_payload and cat_payload.lower() != category.slug.lower():
                category_rel = 0.5  # Hard mismatch
                notes.append(f"Hard category mismatch: trigger '{cat_payload}' vs merchant '{category.slug}'")

        # 4. Merchant Relevance (Scale 0-10)
        merchant_rel = 5.0

        if category_rel <= 1.0:
            merchant_rel = 0.5
            evidence_score = 0.5
        else:
            # Research digest with high-risk adult or chronic-rx cohort match
            if "research" in kind or "digest" in kind:
                if merchant_state.has_high_risk_cohort or merchant_state.has_chronic_rx_cohort:
                    merchant_rel += 4.5
                elif merchant_state.ctr_state == "below_peer":
                    merchant_rel += 2.0

            # Performance dip
            elif "dip" in kind or "perf_dip" in kind:
                if merchant_state.health in ("declining", "underperforming") or merchant_state.calls_trend in ("dipping", "declining"):
                    merchant_rel += 4.5
                else:
                    merchant_rel += 1.5

            # Review theme
            elif "review_theme" in kind:
                merchant_rel += 4.0

            # Winback
            elif "winback" in kind:
                merchant_rel += 4.5

            # Active planning
            elif "planning" in kind:
                merchant_rel += 4.5

            # Performance spike / milestone
            elif "spike" in kind or "milestone" in kind:
                if merchant_state.views_trend in ("spiking", "growing") or merchant_state.calls_trend in ("spiking", "growing"):
                    merchant_rel += 4.0

            # Renewal due
            elif "renewal" in kind:
                if merchant_state.urgent_renewal:
                    merchant_rel += 4.5

            # Curious ask
            elif "curious" in kind:
                if merchant_state.engagement_level == "recently_engaged":
                    merchant_rel += 3.5

            # Customer scope
            elif trigger.scope == "customer" and customer:
                merchant_rel += 4.5
                if customer.state in ("lapsed_soft", "lapsed_hard") and "recall" in kind:
                    merchant_rel += 1.0

        merchant_rel = min(10.0, max(0.5, merchant_rel))

        # 5. Actionability (Scale 0-10)
        actionability = strategy.actionability_score
        if merchant_state.has_active_offer:
            actionability = min(10.0, actionability + 1.0)

        # 6. Freshness & Timing Fit
        freshness = 9.0
        timing_fit = 8.5
        if "festival" in kind:
            days = payload.get("days_until", 180)
            if days > 30:
                timing_fit = 1.0
                urgency_score = 1.0

        # 7. Penalties
        fatigue_penalty = 0.0
        if merchant_state.engagement_level == "disengaged":
            fatigue_penalty += 1.5

        repetition_penalty = 0.0
        uncertainty_penalty = 0.0
        if not payload or len(payload) == 0:
            if "curious" not in kind and "milestone" not in kind:
                uncertainty_penalty += 2.5

        # 8. Composite Opportunity Score
        composite = (
            (merchant_rel * 2.8) +
            (evidence_score * 2.2) +
            (actionability * 2.0) +
            (timing_fit * 1.5) +
            (urgency_score * 1.0) +
            (category_rel * 1.0) +
            (freshness * 0.5)
        ) - (fatigue_penalty * 2.0) - (repetition_penalty * 2.0) - (uncertainty_penalty * 3.0)

        final_score = round(max(0.0, min(100.0, composite)), 2)

        return Opportunity(
            trigger_id=trigger.id,
            trigger_kind=trigger.kind,
            merchant_id=merchant.merchant_id,
            customer_id=customer.customer_id if customer else None,
            scope=trigger.scope,
            urgency=urgency_score,
            freshness=freshness,
            evidence_strength=evidence_score,
            merchant_relevance=merchant_rel,
            category_relevance=category_rel,
            actionability=actionability,
            timing_fit=timing_fit,
            novelty=9.0,
            conversation_fit=8.0,
            offer_fit=8.5 if merchant_state.has_active_offer else 6.0,
            customer_fit=9.0 if customer else 5.0,
            fatigue_penalty=fatigue_penalty,
            repetition_penalty=repetition_penalty,
            uncertainty_penalty=uncertainty_penalty,
            final_score=final_score,
            ranking_notes=notes,
        )

    @staticmethod
    def rank_opportunities(opportunities: List[Opportunity]) -> AuctionResult:
        if not opportunities:
            return AuctionResult(winning_opportunity=None, ranked_opportunities=[])

        # Sort descending by final_score, breaking ties deterministically
        ranked = sorted(
            opportunities,
            key=lambda opp: (
                opp.final_score,
                opp.merchant_relevance,
                opp.evidence_strength,
                opp.actionability,
                opp.urgency,
                opp.trigger_id,
            ),
            reverse=True,
        )

        winner = ranked[0] if ranked else None
        second = ranked[1] if len(ranked) > 1 else None
        margin = round(winner.final_score - (second.final_score if second else 0.0), 2) if winner else 0.0

        return AuctionResult(
            winning_opportunity=winner,
            ranked_opportunities=ranked,
            score_margin=margin,
            total_evaluated=len(opportunities),
        )
