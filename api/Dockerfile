# Non-root by construction. The Helm chart sets runAsNonRoot: true and
# readOnlyRootFilesystem: true, and Project 2's Pod Security Admission and
# Kyverno policies will reject the image outright if it wants root — so it is
# cheaper to build it correctly now than to retrofit it later.
FROM python:3.12-slim

# Numeric UID, not just a name: runAsNonRoot cannot verify a username at admission
# time, only a numeric id. An image whose USER is a name still gets rejected.
RUN useradd -u 10001 -m appuser

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY main.py .

USER 10001
EXPOSE 8000

# --proxy-headers so the client IP survives the Istio sidecar and ingress gateway.
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
