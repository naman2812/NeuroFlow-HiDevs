FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y tesseract-ocr && rm -rf /var/lib/apt/lists/*
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install mlflow==2.9.2

COPY backend ./backend
COPY pipelines ./pipelines
COPY evaluation ./evaluation

CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
