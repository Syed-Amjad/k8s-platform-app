"""
web service — the front half of the demo pair.

It calls `api` over the cluster network, which is what gives Istio something
real to route and Kiali a graph edge to draw. Without a second hop the service
mesh has nothing to demonstrate.
"""

import os
import time

import httpx
from fastapi import FastAPI, Request, Response
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest

app = FastAPI(title="web", version="1.0")

VERSION = os.getenv("APP_VERSION", "v1")
SERVICE = "web"
API_URL = os.getenv("API_URL", "http://api.webapp-prod.svc.cluster.local:8000")

REQUESTS = Counter(
    "http_requests_total",
    "Total HTTP requests",
    ["service", "version", "method", "path", "code"],
)

LATENCY = Histogram(
    "http_request_duration_seconds",
    "HTTP request latency in seconds",
    ["service", "version", "method", "path"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
)

KNOWN_PATHS = {"/", "/health", "/metrics"}


@app.middleware("http")
async def record_metrics(request: Request, call_next):
    path = request.url.path if request.url.path in KNOWN_PATHS else "other"
    start = time.perf_counter()
    try:
        response = await call_next(request)
        code = response.status_code
    except Exception:
        code = 500
        raise
    finally:
        elapsed = time.perf_counter() - start
        REQUESTS.labels(SERVICE, VERSION, request.method, path, str(code)).inc()
        LATENCY.labels(SERVICE, VERSION, request.method, path).observe(elapsed)
    return response


@app.get("/health")
def health():
    return {"status": "ok", "service": SERVICE, "version": VERSION}


@app.get("/")
async def index():
    """Calls the api service and reports which VERSION answered.

    This is what makes the canary visible: hammer this endpoint during a
    weighted rollout and count how many responses report v1 versus v2.
    """
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(f"{API_URL}/data")
        upstream = r.json()
        upstream_error = None
    except Exception as exc:  # noqa: BLE001 - surface the cause, never a bare 500
        upstream = None
        upstream_error = f"{type(exc).__name__}: {exc}"

    return {
        "service": SERVICE,
        "version": VERSION,
        "upstream": upstream,
        "upstream_error": upstream_error,
    }


@app.get("/metrics")
def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
