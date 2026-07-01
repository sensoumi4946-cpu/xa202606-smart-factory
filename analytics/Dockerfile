FROM python:3.11-slim

WORKDIR /app

COPY shared/ /app/shared/
RUN pip install /app/shared/

COPY analytics/ /app/analytics/
RUN pip install /app/analytics/

ENTRYPOINT ["python", "-m", "analytics.mock.generator"]
