# Magicpin Vera: Attention-Aware Agentic Decision Engine

Vera is an **evidence-first, attention-aware merchant growth decision engine** built for the official Magicpin AI Challenge.

Unlike standard conversational chatbots that simply generate reactive messages or wrap single large prompts, Vera treats **merchant attention as a scarce, valuable asset**. It makes systematic, deterministic decisions on:

**Decision logic is deterministic; LLM generation is constrained and validated, with deterministic fallback behavior.**
1. **WHAT** deserves the merchant's attention before deciding how to phrase it.
2. **WHY** it deserves to be said now (anchored on verifiable operational or clinical facts).
3. **WHICH** opportunity wins in a multidimensional candidate auction.
4. **WHEN** it is better to say nothing (`WAIT` or `SUPPRESS`).

---

## Architecture Overview

```
                      ┌─────────────────┐
                      │  Context Store  │ (Atomic versioning, dynamic context ingestion)
                      └────────┬────────┘
                               ↓
                       Evidence Builder (Fact extraction & Provenance tracking)
                               ↓
                     Merchant State Engine (Operational trajectory & cohorts)
                               ↓
                    Merchant Fatigue Model (Low / Medium / High pressure)
                               ↓
                      Opportunity Auction (Evidence-weighted candidate ranking)
                               ↓
                   Counterfactual Send Gate (SEND_NOW vs WAIT vs SUPPRESS)
                               ↓
                      Consent Hard Gate (Customer opt-in & scope validation)
                               ↓
                  Conversation State Machine (14 states & turn memory)
                               ↓
                        Intent Engine (15 intents + Hindi-English code-mix)
                               ↓
                      Action Handoff Gate (Zero-qualification immediate action)
                               ↓
                     Strategy Selector (10 controlled message strategies)
                               ↓
                       Language Adapter (Dynamic code-mix & domain terms)
                               ↓
                       Message Realizer (Evidence-grounded copy generation)
                               ↓
                     Evidence & Copy Critic (Evidence-grounded generation with deterministic provenance validation and fallback & single CTA)
                               ↓
                    Output / Execution Endpoints (/v1/tick, /v1/reply)
```

---

## Key Core Pillars

1. **Context as Truth & Evidence Provenance**:
   - Structured context ingestion across 4 scopes: `category`, `merchant`, `trigger`, and `customer`.
   - Every claim, number, discount, and citation is mapped back to its field path provenance in the `EvidenceLedger`.

2. **Opportunity Auction & Attention Budgeting**:
   - Competing triggers are evaluated across 11 sub-dimensions (evidence strength, merchant relevance, category relevance, urgency, timing fit, novelty, offer fit, customer fit, repetition penalties).
   - Scarcity constraints: maximum 1 message per merchant per tick window, suppression key deduplication, and attention cooldowns.

3. **Counterfactual Send Gating (`SEND_NOW` vs `WAIT` vs `SUPPRESS`)**:
   - Evaluates whether the incremental value of an opportunity justifies interrupting the business owner.

4. **14-State Conversation State Machine & Action Handoff**:
   - Deterministic transitions across states (`NEW`, `OUTBOUND_SENT`, `ENGAGED`, `QUALIFYING`, `QUESTIONED`, `ACTION_READY`, `ACTION_CONFIRMED`, `WAITING`, `NOT_INTERESTED`, `STOPPED`, `AUTO_REPLY`, `CUSTOMER_RECALL`, `CUSTOMER_APPOINTMENT`, `ENDED`).
   - **Action Handoff Rule**: When a merchant says *"yes"*, *"join"*, *"let's do it"*, or *"go ahead"*, Vera immediately switches to concrete execution with zero qualifying delays.
   - **Answer First Policy**: When a merchant asks about pricing or details, Vera answers the question directly before presenting next steps.

5. **Customer Consent Hard Gate**:
   - Customer outreach requires verified consent records matching the specific outreach scope (`recall_reminders`, `appointment_reminders`, `promotional_offers`).

6. **Evidence-grounded generation with deterministic provenance validation and fallback**:
   - Enforces single clear CTAs, replaces category taboos with compliant phrases, strips raw URLs to protect WhatsApp outbound templates, and detects/penalizes generic empty copy.

---

## API Contract

- `GET /v1/healthz` — Health and service uptime check.
- `GET /v1/metadata` — Team metadata and architectural approach details.
- `POST /v1/context` — Atomic versioned context ingestion (`category`, `merchant`, `trigger`, `customer`).
- `POST /v1/tick` — Proactive trigger evaluation batching and action generation.
- `POST /v1/reply` — Reactive multi-turn conversational reply processing.

---

## Quick Start & Local Execution

### 1. Run Unit & Adversarial Tests
```bash
python -m pytest tests/ -v
```

### 2. Start the API Server
```bash
python -m uvicorn bot:app --host 0.0.0.0 --port 8080
```

### 3. Run the Official Judge Simulator
```bash
python judge_simulator.py --scenario all
python judge_simulator.py --scenario phase2_short
```

---

## Production Deployment on Render

This repository is pre-configured for deployment on Render as a Docker Web Service.

### Option 1: One-Click / Web Service Deployment via Render Dashboard

1. **Create a New Web Service**:
   - Go to [dashboard.render.com](https://dashboard.render.com) and click **New + > Web Service**.
   - Connect your GitHub repository: `https://github.com/sandeepbehera21/magicpin-ai-challenge.git`.
2. **Configure Service Settings**:
   - **Environment**: `Docker` (or `Python 3`)
   - **Region**: `Oregon (US West)` or preferred region
   - **Branch**: `main` (or `master`)
   - **Plan**: `Free` or higher
   - **Docker Command** (Optional): `sh -c "uvicorn bot:app --host 0.0.0.0 --port ${PORT:-8080}"`
   - **Health Check Path**: `/v1/healthz`
3. **Environment Variables**:
   - `PYTHONUNBUFFERED`: `1`
   - `MAX_ACTIONS_PER_TICK`: `20`
   - `MIN_SCORE_THRESHOLD`: `35.0`
4. **Deploy**:
   - Click **Create Web Service**.
   - Render will build the Docker container and bind dynamically to `$PORT`.

### Option 2: Render Blueprint (`render.yaml`)

- Connect the repo to Render Blueprints; Render will automatically detect [`render.yaml`](file:///d:/magicpin-ai-challenge/render.yaml) and configure the healthcheck at `/v1/healthz`.

---

## Production Docker Deployment (Local)

```bash
docker build -t vera-decision-engine .
docker run -p 8080:8080 -e PORT=8080 vera-decision-engine
```

Or using Docker Compose:
```bash
docker-compose up -d --build
```
The server will start at `http://localhost:8080` with automated health checks enabled.

