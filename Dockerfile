FROM python:3.11-slim

# Установка системных зависимостей
RUN apt-get update && apt-get install -y \
    libreoffice \
    tini \
    && rm -rf /var/lib/apt/lists/*

# Настройка рабочей директории
WORKDIR /app
COPY . .

# Установка Python зависимостей
RUN pip install --no-cache-dir -r requirements.txt

# Использование tini как init-процесса
ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["python", "main.py"]

# Экспорт порта
EXPOSE 10000
