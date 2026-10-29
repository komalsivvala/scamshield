# 🛡️ ScamShield

**Forward any suspicious message. Get a verdict, the evidence, and an explanation your parents can understand, in their language.**

ScamShield is an AI fraud investigator for ordinary families. Paste an SMS, WhatsApp message, email or UPI request, or drop in a screenshot. A team of NVIDIA Nemotron models running on **Nebius Token Factory** works with live **Tavily** web search to investigate the phone numbers, links and organisations in it. You get back a clear **Scam / Suspicious / Likely safe** verdict with cited evidence, concrete next steps, and a plain-language explanation in Hindi, Telugu, Tamil and 7 other languages, ready to forward to the family WhatsApp group.

> 🔗 **Live demo:** _TBD_ · 🎥 **Video:** _TBD_ · Track: **Best Apps and Agents**

---

## The problem

- India's National Cyber Crime Reporting Portal logs **well over a million financial-fraud complaints a year**. The scripts are simple: "your electricity will be cut tonight", "update KYC or your account will be blocked", "digital arrest", part-time "like videos" jobs, "enter your PIN to receive money".
- The people most targeted, **elderly parents and first-time smartphone users**, are the least able to check a message themselves. Today they forward it to a son or daughter and wait, or they act on it.
- Generic spam filters only see the text. A scam message often looks fine on the surface. The giveaway is **outside** the message: the number has 40 complaints online, the "SBI" link isn't an SBI domain, the real company never sends such SMSes.

ScamShield does that outside check automatically, and explains the result in the reader's own language.

## How it works

```
 message / screenshot
        │
        ▼
 ┌──────────────────┐   ┌───────────────────────┐
 │ Nemotron VL      │──▶│ Nemotron 3 Super       │  extract sender, phone numbers, links,
 │ (screenshot OCR) │   │ entity extraction      │  UPI IDs, pressure tactics, scam pattern
 └──────────────────┘   └───────────┬───────────┘
                                    │        ┌──────────────────────────┐
                                    ├───────▶│ Rule engine (deterministic)│ fake-brand domains, OTP/PIN
                                    │        │ 20+ auditable fraud checks │ requests, risky TLDs, shorteners…
                                    ▼        └─────────────┬────────────┘
                     ┌───────────────────────────┐         │
                     │ Tavily live web search     │ scam reports for the number/domain,
                     │ (parallel, targeted)       │ the organisation's OFFICIAL site & helpline
                     └─────────────┬─────────────┘         │
                                   ▼                       ▼
                     ┌──────────────────────────────────────────┐
                     │ Nemotron Ultra: evidence-weighing verdict │ verdict, risk score, red flags
                     │ + safety guardrails                       │ with citations [E1], next steps
                     └─────────────┬────────────────────────────┘
                                   ▼
                     ┌───────────────────────────┐
                     │ Nemotron Ultra: family     │ simple explanation + WhatsApp warning
                     │ explanation, any language  │ in Hindi / Telugu / Tamil / …
                     └───────────────────────────┘
```

Every step streams to the UI live, so the user sees *why*, not just *what*.

### Why multiple Nemotron models
| Step | Model | Thinking | Why |
|---|---|---|---|
| Screenshot reading | **Nemotron 3.5 Super VL** | – | Most people *receive* scams as screenshots forwarded by family |
| Entity extraction | **Nemotron 3 Super** | off | Fast structured JSON (~1 s). Benchmarked 8× faster than Nano on Token Factory |
| Verdict | **Nemotron 3 Ultra** | **on** | Weighs conflicting evidence, decides when "no reports found" ≠ safe |
| Family explanation | **Nemotron 3 Ultra** | off | Clearly better Telugu/Hindi than Super in side-by-side tests, still ~2–5 s |

Models are auto-selected from your Token Factory catalogue at startup (`/v1/models`), and the Nemotron 3 reasoning toggle (`enable_thinking`) is set per call. We pay for reasoning tokens only where reasoning changes the answer. See [`eval/latency.md`](eval/latency.md).

This follows the track guidance: *"Reach for Nemotron 3 Ultra when you need serious reasoning, and let Nano or Super handle the fast, everyday calls."*

### Trust and safety design
- **Grounded verdicts:** Ultra must cite web evidence by id (`E1`, `E2`…). Citations link to the actual source in the UI.
- **Deterministic guardrails:** if a high-severity rule fires (e.g. a link that contains "sbi" but isn't an SBI domain), the model **cannot** return "Likely safe". Two or more high-severity rules force "Scam". The UI tells the user when a guardrail changed the verdict.
- **Graceful degradation:** if a model or search call fails, the user still gets a rule-based verdict, clearly labelled.
- **Privacy:** messages are processed in memory only. Nothing is stored or logged.

## Evaluation

`eval/dataset.jsonl` holds 50 labelled messages: 26 scams covering 20+ scam types (electricity, KYC, digital arrest, task jobs, UPI-PIN, family impersonation, loan apps, crypto, US toll scams…) and 24 genuine messages chosen to be confusable (real bank OTPs, debit alerts, a genuine KYC reminder, genuine "URGENT" flight delays, cashback notices).

The last 10 are a **hard set**, written *after* the rule engine was frozen, with no keyword giveaways: romance-investment, fake landlord deposit, wedding-invite APK, fake customer care.

<!-- EVAL_RESULTS -->
| System | Accuracy | Precision | Recall | F1 | Hard-set accuracy |
|---|---|---|---|---|---|
| Rule engine only | 88% | 100% | 77% | 0.87 | 60% |
| **ScamShield (Nemotron + Tavily)** | **96%** | **93%** | **100%** | **0.96** | **90%** |

- **Every scam caught (26/26)**, including all 5 hard-set scams. The rule engine missed 4 of those 5.
- The 2 remaining errors are genuine messages labelled *Suspicious* (never *Scam*), the cautious direction for a safety tool.
- Median end-to-end latency: **12.3 s** for 3–4 Nemotron calls plus up to 6 parallel Tavily searches.
- Full results: [`eval/results.md`](eval/results.md) · model latency benchmark: [`eval/latency.md`](eval/latency.md)

**What the first run taught us.** The first full run caught every scam but flagged 6 genuine messages. Two lessons:
1. *The agent found a bug in our test data.* We had put HDFC's helpline number in a message signed "SBI". ScamShield searched the number, found it on HDFC's site, and flagged the impersonation, which is exactly what it is for. We fixed the data.
2. *Calibration.* It treated a genuine OTP as suspicious ("someone may be using your card") and didn't know Indian banks' legacy domains stay official during the move to `.bank.in`. We added rule-engine **trust signals** (verified official domains, "do not share" warnings) and a clear SCAM / SUSPICIOUS / SAFE rubric. False positives dropped from 6 to 2.

Reproduce: `python -m eval.run_eval` (full agent) or `python -m eval.run_eval --rules` (baseline, no keys).

*Caveat: this is a small, hand-written set, and prompts were calibrated after seeing the first run's errors, so treat these as development numbers, not a field accuracy claim. Run it yourself, and add your own messages to `eval/dataset.jsonl`.*

## Run it locally

```bash
git clone <this repo> && cd scamshield
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env        # add NEBIUS_API_KEY and TAVILY_API_KEY
uvicorn app.main:app --reload --port 8000
```
Open http://localhost:8000. Try `http://localhost:8000/?try=0` to auto-run an example.

On startup ScamShield calls Token Factory's `/v1/models` and picks the best available Nemotron model for each role. Pin specific ids with `FAST_MODEL`, `REASON_MODEL` and `VISION_MODEL` if you prefer.

**Docker:** `docker build -t scamshield . && docker run -p 7860:7860 --env-file .env scamshield`

## Project structure
```
app/
  main.py       FastAPI app, streaming /api/analyze endpoint (SSE)
  pipeline.py   the agent: OCR → extract → rules → Tavily → verdict → family explanation
  llm.py        Nebius Token Factory client + Nemotron model auto-selection
  search.py     Tavily client + targeted query builder
  signals.py    deterministic fraud rules (domains, OTP/PIN requests, threats…)
  static/       single-page UI (no build step)
eval/           labelled dataset + evaluation script + results
```

## Built with
- **NVIDIA Nemotron 3** open models: Ultra (550B), Super (120B), Super VL (benchmarked Nano, Lightning)
- **Nebius Token Factory**: OpenAI-compatible inference for every model call
- **Tavily**: live web search for evidence
- FastAPI · vanilla JS

## What was built during the hackathon
Everything in this repository was created during the submission period.

## License
[MIT](LICENSE)
