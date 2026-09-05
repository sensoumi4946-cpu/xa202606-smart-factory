FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY shared/ /app/shared/
RUN pip install /app/shared/

COPY semantic-layer/ /app/semantic-layer/
RUN pip install /app/semantic-layer/

COPY analytics/ /app/analytics/
RUN pip install /app/analytics/

COPY backend/ /app/backend/
RUN pip install /app/backend/

CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
