ARG PYTHON_IMAGE=public.ecr.aws/docker/library/python:3.12-slim
FROM ${PYTHON_IMAGE}

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY backend/requirements.txt /tmp/requirements.txt
RUN pip install -r /tmp/requirements.txt

COPY backend/ /app/backend/
RUN mkdir -p /app/uploads /app/backend/storage/uploads

EXPOSE 8000
CMD ["python", "-m", "uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
