from __future__ import annotations
from typing import Optional, Tuple
from ..models.context import CustomerContext, TriggerContext


class ConsentGate:
    @classmethod
    def verify_customer_consent(
        cls,
        customer: Optional[CustomerContext],
        trigger: TriggerContext,
        merchant_id: str,
    ) -> Tuple[bool, str]:
        """
        Enforces a hard gate on customer outreach:
        - Customer profile exists and belongs to merchant
        - Consent record is present with valid timestamp
        - Trigger type falls within customer's opted-in consent scope
        """
        if not customer:
            return False, "Customer context is missing for customer-scoped outreach"

        if customer.merchant_id != merchant_id:
            return False, f"Customer merchant mismatch: customer belongs to '{customer.merchant_id}', outreach by '{merchant_id}'"

        consent = customer.consent
        if not consent or not consent.opted_in_at:
            return False, "Customer has no recorded opt-in consent timestamp"

        allowed_scopes = [s.lower() for s in consent.scope]
        kind = trigger.kind.lower()

        # Map trigger kinds to required consent scopes
        if "recall" in kind:
            required = ["recall_reminders", "appointment_reminders", "promotional_offers"]
            if not any(req in allowed_scopes for req in required):
                return False, f"Recall trigger requires recall_reminders scope, customer only has {allowed_scopes}"

        elif "refill" in kind or "chronic" in kind:
            required = ["refill_reminders", "recall_reminders", "appointment_reminders", "promotional_offers"]
            if not any(req in allowed_scopes for req in required):
                return False, f"Refill trigger requires refill_reminders scope, customer only has {allowed_scopes}"

        elif "appointment" in kind:
            required = ["appointment_reminders", "recall_reminders"]
            if not any(req in allowed_scopes for req in required):
                return False, f"Appointment trigger requires appointment_reminders scope, customer only has {allowed_scopes}"

        elif "bridal" in kind or "wedding" in kind or "promo" in kind:
            required = ["promotional_offers", "bridal_followup", "special_offers"]
            if not any(req in allowed_scopes for req in required):
                return False, f"Promotional trigger requires promotional_offers scope, customer only has {allowed_scopes}"

        return True, "Customer consent verified and scope matches outreach purpose"
