"""Tavily web search: live evidence about phone numbers, domains and claimed organisations."""
import asyncio
import os
import time

import httpx

TAVILY_URL = "https://api.tavily.com/search"


class Tavily:
    def __init__(self):
        self.api_key = os.getenv("TAVILY_API_KEY", "").strip()
        self.client = httpx.AsyncClient(timeout=httpx.Timeout(30, connect=10))

    @property
    def configured(self) -> bool:
        return bool(self.api_key)

    async def search(self, query: str, purpose: str, max_results=5) -> dict:
        t0 = time.perf_counter()
        resp = await self.client.post(
            TAVILY_URL,
            headers={"Authorization": f"Bearer {self.api_key}"},
            json={
                "query": query,
                "search_depth": "basic",
                "max_results": max_results,
                "include_answer": True,
            },
        )
        resp.raise_for_status()
        data = resp.json()
        return {
            "query": query,
            "purpose": purpose,
            "answer": data.get("answer"),
            "results": [
                {"title": r.get("title", ""), "url": r.get("url", ""), "snippet": (r.get("content") or "")[:500]}
                for r in data.get("results", [])
            ],
            "ms": int((time.perf_counter() - t0) * 1000),
        }

    async def search_many(self, queries: list[tuple[str, str]]) -> list[dict]:
        tasks = [self.search(q, purpose) for q, purpose in queries]
        out = await asyncio.gather(*tasks, return_exceptions=True)
        return [
            r if not isinstance(r, Exception) else {"query": q, "purpose": p, "error": str(r), "results": []}
            for r, (q, p) in zip(out, queries)
        ]


def build_queries(entities: dict, limit=6) -> list[tuple[str, str]]:
    """Turn extracted entities into targeted verification searches."""
    q: list[tuple[str, str]] = []
    for phone in entities.get("phone_numbers", [])[:2]:
        q.append((f'"{phone}" scam OR fraud complaint', f"Reports about {phone}"))
    for dom in entities.get("domains", [])[:2]:
        q.append((f'"{dom}" scam OR phishing OR fraud', f"Reputation of {dom}"))
    for upi in entities.get("upi_ids", [])[:1]:
        q.append((f'"{upi}" UPI fraud', f"Reports about UPI ID {upi}"))
    for org in entities.get("organizations", [])[:2]:
        q.append((f"{org} official website customer care number", f"Official channels of {org}"))
    pattern = entities.get("scam_pattern_query")
    if pattern:
        q.append((pattern, "Known scam pattern"))
    seen, unique = set(), []
    for item in q:
        if item[0].lower() not in seen:
            seen.add(item[0].lower())
            unique.append(item)
    return unique[:limit]
