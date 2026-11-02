FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY knowledge ./knowledge
COPY main.py ./main.py

CMD ["sh", "-c", "uvicorn main:api --host 0.0.0.0 --port ${PORT}"]
