FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY *.py ./
VOLUME ["/data"]
ENV DATA_DIR=/data MESSAGES_FILE=/data/messages.jsonl
CMD ["python", "agent.py", "start"]
