from __future__ import annotations
from typing import Optional
from ..models.context import CategoryContext, MerchantContext
from ..models.state import MerchantDerivedState


class MerchantStateEngine:
    @staticmethod
    def derive_state(
        merchant: MerchantContext,
        category: Optional[CategoryContext] = None,
    ) -> MerchantDerivedState:
        mid = merchant.merchant_id
        cat_slug = merchant.category_slug

        state = MerchantDerivedState(
            merchant_id=mid,
            category_slug=cat_slug,
        )

        perf = merchant.performance
        sub = merchant.subscription
        signals = merchant.signals

        # 1. Benchmark & CTR State
        peer_ctr = category.peer_stats.avg_ctr if (category and category.peer_stats and category.peer_stats.avg_ctr) else 0.030
        if perf.ctr > 0:
            if perf.ctr >= peer_ctr * 1.15:
                state.ctr_state = "above_peer"
            elif perf.ctr <= peer_ctr * 0.85:
                state.ctr_state = "below_peer"
            else:
                state.ctr_state = "at_peer"

        # 2. Performance Trajectory (7d deltas)
        vp = 0.0
        cp = 0.0
        if perf.delta_7d:
            if isinstance(perf.delta_7d, dict):
                vp = float(perf.delta_7d.get("views_pct") or 0.0)
                cp = float(perf.delta_7d.get("calls_pct") or 0.0)
            else:
                vp = float(perf.delta_7d.views_pct or 0.0)
                cp = float(perf.delta_7d.calls_pct or 0.0)

        # Views trend
        if vp >= 0.25:
            state.views_trend = "spiking"
        elif vp >= 0.10:
            state.views_trend = "growing"
        elif vp <= -0.25:
            state.views_trend = "declining"
        elif vp <= -0.15:
            state.views_trend = "dipping"
        else:
            state.views_trend = "stable"

        # Calls trend
        if cp >= 0.25:
            state.calls_trend = "spiking"
        elif cp >= 0.10:
            state.calls_trend = "growing"
        elif cp <= -0.25:
            state.calls_trend = "declining"
        elif cp <= -0.15:
            state.calls_trend = "dipping"
        else:
            state.calls_trend = "stable"

        # Health composite
        if state.calls_trend in ("dipping", "declining") or state.views_trend in ("dipping", "declining"):
            state.health = "declining"
        elif state.ctr_state == "below_peer":
            state.health = "underperforming"
        elif state.views_trend in ("spiking", "growing") or state.calls_trend in ("spiking", "growing"):
            state.health = "growing"
        else:
            state.health = "healthy"

        # 3. Offers & Assets
        active_offers = [o.title for o in merchant.offers if o.status == "active"]
        state.has_active_offer = len(active_offers) > 0
        state.active_offer_titles = active_offers

        # 4. Cohorts & Aggregates
        agg = merchant.customer_aggregate
        if agg.high_risk_adult_count and agg.high_risk_adult_count > 0:
            state.has_high_risk_cohort = True
        elif any("high_risk" in s for s in signals):
            state.has_high_risk_cohort = True

        if agg.chronic_rx_count and agg.chronic_rx_count > 0:
            state.has_chronic_rx_cohort = True
        elif any("chronic" in s for s in signals):
            state.has_chronic_rx_cohort = True

        if (agg.lapsed_180d_plus and agg.lapsed_180d_plus > 50) or (agg.retention_6mo_pct and agg.retention_6mo_pct < 0.40):
            state.high_lapsed_rate = True

        # 5. Subscription
        state.days_to_sub_expiry = sub.days_remaining
        if sub.status == "expired" or (sub.days_remaining is not None and sub.days_remaining <= 14):
            state.urgent_renewal = True

        # 6. Reviews
        if any(rt.sentiment == "neg" and rt.occurrences_30d >= 2 for rt in merchant.review_themes):
            state.has_negative_review_spike = True

        # 7. Engagement & Signals
        if merchant.conversation_history:
            last_turn = merchant.conversation_history[-1]
            if last_turn.engagement in ("merchant_replied", "intent_action"):
                state.engagement_level = "recently_engaged"
            elif last_turn.engagement == "merchant_no_reply":
                state.engagement_level = "disengaged"
            else:
                state.engagement_level = "moderately_engaged"
        elif any("dormant" in s for s in signals):
            state.engagement_level = "dormant"
        elif any("engaged" in s for s in signals):
            state.engagement_level = "recently_engaged"

        # Derived signal labels
        derived_signals = list(signals)
        if state.ctr_state == "below_peer" and "ctr_below_peer_median" not in derived_signals:
            derived_signals.append("ctr_below_peer_median")
        if state.urgent_renewal and "renewal_urgent" not in derived_signals:
            derived_signals.append("renewal_urgent")
        if state.has_active_offer and "offer_ready" not in derived_signals:
            derived_signals.append("offer_ready")
        if state.health == "growing" and "growth_momentum" not in derived_signals:
            derived_signals.append("growth_momentum")
        state.derived_signals = derived_signals

        return state
