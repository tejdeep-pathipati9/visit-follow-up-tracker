FROM node:24-slim AS ui-build
WORKDIR /ui
COPY ui/package.json ui/package-lock.json ./
RUN npm ci
COPY ui/ ./
RUN npm run build

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
COPY config/ ./config/
COPY --from=ui-build /ui/dist ./ui/dist
COPY data/sample_visits.json ./data/sample_visits.json
COPY scripts/table_generate.py ./scripts/table_generate.py
COPY scripts/create_manager.py ./scripts/create_manager.py
COPY scripts/generate_synthetic_data.py ./scripts/generate_synthetic_data.py
COPY scripts/import_data.py ./scripts/import_data.py
COPY scripts/delete_old_records.py ./scripts/delete_old_records.py
COPY scripts/backup_db.py ./scripts/backup_db.py

USER tracker
EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
