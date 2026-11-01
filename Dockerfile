FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_DISABLE_PIP_VERSION_CHECK=1 FN_DATABASE_PATH=/data/fieldnotes.db
WORKDIR /app
COPY requirements.lock ./
RUN python -m pip install --no-cache-dir --require-hashes -r requirements.lock
COPY pyproject.toml README.md LICENSE ./
COPY fieldnotes ./fieldnotes
COPY scripts/restore_backup.py ./scripts/restore_backup.py
RUN python -m pip install --no-cache-dir --no-deps . \
    && groupadd --gid 10001 fieldnotes \
    && useradd --uid 10001 --gid fieldnotes --no-create-home fieldnotes \
    && mkdir /data && chown fieldnotes:fieldnotes /data
USER 10001:10001
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health/ready', timeout=3)"
CMD ["fieldnotes", "serve", "--host", "0.0.0.0", "--port", "8000"]
