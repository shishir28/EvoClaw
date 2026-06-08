FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    TZ=Australia/Sydney \
    EVOCLAW_PYTHON=/usr/local/bin/python

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates tzdata iproute2 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /tmp/requirements.txt
RUN pip install -r /tmp/requirements.txt

RUN groupadd -r sandbox && useradd -r -g sandbox sandbox

COPY . /app
RUN chown -R sandbox:sandbox /app

CMD ["tail", "-f", "/dev/null"]
