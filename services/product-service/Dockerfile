# Build context is services/ (not this directory) so the shared srx_common
# package can be copied in. Build with:
#   docker buildx build --platform linux/arm64 -f product-service/Dockerfile services/
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update \
 && apt-get upgrade -y \
 && rm -rf /var/lib/apt/lists/*

COPY product-service/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY common/srx_common ./srx_common
COPY product-service/app ./app

# Run unprivileged - the task role is the only credential this needs.
RUN useradd --create-home --uid 10001 appuser && chown -R appuser /app
USER appuser

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
