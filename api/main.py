"""
api service — the upstream half of the demo pair.

Deliberately small. The platform is the portfolio piece, not the application.
What it does have to do properly is emit metrics, because every alerting rule
in platform-gitops/observability/rules/ is written against these series. An
observability project whose application exposes nothing to observe is a
dashboard of zeros.
"""

import os
import time

from fastapi import FastAPI, HTTPException, Request, Response
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest

app = FastAPI(title="api", version="1.0")

VERSION = os.getenv("APP_VERSION", "v1")
SERVICE = "api"

# Label sets are kept deliberately small. Every distinct combination is a new
# time series, and unbounded labels (raw paths, user ids, request ids) are the
# usual cause of a Prometheus that falls over in week three.
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

# Only these paths become label values. Anything else is recorded as "other",
# so a scanner hitting random URLs cannot inflate cardinality.
KNOWN_PATHS = {"/health", "/data", "/boom", "/slow", "/metrics"}


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


@app.get("/data")
def data():
    return {"service": SERVICE, "version": VERSION, "payload": [1, 2, 3]}


@app.get("/boom")
def boom():
    """Returns 500 on demand. Used to drive the error-budget alert in demo 4 —
    an alert you have never seen fire is a configuration, not an alert."""
    raise HTTPException(status_code=500, detail="deliberate failure")


@app.get("/slow")
def slow():
    """Sleeps long enough to push p99 latency past the 1.5s alert threshold."""
    time.sleep(2)
    return {"service": SERVICE, "version": VERSION, "slow": True}


@app.get("/metrics")
def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
