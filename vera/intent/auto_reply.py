from __future__ import annotations
import re
from typing import List, Tuple


class AutoReplyDetector:
    CANNED_PATTERNS = [
        r"thank you for contacting",
        r"our team will respond shortly",
        r"we have received your message",
        r"automated assistant",
        r"automated response",
        r"out of office",
        r"auto-generated",
        r"will get back to you",
        r"currently unavailable",
        r"hamari team tak pahuncha",
        r"main ek automated assistant hoon",
        r"shukriya.*hum jald hi sampark karenge",
        r"thanks for reaching out.*will reply soon",
    ]

    @classmethod
    def evaluate(
        cls,
        message: str,
        turn_number: int = 1,
        prior_messages: List[str] = None,
    ) -> Tuple[bool, float, str]:
        """
        Analyzes message for WhatsApp Business canned auto-replies.
        Returns (is_auto_reply, confidence, reason).
        """
        raw = message.strip()
        msg_lower = raw.lower()
        prior_messages = prior_messages or []

        # 1. Exact or near-identical message repetition across turns
        if prior_messages:
            for idx, prev in enumerate(prior_messages):
                if prev.strip().lower() == msg_lower and len(msg_lower) > 10:
                    return True, 0.99, f"Exact identical message repeated from turn {idx+1}"

        # 2. Canned phrase matches
        for pattern in cls.CANNED_PATTERNS:
            if re.search(pattern, msg_lower):
                return True, 0.95, f"Matched canned WhatsApp business auto-reply pattern '{pattern}'"

        # 3. High turn number with repeating short acknowledgments without semantic intent
        if turn_number >= 3 and len(raw) > 30 and any(p in msg_lower for p in ["team", "contacting", "shortly", "assistant", "shukriya"]):
            return True, 0.85, "Repeated multi-turn acknowledgment with standard greeting tokens"

        return False, 0.0, "Real conversational reply"
