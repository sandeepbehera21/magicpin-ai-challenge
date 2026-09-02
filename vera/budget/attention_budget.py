from __future__ import annotations
import threading
from datetime import datetime, timezone
from typing import Dict, List, Optional, Set
from ..models.opportunity import Opportunity


class AttentionBudget:
    def __init__(
        self,
        max_actions_per_tick: int = 20,
        max_per_merchant_per_tick: int = 1,
        min_score_threshold: float = 35.0,
    ):
        self._lock = threading.RLock()
        self.max_actions_per_tick = max_actions_per_tick
        self.max_per_merchant_per_tick = max_per_merchant_per_tick
        self.min_score_threshold = min_score_threshold

        # Historical tracking
        self._sent_suppression_keys: Set[str] = set()
        self._merchant_last_touch_iso: Dict[str, str] = {}
        self._opted_out_merchants: Set[str] = set()

    def filter_candidates(self, candidates: List[Opportunity], now_iso: Optional[str] = None) -> List[Opportunity]:
        """
        Applies attention budget constraints deterministically to candidate opportunities.
        """
        with self._lock:
            approved: List[Opportunity] = []
            merchants_sent_this_tick: Set[str] = set()

            for opp in candidates:
                # 1. Minimum score check
                if opp.final_score < self.min_score_threshold:
                    continue

                # 2. Opt-out check
                if opp.merchant_id in self._opted_out_merchants:
                    continue

                # 3. Merchant attention budget per tick
                if opp.merchant_id in merchants_sent_this_tick:
                    continue

                # 4. Total tick capacity
                if len(approved) >= self.max_actions_per_tick:
                    break

                approved.append(opp)
                merchants_sent_this_tick.add(opp.merchant_id)

            return approved

    def is_suppression_key_active(self, suppression_key: str) -> bool:
        with self._lock:
            return suppression_key in self._sent_suppression_keys

    def record_send(self, merchant_id: str, suppression_key: Optional[str] = None, sent_at: Optional[str] = None) -> None:
        with self._lock:
            ts = sent_at or datetime.now(timezone.utc).isoformat()
            self._merchant_last_touch_iso[merchant_id] = ts
            if suppression_key:
                self._sent_suppression_keys.add(suppression_key)

    def record_opt_out(self, merchant_id: str) -> None:
        with self._lock:
            self._opted_out_merchants.add(merchant_id)

    def clear(self) -> None:
        with self._lock:
            self._sent_suppression_keys.clear()
            self._merchant_last_touch_iso.clear()
            self._opted_out_merchants.clear()
