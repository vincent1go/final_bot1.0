FROM python:3.11-slim

RUN apt-get update && apt-get install -y \
    libreoffice \
    tini \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["python", "main.py"]  # Убедитесь что main.py - правильное имя файла
