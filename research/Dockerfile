FROM python:3.12-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
RUN apt-get update && apt-get install -y --no-install-recommends \
    poppler-utils tesseract-ocr tesseract-ocr-rus tesseract-ocr-eng \
    && rm -rf /var/lib/apt/lists/*
RUN python -m pip install --no-cache-dir pypdf==6.10.0
WORKDIR /app
COPY scripts/export_bank_research.py /app/export_bank_research.py
COPY research/sources.json /app/sources.json
ENTRYPOINT ["python", "/app/export_bank_research.py"]
