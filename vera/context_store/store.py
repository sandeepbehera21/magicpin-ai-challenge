from __future__ import annotations
import threading
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple, Union

from ..models.context import (
    CategoryContext,
    MerchantContext,
    CustomerContext,
    TriggerContext,
    CtxPushBody,
    CtxPushResponse,
)


class StoredContextEntry:
    def __init__(self, scope: str, context_id: str, version: int, payload: Dict[str, Any], delivered_at: Optional[str] = None):
        self.scope = scope
        self.context_id = context_id
        self.version = version
        self.payload = payload
        self.delivered_at = delivered_at or datetime.now(timezone.utc).isoformat()
        self.stored_at = datetime.now(timezone.utc).isoformat()
        self.parsed_model: Optional[Union[CategoryContext, MerchantContext, CustomerContext, TriggerContext]] = None
        self._parse()

    def _parse(self) -> None:
        try:
            if self.scope == "category":
                self.parsed_model = CategoryContext.model_validate(self.payload)
            elif self.scope == "merchant":
                self.parsed_model = MerchantContext.model_validate(self.payload)
            elif self.scope == "customer":
                self.parsed_model = CustomerContext.model_validate(self.payload)
            elif self.scope == "trigger":
                self.parsed_model = TriggerContext.model_validate(self.payload)
        except Exception:
            # Keep raw payload accessible even if schema has extra or custom variations
            pass


class ContextStore:
    def __init__(self):
        self._lock = threading.RLock()
        # Key: (scope, context_id) -> StoredContextEntry
        self._storage: Dict[Tuple[str, str], StoredContextEntry] = {}

    def push(self, body: CtxPushBody) -> Tuple[int, CtxPushResponse]:
        """
        Processes an incoming context update with atomic versioning.
        Returns (http_status_code, response_model).
        """
        with self._lock:
            scope = body.scope.lower().strip()
            if scope not in ("category", "merchant", "customer", "trigger"):
                return 400, CtxPushResponse(
                    accepted=False,
                    reason="invalid_scope",
                    details=f"Unknown scope '{body.scope}'. Must be category, merchant, customer, or trigger."
                )

            key = (scope, body.context_id)
            existing = self._storage.get(key)

            if existing is not None:
                if body.version < existing.version:
                    return 409, CtxPushResponse(
                        accepted=False,
                        reason="stale_version",
                        current_version=existing.version,
                        details=f"Current version is {existing.version}; proposed version {body.version} is older."
                    )
                elif body.version == existing.version:
                    # Idempotent re-post of same version is a no-op success
                    return 200, CtxPushResponse(
                        accepted=True,
                        ack_id=f"ack_{body.context_id}_v{body.version}",
                        stored_at=existing.stored_at,
                    )

            entry = StoredContextEntry(
                scope=scope,
                context_id=body.context_id,
                version=body.version,
                payload=body.payload,
                delivered_at=body.delivered_at,
            )
            self._storage[key] = entry

            now_iso = datetime.now(timezone.utc).isoformat()
            return 200, CtxPushResponse(
                accepted=True,
                ack_id=f"ack_{body.context_id}_v{body.version}",
                stored_at=now_iso,
            )

    def get_raw(self, scope: str, context_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            entry = self._storage.get((scope.lower(), context_id))
            return entry.payload if entry else None

    def get_version(self, scope: str, context_id: str) -> Optional[int]:
        with self._lock:
            entry = self._storage.get((scope.lower(), context_id))
            return entry.version if entry else None

    def get_category(self, slug: str) -> Optional[CategoryContext]:
        with self._lock:
            entry = self._storage.get(("category", slug))
            if not entry:
                return None
            if entry.parsed_model and isinstance(entry.parsed_model, CategoryContext):
                return entry.parsed_model
            return CategoryContext.model_validate(entry.payload)

    def get_merchant(self, merchant_id: str) -> Optional[MerchantContext]:
        with self._lock:
            entry = self._storage.get(("merchant", merchant_id))
            if not entry:
                return None
            if entry.parsed_model and isinstance(entry.parsed_model, MerchantContext):
                return entry.parsed_model
            return MerchantContext.model_validate(entry.payload)

    def get_customer(self, customer_id: str) -> Optional[CustomerContext]:
        with self._lock:
            entry = self._storage.get(("customer", customer_id))
            if not entry:
                return None
            if entry.parsed_model and isinstance(entry.parsed_model, CustomerContext):
                return entry.parsed_model
            return CustomerContext.model_validate(entry.payload)

    def get_trigger(self, trigger_id: str) -> Optional[TriggerContext]:
        with self._lock:
            entry = self._storage.get(("trigger", trigger_id))
            if not entry:
                return None
            if entry.parsed_model and isinstance(entry.parsed_model, TriggerContext):
                return entry.parsed_model
            return TriggerContext.model_validate(entry.payload)

    def count_by_scope(self) -> Dict[str, int]:
        with self._lock:
            counts = {"category": 0, "merchant": 0, "customer": 0, "trigger": 0}
            for (scope, _), _ in self._storage.items():
                if scope in counts:
                    counts[scope] += 1
            return counts

    def get_all_merchants(self) -> List[MerchantContext]:
        with self._lock:
            merchants = []
            for (scope, _), entry in self._storage.items():
                if scope == "merchant":
                    try:
                        m = entry.parsed_model if isinstance(entry.parsed_model, MerchantContext) else MerchantContext.model_validate(entry.payload)
                        merchants.append(m)
                    except Exception:
                        pass
            return merchants

    def get_all_triggers(self) -> List[TriggerContext]:
        with self._lock:
            triggers = []
            for (scope, _), entry in self._storage.items():
                if scope == "trigger":
                    try:
                        t = entry.parsed_model if isinstance(entry.parsed_model, TriggerContext) else TriggerContext.model_validate(entry.payload)
                        triggers.append(t)
                    except Exception:
                        pass
            return triggers

    def clear(self) -> None:
        with self._lock:
            self._storage.clear()
