# ---- backend build ----
FROM ghcr.io/astral-sh/uv:python3.12-bookworm AS build
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-group dev --no-install-project
COPY app ./app
COPY scripts ./scripts
COPY data ./data

# ---- backend runtime ----
FROM python:3.12-slim-bookworm AS runtime
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /app
COPY --from=build /app/.venv /app/.venv
COPY --from=build /app/app /app/app
COPY --from=build /app/scripts /app/scripts
COPY --from=build /app/data /app/data
ENV PATH="/app/.venv/bin:$PATH"
RUN useradd -m -u 10001 appuser && mkdir -p /data/uploads /data/parsed && chown -R appuser:appuser /data /app
USER appuser
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/health')" || exit 1
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080", "--workers", "2"]
