# Multi-stage, non-root, minimal image for the Task Manager API.
# BASE_IMAGE defaults to the official image; the offline lab build overrides it (see ansible/roles/images).
ARG BASE_IMAGE=python:3.12-slim

FROM ${BASE_IMAGE} AS builder
ARG PIP_INSTALL_ARGS=""
WORKDIR /build
COPY requirements.txt .
COPY vendor/ /vendor/
RUN python3 -m venv /venv && \
    /venv/bin/pip install --no-cache-dir ${PIP_INSTALL_ARGS} -r requirements.txt

FROM ${BASE_IMAGE}
ARG APP_VERSION=1.0.0
LABEL org.opencontainers.image.title="taskapi" \
      org.opencontainers.image.source="https://github.com/masterjod/devops-capstone" \
      org.opencontainers.image.version="${APP_VERSION}"
ENV PATH="/venv/bin:$PATH" PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 APP_VERSION=${APP_VERSION}
RUN groupadd --system --gid 10001 app && useradd --system --uid 10001 --gid app --no-create-home app
COPY --from=builder /venv /venv
WORKDIR /srv
COPY app/ ./app/
USER 10001
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=3s CMD python3 -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8000/healthz')" || exit 1
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "1", "--threads", "8", "app.main:app"]
