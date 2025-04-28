FROM python:3.11-slim

# Установка LibreOffice и зависимостей для шрифтов и рендеринга
RUN apt-get update && apt-get install -y \
    libreoffice \
    fontconfig \
    libxrender1 \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Установка рабочей директории
WORKDIR /app

# Копирование файлов проекта
COPY requirements.txt .
COPY main.py .
COPY templates/ templates/

# Обновление pip и установка Python-зависимостей без кэша
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Команда для запуска бота
CMD ["python", "main.py"]
