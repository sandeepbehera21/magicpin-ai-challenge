from __future__ import annotations
import re
from enum import Enum
from typing import Optional, Tuple


class IntentKind(str, Enum):
    YES = "YES"
    NO = "NO"
    STOP = "STOP"
    LATER = "LATER"
    QUESTION = "QUESTION"
    PRICE_REQUEST = "PRICE_REQUEST"
    DETAIL_REQUEST = "DETAIL_REQUEST"
    ACTION_REQUEST = "ACTION_REQUEST"
    JOIN_INTENT = "JOIN_INTENT"
    SCHEDULE_INTENT = "SCHEDULE_INTENT"
    CLARIFICATION = "CLARIFICATION"
    POSITIVE_INTEREST = "POSITIVE_INTEREST"
    NEGATIVE_INTEREST = "NEGATIVE_INTEREST"
    AUTO_REPLY = "AUTO_REPLY"
    IRRELEVANT = "IRRELEVANT"


class IntentClassifier:
    @classmethod
    def classify(cls, text: str, is_customer: bool = False) -> Tuple[IntentKind, float, str]:
        """
        Classifies incoming merchant/customer message deterministically.
        Returns (IntentKind, confidence, reason).
        """
        raw = text.strip()
        msg = raw.lower()

        # 1. Stop / Opt-out / Hostile
        stop_patterns = [
            r"\bstop\b", r"\bunsubscribe\b", r"\bmat bhejo\b", r"\bdon'?t message\b",
            r"\bleave me alone\b", r"\buseless spam\b", r"\bband karo\b", r"\bblock\b",
            r"\bnever message\b", r"\bdo not text\b"
        ]
        for p in stop_patterns:
            if re.search(p, msg):
                return IntentKind.STOP, 0.99, f"Matched opt-out pattern '{p}'"

        # 2. Later / Postpone
        later_patterns = [
            r"\blater\b", r"\bbaad mein\b", r"\bbaad me\b", r"\babhi nahi\b",
            r"\bbusy now\b", r"\btomorrow\b", r"\bnext week\b", r"\bcall later\b",
            r"\bnot now\b", r"\bfursat mein\b", r"\btime nahi hai\b"
        ]
        for p in later_patterns:
            if re.search(p, msg):
                return IntentKind.LATER, 0.95, f"Matched postponement pattern '{p}'"

        # 3. Explicit Join Intent
        join_patterns = [
            r"\bjoin\b", r"\bjoin karna hai\b", r"\bjoin magicpin\b", r"\bwant to join\b",
            r"\bi want to join\b", r"\bmujhe judna hai\b", r"\bkaise join karu\b",
            r"\bsign up\b", r"\bonboard me\b", r"\bmembership leni hai\b"
        ]
        for p in join_patterns:
            if re.search(p, msg):
                return IntentKind.JOIN_INTENT, 0.98, f"Matched join intent pattern '{p}'"

        # 4. Detail Request (more specific than general action requests)
        detail_patterns = [
            r"\bsend details\b", r"\bdetails bhejo\b", r"\btell me more\b",
            r"\bmore info\b", r"\bexplain\b", r"\bkya hai yeh\b", r"\bdetails please\b"
        ]
        for p in detail_patterns:
            if re.search(p, msg):
                return IntentKind.DETAIL_REQUEST, 0.95, f"Matched detail request pattern '{p}'"

        # 5. Price Request
        price_patterns = [
            r"\bhow much\b", r"\bkitna\b", r"\bprice\b", r"\bcost\b", r"\bpricing\b",
            r"\brate kya hai\b", r"\bcharges\b", r"\bkitne paise\b", r"\bfees\b"
        ]
        for p in price_patterns:
            if re.search(p, msg):
                return IntentKind.PRICE_REQUEST, 0.95, f"Matched pricing inquiry pattern '{p}'"

        # 6. Action Request / Immediate Execution
        action_patterns = [
            r"\blet'?s do it\b", r"\bgo ahead\b", r"\bsend it\b", r"\bdo it\b",
            r"\bproceed\b", r"\bconfirm\b", r"\bhaan kar do\b", r"\bkar dijiye\b",
            r"\bkar do\b", r"\bsend karo\b", r"\bbhejo\b", r"\bstart karo\b",
            r"\bwhats next\b", r"\bwhat'?s next\b", r"\bok lets do it\b",
            r"\bsend abstract\b", r"\bsend the abstract\b", r"\bdraft the post\b",
            r"\bschedule it\b", r"\bpublish kar do\b", r"\bdispatch\b"
        ]
        for p in action_patterns:
            if re.search(p, msg):
                return IntentKind.ACTION_REQUEST, 0.95, f"Matched action execution pattern '{p}'"

        # 7. Slot / Schedule Selection (especially customer recall / booking)
        schedule_patterns = [
            r"\breply 1\b", r"\breply 2\b", r"\bslot 1\b", r"\bslot 2\b",
            r"\bwednesday\b", r"\bthursday\b", r"\bfriday\b", r"\bsaturday\b",
            r"\bevening\b", r"\bmorning\b", r"\b6pm\b", r"\b5pm\b", r"\b10am\b",
            r"\b1\b", r"\b2\b"
        ]
        if is_customer or "slot" in msg or "appointment" in msg:
            for p in schedule_patterns:
                if re.search(p, msg):
                    return IntentKind.SCHEDULE_INTENT, 0.90, f"Matched slot scheduling choice '{p}'"

        # 8. Irrelevant Domain / Curveball (GST, Tax, Loans)
        irrelevant_patterns = [
            r"\bgst\b", r"\btax\b", r"\baccounting\b", r"\bloan\b", r"\bincome tax\b",
            r"\bcourt\b", r"\blegal dispute\b", r"\bweather\b"
        ]
        for p in irrelevant_patterns:
            if re.search(p, msg):
                return IntentKind.IRRELEVANT, 0.95, f"Matched out-of-scope domain inquiry '{p}'"

        # 9. Simple Affirmative (YES)
        yes_patterns = [
            r"\byes\b", r"\bhaan\b", r"\btheek hai\b", r"\bsure\b", r"\bok\b",
            r"\bokay\b", r"\byep\b", r"\byeah\b", r"\bdefinitely\b", r"\bchalega\b",
            r"\bkar sakte ho\b", r"\by\b"
        ]
        for p in yes_patterns:
            if re.search(p, msg):
                return IntentKind.YES, 0.90, f"Matched affirmative pattern '{p}'"

        # 10. Simple Negative (NO)
        no_patterns = [
            r"\bno\b", r"\bnahi\b", r"\bnah\b", r"\bnope\b", r"\bnot interested\b",
            r"\bnahi chahiye\b", r"\bno thanks\b", r"\bno need\b", r"\bn\b"
        ]
        for p in no_patterns:
            if re.search(p, msg):
                return IntentKind.NO, 0.90, f"Matched negative pattern '{p}'"

        # 11. Positive Sentiment / Interest
        pos_patterns = [
            r"\bsounds good\b", r"\binteresting\b", r"\bbadhiya\b", r"\bachha hai\b",
            r"\bgreat\b", r"\bnice\b", r"\binterested\b"
        ]
        for p in pos_patterns:
            if re.search(p, msg):
                return IntentKind.POSITIVE_INTEREST, 0.85, f"Matched positive interest pattern '{p}'"

        # 12. Negative Sentiment / Unhelpful
        neg_patterns = [
            r"\bnot useful\b", r"\bbekaar\b", r"\buseless\b", r"\bwaste\b", r"\bkharab\b"
        ]
        for p in neg_patterns:
            if re.search(p, msg):
                return IntentKind.NEGATIVE_INTEREST, 0.85, f"Matched negative sentiment pattern '{p}'"

        # 13. Questions
        if "?" in raw or re.search(r"\b(kya|kaise|kyun|kab|how|why|what|when|where|who)\b", msg):
            return IntentKind.QUESTION, 0.85, "Detected question syntax or interrogative keyword"

        # Fallback default
        return IntentKind.CLARIFICATION, 0.60, "General unstructured message"
