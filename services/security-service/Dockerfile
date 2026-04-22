FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY services/security-service/requirements.txt /app/requirements.txt
RUN python -m pip install --no-cache-dir --upgrade pip setuptools wheel \
    && pip install --no-cache-dir --default-timeout=300 --retries 10 -r /app/requirements.txt

COPY services/security-service /app/services/security-service

WORKDIR /app/services/security-service

EXPOSE 8007

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8007"]

