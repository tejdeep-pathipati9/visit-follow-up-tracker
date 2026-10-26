FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    FOLLOWUP_DB_PATH=/data/followups.db

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

RUN groupadd --system tracker \
    && useradd --system --gid tracker tracker \
    && mkdir -p /data \
    && chown tracker:tracker /data

COPY app/ ./app/
COPY data/sample_visits.json ./data/sample_visits.json

USER tracker
EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
