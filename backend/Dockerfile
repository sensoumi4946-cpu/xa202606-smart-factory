FROM python:3.11-slim

WORKDIR /app

COPY shared/ /app/shared/
RUN pip install /app/shared/

COPY backend/ /app/backend/
RUN pip install /app/backend/

CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
