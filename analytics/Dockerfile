FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY shared/ /app/shared/
RUN pip install /app/shared/

COPY analytics/ /app/analytics/
RUN pip install /app/analytics/

CMD ["python", "-m", "analytics.mock.generator"]
