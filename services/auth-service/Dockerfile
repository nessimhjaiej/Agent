FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Install service-specific dependencies first to leverage Docker layer cache.
COPY services/auth-service/requirements.txt /app/requirements.txt
RUN python -m pip install --no-cache-dir --upgrade pip setuptools wheel \
    && pip install --no-cache-dir --default-timeout=300 --retries 10 -r /app/requirements.txt

# Copy only the auth service runtime code.
COPY services/auth-service /app/services/auth-service

WORKDIR /app/services/auth-service

EXPOSE 8001

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001"]
