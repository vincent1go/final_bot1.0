FROM python:3.11-slim

RUN apt-get update && apt-get install -y \
    libreoffice \
    tini \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY . .
RUN pip install --no-cache-dir -r requirements.txt

EXPOSE 10000
ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["python", "main.py"]
