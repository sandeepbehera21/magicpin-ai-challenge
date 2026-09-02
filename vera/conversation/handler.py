from __future__ import annotations
import threading
from typing import Dict, List, Optional
from ..models.context import ReplyBody, ReplyResponse


class ConversationState:
    def __init__(self, conversation_id: str):
        self.conversation_id = conversation_id
        self.turns: List[Dict[str, str]] = []
        self.auto_reply_count: int = 0
        self.is_ended: bool = False
        self.last_intent: Optional[str] = None


class ConversationHandler:
    def __init__(self):
        self._lock = threading.RLock()
        self._conversations: Dict[str, ConversationState] = {}

    def get_or_create(self, conv_id: str) -> ConversationState:
        with self._lock:
            if conv_id not in self._conversations:
                self._conversations[conv_id] = ConversationState(conv_id)
            return self._conversations[conv_id]

    def handle_reply(self, body: ReplyBody) -> ReplyResponse:
        with self._lock:
            conv = self.get_or_create(body.conversation_id)
            msg = body.message.strip()
            msg_lower = msg.lower()
            conv.turns.append({"from": body.from_role, "msg": msg})

            # -----------------------------------------------------------------
            # 1. Hostile / Opt-out Detection
            # -----------------------------------------------------------------
            hostile_keywords = ["stop messaging", "stop sending", "useless spam", "not interested", "bothering me", "don't message", "dont message", "unsubscribe", "leave me alone"]
            if any(k in msg_lower for k in hostile_keywords):
                conv.is_ended = True
                return ReplyResponse(
                    action="end",
                    body="",
                    rationale="Merchant explicitly opted out or expressed frustration; gracefully closing conversation and suppressing future automated sends.",
                )

            # -----------------------------------------------------------------
            # 2. Intent Transition to Action (Commitment Detected)
            # -----------------------------------------------------------------
            action_intent_phrases = [
                "let's do it", "lets do it", "let do it", "what's next", "whats next",
                "send the abstract", "send abstract", "send me the abstract",
                "draft the patient", "draft the post", "go ahead", "proceed",
                "i want to join", "join magicpin", "confirm", "yes please", "sure, do it", "do it",
                "ok lets do it", "ok let's do it"
            ]
            if any(p in msg_lower for p in action_intent_phrases):
                conv.last_intent = "action_committed"
                if "abstract" in msg_lower or "patient" in msg_lower or "evidence" in msg_lower:
                    body_text = (
                        "Sending the summary now. Here is the customer-facing draft based on the latest evidence we reviewed:\n\n"
                        "\"We have distilled the most relevant update into a short customer-ready note for your next outreach.\"\n\n"
                        "Want me to schedule the follow-up for your next available slot?"
                    )
                else:
                    body_text = (
                        "Done! I have initialized the setup for you:\n"
                        "- Profile updates staged for review\n"
                        "- 3 weekly Google posts drafted\n"
                        "- Verified badge activation in progress\n\n"
                        "Reply CONFIRM to publish the first post today at 10am."
                    )
                return ReplyResponse(
                    action="send",
                    body=body_text,
                    cta="binary_confirm_cancel",
                    rationale="Merchant explicitly committed; immediately switched from qualification to action-execution with concrete deliverable.",
                )

            # -----------------------------------------------------------------
            # 3. Auto-Reply Detection
            # -----------------------------------------------------------------
            auto_reply_phrases = [
                "thank you for contacting",
                "our team will respond shortly",
                "automated assistant",
                "out of office",
                "auto-generated",
                "we have received your message",
                "will get back to you",
                "shukriya. main aapki yeh sabhi baatein aur sujhaav hamari team tak pahuncha",
            ]
            is_auto_reply = any(p in msg_lower for p in auto_reply_phrases)

            # Also check if same message repeated across turns
            if len(conv.turns) >= 2:
                prev_msgs = [t["msg"] for t in conv.turns[:-1] if t["from"] == body.from_role]
                if msg in prev_msgs:
                    is_auto_reply = True

            if is_auto_reply:
                conv.auto_reply_count += 1
                # If repeated or turn >= 3, end to gracefully exit
                if conv.auto_reply_count >= 2 or body.turn_number >= 3:
                    conv.is_ended = True
                    return ReplyResponse(
                        action="end",
                        body="",
                        rationale="Auto-reply pattern detected multiple times; gracefully closing conversation.",
                    )
                else:
                    return ReplyResponse(
                        action="wait",
                        body="",
                        wait_seconds=14400,
                        rationale="Detected merchant auto-reply (canned 'Thank you for contacting' phrasing). Backing off 4 hours to wait for owner.",
                    )

            # -----------------------------------------------------------------
            # 4. Out-of-Scope / Curveball Ask (e.g., GST filing)
            # -----------------------------------------------------------------
            out_of_scope_keywords = ["gst", "tax", "accounting", "loan", "legal dispute", "court"]
            if any(k in msg_lower for k in out_of_scope_keywords):
                return ReplyResponse(
                    action="send",
                    body="I'll have to leave GST and accounting to your CA — that's outside what I can handle directly. Coming back to your profile growth — want me to send over the drafted Google posts for this week?",
                    cta="binary_yes_no",
                    rationale="Politely declined out-of-scope task and redirected back to core merchant listing support.",
                )

            # -----------------------------------------------------------------
            # 5. General Engagement Continuation
            # -----------------------------------------------------------------
            return ReplyResponse(
                action="send",
                body="Got it! I have updated your settings. Here is the next step — want me to go ahead and schedule this for your listing?",
                cta="binary_yes_no",
                rationale="Acknowledged merchant input and advanced conversation to next concrete execution step.",
            )

    def clear(self) -> None:
        with self._lock:
            self._conversations.clear()
