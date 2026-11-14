FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=3000

WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install .

EXPOSE 3000

# Asks from inside the container, so it also passes when HOST binds loopback only.
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import os,urllib.request as u; u.urlopen('http://127.0.0.1:%s/health' % os.environ.get('PORT','3000'), timeout=4)"

CMD ["python", "-m", "demo_app"]
