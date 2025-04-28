FROM python:3.11-slim

# Установка системных зависимостей
RUN apt-get update && apt-get install -y \
    libreoffice \
    tini \
    libxml2 \
    libxslt1.1 \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

# Настройка рабочей директории
WORKDIR /app

# Копирование зависимостей сначала для кэширования
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копирование остальных файлов
COPY . .

# Использование tini как init-процесса
ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["python", "main.py"]

# Экспорт порта
EXPOSE 10000
