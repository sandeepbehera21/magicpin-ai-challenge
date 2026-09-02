from __future__ import annotations
from typing import Any, Dict, List, Optional
from ..models.context import (
    CategoryContext,
    MerchantContext,
    CustomerContext,
    TriggerContext,
)
from ..models.evidence import EvidenceItem, EvidenceLedger


class EvidenceBuilder:
    @staticmethod
    def build_ledger(
        category: Optional[CategoryContext] = None,
        merchant: Optional[MerchantContext] = None,
        trigger: Optional[TriggerContext] = None,
        customer: Optional[CustomerContext] = None,
    ) -> EvidenceLedger:
        ledger = EvidenceLedger()

        # -----------------------------------------------------------------
        # 1. Category Evidence
        # -----------------------------------------------------------------
        if category:
            slug = category.slug
            ledger.add(EvidenceItem(
                evidence_id=f"cat_{slug}_slug",
                source_scope="category",
                source_context_id=slug,
                field_path="category.slug",
                value=slug,
                evidence_type="profile",
                display_fact=f"category is {slug}",
            ))

            if category.peer_stats.avg_ctr is not None:
                ledger.add(EvidenceItem(
                    evidence_id=f"cat_{slug}_peer_ctr",
                    source_scope="category",
                    source_context_id=slug,
                    field_path="category.peer_stats.avg_ctr",
                    value=category.peer_stats.avg_ctr,
                    evidence_type="benchmark",
                    display_fact=f"peer avg CTR is {category.peer_stats.avg_ctr:.3f}",
                ))

            if category.peer_stats.avg_rating is not None:
                ledger.add(EvidenceItem(
                    evidence_id=f"cat_{slug}_peer_rating",
                    source_scope="category",
                    source_context_id=slug,
                    field_path="category.peer_stats.avg_rating",
                    value=category.peer_stats.avg_rating,
                    evidence_type="benchmark",
                    display_fact=f"peer avg rating is {category.peer_stats.avg_rating}",
                ))

            for d in category.digest:
                ledger.add(EvidenceItem(
                    evidence_id=f"digest_{d.id}",
                    source_scope="category",
                    source_context_id=slug,
                    field_path=f"category.digest.{d.id}",
                    value={
                        "id": d.id,
                        "title": d.title,
                        "source": d.source,
                        "trial_n": d.trial_n,
                        "patient_segment": d.patient_segment,
                        "summary": d.summary,
                        "actionable": d.actionable,
                        "date": d.date,
                        "credits": d.credits,
                    },
                    evidence_type="citation",
                    display_fact=f"Digest '{d.title}' from {d.source or 'verified source'}",
                ))

            for o in category.offer_catalog:
                ledger.add(EvidenceItem(
                    evidence_id=f"cat_offer_{o.id or o.title}",
                    source_scope="category",
                    source_context_id=slug,
                    field_path="category.offer_catalog",
                    value=o.title,
                    evidence_type="offer",
                    display_fact=f"Standard category offer template: {o.title}",
                ))

        # -----------------------------------------------------------------
        # 2. Merchant Evidence
        # -----------------------------------------------------------------
        if merchant:
            mid = merchant.merchant_id
            ident = merchant.identity
            ledger.add(EvidenceItem(
                evidence_id=f"m_{mid}_name",
                source_scope="merchant",
                source_context_id=mid,
                field_path="merchant.identity.name",
                value=ident.name,
                evidence_type="profile",
                display_fact=f"Merchant name: {ident.name}",
            ))

            if ident.owner_first_name:
                ledger.add(EvidenceItem(
                    evidence_id=f"m_{mid}_owner",
                    source_scope="merchant",
                    source_context_id=mid,
                    field_path="merchant.identity.owner_first_name",
                    value=ident.owner_first_name,
                    evidence_type="profile",
                    display_fact=f"Owner first name: {ident.owner_first_name}",
                ))

            ledger.add(EvidenceItem(
                evidence_id=f"m_{mid}_locality",
                source_scope="merchant",
                source_context_id=mid,
                field_path="merchant.identity.locality",
                value=ident.locality,
                evidence_type="profile",
                display_fact=f"Locality: {ident.locality}",
            ))

            ledger.add(EvidenceItem(
                evidence_id=f"m_{mid}_city",
                source_scope="merchant",
                source_context_id=mid,
                field_path="merchant.identity.city",
                value=ident.city,
                evidence_type="profile",
                display_fact=f"City: {ident.city}",
            ))

            # Performance
            perf = merchant.performance
            ledger.add(EvidenceItem(
                evidence_id=f"m_{mid}_perf_views",
                source_scope="merchant",
                source_context_id=mid,
                field_path="merchant.performance.views",
                value=perf.views,
                evidence_type="metric",
                display_fact=f"30d views: {perf.views}",
            ))
            ledger.add(EvidenceItem(
                evidence_id=f"m_{mid}_perf_calls",
                source_scope="merchant",
                source_context_id=mid,
                field_path="merchant.performance.calls",
                value=perf.calls,
                evidence_type="metric",
                display_fact=f"30d calls: {perf.calls}",
            ))
            ledger.add(EvidenceItem(
                evidence_id=f"m_{mid}_perf_ctr",
                source_scope="merchant",
                source_context_id=mid,
                field_path="merchant.performance.ctr",
                value=perf.ctr,
                evidence_type="metric",
                display_fact=f"30d CTR: {perf.ctr:.3f}",
            ))

            if perf.delta_7d:
                if isinstance(perf.delta_7d, dict):
                    vp = perf.delta_7d.get("views_pct")
                    cp = perf.delta_7d.get("calls_pct")
                else:
                    vp = perf.delta_7d.views_pct
                    cp = perf.delta_7d.calls_pct

                if vp is not None:
                    ledger.add(EvidenceItem(
                        evidence_id=f"m_{mid}_perf_delta_views",
                        source_scope="merchant",
                        source_context_id=mid,
                        field_path="merchant.performance.delta_7d.views_pct",
                        value=vp,
                        evidence_type="metric",
                        display_fact=f"7d views change: {vp:+.0%}",
                    ))
                if cp is not None:
                    ledger.add(EvidenceItem(
                        evidence_id=f"m_{mid}_perf_delta_calls",
                        source_scope="merchant",
                        source_context_id=mid,
                        field_path="merchant.performance.delta_7d.calls_pct",
                        value=cp,
                        evidence_type="metric",
                        display_fact=f"7d calls change: {cp:+.0%}",
                    ))

            # Active offers
            for o in merchant.offers:
                if o.status == "active":
                    ledger.add(EvidenceItem(
                        evidence_id=f"m_{mid}_offer_{o.id or o.title}",
                        source_scope="merchant",
                        source_context_id=mid,
                        field_path="merchant.offers.active",
                        value=o.title,
                        evidence_type="offer",
                        display_fact=f"Active offer: {o.title}",
                    ))

            # Customer Aggregate
            agg = merchant.customer_aggregate
            if agg.total_unique_ytd:
                ledger.add(EvidenceItem(
                    evidence_id=f"m_{mid}_agg_ytd",
                    source_scope="merchant",
                    source_context_id=mid,
                    field_path="merchant.customer_aggregate.total_unique_ytd",
                    value=agg.total_unique_ytd,
                    evidence_type="aggregate",
                    display_fact=f"Total unique customers YTD: {agg.total_unique_ytd}",
                ))
            if agg.lapsed_180d_plus:
                ledger.add(EvidenceItem(
                    evidence_id=f"m_{mid}_agg_lapsed_180d",
                    source_scope="merchant",
                    source_context_id=mid,
                    field_path="merchant.customer_aggregate.lapsed_180d_plus",
                    value=agg.lapsed_180d_plus,
                    evidence_type="aggregate",
                    display_fact=f"Lapsed >180 days count: {agg.lapsed_180d_plus}",
                ))
            if agg.high_risk_adult_count:
                ledger.add(EvidenceItem(
                    evidence_id=f"m_{mid}_agg_high_risk_adults",
                    source_scope="merchant",
                    source_context_id=mid,
                    field_path="merchant.customer_aggregate.high_risk_adult_count",
                    value=agg.high_risk_adult_count,
                    evidence_type="aggregate",
                    display_fact=f"High-risk adult patient cohort count: {agg.high_risk_adult_count}",
                ))
            if agg.chronic_rx_count:
                ledger.add(EvidenceItem(
                    evidence_id=f"m_{mid}_agg_chronic_rx",
                    source_scope="merchant",
                    source_context_id=mid,
                    field_path="merchant.customer_aggregate.chronic_rx_count",
                    value=agg.chronic_rx_count,
                    evidence_type="aggregate",
                    display_fact=f"Chronic Rx patient cohort count: {agg.chronic_rx_count}",
                ))

            # Subscription
            sub = merchant.subscription
            ledger.add(EvidenceItem(
                evidence_id=f"m_{mid}_sub_status",
                source_scope="merchant",
                source_context_id=mid,
                field_path="merchant.subscription.status",
                value=sub.status,
                evidence_type="profile",
                display_fact=f"Subscription status: {sub.status}",
            ))
            if sub.days_remaining is not None:
                ledger.add(EvidenceItem(
                    evidence_id=f"m_{mid}_sub_days_remaining",
                    source_scope="merchant",
                    source_context_id=mid,
                    field_path="merchant.subscription.days_remaining",
                    value=sub.days_remaining,
                    evidence_type="metric",
                    display_fact=f"Subscription days remaining: {sub.days_remaining}",
                ))

            # Signals
            for sig in merchant.signals:
                ledger.add(EvidenceItem(
                    evidence_id=f"m_{mid}_signal_{sig}",
                    source_scope="merchant",
                    source_context_id=mid,
                    field_path="merchant.signals",
                    value=sig,
                    evidence_type="profile",
                    display_fact=f"Merchant signal: {sig}",
                ))

            # Review themes
            for rt in merchant.review_themes:
                ledger.add(EvidenceItem(
                    evidence_id=f"m_{mid}_review_theme_{rt.theme}",
                    source_scope="merchant",
                    source_context_id=mid,
                    field_path=f"merchant.review_themes.{rt.theme}",
                    value={"theme": rt.theme, "sentiment": rt.sentiment, "occurrences": rt.occurrences_30d, "quote": rt.common_quote},
                    evidence_type="profile",
                    display_fact=f"Review theme: {rt.theme} ({rt.sentiment}, {rt.occurrences_30d} occurrences)",
                ))

        # -----------------------------------------------------------------
        # 3. Customer Evidence
        # -----------------------------------------------------------------
        if customer:
            cid = customer.customer_id
            ledger.add(EvidenceItem(
                evidence_id=f"c_{cid}_name",
                source_scope="customer",
                source_context_id=cid,
                field_path="customer.identity.name",
                value=customer.identity.name,
                evidence_type="profile",
                display_fact=f"Customer name: {customer.identity.name}",
            ))
            ledger.add(EvidenceItem(
                evidence_id=f"c_{cid}_state",
                source_scope="customer",
                source_context_id=cid,
                field_path="customer.state",
                value=customer.state,
                evidence_type="profile",
                display_fact=f"Customer state: {customer.state}",
            ))
            if customer.relationship.last_visit:
                ledger.add(EvidenceItem(
                    evidence_id=f"c_{cid}_last_visit",
                    source_scope="customer",
                    source_context_id=cid,
                    field_path="customer.relationship.last_visit",
                    value=customer.relationship.last_visit,
                    evidence_type="metric",
                    display_fact=f"Last visit date: {customer.relationship.last_visit}",
                ))
            if customer.preferences.preferred_slots:
                ledger.add(EvidenceItem(
                    evidence_id=f"c_{cid}_pref_slots",
                    source_scope="customer",
                    source_context_id=cid,
                    field_path="customer.preferences.preferred_slots",
                    value=customer.preferences.preferred_slots,
                    evidence_type="profile",
                    display_fact=f"Preferred slots: {customer.preferences.preferred_slots}",
                ))

        # -----------------------------------------------------------------
        # 4. Trigger Evidence
        # -----------------------------------------------------------------
        if trigger:
            tid = trigger.id
            ledger.add(EvidenceItem(
                evidence_id=f"trg_{tid}_kind",
                source_scope="trigger",
                source_context_id=tid,
                field_path="trigger.kind",
                value=trigger.kind,
                evidence_type="trigger_payload",
                display_fact=f"Trigger kind: {trigger.kind}",
            ))
            ledger.add(EvidenceItem(
                evidence_id=f"trg_{tid}_urgency",
                source_scope="trigger",
                source_context_id=tid,
                field_path="trigger.urgency",
                value=trigger.urgency,
                evidence_type="metric",
                display_fact=f"Trigger urgency: {trigger.urgency}",
            ))

            for k, v in trigger.payload.items():
                ledger.add(EvidenceItem(
                    evidence_id=f"trg_{tid}_payload_{k}",
                    source_scope="trigger",
                    source_context_id=tid,
                    field_path=f"trigger.payload.{k}",
                    value=v,
                    evidence_type="trigger_payload",
                    display_fact=f"Trigger payload {k}: {v}",
                ))

        return ledger
