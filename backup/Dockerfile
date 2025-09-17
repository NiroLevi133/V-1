# syntax=docker/dockerfile:1
FROM python:3.11-slim

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# אופציונלי: כלים לקומפילציה אם תצטרך
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# מתקינים תלות
COPY requirements.txt .
RUN pip install -r requirements.txt

# מעתיקים את כל הקוד והנכסים
COPY . .

# Cloud Run ייתן PORT; Streamlit חייב להשתמש בו
ENV PORT=8080

# הפעלה ב-Headless (ללא דפדפן) ובפורט הנכון
CMD streamlit run src/app.py \
  --server.port=$PORT \
  --server.address=0.0.0.0 \
  --server.headless=true \
  --browser.gatherUsageStats=false
