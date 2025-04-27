FROM python:3.9-slim

# Устанавливаем только минимально необходимые пакеты для LibreOffice
RUN apt-get update && apt-get install -y --no-install-recommends \
    libreoffice-writer \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY . .
RUN pip install --no-cache-dir -r requirements.txt

CMD ["python", "main.py"]
