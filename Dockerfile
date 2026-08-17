FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
COPY constraints.txt .
RUN pip install --no-cache-dir -r requirements.txt -c constraints.txt

RUN addgroup --system bot && adduser --system --ingroup bot bot

COPY alembic.ini .
COPY migrations ./migrations
COPY app ./app

USER bot

CMD ["python3", "-m", "app.main"]
