FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    TZ=Australia/Sydney \
    EVOCLAW_PYTHON=/usr/local/bin/python

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends cron ca-certificates tzdata gosu \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /tmp/requirements.txt
RUN pip install -r /tmp/requirements.txt

COPY docker/entrypoint.sh /usr/local/bin/evoclaw-entrypoint
RUN chmod +x /usr/local/bin/evoclaw-entrypoint

COPY . /app

ENTRYPOINT ["evoclaw-entrypoint"]
CMD ["cron"]
