FROM python:3.10-slim-bookworm AS dependencies
ENV PIP_DISABLE_PIP_VERSION_CHECK=1 PIP_NO_CACHE_DIR=1
WORKDIR /build
COPY requirements.txt ./requirements.txt
RUN python -m pip install --prefix=/install -r requirements.txt

FROM python:3.10-slim-bookworm AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \
    NEWS_ANALYTICS_DB=/app/data/news_analytics.sqlite3
RUN apt-get update && apt-get install -y --no-install-recommends \
      ca-certificates curl libasound2 libatk-bridge2.0-0 libatk1.0-0 libatspi2.0-0 \
      libcups2 libdbus-1-3 libdrm2 libgbm1 libglib2.0-0 libgtk-3-0 libnspr4 \
      libnss3 libpango-1.0-0 libx11-6 libx11-xcb1 libxcb1 libxcomposite1 \
      libxdamage1 libxext6 libxfixes3 libxkbcommon0 libxrandr2 libxshmfence1 \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --system app && useradd --system --gid app --home-dir /app app
COPY --from=dependencies /install /usr/local
WORKDIR /app
COPY . /app
RUN python -m playwright install chromium \
    && mkdir -p /app/data /app/.cache \
    && chown -R app:app /app
USER app:app
EXPOSE 5000
CMD ["gunicorn", "--bind=0.0.0.0:5000", "--workers=1", "--timeout=300", "webhook_server:app"]
