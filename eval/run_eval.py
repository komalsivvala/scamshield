"""Evaluate ScamShield on a labelled set of scam and genuine messages.

Compares two systems:
  baseline  : the deterministic rule engine alone
  scamshield: the full agent (Nemotron + Tavily + guardrails)

A message counts as flagged when the verdict is SCAM or SUSPICIOUS.

Usage:  python -m eval.run_eval            (full agent; needs API keys in .env)
        python -m eval.run_eval --rules    (rule engine only, no keys needed)
"""
import argparse
import asyncio
import json
import time
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from app import pipeline, signals  # noqa: E402
from app.llm import TokenFactory  # noqa: E402
from app.search import Tavily  # noqa: E402

HERE = Path(__file__).parent


def metrics(rows, key):
    tp = sum(1 for r in rows if r["label"] == "scam" and r[key])
    fp = sum(1 for r in rows if r["label"] == "legit" and r[key])
    fn = sum(1 for r in rows if r["label"] == "scam" and not r[key])
    tn = sum(1 for r in rows if r["label"] == "legit" and not r[key])
    precision = tp / (tp + fp) if tp + fp else 0
    recall = tp / (tp + fn) if tp + fn else 0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0
    return {"accuracy": (tp + tn) / len(rows), "precision": precision, "recall": recall, "f1": f1,
            "tp": tp, "fp": fp, "fn": fn, "tn": tn}


async def agent_verdict(text, llm, tavily):
    verdict, ms = None, 0
    t0 = time.perf_counter()
    async for ev in pipeline.run(text, None, "English", "India", llm, tavily):
        if ev["type"] == "verdict":
            verdict = ev
    ms = int((time.perf_counter() - t0) * 1000)
    return verdict, ms


async def main(rules_only: bool, limit: int | None, concurrency: int):
    rows = [json.loads(line) for line in (HERE / "dataset.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    if limit:
        rows = rows[:limit]

    for r in rows:
        res = signals.analyze(r["text"])
        r["baseline_score"] = res["score"]
        r["baseline_flag"] = res["score"] >= 20

    if not rules_only:
        llm, tavily = TokenFactory(), Tavily()
        await llm.resolve_models()
        print("Models:", llm.models)
        sem = asyncio.Semaphore(concurrency)

        async def one(r):
            async with sem:
                v, ms = await agent_verdict(r["text"], llm, tavily)
                r["agent_verdict"] = v["verdict"] if v else "ERROR"
                r["agent_score"] = v.get("risk_score") if v else None
                r["agent_flag"] = r["agent_verdict"] in {"SCAM", "SUSPICIOUS"}
                r["latency_ms"] = ms
                print(f"  #{r['id']:>2} {r['label']:<5} -> {r['agent_verdict']:<11} ({ms / 1000:.1f}s)")

        await asyncio.gather(*(one(r) for r in rows))

    report = ["# ScamShield evaluation", "", f"Dataset: {len(rows)} messages "
              f"({sum(r['label'] == 'scam' for r in rows)} scam, {sum(r['label'] == 'legit' for r in rows)} genuine). "
              "Flagged = SCAM or SUSPICIOUS.", "", "| System | Accuracy | Precision | Recall | F1 | FP | FN |", "|---|---|---|---|---|---|---|"]
    systems = [("Rule engine only (baseline)", "baseline_flag")]
    if not rules_only:
        systems.append(("ScamShield full agent", "agent_flag"))
    results = {}
    for name, key in systems:
        m = metrics(rows, key)
        results[key] = m
        report.append(f"| {name} | {m['accuracy']:.0%} | {m['precision']:.0%} | {m['recall']:.0%} | {m['f1']:.2f} | {m['fp']} | {m['fn']} |")
    hard = [r for r in rows if r["type"].startswith("hard_")]
    if hard:
        report += ["", f"**Hard set** ({len(hard)} subtle messages written after the rules were frozen, no keyword giveaways):", "",
                   "| System | Accuracy | Recall | FP | FN |", "|---|---|---|---|---|"]
        for name, key in systems:
            m = metrics(hard, key)
            report.append(f"| {name} | {m['accuracy']:.0%} | {m['recall']:.0%} | {m['fp']} | {m['fn']} |")
    if not rules_only:
        lat = sorted(r["latency_ms"] for r in rows)
        report += ["", f"Median end-to-end latency: {lat[len(lat) // 2] / 1000:.1f}s"]
        misses = [r for r in rows if r["agent_flag"] != (r["label"] == "scam")]
        report += ["", "## Errors", ""] + [f"- #{r['id']} ({r['label']}, {r['type']}): agent said {r['agent_verdict']}" for r in misses] if misses else ["", "No errors."]
    text = "\n".join(report)
    out = HERE / ("results_rules.md" if rules_only else "results.md")
    out.write_text(text + "\n", encoding="utf-8")
    (HERE / ("predictions_rules.json" if rules_only else "predictions.json")).write_text(json.dumps(rows, indent=1, ensure_ascii=False), encoding="utf-8")
    print("\n" + text)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--rules", action="store_true", help="rule engine only")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--concurrency", type=int, default=4)
    a = ap.parse_args()
    asyncio.run(main(a.rules, a.limit, a.concurrency))
