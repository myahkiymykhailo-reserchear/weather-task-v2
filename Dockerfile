FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# ca-certificates is needed for outbound HTTPS to the upstream APIs.
# `python:3.12-slim` ships with it, but pin it explicitly so updates do
# not silently drop it. `tini` makes Ctrl-C / docker stop responsive.
# `curl` is handy for in-container HEALTHCHECK and debugging DNS.
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        tini \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

# Run as a non-root user (docker security best practice).
RUN useradd --create-home --uid 1000 --shell /bin/bash app \
 && chown -R app:app /app
USER app

EXPOSE 8000

# HEALTHCHECK uses curl (added above) — more readable than the urllib snippet.
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD curl --fail --silent --show-error --max-time 3 http://127.0.0.1:8000/livez || exit 1

ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
