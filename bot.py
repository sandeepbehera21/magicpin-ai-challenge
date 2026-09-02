from __future__ import annotations
import os
import sys
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Union

from fastapi import FastAPI, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from vera.engine import VeraEngine
from vera.models.context import (
    CtxPushBody,
    CtxPushResponse,
    TickBody,
    TickResponse,
    ReplyBody,
    ReplyResponse,
    HealthResponse,
    MetadataResponse,
)

app = FastAPI(title="Vera Decision Engine", version="1.0.0")
engine = VeraEngine()


# -----------------------------------------------------------------------------
# 1. Health & Metadata Endpoints
# -----------------------------------------------------------------------------

@app.get("/v1/healthz", response_model=HealthResponse)
async def healthz():
    return HealthResponse(
        status="ok",
        uptime_seconds=engine.get_uptime_seconds(),
        contexts_loaded=engine.get_context_counts(),
    )


@app.get("/v1/metadata", response_model=MetadataResponse)
async def metadata():
    return MetadataResponse(
        team_name="Vera Decision Engine",
        team_members=["Sandeep Kumar Behera"],
        model="deterministic-evidence-engine-v2",
        approach="Evidence-first deterministic decision engine with opportunity auction, merchant attention budgeting, counterfactual send gating, conversation-state routing, and LLM language realization.",
        contact_email="vera-challenge@magicpin.in",
        version="2.0.0",
        submitted_at="2026-04-26T08:00:00Z",
    )


# -----------------------------------------------------------------------------
# 2. Context Push Endpoint
# -----------------------------------------------------------------------------

@app.post("/v1/context")
async def push_context(body: CtxPushBody):
    status_code, response_data = engine.push_context(
        scope=body.scope,
        context_id=body.context_id,
        version=body.version,
        payload=body.payload,
        delivered_at=body.delivered_at,
    )
    return JSONResponse(status_code=status_code, content=response_data.model_dump())


# -----------------------------------------------------------------------------
# 3. Tick Endpoint (Proactive Sends)
# -----------------------------------------------------------------------------

@app.post("/v1/tick", response_model=TickResponse)
async def tick(body: TickBody):
    return engine.process_tick(body)


# -----------------------------------------------------------------------------
# 4. Reply Endpoint (Multi-turn Merchant / Customer Replies)
# -----------------------------------------------------------------------------

@app.post("/v1/reply", response_model=ReplyResponse)
async def reply(body: ReplyBody):
    return engine.process_reply(body)


# -----------------------------------------------------------------------------
# 5. Standalone Challenge Brief Exports
# -----------------------------------------------------------------------------

def compose(
    category: Dict[str, Any],
    merchant: Dict[str, Any],
    trigger: Dict[str, Any],
    customer: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Standalone function interface required by challenge-brief.md §7.1.
    Inputs are raw dictionary payloads.
    Returns dictionary with body, cta, send_as, suppression_key, rationale.
    """
    return engine.compose_standalone(
        category_dict=category,
        merchant_dict=merchant,
        trigger_dict=trigger,
        customer_dict=customer,
    )


def respond(conversation_id: str, merchant_message: str, turn_number: int = 2) -> Dict[str, Any]:
    """
    Standalone function interface required by challenge-brief.md §7.4 for multi-turn replies.
    """
    reply_body = ReplyBody(
        conversation_id=conversation_id,
        message=merchant_message,
        turn_number=turn_number,
    )
    resp = engine.process_reply(reply_body)
    return resp.model_dump()


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8080))
    host = os.environ.get("HOST", "0.0.0.0")
    uvicorn.run("bot:app", host=host, port=port, reload=False)
