FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Persist the SQLite DB outside the container layer
VOLUME ["/data"]
ENV DB_PATH=/data/scanner.db

CMD ["python", "main.py"]
