FROM python:3.12-slim
# Run as an unprivileged user with its own home (plugins cache models under HOME). /data is the persisted volume.
RUN useradd --system --uid 10004 --create-home --home-dir /home/agent agent \
    && mkdir -p /data && chown agent:agent /data
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY *.py ./
VOLUME ["/data"]
ENV HOME=/home/agent DATA_DIR=/data MESSAGES_FILE=/data/messages.jsonl
USER agent
CMD ["python", "agent.py", "start"]
