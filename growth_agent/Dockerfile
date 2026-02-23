FROM python:3.12-slim

WORKDIR /app

# Install dependencies first (layer cache)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source
COPY src/ ./src/
COPY scripts/ ./scripts/

# Telethon session file persists via volume
VOLUME ["/app/sessions"]

ENV TG_SESSION_NAME=/app/sessions/growth_agent
ENV PYTHONUNBUFFERED=1

CMD ["python", "-m", "scripts.run_agent"]
