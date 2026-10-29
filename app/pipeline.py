"""ScamShield agent: read -> extract -> rule checks -> web investigation -> verdict -> family explanation.

`run()` is an async generator of events streamed to the UI, so users (and judges) can watch
each Nemotron / Tavily step happen live.
"""
import asyncio
import json
import os
import time

from . import signals as sig
from .llm import LLMError, TokenFactory
from .search import Tavily, build_queries

MOCK_DELAY = float(os.getenv("MOCK_DELAY", "1"))

HELPLINES = {
    "India": [
        "Call the National Cyber Crime Helpline 1930 immediately if money was lost",
        "Report at cybercrime.gov.in",
        "Report fraud calls/SMS on Sanchar Saathi (sancharsaathi.gov.in → Chakshu)",
    ],
    "United States": ["Report at reportfraud.ftc.gov", "Forward scam texts to 7726 (SPAM)"],
    "United Kingdom": ["Forward scam texts to 7726", "Report to Action Fraud: actionfraud.police.uk or 0300 123 2040"],
    "Other": ["Contact your bank using the number on the back of your card", "Report to your national cybercrime authority"],
}

EXTRACT_SYSTEM = """You are a fraud analyst. Extract facts from a message a user received.
Return ONLY a JSON object with these keys:
{"language": "language the message is written in",
 "channel": "sms|whatsapp|email|call|social|other",
 "claimed_sender": "who the message claims to be from, or null",
 "organizations": ["brands/companies/government bodies named or impersonated"],
 "phone_numbers": [], "urls": [], "upi_ids": [], "amounts": [],
 "requested_actions": ["what the sender wants the recipient to do"],
 "pressure_tactics": ["fear, urgency, greed, authority... with the exact phrase"],
 "scam_pattern_query": "a short web search query describing this message pattern + the word scam, e.g. 'electricity bill disconnection SMS scam India'",
 "summary": "one neutral sentence describing the message"}
Use [] for empty lists. Do not invent entities that are not in the message."""

VERDICT_SYSTEM = """You are ScamShield, a careful fraud investigator protecting ordinary people.
Weigh the message, the deterministic rule signals and the live web evidence, then decide.
Rules:
- Judge THIS MESSAGE: is it itself a scam attempt? Calibrate:
  SCAM = the message tries to get money, credentials, codes or remote access through deception or impersonation.
  SUSPICIOUS = real warning signs but no clear deceptive ask, or impersonation cannot be confirmed either way.
  LIKELY_SAFE = an informational notification (OTP, debit/credit alert, delivery, bill reminder, appointment) that
  asks for nothing risky, or a normal personal message. A genuine OTP or transaction alert is LIKELY_SAFE even if
  the reader did not start the transaction; put that caveat in what_to_do ("if you didn't make this payment, call
  the number on your card"), do NOT raise the verdict for it.
- Trust "trust_signals" from the rule engine: a link on a verified official domain is genuine. Note Indian banks are
  migrating to *.bank.in, and their older domains (e.g. hdfcbank.com, icicibank.com, sbi.co.in) remain official.
- Do not treat a phone number as proof of fraud just because web results tie it to a different organisation unless
  the evidence clearly shows it; toll-free numbers are often shared or listed by aggregators.
- Cite evidence by id (E1, E2...) only when the evidence actually supports the point. Never invent sources.
- If a link's domain differs from the official domain found in evidence, say so explicitly.
- Absence of web reports is NOT proof of safety.
Return ONLY JSON:
{"verdict": "SCAM|SUSPICIOUS|LIKELY_SAFE",
 "risk_score": 0-100,
 "confidence": "low|medium|high",
 "scam_type": "e.g. KYC phishing, electricity bill scam, task job scam, digital arrest, none",
 "headline": "one short sentence verdict for a non-technical person",
 "red_flags": [{"flag": "short title", "why": "1-2 sentence explanation", "evidence": ["E1"]}],
 "safe_signs": ["reasons it might be genuine, if any"],
 "official_channel": "the real website/number to use instead, if found in evidence, else null",
 "what_to_do": ["concrete next steps"],
 "do_not": ["things the person must not do"]}"""

FAMILY_SYSTEM = """You explain scam-check results to elderly parents and people who are not tech-savvy.
Write in {language}, using the native script of that language. Very simple words, warm tone, no jargon, no English
technical terms unless unavoidable. Return ONLY JSON:
{{"explanation": "3-5 short sentences: what this message is, why, and what to do",
  "share_text": "a WhatsApp message (max 60 words, in {language}) warning family members about this exact message, starting with an emoji"}}"""


def event(kind, **data):
    return {"type": kind, **data}


async def run(text: str, image_data_url: str | None, language: str, region: str, llm: TokenFactory, tavily: Tavily, mock=False):
    t_start = time.perf_counter()
    if mock:
        async for e in _mock_run(text, language, region):
            yield e
        return

    # 1. Screenshot -> text (Nemotron vision)
    if image_data_url:
        yield event("step", id="ocr", status="running", title="Reading screenshot", agent="Nemotron vision")
        if not llm.models.get("vision"):
            yield event("step", id="ocr", status="skipped", title="Reading screenshot",
                        detail="No Nemotron vision model available on this account")
        else:
            try:
                out = await llm.chat("vision", [{"role": "user", "content": [
                    {"type": "text", "text": "Transcribe every word of the message(s) in this screenshot exactly, "
                                             "including sender name/number, links and amounts. Output only the transcription."},
                    {"type": "image_url", "image_url": {"url": image_data_url}},
                ]}], max_tokens=1200, temperature=0)
                text = (text + "\n" + out["text"]).strip()
                yield event("step", id="ocr", status="done", title="Reading screenshot", model=out["model"],
                            ms=out["ms"], detail=out["text"][:400])
            except Exception as ex:  # keep going with whatever text we have
                yield event("step", id="ocr", status="error", title="Reading screenshot", detail=str(ex)[:200])
    if not text.strip():
        yield event("error", message="Please paste a message or upload a screenshot.")
        return

    # 2. Deterministic checks + Nemotron Super extraction
    yield event("step", id="extract", status="running", title="Extracting phone numbers, links & claims", agent="Nemotron Super")
    yield event("step", id="rules", status="running", title="Running fraud-pattern checks", agent="Rule engine")
    regex_entities = sig.extract_entities(text)
    rules = sig.analyze(text, regex_entities)
    yield event("step", id="rules", status="done", title="Running fraud-pattern checks", agent="Rule engine",
                detail=f"{len(rules['signals'])} signal(s) · baseline risk {rules['score']}", signals=rules["signals"])

    extracted = {}
    try:
        extracted, out = await llm.chat_json("fast", [
            {"role": "system", "content": EXTRACT_SYSTEM},
            {"role": "user", "content": f"MESSAGE:\n{text[:6000]}"},
        ], max_tokens=900, temperature=0)
        yield event("step", id="extract", status="done", title="Extracting phone numbers, links & claims",
                    model=out["model"], ms=out["ms"], detail=extracted.get("summary", ""), entities=extracted)
    except (LLMError, Exception) as ex:
        yield event("step", id="extract", status="error", title="Extracting phone numbers, links & claims", detail=str(ex)[:200])

    entities = merge_entities(regex_entities, extracted)

    # 3. Live web investigation (Tavily)
    evidence = []
    queries = build_queries(entities)
    if tavily.configured and queries:
        yield event("step", id="search", status="running", title=f"Investigating on the web ({len(queries)} searches)",
                    agent="Tavily", detail=" · ".join(q for q, _ in queries))
        results = await tavily.search_many(queries)
        for r in results:
            for item in r.get("results", [])[:3]:
                evidence.append({"id": f"E{len(evidence) + 1}", "purpose": r["purpose"], **item})
        errors = [r for r in results if r.get("error")]
        yield event("step", id="search", status="done" if not errors or evidence else "error",
                    title=f"Investigating on the web ({len(queries)} searches)", agent="Tavily",
                    ms=max((r.get("ms", 0) for r in results), default=0),
                    detail=f"{len(evidence)} sources collected" + (f" · {len(errors)} search(es) failed" if errors else ""),
                    evidence=evidence)
    else:
        yield event("step", id="search", status="skipped", title="Investigating on the web", agent="Tavily",
                    detail="Tavily not configured" if not tavily.configured else "Nothing specific to look up")

    # 4. Verdict (Nemotron Ultra)
    yield event("step", id="verdict", status="running", title="Weighing the evidence", agent="Nemotron Ultra")
    payload = {
        "message": text[:6000],
        "extracted": extracted,
        "rule_signals": [{k: s[k] for k in ("severity", "title", "detail", "match")} for s in rules["signals"]],
        "rule_baseline_score": rules["score"],
        "trust_signals": rules["trust"],
        "web_evidence": [{k: e[k] for k in ("id", "purpose", "title", "url", "snippet")} for e in evidence],
        "user_region": region,
    }
    try:
        verdict, out = await llm.chat_json("reason", [
            {"role": "system", "content": VERDICT_SYSTEM},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
        ], max_tokens=4000, temperature=0.1)
        verdict = apply_guardrails(verdict, rules)
        yield event("step", id="verdict", status="done", title="Weighing the evidence", model=out["model"], ms=out["ms"],
                    detail=f"{verdict['verdict']} · risk {verdict['risk_score']}")
    except Exception as ex:
        yield event("step", id="verdict", status="error", title="Weighing the evidence", detail=str(ex)[:200])
        verdict = fallback_verdict(rules)

    verdict["helplines"] = HELPLINES.get(region, HELPLINES["Other"]) if verdict["verdict"] != "LIKELY_SAFE" else []
    verdict["evidence"] = evidence
    verdict["signals"] = rules["signals"]
    verdict["entities"] = entities
    yield event("verdict", **verdict)

    # 5. Family explanation in the user's language. Ultra without thinking: much better
    #    Indic-language fluency than Super in our tests, at ~2-5s.
    yield event("step", id="family", status="running", title=f"Explaining for family in {language}", agent="Nemotron Ultra")
    try:
        fam, out = await llm.chat_json("reason", [
            {"role": "system", "content": FAMILY_SYSTEM.format(language=language)},
            {"role": "user", "content": json.dumps({
                "verdict": verdict["verdict"], "headline": verdict.get("headline"), "scam_type": verdict.get("scam_type"),
                "red_flags": [f["flag"] for f in verdict.get("red_flags", [])], "what_to_do": verdict.get("what_to_do"),
                "do_not": verdict.get("do_not"), "message_summary": extracted.get("summary") or text[:300],
            }, ensure_ascii=False)},
        ], max_tokens=900, temperature=0.3, think=False)
        yield event("step", id="family", status="done", title=f"Explaining for family in {language}", model=out["model"], ms=out["ms"])
        yield event("family", language=language, **fam)
    except Exception as ex:
        yield event("step", id="family", status="error", title=f"Explaining for family in {language}", detail=str(ex)[:200])

    yield event("done", total_ms=int((time.perf_counter() - t_start) * 1000), models=llm.models)


def merge_entities(regex_entities: dict, extracted: dict) -> dict:
    def uniq(*lists):
        return list(dict.fromkeys(x.strip() for lst in lists for x in (lst or []) if isinstance(x, str) and x.strip()))

    domains = list(regex_entities["domains"])
    for u in extracted.get("urls") or []:
        d = sig.extract_entities(u)["domains"]
        domains.extend(d)
    return {
        "phone_numbers": uniq(regex_entities["phone_numbers"], [p.replace(" ", "").replace("-", "") for p in extracted.get("phone_numbers") or []]),
        "domains": uniq(domains),
        "urls": uniq(regex_entities["urls"], extracted.get("urls")),
        "upi_ids": uniq(regex_entities["upi_ids"], extracted.get("upi_ids")),
        "organizations": uniq(extracted.get("organizations"), [b.title() for b in regex_entities["brands_mentioned"]])[:3],
        "scam_pattern_query": extracted.get("scam_pattern_query"),
    }


def apply_guardrails(v: dict, rules: dict) -> dict:
    """Never let a model call something 'safe' when hard, auditable red flags fired."""
    v.setdefault("red_flags", [])
    v.setdefault("what_to_do", [])
    v.setdefault("do_not", [])
    verdict = str(v.get("verdict", "SUSPICIOUS")).upper().replace(" ", "_")
    if verdict not in {"SCAM", "SUSPICIOUS", "LIKELY_SAFE"}:
        verdict = "SUSPICIOUS"
    try:
        score = max(0, min(100, int(float(v.get("risk_score", 50)))))
    except (TypeError, ValueError):
        score = 50
    highs = sum(1 for s in rules["signals"] if s["severity"] == "high")
    if verdict == "LIKELY_SAFE" and highs >= 1:
        verdict, v["guardrail"] = "SUSPICIOUS", "Raised to SUSPICIOUS: a high-severity rule fired."
        score = max(score, 50)
    if verdict != "SCAM" and highs >= 2:
        verdict, v["guardrail"] = "SCAM", "Raised to SCAM: multiple high-severity rules fired."
        score = max(score, 80)
    v["verdict"], v["risk_score"] = verdict, score
    return v


def fallback_verdict(rules: dict) -> dict:
    score = rules["score"]
    verdict = "SCAM" if score >= 60 else "SUSPICIOUS" if score >= 20 else "LIKELY_SAFE"
    return {
        "verdict": verdict, "risk_score": score, "confidence": "low", "scam_type": "unknown",
        "headline": "AI analysis unavailable. This verdict is based on pattern checks only.",
        "red_flags": [{"flag": s["title"], "why": s["detail"], "evidence": []} for s in rules["signals"]],
        "safe_signs": [], "official_channel": None,
        "what_to_do": ["Verify with the organisation using its official website or app"], "do_not": ["Do not click links or share OTPs"],
    }


async def _mock_run(text, language, region):
    """UI development mode: real rule engine, canned model/search output. Clearly labelled MOCK."""
    rules = sig.analyze(text)
    for sid, title, agent in [("extract", "Extracting phone numbers, links & claims", "Nemotron Super (MOCK)"),
                              ("rules", "Running fraud-pattern checks", "Rule engine")]:
        yield event("step", id=sid, status="running", title=title, agent=agent)
    await asyncio.sleep(0.6 * MOCK_DELAY)
    yield event("step", id="rules", status="done", title="Running fraud-pattern checks", agent="Rule engine",
                detail=f"{len(rules['signals'])} signal(s) · baseline risk {rules['score']}", signals=rules["signals"])
    yield event("step", id="extract", status="done", title="Extracting phone numbers, links & claims", model="MOCK", ms=600,
                detail="MOCK summary of the message")
    yield event("step", id="search", status="running", title="Investigating on the web (3 searches)", agent="Tavily (MOCK)")
    await asyncio.sleep(0.8 * MOCK_DELAY)
    evidence = [{"id": "E1", "purpose": "MOCK", "title": "MOCK search result", "url": "https://example.com", "snippet": "Mock evidence."}]
    yield event("step", id="search", status="done", title="Investigating on the web (3 searches)", model="MOCK", ms=800,
                detail="1 sources collected", evidence=evidence)
    yield event("step", id="verdict", status="running", title="Weighing the evidence", agent="Nemotron Ultra (MOCK)")
    await asyncio.sleep(0.8 * MOCK_DELAY)
    v = fallback_verdict(rules)
    v["headline"] = "MOCK MODE: " + v["headline"]
    v["red_flags"] = [{"flag": f["flag"], "why": f["why"], "evidence": ["E1"]} for f in v["red_flags"]]
    yield event("step", id="verdict", status="done", title="Weighing the evidence", model="MOCK", ms=800,
                detail=f"{v['verdict']} · risk {v['risk_score']}")
    v.update(helplines=HELPLINES.get(region, HELPLINES["Other"]), evidence=evidence, signals=rules["signals"], entities=rules["entities"])
    yield event("verdict", **v)
    yield event("family", language=language, explanation=f"(MOCK) Simple explanation in {language} appears here.",
                share_text="⚠️ (MOCK) WhatsApp warning text appears here.")
    yield event("done", total_ms=3000, models={"fast": "MOCK", "reason": "MOCK", "vision": "MOCK"})
