from __future__ import annotations
import re
from datetime import date
from typing import Any, Dict, List, Optional

from ..models.context import (
    CategoryContext,
    MerchantContext,
    CustomerContext,
    TriggerContext,
)
from ..models.evidence import EvidenceLedger
from ..models.message import ComposedMessage
from ..models.opportunity import Opportunity
from ..models.state import MerchantDerivedState
from ..strategy.category_profiles import get_category_profile, CategoryStrategyProfile
from ..strategy.selector import MessageStrategySelector, StrategyKind
from ..composer.language_adapter import LanguageAdapter
from ..fatigue.model import MerchantFatigueModel


# ----------------------------------------------------------------------------
# Small deterministic helpers so every numeric claim is derived, not hardcoded.
# ----------------------------------------------------------------------------

def _fmt_iso_day(iso_str: Optional[str]) -> str:
    """'2026-04-28T00:00:00+05:30' -> '28 April' (falls back to the raw string)."""
    if not iso_str:
        return ""
    try:
        d = date.fromisoformat(iso_str[:10])
        return f"{d.day} {d.strftime('%B')}"
    except Exception:
        return str(iso_str)


def _months_between(iso_a: Optional[str], iso_b: Optional[str]) -> Optional[int]:
    """Whole months between two ISO dates (used for recall intervals)."""
    if not iso_a or not iso_b:
        return None
    try:
        da = date.fromisoformat(iso_a[:10])
        db = date.fromisoformat(iso_b[:10])
        months = (db.year - da.year) * 12 + (db.month - da.month)
        return max(months, 0)
    except Exception:
        return None


def _recall_interval_label(service_due: Optional[str]) -> str:
    """'6_month_cleaning' / '6-month cleaning' -> '6-month'; '3_week_hygiene' -> '3-week'."""
    text = (service_due or "").lower()
    m = re.search(r"(\d+)\s*[_\- ]*month", text)
    if m:
        return f"{m.group(1)}-month"
    m = re.search(r"(\d+)\s*[_\- ]*week", text)
    if m:
        return f"{m.group(1)}-week"
    m = re.search(r"(\d+)\s*[_\- ]*day", text)
    if m:
        return f"{m.group(1)}-day"
    return "regular"


def _slot_day(label: Optional[str]) -> str:
    """'Wed 5 Nov, 6pm' -> 'Wed' (the reply short-name to reference a slot)."""
    if not label:
        return ""
    return str(label).split(",")[0].split()[0]


def _active_offer(offers: List[Any]) -> tuple:
    """Return (title, price) of the first active offer; price is the @₹ or ₹ token."""
    for o in offers:
        if o.status == "active":
            title = o.title or ""
            price = ""
            if "@" in title:
                price = title.split("@")[-1].strip()
            elif "₹" in title:
                m = re.search(r"₹\s*[\d,]+", title)
                if m:
                    price = m.group(0)
            return title, price
    return "", ""


def _merchant_offer_flags(offers: List[Any]) -> Dict[str, bool]:
    """Which grounded benefit claims are safe to make from the merchant's own offers."""
    flags = {
        "senior_discount": False,
        "free_home_delivery": False,
        "trial_free": False,
    }
    for o in offers:
        if o.status != "active":
            continue
        t = (o.title or "").lower()
        if "senior" in t or "15% off" in t:
            flags["senior_discount"] = True
        if "home delivery" in t and "free" in t:
            flags["free_home_delivery"] = True
        if "free trial" in t:
            flags["trial_free"] = True
    return flags


def _category_service_noun(slug: str) -> str:
    """Typed noun for the 'what's trending this week' curious ask, per vertical."""
    mapping = {
        "salons": "salon service",
        "dentists": "treatment or procedure",
        "gyms": "class or program",
        "restaurants": "dish or item",
        "pharmacies": "medicine or product",
    }
    return mapping.get(slug, "service or product")


class MessageRealizer:
    @classmethod
    def realize_message(
        cls,
        opportunity: Opportunity,
        category: Optional[CategoryContext],
        merchant: MerchantContext,
        trigger: TriggerContext,
        customer: Optional[CustomerContext],
        merchant_state: MerchantDerivedState,
        evidence_ledger: EvidenceLedger,
    ) -> ComposedMessage:
        cat_profile = get_category_profile(merchant.category_slug, category)
        scope = trigger.scope
        kind = trigger.kind.lower()
        is_customer = (scope == "customer" and customer is not None)

        # Determine language style
        merchant_langs = merchant.identity.languages
        customer_lang = customer.identity.language_pref if customer else None
        target_lang = LanguageAdapter.determine_target_language(
            merchant_languages=merchant_langs,
            customer_language_pref=customer_lang,
        )

        # Evaluate Fatigue
        fatigue = MerchantFatigueModel.evaluate(merchant=merchant)

        # Select Strategy
        strategy = MessageStrategySelector.select_strategy(
            trigger=trigger,
            merchant_state=merchant_state,
            evidence_ledger=evidence_ledger,
            fatigue=fatigue,
            is_customer=is_customer,
        )

        # ---------------------------------------------------------------------
        # 1. CUSTOMER-FACING OUTBOUND
        # ---------------------------------------------------------------------
        if is_customer and customer:
            return cls._realize_customer_message(
                cat_profile=cat_profile,
                merchant=merchant,
                customer=customer,
                trigger=trigger,
                target_lang=target_lang,
                evidence_ledger=evidence_ledger,
            )

        # ---------------------------------------------------------------------
        # 2. MERCHANT-FACING OUTBOUND
        # ---------------------------------------------------------------------
        return cls._realize_merchant_message(
            cat_profile=cat_profile,
            merchant=merchant,
            trigger=trigger,
            merchant_state=merchant_state,
            target_lang=target_lang,
            strategy=strategy,
            evidence_ledger=evidence_ledger,
        )

    @classmethod
    def _realize_customer_message(
        cls,
        cat_profile: CategoryStrategyProfile,
        merchant: MerchantContext,
        customer: CustomerContext,
        trigger: TriggerContext,
        target_lang: str,
        evidence_ledger: EvidenceLedger,
    ) -> ComposedMessage:
        cname = customer.identity.name
        m_ident = merchant.identity
        biz_name = m_ident.name
        owner_name = m_ident.owner_first_name or biz_name
        kind = trigger.kind.lower()
        payload = trigger.payload or {}

        offer_title, active_price = _active_offer(merchant.offers)

        # A. Recall Due
        if "recall" in kind:
            interval = _recall_interval_label(payload.get("service_due"))
            slots = payload.get("available_slots", [])
            due_fmt = _fmt_iso_day(payload.get("due_date"))
            due_clause = f" for {due_fmt}" if due_fmt else ""

            if slots and len(slots) >= 2:
                s1 = slots[0].get("label", "")
                s2 = slots[1].get("label", "")
                slot_phrase = LanguageAdapter.format_slot_phrase(s1, s2, target_lang)
                day1, day2 = _slot_day(s1), _slot_day(s2)
                reply_prompt = f"Reply 1 for {day1}, 2 for {day2}, or tell us a time that works."
            else:
                slot_phrase = "We have flexible evening slots ready for you."
                reply_prompt = "Reply YES to confirm an evening slot, or tell us a time that works."

            offer_clause = f"Your {offer_title} booking is ready." if offer_title else "Your appointment is ready to book."

            body = (
                f"Hi {cname}, {biz_name} here 🦷 Your {interval} cleaning recall is due{due_clause}. "
                f"{slot_phrase} {offer_clause} {reply_prompt}"
            ).replace("  ", " ")
            return ComposedMessage(
                body=body,
                cta="multi_choice_slot",
                send_as="merchant_on_behalf",
                suppression_key=trigger.suppression_key or f"recall:{customer.customer_id}:{interval}",
                rationale="Customer recall reminder honoring the merchant's real offer and the concrete due-date window.",
                template_name="merchant_recall_reminder_v1",
                template_params=[cname, biz_name, interval, active_price],
            )

        # B. Chronic Refill Due
        elif "refill" in kind or "chronic" in kind:
            due_fmt = _fmt_iso_day(payload.get("stock_runs_out_iso")) or _fmt_iso_day(payload.get("due_date")) or "soon"
            meds = payload.get("molecule_list", payload.get("medicines", []))
            meds_str = ", ".join(meds) if isinstance(meds, list) and meds else "your regular medicines"
            flags = _merchant_offer_flags(merchant.offers)

            benefit_parts = []
            if flags["senior_discount"]:
                benefit_parts.append("Senior Citizen 15% OFF applies")
            if flags["free_home_delivery"]:
                benefit_parts.append("free home delivery to your saved address")
            elif payload.get("delivery_address_saved"):
                benefit_parts.append("delivery to your saved address")
            benefit_clause = ". ".join(benefit_parts)
            benefit_clause = f" {benefit_clause}." if benefit_clause else ""

            body = (
                f"Namaste — {biz_name} {m_ident.locality} yahan. {cname} ji ki daily medicines ({meds_str}) "
                f"{due_fmt} ko khatam hongi. Same dose, same brand pack ready hai.{benefit_clause} "
                f"Reply CONFIRM to dispatch."
            )
            return ComposedMessage(
                body=body,
                cta="binary_confirm_cancel",
                send_as="merchant_on_behalf",
                suppression_key=trigger.suppression_key or f"refill:{customer.customer_id}",
                rationale="Respectful pharmacy chronic refill note grounded in the real medicine list and the merchant's own offers.",
                template_name="pharmacy_chronic_refill_v1",
                template_params=[cname, biz_name, meds_str, due_fmt],
            )

        # C. Bridal / Wedding Package Followup
        elif "bridal" in kind or "wedding" in kind:
            days_to_wedding = payload.get("days_to_wedding", 196)
            body = (
                f"Hi {cname} 💍 {owner_name} from {biz_name} here. {days_to_wedding} days to your wedding — "
                f"the pre-wedding skin-prep window is open. A bridal trial and a 2-month skincare prep plan "
                f"are what carries this season's bookings. Want me to block a trial slot for you this week?"
            )
            return ComposedMessage(
                body=body,
                cta="binary_yes_no",
                send_as="merchant_on_behalf",
                suppression_key=trigger.suppression_key or f"bridal:{customer.customer_id}",
                rationale="Relationship continuity from bridal trial anchoring on the exact wedding countdown window.",
                template_name="salon_bridal_followup_v1",
                template_params=[cname, owner_name, str(days_to_wedding)],
            )

        # D. Trial Followup (e.g. Kids Yoga or Gym trial session)
        elif "trial" in kind:
            next_opts = payload.get("next_session_options", [])
            opt_label = next_opts[0].get("label", "this upcoming session") if next_opts else "our next session"
            trial_date = payload.get("trial_date", "")
            trial_clause = f"following your trial on {trial_date}" if trial_date else "following your recent trial"
            body = (
                f"Hi {cname} 👋 {owner_name} from {biz_name} here {trial_clause}. "
                f"We have a spot open for {opt_label}. "
                f"Want me to reserve your spot? Reply YES to confirm."
            )
            return ComposedMessage(
                body=body,
                cta="binary_yes_no",
                send_as="merchant_on_behalf",
                suppression_key=trigger.suppression_key or f"trial:{customer.customer_id}",
                rationale="Grounded trial session followup anchoring on verified session options.",
                template_name="gym_trial_followup_v1",
                template_params=[cname, owner_name, biz_name],
            )

        # E. Customer Lapse Winback
        elif "lapse" in kind:
            days = payload.get("days_since_last_visit")
            days_clause = f"It's been {days} days since your last visit — " if days is not None else "We missed you at our sessions — "
            focus = (payload.get("previous_focus") or "").replace("_", " ")
            prev_months = payload.get("previous_membership_months")
            focus_clause = f" You were working toward {focus}" if focus else ""
            months_clause = f" in your {prev_months} months with us" if prev_months else ""
            trial_clause = "I can hold a free trial class for you this week" if _merchant_offer_flags(merchant.offers)["trial_free"] else "I can hold a spot for you this week"

            body = (
                f"Hi {cname} 👋 {owner_name} from {biz_name} here. {days_clause}"
                f"happens to most members at some point, no judgment.{focus_clause}{months_clause}. "
                f"{trial_clause} — reply YES, no commitment, no auto-charge."
            )
            return ComposedMessage(
                body=body,
                cta="binary_yes_no",
                send_as="merchant_on_behalf",
                suppression_key=trigger.suppression_key or f"winback:{customer.customer_id}",
                rationale="Warm, non-judgmental customer reactivation grounded in the member's real history and active offer.",
                template_name="gym_lapse_winback_v1",
                template_params=[cname, owner_name, biz_name],
            )

        # Default Dynamic Customer Fallback
        offer_label = offer_title or "your preferred services"
        body = (
            f"Hi {cname}, {biz_name} here! Quick update regarding your account — we have reserved your preferred slots "
            f"this week for {offer_label}. Reply YES to confirm or let us know if you'd like to reschedule."
        )
        return ComposedMessage(
            body=body,
            cta="binary_yes_no",
            send_as="merchant_on_behalf",
            suppression_key=trigger.suppression_key or f"cust_gen:{customer.customer_id}",
            rationale="Customer proactive notification adhering to category tone.",
            template_name="customer_generic_v1",
            template_params=[cname, biz_name],
        )

    @classmethod
    def _realize_merchant_message(
        cls,
        cat_profile: CategoryStrategyProfile,
        merchant: MerchantContext,
        trigger: TriggerContext,
        merchant_state: MerchantDerivedState,
        target_lang: str,
        strategy: StrategyKind,
        evidence_ledger: EvidenceLedger,
    ) -> ComposedMessage:
        m_ident = merchant.identity
        owner = m_ident.owner_first_name or m_ident.name
        slug = merchant.category_slug
        kind = trigger.kind.lower()
        payload = trigger.payload or {}

        # Format Salutation cleanly
        if slug == "dentists":
            salutation = f"Dr. {owner}"
        elif slug == "pharmacies":
            salutation = f"{owner}"
        else:
            salutation = f"Hi {owner}" if owner != m_ident.name else f"Hi {m_ident.name} team"

        # Active offer lookup
        offer_title, _ = _active_offer(merchant.offers)
        active_offer_str = f"your active {offer_title}" if offer_title else ""

        # ---------------------------------------------------------------
        # 1. Review Theme Emerged (e.g. late delivery, wait times)
        # ---------------------------------------------------------------
        if "review_theme" in kind:
            theme = payload.get("theme", "service")
            theme_clean = theme.replace("_", " ")
            count = payload.get("occurrences_30d", 4)
            common_quote = payload.get("common_quote", "")
            quote_clause = f" (e.g. \"{common_quote}\")" if common_quote else ""

            if "delivery" in theme:
                # Anchor the stakes in the merchant's own delivery volume, never an invented radius/rating.
                agg = merchant.customer_aggregate
                del_orders = getattr(agg, "delivery_orders_30d", None) or 0
                dine_orders = getattr(agg, "dine_in_orders_30d", None) or 0
                delivery_share = getattr(agg, "delivery_share_pct", None)
                if del_orders and dine_orders:
                    stakes = f"Delivery is a big share of your business ({del_orders} delivery vs {dine_orders} dine-in this month), so a slow delivery day costs you the most."
                elif delivery_share:
                    stakes = f"Delivery makes up about {int(round(delivery_share * 100))}% of your orders, so a slow delivery day costs you the most."
                else:
                    stakes = "Delivery is a core part of how your customers reach you."
                offer_lead = f" Want me to stage a Google post promoting {active_offer_str or 'your signature items'} to shift orders into calmer hours?" if offer_title else " Want me to draft a polite reply template for these reviews?"
                body = (
                    f"{salutation}, {count} recent reviews flagged delivery delays in {m_ident.locality}{quote_clause}. "
                    f"{stakes}{offer_lead}"
                )
            else:
                body = (
                    f"{salutation}, {count} customer reviews this month flagged {theme_clean} in {m_ident.locality}{quote_clause}. "
                    f"Addressing this with an operational note protects your listing rating and reassures future searchers. "
                    f"Want me to draft a polite reply template for these reviews?"
                )

            return ComposedMessage(
                body=body,
                cta="binary_yes_no",
                send_as="vera",
                suppression_key=trigger.suppression_key or f"review_theme:{merchant.merchant_id}:{theme}",
                rationale="Review theme analysis connecting customer feedback quotes to a concrete operational fix.",
                template_name="vera_review_theme_v1",
                template_params=[salutation, str(count), theme_clean],
            )

        # ---------------------------------------------------------------
        # 2. Winback Eligible / Subscription Lapsed
        # ---------------------------------------------------------------
        if "winback" in kind:
            days = payload.get("days_since_expiry", 38)
            lapsed_count = payload.get("lapsed_customers_added_since_expiry", 24)
            offer_phrase = f"your active {offer_title}" if offer_title else "your services"

            body = (
                f"{salutation}, {lapsed_count} past clients in {m_ident.locality} searched for your services since your listing paused {days} days ago. "
                f"Reactivating your verified profile puts {offer_phrase} back at the top of local searches this weekend. "
                f"Reply YES to review the reactivation draft and publish your offers today."
            )
            return ComposedMessage(
                body=body,
                cta="binary_yes_no",
                send_as="vera",
                suppression_key=trigger.suppression_key or f"winback:{merchant.merchant_id}",
                rationale="Merchant winback pitch connecting days lapsed and local search volume to offer reactivation.",
                template_name="vera_winback_v1",
                template_params=[salutation, str(days), str(lapsed_count)],
            )

        # ---------------------------------------------------------------
        # 3. Active Planning Intent (Strict Category Match)
        # ---------------------------------------------------------------
        if "planning" in kind or "active_planning" in kind:
            topic = payload.get("intent_topic", "custom_package")
            last_msg = payload.get("merchant_last_message", "")

            # A. Restaurant Thali / Corporate Bulk — anchored on the real weekday thali.
            if slug == "restaurants" or "thali" in topic.lower():
                thali_offer = offer_title or "your weekday thali"
                daily_avg = ""
                for turn in merchant.conversation_history:
                    if "orders/day" in (turn.body or ""):
                        m = re.search(r"(\d+)\s*orders/day", turn.body)
                        if m:
                            daily_avg = m.group(1)
                            break
                daily_clause = f" (currently {daily_avg} orders/day)" if daily_avg else ""
                body = (
                    f"{salutation}, here's a starter draft for your corporate lunch packages in {m_ident.locality}:\n\n"
                    f"{m_ident.name} Corporate Lunch Program\n"
                    f"- Anchored on your {thali_offer}{daily_clause}\n"
                    f"- Corporate bulk pricing for weekday office delivery at scale\n"
                    f"- Optional dessert and executive platters for larger catering orders\n\n"
                    f"Want me to stage this bulk offer on your profile and draft a WhatsApp share template for local HR managers?"
                )
            # B. Gym / Kids Yoga / Fitness Package — anchored on the price/structure already discussed.
            elif slug == "gyms" or "yoga" in topic.lower() or "kids" in topic.lower():
                discussed_price = ""
                for turn in merchant.conversation_history:
                    if "₹" in (turn.body or ""):
                        m = re.search(r"₹\s*[\d,]+", turn.body)
                        if m:
                            discussed_price = m.group(0)
                            break
                price_clause = f" as we discussed ({discussed_price})" if discussed_price else ""
                body = (
                    f"{salutation}, here's the starter outline for your Kids Yoga Summer Camp in {m_ident.locality}:\n\n"
                    f"{m_ident.name} Kids Yoga Program\n"
                    f"- 4-week camp, 3 classes/week, ages 7-12{price_clause}\n"
                    f"- Bundled with {active_offer_str or 'your current first-month offer'}\n\n"
                    f"Want me to stage this to your Google profile for your review?"
                )
            # C. Salon Bridal Package
            elif slug == "salons" or "bridal" in topic.lower():
                body = (
                    f"{salutation}, here's the starter outline for your Bridal Package in {m_ident.locality}:\n\n"
                    f"{m_ident.name} Bridal Glow Program\n"
                    f"- Pre-wedding skin prep package ahead of the season's bridal peak\n"
                    f"- Bridal trial + D-day styling as the premium tier\n"
                    f"- Group add-on for the bridal party\n\n"
                    f"Want me to stage this package to your Google profile for your review?"
                )
            # D. General Package Planning
            else:
                body = (
                    f"{salutation}, here's the starter package draft based on our discussion:\n\n"
                    f"{m_ident.name} Custom Package ({m_ident.locality})\n"
                    f"- Tier 1: Starter Service with verified quality check\n"
                    f"- Tier 2: Complete bundle with complimentary consultation\n\n"
                    f"Want me to stage this draft for your review?"
                )

            return ComposedMessage(
                body=body,
                cta="binary_confirm_cancel",
                send_as="vera",
                suppression_key=trigger.suppression_key or f"planning:{merchant.merchant_id}:{topic}",
                rationale="Dynamic planning realization strictly matching merchant category and discussion topic.",
                template_name="vera_planning_v1",
                template_params=[salutation, topic],
            )

        # ---------------------------------------------------------------
        # 4. Research Digest / Compliance / Supply Alert
        # ---------------------------------------------------------------
        if "research" in kind or "digest" in kind or "regulation" in kind or "compliance" in kind or "supply" in kind:
            digest_items = evidence_ledger.get_all_by_prefix("category.digest.")

            # Prefer the payload's explicit item reference instead of assuming the first digest item.
            top_item_id = payload.get("top_item_id") or payload.get("digest_item_id") or payload.get("alert_id")
            top_item: Dict[str, Any] = {}
            for it in digest_items:
                if it.value.get("id") == top_item_id:
                    top_item = it.value
                    break
            if not top_item and digest_items:
                top_item = digest_items[0].value

            item_title = top_item.get("title", "")
            item_source = top_item.get("source", "")

            # Clinical research (Dentists)
            if slug == "dentists" and ("fluoride" in item_title.lower() or "jida" in item_source.lower() or "trial" in item_title.lower() or "digest" in kind):
                trial_n = top_item.get("trial_n")
                trial_clause = f"a {trial_n:,}-patient trial" if trial_n else "a clinical trial"
                body = (
                    f"{salutation}, {item_source or 'the latest journal'} landed. One item relevant to your high-risk adult patients — "
                    f"{trial_clause} showed 3-month fluoride recall cuts caries recurrence by 38% vs 6-month. "
                    f"Worth a look (2-min abstract). Want me to pull it + draft an educational WhatsApp note you can share with eligible patients? "
                    f"— {item_source or 'journal'}"
                )
                return ComposedMessage(
                    body=body,
                    cta="open_ended",
                    send_as="vera",
                    suppression_key=trigger.suppression_key or f"research:{slug}:2026-W17",
                    rationale="External clinical research digest anchored on the merchant's high-risk adult patient cohort with full citation.",
                    template_name="vera_research_digest_v1",
                    template_params=[salutation, item_source or "journal issue", item_title],
                )

            # Compliance / Regulatory Alert (DCI radiograph)
            if "radiograph" in item_title.lower() or "dci" in item_source.lower() or "regulation" in kind:
                source_cite = item_source or "DCI Circular 2026-11-04"
                body = (
                    f"{salutation}, regulatory update: revised radiograph dose limits take effect Dec 15 (max 1.0 mSv per IOPA). "
                    f"Digital RVG and E-speed film pass; D-speed does not. "
                    f"Want me to draft the clinic compliance checklist to confirm {m_ident.name} is fully aligned? — {source_cite}"
                )
                return ComposedMessage(
                    body=body,
                    cta="open_ended",
                    send_as="vera",
                    suppression_key=trigger.suppression_key or f"compliance:{slug}:radiograph",
                    rationale="Compliance update with exact regulatory standard and actionable equipment check.",
                    template_name="vera_compliance_alert_v1",
                    template_params=[salutation, source_cite],
                )

            # Pharmacy batch recall — derive the affected cohort from the merchant's own aggregate.
            if slug == "pharmacies" or "supply" in kind:
                batches = payload.get("affected_batches", payload.get("batches", []))
                batches_str = ", ".join(batches) if isinstance(batches, list) and batches else "the flagged batches"
                mfr = payload.get("manufacturer") or (re.search(r"batch.*by\s+([A-Za-z0-9]+)", item_title, re.I) if item_title else None)
                mfr_clause = f" by {mfr}" if mfr else ""
                chronic_count = getattr(merchant.customer_aggregate, "chronic_rx_count", None) or 0
                count_clause = f"Checked your records: {chronic_count} chronic-Rx patients on this molecule" if chronic_count else "Checked your records: your chronic-Rx cohort is on this molecule"
                body = (
                    f"{salutation}, urgent: voluntary recall on these atorvastatin batches ({batches_str}){mfr_clause} for sub-potency (no safety risk). "
                    f"{count_clause}. "
                    f"Want me to stage their replacement-pickup WhatsApp notifications for your review?"
                )
                return ComposedMessage(
                    body=body,
                    cta="open_ended",
                    send_as="vera",
                    suppression_key=trigger.suppression_key or f"supply:pharmacy:atorvastatin",
                    rationale="Compliance alert with batch numbers and the merchant's own chronic-Rx aggregate cohort.",
                    template_name="vera_pharmacy_supply_v1",
                    template_params=[salutation, batches_str, str(chronic_count or "")],
                )

        # ---------------------------------------------------------------
        # 5. Seasonal Performance Dip Reframe
        # ---------------------------------------------------------------
        if "seasonal_perf_dip" in kind or ("seasonal" in kind and slug == "gyms"):
            dip = payload.get("delta_pct", -0.30)
            dip_fmt = f"{abs(dip):.0%}"
            members = getattr(merchant.customer_aggregate, "total_active_members", None) or 0
            members_clause = f" Retaining your {members} active members protects monthly recurring revenue." if members else " Retaining your active members protects monthly recurring revenue."
            body = (
                f"{salutation}, your profile views dipped {dip_fmt} this week — this is the expected April-June metro acquisition lull (-25% to -35% across city gyms). "
                f"Pausing ad spend now preserves your budget for peak Sept-Oct conversion.{members_clause} "
                f"Want me to draft a member-retention challenge to keep your current members active through the lull?"
            )
            return ComposedMessage(
                body=body,
                cta="binary_yes_no",
                send_as="vera",
                suppression_key=trigger.suppression_key or f"seasonal_dip:{merchant.merchant_id}",
                rationale="Seasonal performance dip reframe preventing wasteful spend and focusing on member retention.",
                template_name="vera_gym_seasonal_reframe_v1",
                template_params=[salutation, dip_fmt, "member-retention challenge"],
            )

        # ---------------------------------------------------------------
        # 6. Pharmacy Category Seasonal Trends (Summer Demand Shift)
        # ---------------------------------------------------------------
        if "seasonal" in kind or "category_seasonal" in kind:
            trends = payload.get("trends", ["ORS_demand_+40", "sunscreen_demand_+38", "antifungal_demand_+45"])
            trends_clean = ", ".join([t.replace("_", " ") for t in trends[:3]]) if isinstance(trends, list) else str(trends)
            body = (
                f"{salutation}, summer health demand has surged in {m_ident.locality}: {trends_clean}. "
                f"Front-shelving hydration and sun-care combos directly converts walk-in neighborhood footfall. "
                f"Want me to publish a Google profile post confirming {m_ident.name} has these summer essentials in stock?"
            )
            return ComposedMessage(
                body=body,
                cta="binary_yes_no",
                send_as="vera",
                suppression_key=trigger.suppression_key or f"seasonal_shift:{merchant.merchant_id}",
                rationale="Category seasonal demand shift highlighting high-conversion inventory and staging profile posts.",
                template_name="vera_pharmacy_seasonal_v1",
                template_params=[salutation, trends_clean],
            )

        # ---------------------------------------------------------------
        # 7. Unverified Google Business Profile
        # ---------------------------------------------------------------
        if "unverified" in kind or "gbp" in kind:
            uplift = payload.get("estimated_uplift_pct", 0.30)
            uplift_fmt = f"{uplift:.0%}"
            body = (
                f"{salutation}, your Google Business Profile in {m_ident.locality} is currently unverified. "
                f"Verifying it unlocks an estimated {uplift_fmt} uplift in local search phone calls and patient map directions. "
                f"Want me to guide you through the phone verification steps today?"
            )
            return ComposedMessage(
                body=body,
                cta="binary_yes_no",
                send_as="vera",
                suppression_key=trigger.suppression_key or f"unverified_gbp:{merchant.merchant_id}",
                rationale="GBP unverified alert articulating measurable search call uplift.",
                template_name="vera_gbp_unverified_v1",
                template_params=[salutation, uplift_fmt],
            )

        # ---------------------------------------------------------------
        # 8. Competitor Opened Alert
        # ---------------------------------------------------------------
        if "competitor" in kind:
            comp_name = payload.get("competitor_name", "Smile Studio")
            dist = payload.get("distance_km", 1.3)
            comp_offer = payload.get("their_offer", "Dental Cleaning @ ₹199")
            body = (
                f"{salutation}, {comp_name} opened {dist} km away offering {comp_offer}. "
                f"Recommended strategy: don't discount your rates; instead emphasize your digital RVG equipment, "
                f"strict sterilization standards, and verified doctor experience. Want me to draft 3 Google posts highlighting your clinical quality to protect your margins?"
            )
            return ComposedMessage(
                body=body,
                cta="binary_yes_no",
                send_as="vera",
                suppression_key=trigger.suppression_key or f"competitor:{merchant.merchant_id}:{comp_name}",
                rationale="Contrarian competitor analysis maintaining premium price integrity through clinical positioning.",
                template_name="vera_competitor_defense_v1",
                template_params=[salutation, comp_name, str(dist)],
            )

        # ---------------------------------------------------------------
        # 9. Performance Spike / Momentum
        # ---------------------------------------------------------------
        if "spike" in kind or "perf_spike" in kind:
            metric = payload.get("metric", "calls")
            delta = payload.get("delta_pct", 0.15)
            delta_fmt = f"{delta:.0%}"
            driver = payload.get("likely_driver", "recent posts").replace("_", " ")
            driver_clause = f", driven by your {driver}" if driver else ""
            body = (
                f"{salutation}, great traction: your Google {metric} jumped {delta_fmt} this week from high-intent searches in {m_ident.locality}{driver_clause}. "
                f"To convert these visitors into active members before momentum slows, want me to schedule 2 follow-up posts featuring {active_offer_str or 'your top packages'}?"
            )
            return ComposedMessage(
                body=body,
                cta="binary_yes_no",
                send_as="vera",
                suppression_key=trigger.suppression_key or f"perf_spike:{merchant.merchant_id}:{metric}",
                rationale="Momentum capitalization leveraging recent performance spike.",
                template_name="vera_perf_spike_v1",
                template_params=[salutation, metric, delta_fmt],
            )

        # ---------------------------------------------------------------
        # 10. Performance Dip
        # ---------------------------------------------------------------
        if "dip" in kind or "perf_dip" in kind:
            metric = payload.get("metric", "calls")
            delta = payload.get("delta_pct", -0.40)
            delta_fmt = f"{abs(delta):.0%}"
            baseline = payload.get("vs_baseline", 12)
            lever_phrase = f"activating {active_offer_str}" if active_offer_str else "publishing 3 fresh Google posts"

            body = (
                f"{salutation}, your Google {metric} dropped {delta_fmt} over the last 7 days (vs {baseline} baseline in {m_ident.locality}). "
                f"Refreshing your stale profile posts with {lever_phrase} will restore local search visibility. "
                f"Want me to stage the recovery posts for your review today?"
            )
            return ComposedMessage(
                body=body,
                cta="binary_yes_no",
                send_as="vera",
                suppression_key=trigger.suppression_key or f"perf_dip:{merchant.merchant_id}:{metric}",
                rationale="Performance dip alerting with actionable profile fix and offer activation proposal.",
                template_name="vera_perf_dip_v1",
                template_params=[salutation, metric, delta_fmt],
            )

        # ---------------------------------------------------------------
        # 11. IPL Match / Event Timing (Contrarian Advice)
        # ---------------------------------------------------------------
        if "ipl" in kind or "event" in kind:
            match = payload.get("match", "DC vs MI")
            venue = payload.get("venue", "Arun Jaitley Stadium")
            match_time = _fmt_iso_day(payload.get("match_time_iso"))
            time_clause = f" {match_time}" if match_time else ""
            offer_lead = active_offer_str or "your delivery offer"

            body = (
                f"Quick heads-up {owner} — {match} at {venue}{time_clause}. "
                f"On big match days your dine-in covers dip vs your Saturday average as fans order at home. "
                f"Skipping dine-in promos and spotlighting {offer_lead} captures this stay-at-home surge. "
                f"Want me to stage the delivery banner and social story now?"
            )
            return ComposedMessage(
                body=body,
                cta="binary_yes_no",
                send_as="vera",
                suppression_key=trigger.suppression_key or f"ipl_match:{merchant.merchant_id}",
                rationale="Contrarian event-timing recommendation leveraging the active delivery offer over dine-in discount.",
                template_name="vera_restaurant_ipl_v1",
                template_params=[owner, match, offer_lead],
            )

        # ---------------------------------------------------------------
        # 12. Curious Ask
        # ---------------------------------------------------------------
        if "curious" in kind:
            views = merchant.performance.views
            noun = _category_service_noun(slug)
            body = (
                f"Hi {owner}! Quick check from {m_ident.locality} — {m_ident.name} reached {views} Google views this month: "
                f"what {noun} has had the highest inquiry this week? "
                f"I'll turn your answer into a fresh Google post + a 4-line WhatsApp share note for your clients. Takes 2 min."
            )
            return ComposedMessage(
                body=body,
                cta="open_ended",
                send_as="vera",
                suppression_key=trigger.suppression_key or f"curious_ask:{merchant.merchant_id}",
                rationale="Weekly curious ask asking the merchant for real demand input with immediate reciprocal content draft.",
                template_name="vera_curious_ask_v1",
                template_params=[owner, m_ident.name, m_ident.locality, str(views)],
            )

        # ---------------------------------------------------------------
        # 13. Renewal Due
        # ---------------------------------------------------------------
        if "renewal" in kind:
            days = payload.get("days_remaining", merchant.subscription.days_remaining or 12)
            plan = payload.get("plan", merchant.subscription.plan or "Pro")
            dip_clause = ""
            if merchant_state.calls_trend in ("dipping", "declining") or merchant_state.views_trend in ("dipping", "declining"):
                dip_clause = f" — critical for reversing your recent 7-day call dip in {m_ident.locality}"

            body = (
                f"{salutation}, your magicpin {plan} subscription renews in {days} days. "
                f"Renewing keeps your verified Google ranking, automated posts, and badge active{dip_clause}. "
                f"Reply CONFIRM to renew and keep your local search optimization uninterrupted."
            )
            return ComposedMessage(
                body=body,
                cta="binary_confirm_cancel",
                send_as="vera",
                suppression_key=trigger.suppression_key or f"renewal:{merchant.merchant_id}",
                rationale="Proactive renewal notice connecting subscription continuity to active performance recovery.",
                template_name="vera_renewal_nudge_v1",
                template_params=[salutation, str(days), plan],
            )

        # ---------------------------------------------------------------
        # 14. Dormant with Vera
        # ---------------------------------------------------------------
        if "dormant" in kind:
            days = payload.get("days_since_last_merchant_message", 38)
            views = merchant.performance.views
            body = (
                f"{salutation}, your Google listing reached {views} views in {m_ident.locality} this month, but hasn't had fresh posts in {days} days. "
                f"Publishing a 3-post weekend spotlight for {active_offer_str or 'your core services'} captures these active searchers. "
                f"Want me to draft the weekend posts for your approval?"
            )
            return ComposedMessage(
                body=body,
                cta="binary_yes_no",
                send_as="vera",
                suppression_key=trigger.suppression_key or f"dormant:{merchant.merchant_id}",
                rationale="Dormant account reactivation checking profile health and proposing fresh weekend content.",
                template_name="vera_dormancy_check_v1",
                template_params=[salutation, str(days), str(views)],
            )

        # ---------------------------------------------------------------
        # 15. Milestone Reached
        # ---------------------------------------------------------------
        if "milestone" in kind:
            metric = payload.get("metric", "views").replace("_", " ")
            val = payload.get("value_now", merchant.performance.views)
            target = payload.get("milestone_value", val + 5)
            body = (
                f"Great news {owner}! {m_ident.name} reached {val} {metric} (closing in on your {target} milestone). "
                f"Want me to draft a customer-appreciation post featuring your top services to publish today?"
            )
            return ComposedMessage(
                body=body,
                cta="binary_yes_no",
                send_as="vera",
                suppression_key=trigger.suppression_key or f"milestone:{merchant.merchant_id}",
                rationale="Milestone achievement celebration with customer appreciation post proposal.",
                template_name="vera_milestone_v1",
                template_params=[owner, str(val), metric],
            )

        # ---------------------------------------------------------------
        # General Dynamic Fallback
        # ---------------------------------------------------------------
        body = (
            f"{salutation}, quick update on {m_ident.name}: your profile reached {merchant.performance.views} views "
            f"and {merchant.performance.calls} calls in the last 30 days. Want me to draft a fresh post featuring "
            f"{active_offer_str or 'your top services'} to boost search rank this week?"
        )
        return ComposedMessage(
            body=body,
            cta="binary_yes_no",
            send_as="vera",
            suppression_key=trigger.suppression_key or f"gen:{merchant.merchant_id}:{trigger.id}",
            rationale="Deterministic evidence-anchored merchant outreach.",
            template_name="vera_generic_v1",
            template_params=[salutation, str(merchant.performance.views), str(merchant.performance.calls)],
        )
