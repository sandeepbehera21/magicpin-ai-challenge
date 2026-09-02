from __future__ import annotations
from typing import List, Optional


class LanguageAdapter:
    @classmethod
    def determine_target_language(
        cls,
        merchant_languages: List[str],
        customer_language_pref: Optional[str] = None,
        latest_user_message: Optional[str] = None,
    ) -> str:
        """
        Determines target language mode: 'en', 'hi', or 'hi-en mix'.
        """
        # If customer-facing, honor customer preference first
        if customer_language_pref:
            pref = customer_language_pref.lower().strip()
            if "mix" in pref or ("hi" in pref and "en" in pref):
                return "hi-en mix"
            elif "hi" in pref:
                return "hi"
            elif "en" in pref:
                return "en"

        # Check latest user message for code-mix cues
        if latest_user_message:
            msg_lower = latest_user_message.lower()
            hindi_tokens = ["karo", "bhejo", "kar do", "theek", "shukriya", "nahi", "baad", "abhi", "hai", "karna", "aapka", "kya"]
            if any(token in msg_lower for token in hindi_tokens):
                return "hi-en mix"

        # Merchant language preference
        if "hi" in merchant_languages and "en" in merchant_languages:
            return "hi-en mix"
        elif "hi" in merchant_languages:
            return "hi-en mix"

        return "en"

    @classmethod
    def format_slot_phrase(cls, slot1: str, slot2: Optional[str], lang: str) -> str:
        if not slot2:
            return f"Slot: {slot1}"
        if lang in ("hi", "hi-en mix"):
            return f"Apke liye 2 slots ready hain: {slot1} ya {slot2}"
        return f"We have 2 slots ready for you: {slot1} or {slot2}"

    @classmethod
    def format_price_phrase(cls, price: str, original_price: Optional[str] = None, savings: Optional[str] = None, lang: str = "en") -> str:
        if savings:
            if lang in ("hi", "hi-en mix"):
                return f"total {price} ({savings} saved)"
            return f"total {price} (saving {savings})"
        return price
