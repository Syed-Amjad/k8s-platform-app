# k8s-platform-app

Application source for the GitOps delivery platform. Two small FastAPI services
so the service mesh has something real to route.

**Deliberately tiny.** The platform is the portfolio piece, not the application.
What the app *does* have to do properly is emit metrics — every alerting rule in
the GitOps repo is written against these series, and an observability project
whose application exposes nothing to observe is a dashboard of zeros.

Deployment manifests live in the companion repo, `platform-gitops`.

---

## The two services

| Service | Role |
|---|---|
| `api` | Upstream. Returns its own `APP_VERSION`, which is how the canary split becomes visible. |
| `web` | Calls `api` over the cluster network and reports which version answered. The second hop is what gives Kiali a graph edge to draw. |

### Endpoints

| Path | Purpose |
|---|---|
| `/health` | Liveness and readiness probes |
| `/` (web) | Calls `api`, reports the upstream version |
| `/data` (api) | Trivial payload |
| `/boom` (api) | Returns **500 on demand** — drives the error-budget alert |
| `/slow` (api) | Sleeps 2s — pushes p99 past the latency threshold |
| `/metrics` | Prometheus exposition |

`/boom` and `/slow` exist because **an alert you have never seen fire is a
configuration, not an alert.** They are how demonstration 4 produces a real
firing alert instead of a screenshot of a rule definition.

---

## Metrics

Two series, matching the recording rules in `platform-gitops`:

```
http_requests_total{service, version, method, path, code}
http_request_duration_seconds{service, version, method, path}
```

The `version` label is what lets the SLO be broken down per canary version —
comparing v2's error ratio against v1's is how you decide whether to promote,
and a blended number would hide a bad canary behind a good stable.

**Path labels are bounded to a known set**, with anything else recorded as
`other`. Every distinct label combination is a new time series, and unbounded
labels — raw paths, user ids, request ids — are the usual reason a Prometheus
falls over in week three.

---

## CI

`.github/workflows/build.yml` builds both images, pushes them to GHCR tagged
with the **commit SHA** — never `:latest`, because a mutable tag means you
cannot tell which code is running — and then writes that tag into the GitOps
repo.

**CI never touches the cluster.** It has no kubeconfig and no cluster
credentials. That separation is the security argument for two repos: a
compromised application pipeline can push a bad image, but it cannot rewrite
cluster configuration, because there is nothing there to steal.

### Required repository configuration

| Kind | Name | Value |
|---|---|---|
| Variable | `GITOPS_REPO` | `Syed-Amjad/platform-gitops` |
| Secret | `GITOPS_TOKEN` | Fine-grained PAT, **contents: write on the GitOps repo only** |

`GITHUB_TOKEN` cannot reach another repository, which is why the PAT exists.
Scope it to that one repo — a token that can write to every repo you own is a
much worse trade than the convenience is worth.

Only the **v2 (canary)** tag moves automatically. `values-api-v1.yaml` is stable
and is promoted deliberately by a human, in git.

---

## Running locally

```bash
cd api
pip install -r requirements.txt
APP_VERSION=v1 uvicorn main:app --port 8000

curl localhost:8000/data
curl localhost:8000/metrics
```

```bash
cd web
pip install -r requirements.txt
API_URL=http://localhost:8000 APP_VERSION=v1 uvicorn main:app --port 8001

curl localhost:8001/ | jq
```

## Container notes

Both images run as **UID 10001, non-root, with a read-only root filesystem**.
That is not decoration — the Helm chart sets `runAsNonRoot: true`, and the
Pod Security Admission and Kyverno policies in the follow-on Zero-Trust project
reject the image outright otherwise. Building it correctly now is cheaper than
retrofitting it later.

The `USER` directive uses a **numeric** UID deliberately. `runAsNonRoot` cannot
verify a username at admission time, only a numeric id — an image whose `USER`
is a name still gets rejected.
