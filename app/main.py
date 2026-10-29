import json
import logging
import os
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

try:  # trust the OS certificate store (corporate proxies / antivirus TLS inspection)
    import truststore

    truststore.inject_into_ssl()
except ImportError:
    pass

from fastapi import FastAPI, Request  # noqa: E402
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402
from pydantic import BaseModel, Field  # noqa: E402

from . import pipeline  # noqa: E402
from .llm import TokenFactory  # noqa: E402
from .search import Tavily  # noqa: E402

log = logging.getLogger("scamshield")
STATIC = Path(__file__).parent / "static"
MOCK = os.getenv("MOCK_MODE", "0") == "1"

LANGUAGES = {"English", "Hindi", "Telugu", "Tamil", "Kannada", "Marathi", "Bengali", "Malayalam", "Gujarati", "Spanish"}
REGIONS = {"India", "United States", "United Kingdom", "Other"}

# Abuse protection for the public demo: per-IP sliding window + global daily cap.
PER_IP_LIMIT = int(os.getenv("PER_IP_LIMIT", "15"))  # requests per 10 minutes
DAILY_LIMIT = int(os.getenv("DAILY_LIMIT", "1500"))
_hits: dict[str, deque] = defaultdict(deque)
_day = {"date": "", "count": 0}

llm = TokenFactory()
tavily = Tavily()


def rate_limited(request: Request) -> str | None:
    now = time.time()
    today = time.strftime("%Y-%m-%d")
    if _day["date"] != today:
        _day.update(date=today, count=0)
    if _day["count"] >= DAILY_LIMIT:
        return "The public demo has reached today's limit. Please try again tomorrow or run it locally."
    ip = (request.headers.get("x-forwarded-for") or (request.client.host if request.client else "?")).split(",")[0].strip()
    q = _hits[ip]
    while q and now - q[0] > 600:
        q.popleft()
    if len(q) >= PER_IP_LIMIT:
        return "Too many checks in a short time. Please wait a few minutes."
    q.append(now)
    _day["count"] += 1
    return None


@asynccontextmanager
async def lifespan(_app):
    if llm.configured:
        try:
            models = await llm.resolve_models()
            log.warning("Nemotron models resolved: %s", models)
        except Exception as ex:  # surfaced via /api/health
            log.error("Could not list Token Factory models: %s", ex)
    yield


app = FastAPI(title="ScamShield", lifespan=lifespan)


class AnalyzeRequest(BaseModel):
    text: str = Field("", max_length=8000)
    image: str | None = Field(None, description="data: URL of a screenshot")
    language: str = "English"
    region: str = "India"


@app.get("/api/health")
async def health():
    return {
        "mock": MOCK,
        "nebius": llm.configured,
        "tavily": tavily.configured,
        "models": llm.models,
    }


@app.post("/api/analyze")
async def analyze(req: AnalyzeRequest, request: Request):
    if msg := rate_limited(request):
        return JSONResponse({"detail": msg}, status_code=429)
    language = req.language if req.language in LANGUAGES else "English"
    region = req.region if req.region in REGIONS else "Other"
    image = req.image if req.image and req.image.startswith("data:image/") and len(req.image) < 8_000_000 else None

    async def stream():
        try:
            async for ev in pipeline.run(req.text, image, language, region, llm, tavily, mock=MOCK or not llm.configured):
                yield f"data: {json.dumps(ev, ensure_ascii=False)}\n\n"
        except Exception as ex:
            log.exception("analysis failed")
            yield f"data: {json.dumps({'type': 'error', 'message': str(ex)[:300]})}\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.get("/")
async def index():
    return FileResponse(STATIC / "index.html")


app.mount("/static", StaticFiles(directory=STATIC), name="static")
