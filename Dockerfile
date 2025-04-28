FROM python:3.11-slim

# Установка LibreOffice и зависимостей
RUN apt-get update && apt-get install -y \
    libreoffice \
    && rm -rf /var/lib/apt/lists/*

# Установка рабочей директории
WORKDIR /app

# Копирование файлов проекта
COPY requirements.txt .
COPY main.py .
COPY templates/ templates/

# Установка Python-зависимостей
RUN pip install --no-cache-dir -r requirements.txt

# Команда для запуска бота
CMD ["python", "main.py"]
