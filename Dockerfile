FROM python:3.11-slim

WORKDIR /app

# Cài pymssql dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    freetds-dev freetds-bin gcc && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 5000

CMD ["gunicorn", "-w", "1", "-b", "0.0.0.0:5000", "wsgi:app"]