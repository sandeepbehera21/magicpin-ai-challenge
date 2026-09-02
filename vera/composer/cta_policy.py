from __future__ import annotations
from typing import Optional
from ..models.decision import CTAConfig


class CTAPolicy:
    @staticmethod
    def get_cta(trigger_kind: str, scope: str = "merchant", is_customer: bool = False) -> CTAConfig:
        kind = trigger_kind.lower()

        if scope == "customer" or is_customer:
            if "recall" in kind or "slot" in kind:
                return CTAConfig(
                    cta_type="multi_choice_slot",
                    text="Reply 1 for Slot A, 2 for Slot B, or tell us a time that works.",
                    target_action="book_slot",
                )
            elif "refill" in kind or "appointment" in kind:
                return CTAConfig(
                    cta_type="binary_confirm_cancel",
                    text="Reply CONFIRM to dispatch, or let us know if any change.",
                    target_action="confirm_refill",
                )
            else:
                return CTAConfig(
                    cta_type="binary_yes_no",
                    text="Reply YES to reserve your spot — no commitment, no auto-charge.",
                    target_action="confirm_booking",
                )

        # Merchant-facing CTAs
        if "research" in kind or "digest" in kind:
            return CTAConfig(
                cta_type="open_ended",
                text="Want me to pull the abstract + draft a patient-ed WhatsApp you can share?",
                target_action="pull_digest_abstract",
            )
        elif "regulation" in kind or "compliance" in kind or "supply" in kind:
            return CTAConfig(
                cta_type="open_ended",
                text="Want me to draft the patient advisory note + replacement workflow?",
                target_action="generate_compliance_pack",
            )
        elif "curious" in kind:
            return CTAConfig(
                cta_type="open_ended",
                text="What service has been most asked-for this week? Takes 2 min to reply.",
                target_action="collect_merchant_insight",
            )
        elif "perf_dip" in kind or "seasonal" in kind:
            return CTAConfig(
                cta_type="binary_yes_no",
                text="Want me to draft a targeted retention challenge to keep members engaged?",
                target_action="draft_retention_campaign",
            )
        elif "renewal" in kind:
            return CTAConfig(
                cta_type="binary_confirm_cancel",
                text="Reply CONFIRM to renew and protect your verified Google profile ranking.",
                target_action="confirm_renewal",
            )
        elif "active_planning" in kind:
            return CTAConfig(
                cta_type="binary_confirm_cancel",
                text="Want me to draft the 3-line WhatsApp to send to nearby facilities managers?",
                target_action="dispatch_b2b_outreach",
            )
        else:
            return CTAConfig(
                cta_type="binary_yes_no",
                text="Want me to draft the Google post + WhatsApp template for review?",
                target_action="draft_general_post",
            )
