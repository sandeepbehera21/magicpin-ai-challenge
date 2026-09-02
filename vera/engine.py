from __future__ import annotations
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple, Union

from .models.context import (
    CategoryContext,
    MerchantContext,
    CustomerContext,
    TriggerContext,
    CtxPushBody,
    CtxPushResponse,
    TickBody,
    TickAction,
    TickResponse,
    ReplyBody,
    ReplyResponse,
)
from .models.message import ComposedMessage
from .models.opportunity import Opportunity
from .models.decision import SendDecisionKind
from .context_store.store import ContextStore
from .evidence.builder import EvidenceBuilder
from .merchant_state.engine import MerchantStateEngine
from .auction.auction import OpportunityAuction
from .budget.attention_budget import AttentionBudget
from .gate.counterfactual import CounterfactualGate
from .gate.consent import ConsentGate
from .composer.realizer import MessageRealizer
from .critic.critic import EvidenceCritic
from .conversation.state_machine import ConversationStateMachine
from .fatigue.model import MerchantFatigueModel


class VeraEngine:
    def __init__(
        self,
        max_actions_per_tick: int = 20,
        min_score_threshold: float = 35.0,
    ):
        self.context_store = ContextStore()
        self.attention_budget = AttentionBudget(
            max_actions_per_tick=max_actions_per_tick,
            min_score_threshold=min_score_threshold,
        )
        self.state_machine = ConversationStateMachine()
        self.conversation_handler = self.state_machine
        self.start_time = time.time()

    def get_uptime_seconds(self) -> int:
        return int(time.time() - self.start_time)

    def get_context_counts(self) -> Dict[str, int]:
        return self.context_store.count_by_scope()

    def push_context(
        self,
        scope: str,
        context_id: str,
        version: int,
        payload: Dict[str, Any],
        delivered_at: Optional[str] = None,
    ) -> Tuple[int, CtxPushResponse]:
        body = CtxPushBody(
            scope=scope,
            context_id=context_id,
            version=version,
            payload=payload,
            delivered_at=delivered_at,
        )
        return self.context_store.push(body)

    def process_tick(self, tick_body: TickBody) -> TickResponse:
        trigger_ids = tick_body.available_triggers
        if not trigger_ids:
            all_triggers = self.context_store.get_all_triggers()
            trigger_ids = [t.id for t in all_triggers]

        candidate_opportunities: List[Tuple[Opportunity, TriggerContext, MerchantContext, Optional[CategoryContext], Optional[CustomerContext]]] = []

        for tid in trigger_ids:
            trg = self.context_store.get_trigger(tid)
            if not trg:
                continue

            mid = trg.merchant_id or (trg.payload.get("merchant_id") if trg.payload else None)
            if not mid:
                continue

            merchant = self.context_store.get_merchant(mid)
            if not merchant:
                continue

            category = self.context_store.get_category(merchant.category_slug)
            
            customer = None
            cid = trg.customer_id or (trg.payload.get("customer_id") if trg.payload else None)
            if cid:
                customer = self.context_store.get_customer(cid)

            # Customer Consent Hard Gate
            if trg.scope == "customer" or customer is not None:
                consent_ok, consent_reason = ConsentGate.verify_customer_consent(
                    customer=customer,
                    trigger=trg,
                    merchant_id=merchant.merchant_id,
                )
                if not consent_ok:
                    continue

            # 1. Build Evidence Ledger
            ledger = EvidenceBuilder.build_ledger(
                category=category,
                merchant=merchant,
                trigger=trg,
                customer=customer,
            )

            # 2. Derive Merchant State
            m_state = MerchantStateEngine.derive_state(merchant, category)

            # 3. Evaluate Opportunity in Auction
            opp = OpportunityAuction.evaluate_opportunity(
                trigger=trg,
                merchant=merchant,
                category=category,
                customer=customer,
                merchant_state=m_state,
                evidence_ledger=ledger,
            )

            candidate_opportunities.append((opp, trg, merchant, category, customer))

        if not candidate_opportunities:
            return TickResponse(actions=[])

        # 4. Rank candidates in Opportunity Auction
        just_opps = [c[0] for c in candidate_opportunities]
        auction_result = OpportunityAuction.rank_opportunities(just_opps)

        # 5. Apply Attention Budget
        approved_opps = self.attention_budget.filter_candidates(
            candidates=auction_result.ranked_opportunities,
            now_iso=tick_body.now,
        )

        opp_lookup = {c[0].trigger_id: c for c in candidate_opportunities}
        actions: List[TickAction] = []

        for opp in approved_opps:
            tuple_data = opp_lookup.get(opp.trigger_id)
            if not tuple_data:
                continue

            _, trg, merchant, category, customer = tuple_data
            m_state = MerchantStateEngine.derive_state(merchant, category)
            ledger = EvidenceBuilder.build_ledger(
                category=category,
                merchant=merchant,
                trigger=trg,
                customer=customer,
            )

            # 6. Counterfactual Send Gate
            gate_decision, gate_rationale, _ = CounterfactualGate.evaluate(
                opportunity=opp,
                trigger=trg,
                merchant_state=m_state,
                evidence_ledger=ledger,
            )

            if gate_decision != SendDecisionKind.SEND_NOW:
                continue

            # 7. Message Realization
            composed = MessageRealizer.realize_message(
                opportunity=opp,
                category=category,
                merchant=merchant,
                trigger=trg,
                customer=customer,
                merchant_state=m_state,
                evidence_ledger=ledger,
            )

            # 8. Evidence Critic Validation & Repair
            is_valid, final_msg, _ = EvidenceCritic.review_and_repair(
                message=composed,
                category_slug=merchant.category_slug,
                evidence_ledger=ledger,
            )

            if not is_valid:
                continue

            clean_tid = trg.id.replace("trg_", "").replace("-", "_")
            conv_id = f"conv_{merchant.merchant_id}_{clean_tid}"

            action = TickAction(
                conversation_id=conv_id,
                merchant_id=merchant.merchant_id,
                customer_id=customer.customer_id if customer else None,
                send_as=final_msg.send_as,  # type: ignore
                trigger_id=trg.id,
                template_name=final_msg.template_name,
                template_params=final_msg.template_params,
                body=final_msg.body,
                cta=final_msg.cta,
                suppression_key=final_msg.suppression_key or trg.suppression_key or f"{trg.kind}:{merchant.merchant_id}",
                rationale=final_msg.rationale,
            )

            actions.append(action)
            self.attention_budget.record_send(
                merchant_id=merchant.merchant_id,
                suppression_key=action.suppression_key,
                sent_at=tick_body.now,
            )

            # Record in Conversation Memory
            memory = self.state_machine.get_or_create_memory(
                conv_id=conv_id,
                merchant_id=merchant.merchant_id,
                customer_id=customer.customer_id if customer else None,
            )
            memory.last_trigger_id = trg.id
            memory.last_trigger_kind = trg.kind
            memory.last_message_body = final_msg.body
            memory.last_cta_type = final_msg.cta

        return TickResponse(actions=actions)

    def process_reply(self, reply_body: ReplyBody) -> ReplyResponse:
        merchant = self.context_store.get_merchant(reply_body.merchant_id) if reply_body.merchant_id else None
        category = self.context_store.get_category(merchant.category_slug) if merchant else None
        return self.state_machine.process_reply(
            body=reply_body,
            merchant=merchant,
            category=category,
        )

    def compose_standalone(
        self,
        category_dict: Dict[str, Any],
        merchant_dict: Dict[str, Any],
        trigger_dict: Dict[str, Any],
        customer_dict: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        category = CategoryContext.model_validate(category_dict) if category_dict else None
        merchant = MerchantContext.model_validate(merchant_dict)
        trigger = TriggerContext.model_validate(trigger_dict)
        customer = CustomerContext.model_validate(customer_dict) if customer_dict else None

        ledger = EvidenceBuilder.build_ledger(
            category=category,
            merchant=merchant,
            trigger=trigger,
            customer=customer,
        )
        m_state = MerchantStateEngine.derive_state(merchant, category)
        opp = OpportunityAuction.evaluate_opportunity(
            trigger=trigger,
            merchant=merchant,
            category=category,
            customer=customer,
            merchant_state=m_state,
            evidence_ledger=ledger,
        )

        composed = MessageRealizer.realize_message(
            opportunity=opp,
            category=category,
            merchant=merchant,
            trigger=trigger,
            customer=customer,
            merchant_state=m_state,
            evidence_ledger=ledger,
        )

        _, final_msg, _ = EvidenceCritic.review_and_repair(
            message=composed,
            category_slug=merchant.category_slug,
            evidence_ledger=ledger,
        )

        return {
            "body": final_msg.body,
            "cta": final_msg.cta,
            "send_as": final_msg.send_as,
            "suppression_key": final_msg.suppression_key,
            "rationale": final_msg.rationale,
            "template_name": final_msg.template_name,
            "template_params": final_msg.template_params,
        }
