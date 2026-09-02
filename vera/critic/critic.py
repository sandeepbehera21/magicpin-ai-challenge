from __future__ import annotations
import re
from typing import List, Tuple
from ..models.evidence import EvidenceLedger
from ..models.message import ComposedMessage
from ..strategy.category_profiles import get_category_profile


class GenericCopyDetector:
    GENERIC_FILLER_PHRASES = [
        "grow your business",
        "increase your sales",
        "boost engagement",
        "run a campaign",
        "special offer",
        "improve your profile",
        "get more customers",
        "reach new heights",
    ]

    @classmethod
    def calculate_specificity_score(cls, body: str, evidence_ledger: EvidenceLedger) -> float:
        """
        Calculates specificity score (0.0 to 10.0) based on concrete numbers,
        citations, specific offers, and local references vs generic filler.
        """
        score = 5.0
        
        # Numbers count (percentages, rupee prices, patient counts)
        numbers = re.findall(r"\b\d+[\d,\.%]*\b|₹\s*[\d,]+", body)
        if numbers:
            score += min(3.0, len(numbers) * 0.8)

        # Source citations
        if any(w in body for w in ["trial", "study", "journal", "circular", "batch", "regulatory", "recall"]):
            score += 1.5

        # Penalize generic filler if no numbers/facts are present
        body_lower = body.lower()
        filler_count = sum(1 for phrase in cls.GENERIC_FILLER_PHRASES if phrase in body_lower)
        if filler_count > 0 and len(numbers) == 0:
            score -= filler_count * 1.5

        return min(10.0, max(0.0, score))


class EvidenceCritic:
    @classmethod
    def review_and_repair(
        cls,
        message: ComposedMessage,
        category_slug: str,
        evidence_ledger: EvidenceLedger,
    ) -> Tuple[bool, ComposedMessage, List[str]]:
        notes = []
        body = message.body
        is_valid = True

        cat_profile = get_category_profile(category_slug)

        # 1. Check & eliminate raw URLs (Meta outbound template rule)
        url_pattern = re.compile(r"https?://\S+")
        if url_pattern.search(body):
            body = url_pattern.sub("", body).strip()
            notes.append("Repaired: Removed raw URL to comply with WhatsApp outbound template guidelines.")

        # 2. Check & eliminate category taboos
        for taboo in cat_profile.vocab_taboo:
            pattern = re.compile(re.escape(taboo), re.IGNORECASE)
            if pattern.search(body):
                body = pattern.sub("reliable", body)
                notes.append(f"Repaired: Replaced taboo term '{taboo}' with compliant vocabulary.")

        # 3. Check for multiple conflicting CTAs (enforce single primary CTA)
        cta_questions = [s for s in body.split("?") if len(s.strip()) > 0]
        if len(cta_questions) > 2:
            base = "?".join(cta_questions[:-1]) + "."
            final_cta = cta_questions[-1].strip() + "?"
            body = base + " " + final_cta
            notes.append("Repaired: Consolidated multiple questions into a single clear primary CTA.")

        # 4. Check that body is not empty
        if not body or len(body.strip()) < 10:
            is_valid = False
            notes.append("Critical: Body is empty or too short.")

        # 5. Specificity assessment
        spec_score = GenericCopyDetector.calculate_specificity_score(body, evidence_ledger)
        notes.append(f"Specificity score: {spec_score:.1f}/10")

        repaired_message = ComposedMessage(
            body=body,
            cta=message.cta,
            send_as=message.send_as,
            suppression_key=message.suppression_key,
            rationale=message.rationale + (f" [Critic: {'; '.join(notes)}]" if notes else ""),
            template_name=message.template_name,
            template_params=message.template_params,
            confidence=message.confidence,
            evidence_used=message.evidence_used,
        )

        return is_valid, repaired_message, notes
