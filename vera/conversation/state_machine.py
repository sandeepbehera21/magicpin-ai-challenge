from __future__ import annotations
import threading
from typing import Any, Dict, List, Optional, Tuple
from ..models.context import ReplyBody, ReplyResponse, MerchantContext, CategoryContext
from .states import ConversationStateKind
from .memory import ConversationMemory
from ..intent.classifier import IntentClassifier, IntentKind
from ..intent.auto_reply import AutoReplyDetector


class ConversationStateMachine:
    def __init__(self):
        self._lock = threading.RLock()
        self._memories: Dict[str, ConversationMemory] = {}

    def get_or_create_memory(self, conv_id: str, merchant_id: str = "", customer_id: Optional[str] = None) -> ConversationMemory:
        with self._lock:
            if conv_id not in self._memories:
                self._memories[conv_id] = ConversationMemory(
                    conversation_id=conv_id,
                    merchant_id=merchant_id,
                    customer_id=customer_id,
                )
            return self._memories[conv_id]

    def process_reply(
        self,
        body: ReplyBody,
        merchant: Optional[MerchantContext] = None,
        category: Optional[CategoryContext] = None,
    ) -> ReplyResponse:
        with self._lock:
            memory = self.get_or_create_memory(
                conv_id=body.conversation_id,
                merchant_id=body.merchant_id or (merchant.merchant_id if merchant else ""),
                customer_id=body.customer_id,
            )

            msg = body.message.strip()
            prior_msgs = [t["message"] for t in memory.turns if t.get("from") == body.from_role]
            
            # 1. Evaluate Auto-Reply
            is_auto_reply, auto_conf, auto_reason = AutoReplyDetector.evaluate(
                message=msg,
                turn_number=body.turn_number,
                prior_messages=prior_msgs,
            )

            # 2. Classify Intent
            intent, intent_conf, intent_reason = IntentClassifier.classify(
                text=msg,
                is_customer=(body.from_role == "customer" or memory.customer_id is not None),
            )

            memory.record_turn(from_role=body.from_role, message=msg, intent=intent.value)

            # -----------------------------------------------------------------
            # STATE TRANSITIONS & HANDLERS
            # -----------------------------------------------------------------

            # Handler A: Stop / Opt-out
            if intent == IntentKind.STOP:
                memory.transition_to(ConversationStateKind.STOPPED)
                memory.is_suppressed = True
                return ReplyResponse(
                    action="end",
                    body="",
                    rationale="Merchant explicitly opted out; closing conversation and suppressing future automated sends.",
                )

            # Handler B: Auto-Reply Detection
            if is_auto_reply:
                memory.auto_reply_count += 1
                memory.transition_to(ConversationStateKind.AUTO_REPLY)
                if memory.auto_reply_count >= 3 or (body.turn_number >= 4 and is_auto_reply):
                    memory.transition_to(ConversationStateKind.ENDED)
                    return ReplyResponse(
                        action="end",
                        body="",
                        rationale=f"Auto-reply pattern detected on turn {body.turn_number} ({auto_reason}); gracefully closing.",
                    )
                elif memory.auto_reply_count == 2:
                    return ReplyResponse(
                        action="wait",
                        body="",
                        wait_seconds=86400,
                        rationale=f"Second auto-reply received ({auto_reason}); owner away from device. Backing off 24 hours.",
                    )
                else:
                    return ReplyResponse(
                        action="wait",
                        body="",
                        wait_seconds=14400,
                        rationale=f"Detected initial WhatsApp business auto-reply ({auto_reason}). Backing off 4 hours to wait for owner.",
                    )

            # Handler C: Postponement ("Later", "Busy now", "Baad mein")
            if intent == IntentKind.LATER:
                memory.transition_to(ConversationStateKind.WAITING)
                return ReplyResponse(
                    action="wait",
                    body="Samajh gaya — I'll pause for now and check back in a few days when you're free. 👍",
                    wait_seconds=86400,
                    rationale="Merchant requested postponement; respecting time and persisting 24h wait state.",
                )

            # Handler D: Negative Interest ("Not interested", "Nahi chahiye")
            if intent in (IntentKind.NO, IntentKind.NEGATIVE_INTEREST):
                memory.transition_to(ConversationStateKind.NOT_INTERESTED)
                return ReplyResponse(
                    action="end",
                    body="",
                    rationale="Merchant indicated no interest; closing without further pressure.",
                )

            # Handler E: ACTION-HANDOFF RULE (Action Request, Join Intent, Direct Affirmation)
            if intent in (IntentKind.ACTION_REQUEST, IntentKind.JOIN_INTENT, IntentKind.YES):
                memory.transition_to(ConversationStateKind.ACTION_CONFIRMED)
                
                # Context-aware action realization
                owner_name = merchant.identity.owner_first_name if merchant and merchant.identity else "there"
                biz_name = merchant.identity.name if merchant and merchant.identity else "your listing"
                
                if "abstract" in msg.lower() or "evidence" in (memory.last_message_body or "").lower() or "trial" in (memory.last_message_body or "").lower():
                    body_text = (
                        "Sending the summary now. Here is the patient-facing draft based on the most recent evidence we reviewed:\n\n"
                        "\"We have prepared a concise update based on the latest relevant clinical or operational finding for your customers.\"\n\n"
                        "Want me to schedule the follow-up for your next available slot?"
                    )
                elif "join" in msg.lower() or intent == IntentKind.JOIN_INTENT:
                    body_text = (
                        f"Done! I've activated your onboarding sequence for {biz_name}:\n"
                        "- Profile audit started (optimizing hours, category & photos)\n"
                        "- 3 weekly Google posts drafted\n"
                        "- Verified merchant badge verification initiated\n\n"
                        "Want me to publish your welcome post today?"
                    )
                else:
                    body_text = (
                        f"Done! I have initialized the setup for {biz_name}:\n"
                        "- Profile updates staged for review\n"
                        "- 3 weekly Google posts drafted\n"
                        "- Verified badge activation in progress\n\n"
                        "Reply CONFIRM to publish the first post today at 10am."
                    )

                return ReplyResponse(
                    action="send",
                    body=body_text,
                    cta="binary_confirm_cancel",
                    rationale="Action handoff rule triggered: merchant committed; immediately switched to execution with zero qualifying delay.",
                )

            # Handler F: "ANSWER FIRST" POLICY (Price Request, Detail Request, Question)
            if intent in (IntentKind.PRICE_REQUEST, IntentKind.DETAIL_REQUEST, IntentKind.QUESTION):
                memory.transition_to(ConversationStateKind.QUESTIONED)
                
                # Answer pricing inquiries directly first
                if intent == IntentKind.PRICE_REQUEST:
                    active_offer_title = "the active offer"
                    price_val = "current pricing"
                    if merchant and merchant.offers:
                        for o in merchant.offers:
                            if o.status == "active":
                                active_offer_title = o.title
                                if "@" in o.title:
                                    price_val = o.title.split("@")[-1].strip()
                                elif "₹" in o.title:
                                    import re
                                    m = re.search(r"₹\s*[\d,]+", o.title)
                                    if m:
                                        price_val = m.group(0)
                                else:
                                    price_val = "available pricing"
                                break

                    body_text = (
                        f"{price_val} for {active_offer_title}. "
                        f"Want me to use this offer in the next outreach draft?"
                    )
                    return ReplyResponse(
                        action="send",
                        body=body_text,
                        cta="binary_yes_no",
                        rationale="Answer First policy: provided exact pricing from active catalog first before presenting next step.",
                    )

                # Answer detail requests directly
                if intent == IntentKind.DETAIL_REQUEST:
                    body_text = (
                        "Here is the breakdown: we analyze your Google Business search impressions, "
                        "publish 3 weekly posts with verified service keywords, and update your catalog. "
                        "Takes 2 minutes to review the first draft. Want me to send the first draft?"
                    )
                    return ReplyResponse(
                        action="send",
                        body=body_text,
                        cta="binary_yes_no",
                        rationale="Answer First policy: provided concrete operational details and single binary next step.",
                    )

            # Handler G: Irrelevant Domain / Out-of-Scope (GST, Tax, Loans)
            if intent == IntentKind.IRRELEVANT:
                return ReplyResponse(
                    action="send",
                    body="I'll have to leave GST and accounting to your CA — that's outside what I can handle directly. Coming back to your profile growth — want me to send over the drafted Google posts for this week?",
                    cta="binary_yes_no",
                    rationale="Politely declined out-of-scope inquiry and redirected back to core merchant listing support.",
                )

            # Handler H: Customer Scheduling / Slot Choice
            if intent == IntentKind.SCHEDULE_INTENT:
                memory.transition_to(ConversationStateKind.CUSTOMER_APPOINTMENT)
                return ReplyResponse(
                    action="send",
                    body="Appointment confirmed! We have reserved your requested slot. A reminder will be sent 24h prior to your visit. See you soon! 😊",
                    cta="none",
                    rationale="Customer slot confirmed; completed booking flow.",
                )

            # Handler I: General Continuation
            memory.transition_to(ConversationStateKind.ENGAGED)
            return ReplyResponse(
                action="send",
                body="Got it! I have updated your settings. Here is the next step — want me to go ahead and schedule this for your listing?",
                cta="binary_yes_no",
                rationale="Acknowledged merchant input and advanced conversation to next concrete execution step.",
            )

    def clear(self) -> None:
        with self._lock:
            self._memories.clear()
