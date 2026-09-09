"""
Offline measurement harness.

Mirrors judge_simulator._full() exactly (same push order, same batching of 5)
but drives VeraEngine directly so it can run without a bot server or LLM API.

Captures each scored action and applies a *deterministic* proxy of the judge's
5-dimension rubric using only ground-truth seed data. This detects fabrication,
cross-category leakage, internal jargon, and weak CTAs. It is a measurement
instrument -- NOT the thing being optimized. A real improvement must also be
confirmed by running judge_simulator.py against a live bot before claiming it.

Usage:
    python measure_offline.py            # baseline print + JSON report
    python measure_offline.py --after    # label report as AFTER
"""
from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).parent
DATASET_DIR = ROOT / "dataset"

# Force UTF-8 so emoji / rupee symbols print on a cp1252 Windows console.
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from vera.engine import VeraEngine
from vera.models.context import TickBody


def load_dataset():
    categories = {}
    for f in (DATASET_DIR / "categories").glob("*.json"):
        data = json.load(open(f, encoding="utf-8"))
        categories[data.get("slug", f.stem)] = data

    def load_container(filename, container, key):
        path = DATASET_DIR / filename
        if not path.exists():
            return {}
        data = json.load(open(path, encoding="utf-8"))
        items = data.get(container, data.get(container.rstrip("s"), []))
        return {item[key]: item for item in items if key in item}

    merchants = load_container("merchants_seed.json", "merchants", "merchant_id")
    customers = load_container("customers_seed.json", "customers", "customer_id")
    triggers = load_container("triggers_seed.json", "triggers", "id")
    return categories, merchants, customers, triggers


# ----------------------------------------------------------------------------
# Ground-truth fact index
# ----------------------------------------------------------------------------

def build_ground_truth(categories, merchants, customers, triggers):
    """Every verifiable string present in the seed data, lowercased.

    A numeric/unit-bearing fact in a message is 'fabricated' when no variant of
    it appears here. We only flag tokens that LOOK like a specific claim
    (a price, a percentage, a distance, a date-ish number), so plain counts
    like "2 slots" or "6 months" that are directly derivable are not flagged.
    """
    gt = set()

    def add(*vals):
        for v in vals:
            if v is None:
                continue
            if isinstance(v, (dict, list)):
                continue
            s = str(v).strip().lower()
            if s:
                gt.add(s)

    for slug, cat in categories.items():
        for d in cat.get("digest", []):
            add(d.get("id"), d.get("title"), d.get("source"),
                d.get("summary"), d.get("actionable"), d.get("kind"))
        for o in cat.get("offer_catalog", []):
            add(o.get("title"), o.get("value"), o.get("id"))
        for pc in cat.get("patient_content_library", []):
            add(pc.get("title"), pc.get("body"))
        for sb in cat.get("seasonal_beats", []):
            add(sb.get("month_range"), sb.get("note"), sb.get("month"))
        for ts in cat.get("trend_signals", []):
            add(ts.get("query"), ts.get("delta_yoy"))
        add(cat.get("display_name"), slug)
        for aw in cat.get("voice", {}).get("vocab_allowed", []):
            add(aw)
        for tw in cat.get("voice", {}).get("vocab_taboo", []):
            add(tw)

    for mid, m in merchants.items():
        add(mid, m.get("category_slug"))
        idn = m.get("identity", {})
        add(idn.get("name"), idn.get("city"), idn.get("locality"),
            idn.get("owner_first_name"), idn.get("established_year"),
            idn.get("place_id"))
        for lang in idn.get("languages", []):
            add(lang)
        sub = m.get("subscription", {})
        add(sub.get("status"), sub.get("plan"), sub.get("days_remaining"),
            sub.get("days_since_expiry"), sub.get("renewed_at"))
        perf = m.get("performance", {})
        add(perf.get("views"), perf.get("calls"), perf.get("directions"),
            perf.get("ctr"), perf.get("leads"), perf.get("window_days"))
        for d7k, d7v in (perf.get("delta_7d") or {}).items():
            add(d7v)
        for o in m.get("offers", []):
            add(o.get("title"), o.get("status"), o.get("started"),
                o.get("ended"), o.get("id"))
        for cht in m.get("conversation_history", []):
            add(cht.get("body"), cht.get("engagement"))
        agg = m.get("customer_aggregate", {})
        add(agg.get("total_unique_ytd"), agg.get("lapsed_180d_plus"),
            agg.get("retention_6mo_pct"), agg.get("high_risk_adult_count"),
            agg.get("chronic_rx_count"))
        for sig in m.get("signals", []):
            add(sig)
        for rt in m.get("review_themes", []):
            add(rt.get("theme"), rt.get("sentiment"), rt.get("occurrences_30d"),
                rt.get("common_quote"))

    for cid, c in customers.items():
        idn = c.get("identity", {})
        add(cid, c.get("merchant_id"), idn.get("name"), idn.get("age_band"),
            idn.get("language_pref"))
        rel = c.get("relationship", {})
        add(rel.get("first_visit"), rel.get("last_visit"), rel.get("visits_total"),
            rel.get("lifetime_value"), rel.get("favourite_dish"))
        for sv in rel.get("services_received", []):
            add(sv)
        for cond in rel.get("chronic_conditions", []):
            add(cond)
        add(c.get("state"))

    for tid, trg in triggers.items():
        add(tid, trg.get("kind"), trg.get("scope"), trg.get("source"))
        for k, v in (trg.get("payload") or {}).items():
            if isinstance(v, (dict, list)):
                continue
            add(v)
            add(k)
        add(trg.get("urgency"), trg.get("suppression_key"),
            trg.get("merchant_id"), trg.get("customer_id"))

    return gt


# ----------------------------------------------------------------------------
# Deterministic proxy scorer
# ----------------------------------------------------------------------------

class ProxyScore:
    def __init__(self, spec, cat, merch, dec, eng, penalties, reasons):
        self.spec = spec
        self.cat = cat
        self.merch = merch
        self.dec = dec
        self.eng = eng
        self.penalties = penalties
        self.reasons = reasons

    @property
    def total(self):
        return max(0, self.spec + self.cat + self.merch + self.dec +
                   self.eng - self.penalties)


NUM_CLAIM_RE = re.compile(
    r'₹\s*\d[\d,]*(?:\.\d+)?'
    r'|\d+(?:\.\d+)?\s*(?:%|percent|km|kms)'
    r'|\b\d{2,4}(?:\.\d+)?\s*(?:am|pm)'
    r'|₹?\s*\d{3,}',
    re.I,
)
JARGON_RE = re.compile(
    r'\b(evidence ledger|composite score|auction|actionability|timing fit|'
    r'merchant_rel|counterfactual|suppression key|attention budget|'
    r'get_all_by_prefix|field_path|ledger)\b',
    re.I,
)


def proxy_score(action, merchant, category, trigger, customer, gt):
    body = action.get("body", "")
    bid = action.get("merchant_id", "")
    cat_slug = (merchant or {}).get("category_slug", "")
    low = body.lower()
    reasons = []
    penalties = 0

    # --- specificity: concrete, verifiable info ---
    nums = len(set(re.findall(r'\d+', body)))
    has_price = bool(re.search(r'₹|Rs\.?', body, re.I))
    has_pct = bool(re.search(r'\d+\s*%', body))
    has_dist = bool(re.search(r'\d+(\.\d+)?\s*km', body, re.I))
    has_time = bool(re.search(r'\d{1,2}(:\d{2})?\s*(am|pm)', body, re.I))
    concrete = (has_price, has_pct, has_dist, has_time, nums >= 2)
    spec = 4 + sum(concrete) + (1 if nums >= 3 else 0)
    spec = max(1, min(10, spec))

    # --- category fit ---
    cat_fit = 8
    cat_taboos = [t.lower() for t in (category or {}).get("voice", {}).get("vocab_taboo", [])]
    for taboo in cat_taboos:
        if taboo in low:
            cat_fit = min(cat_fit, 3)
            penalties += 1
            reasons.append(f"taboo:'{taboo}'")
    # wrong vertical noun leakage
    leaks = {
        "dentists": [r'salon', r'haircut', r'hairdress', r'bridal', r'thali'],
        "salons":   [r'dental', r'flouride|fluoride', r'root canal', r'cleaning @', r'mSv', r'iopa'],
        "pharmacies": [r'salon', r'haircut', r'bridal', r'thali', r'pizza', r'workout', r'1rm'],
        "restaurants": [r'dental', r'salon', r'flouride|fluoride', r'workout', r'membership churn'],
        "gyms":     [r'thali', r'dental', r'pharmac', r'recipe'],
    }
    for pat in leaks.get(cat_slug, []):
        if re.search(pat, low, re.I):
            cat_fit = min(cat_fit, 4)
            penalties += 1
            reasons.append(f"cross-cat:{pat}")
            break

    # --- merchant fit ---
    owner = (merchant or {}).get("identity", {}).get("owner_first_name", "")
    m_name = (merchant or {}).get("identity", {}).get("name", "")
    merch_fit = 8
    if m_name and m_name.lower() not in low:
        # not fatal; many messages use owner name
        pass
    # referencing ANOTHER merchant's name/locality
    other_names = []
    for mid_o, m_o in merchants_by_id.items():
        if mid_o == bid:
            continue
        idn = m_o.get("identity", {}) or {}
        other_names += [idn.get("name"), idn.get("locality")]
    for nm in other_names:
        if nm and len(nm) > 4 and nm.lower() in low:
            merch_fit = min(merch_fit, 3)
            penalties += 1
            reasons.append(f"wrong-merchant:'{nm}'")

    # --- decision quality: connect to why-now + actionable next step ---
    payload = (trigger or {}).get("payload", {}) or {}
    pl_low = json.dumps(payload).lower()
    # which why-now facts appear in the body
    pl_keys = set(re.findall(r'"([a-z_]{3,20})":', pl_low))
    why_hits = 0
    for k in pl_keys:
        if k in ("true", "false", "null", "none"):
            continue
        # also extract payload values
        pass
    # Simpler: check a few conversational markers: does it reference the trigger kind?
    kind = (trigger or {}).get("kind", "")
    dec = 6
    # actionable next step
    cta = (action.get("cta") or "").lower()
    has_cta = bool(cta) and cta not in ("none", "")
    if has_cta:
        dec = min(10, dec + 1)
    # references a concrete number from the trigger/merchant (why-now)
    if any(t in low for t in ["days", "week", "today", "tmr", "tomorrow", "this ", "since "]):
        dec = min(10, dec + 1)
    if kind and kind.replace("_", " ") in body.lower():
        dec = min(10, dec + 1)

    # --- engagement compulsion ---
    questions = len(re.findall(r'\?', body))
    cta_verbs = re.findall(r'\b(reply|book|let me know|want me|shall i|reply yes|reserve|join|dm|call|whatsapp|confirm|would you like|say yes)\b', low)
    eng = 7 if has_cta else 4
    if questions >= 2:
        eng = max(1, eng - 1)
        reasons.append("multiple-questions")
    if len(set(cta_verbs)) >= 2:
        eng = max(1, eng - 2)
        reasons.append("multiple-ctas")
    if not has_cta:
        eng = max(1, eng - 1)
        reasons.append("no-cta")

    # --- fabrication: numeric/unit claims not in ground truth ---
    fabricated = 0
    for m in NUM_CLAIM_RE.finditer(body):
        tok = m.group(0).strip().lower()
        num = re.search(r'\d[\d,]*', tok)
        num = num.group(0).replace(",", "") if num else ""
        if num and (num in gt or tok in gt):
            continue
        # allow small counts / derived numbers that match a real aggregate
        try:
            fnum = float(num)
        except ValueError:
            continue
        # If number appears in merchant perf/subscription/customer aggregate it's legit
        if fnum in ground_truth_numbers:
            continue
        fabricated += 1
    if fabricated:
        penalties += fabricated * 2
        reasons.append(f"fabricated x{fabricated}")

    # --- internal jargon penalty ---
    jm = JARGON_RE.search(body)
    if jm:
        penalties += 1
        reasons.append(f"jargon:'{jm.group(0)}'")

    return ProxyScore(spec, cat_fit, merch_fit, dec, eng, penalties, reasons)


categories_by_slug = {}
merchants_by_id = {}
ground_truth_numbers = set()


def run(after: bool = False):
    global categories_by_slug, merchants_by_id, ground_truth_numbers
    categories, merchants, customers, triggers = load_dataset()
    categories_by_slug = categories
    merchants_by_id = merchants

    # precompute legit numeric ground-truth values
    gt = build_ground_truth(categories, merchants, customers, triggers)
    ground_truth_numbers = set()
    for s in gt:
        m = re.fullmatch(r'\d+(\.\d+)?', s)
        if m:
            ground_truth_numbers.add(float(s))

    engine = VeraEngine()

    # Same push order as judge._full(): categories, then merchants, then triggers.
    for slug, cat in categories.items():
        engine.push_context("category", slug, 1, cat)
    for mid, m in merchants.items():
        engine.push_context("merchant", mid, 1, m)
    for cid, c in customers.items():
        engine.push_context("customer", cid, 1, c)
    for tid, t in triggers.items():
        engine.push_context("trigger", tid, 1, t)

    tids = list(triggers.keys())
    print(f"Total triggers: {len(tids)}, merchants: {len(merchants)}, customers: {len(customers)}")

    now = datetime.now(timezone.utc).isoformat()

    all_actions = []
    for i in range(0, len(tids), 5):
        batch = tids[i:i + 5]
        resp = engine.process_tick(TickBody(now=now, available_triggers=batch))
        label = f"Batch {i//5 + 1} [{batch[0].split('_')[1]}..{batch[-1].split('_')[1]}]"
        print(f"\n=== {label}: {len(resp.actions)} action(s) ===")
        for a in resp.actions:
            print(f"  [{a.trigger_id}] {a.merchant_id}")
            print(f"    body: {a.body}")
            print(f"    cta : {a.cta}")
            all_actions.append(a)

    print("\n" + "=" * 74)
    print("DETERMINISTIC PROXY SCORES (measurement instrument, not the object being optimized)")
    print("=" * 74)
    totals = []
    for a in all_actions:
        m = merchants.get(a.merchant_id, {})
        c = categories.get(m.get("category_slug", ""), {})
        trg = triggers.get(a.trigger_id, {})
        cust = customers.get(a.customer_id) if a.customer_id else None
        s = proxy_score({
            "body": a.body, "cta": a.cta, "merchant_id": a.merchant_id,
            "trigger_id": a.trigger_id, "customer_id": a.customer_id,
        }, m, c, trg, cust, gt)
        totals.append(s)
        r = ",".join(s.reasons) or "-"
        print(f"  {a.merchant_id[:8]} {a.trigger_id[:24]:24} spec={s.spec} cat={s.cat} merch={s.merch} dec={s.dec} eng={s.eng} pen=-{s.penalties} TOTAL={s.total:2}/50  [{r}]")

    if totals:
        n = len(totals)
        per_dim = {
            "specificity": sum(t.spec for t in totals) / n,
            "category_fit": sum(t.cat for t in totals) / n,
            "merchant_fit": sum(t.merch for t in totals) / n,
            "decision_quality": sum(t.dec for t in totals) / n,
            "engagement": sum(t.eng for t in totals) / n,
        }
        avg_total = sum(t.total for t in totals) / n
        tot_pen = sum(t.penalties for t in totals)
        print(f"\n  Messages scored: {n}")
        for k, v in per_dim.items():
            print(f"    Avg {k:18}: {v:.1f}")
        print(f"    Avg TOTAL: {avg_total:.1f}/50 ({avg_total/50*100:.0f}%)  penalties_total={tot_pen}")

    tag = "after" if after else "before"
    report = {
        "generated_at": now,
        "tag": tag,
        "n_actions": len(all_actions),
        "actions": [
            {"trigger_id": a.trigger_id, "merchant_id": a.merchant_id,
             "customer_id": a.customer_id, "body": a.body, "cta": a.cta,
             "template_name": a.template_name}
            for a in all_actions
        ],
    }
    out = ROOT / f"measure_report_{tag}.json"
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nReport written to {out}")


if __name__ == "__main__":
    after = "--after" in sys.argv
    run(after=after)
