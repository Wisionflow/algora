FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY scripts/ scripts/
COPY src/ src/

ENV PYTHONIOENCODING=utf-8
ENV PYTHONUNBUFFERED=1

CMD ["python", "-X", "utf8", "-m", "scripts.scheduler"]
