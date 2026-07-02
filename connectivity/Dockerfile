FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY shared/ /app/shared/
RUN pip install /app/shared/

COPY connectivity/ /app/connectivity/
RUN pip install /app/connectivity/

CMD ["python", "-m", "connectivity.runner"]
