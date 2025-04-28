FROM python:3.11-slim

# Установка LibreOffice и зависимостей для шрифтов и рендеринга
RUN apt-get update && apt-get install -y \
    libreoffice \
    fontconfig \
    libxrender1 \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Создание непривилегированного пользователя
RUN useradd -m -s /bin/bash appuser

# Установка рабочей директории
WORKDIR /app

# Копирование файлов проекта
COPY requirements.txt .
COPY main.py .
COPY templates/ templates/

# Изменение владельца файлов
RUN chown -R appuser:appuser /app

# Переключение на непривилегированного пользователя
USER appuser

# Добавление ~/.local/bin в PATH
ENV PATH="/home/appuser/.local/bin:${PATH}"

# Установка Python-зависимостей
RUN pip install --no-cache-dir --user -r requirements.txt

# Команда для запуска бота
CMD ["python", "main.py"]
