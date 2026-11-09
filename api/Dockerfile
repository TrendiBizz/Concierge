FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    FASTEMBED_CACHE_PATH=/opt/fastembed

WORKDIR /srv

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Bake the (free, local) embedding model into the image so the first request is fast
# and the container does not need to download anything at runtime.
RUN python -c "from fastembed import TextEmbedding; TextEmbedding(model_name='BAAI/bge-small-en-v1.5')"

COPY app ./app
COPY static ./static

# COPY keeps the host file modes. A source file that is 600 on the host (for example an
# empty __init__.py) would be unreadable by the unprivileged user below, so normalize.
RUN chmod -R a+rX /srv/app /srv/static

RUN useradd --system --uid 10001 app && chown -R app /opt/fastembed
USER app

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
