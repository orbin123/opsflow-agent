FROM python:3.12.13-slim-bookworm@sha256:4766d8b510c428e595d74b9cc5bbb2fae8e26316fffb4adc89908d79aacd58a2

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 \
    OPSFLOW_API_URL=http://127.0.0.1:8000 \
    OPSFLOW_CHATS_DB=/tmp/opsflow-data/chats.sqlite3 \
    OPSFLOW_REMINDERS_DB=/tmp/opsflow-data/reminders.sqlite3 \
    OPSFLOW_TEMPORARY_DEMO=1 \
    OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1

RUN apt-get update && apt-get install -y --no-install-recommends nginx apache2-utils \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 10001 opsflow
WORKDIR /app
COPY requirements.runtime.txt .
RUN pip install --no-cache-dir -r requirements.runtime.txt && pip check
COPY app/ app/
COPY artifacts/models/ artifacts/models/
COPY data/company_faq.json data/company_faq.json
COPY ui/ ui/
COPY .streamlit/config.toml .streamlit/config.toml
COPY docs/user-guide.md docs/user-guide.md
COPY streamlit_app.py .
COPY deploy/ deploy/
USER opsflow
EXPOSE 10000
CMD ["python", "deploy/run_demo.py"]
