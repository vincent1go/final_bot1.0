import os
import uuid
import subprocess
import sqlite3
import logging
import asyncio
import traceback
from datetime import datetime
from zoneinfo import ZoneInfo
from dotenv import load_dotenv

import docx
import telegram
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
    CallbackQueryHandler,
)
from dateutil.parser import parse
from aiohttp import web

# Загрузка переменных окружения
load_dotenv()

# Проверка обязательных переменных
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    logging.critical("❌ Токен бота не найден! Проверьте переменную окружения BOT_TOKEN")
    exit(1)

# Настройка логирования
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Состояния диалога
(
    MAIN_MENU,
    SELECT_TEMPLATE,
    INPUT_NAME,
    CHANGE_DATE,
    INPUT_NEW_DATE,
    GENERATЕ_ANOTHER,
    VIEW_BOOKMARKS
) = range(7)

# Инициализация базы данных
def init_db():
    with sqlite3.connect("bookmarks.db") as conn:
        c = conn.cursor()
        c.execute("""CREATE TABLE IF NOT EXISTS bookmarks
                    (user_id INTEGER, 
                     client_name TEXT, 
                     template_name TEXT, 
                     date TEXT)""")
        conn.commit()

init_db()

# Шаблоны документов
TEMPLATES = {
    "ur_recruitment": "template_ur.docx",
    "small_world": "template_small_world.docx",
    "imperative": "template_imperative.docx",
}

# ... (все остальные функции остаются без изменений из предыдущего варианта) ...

async def run_server():
    """Запуск сервера с правильной инициализацией"""
    try:
        # Инициализация PTB
        await application.initialize()
        await application.start()
        
        # Настройка веб-сервера
        app = web.Application()
        app.router.add_post("/webhook", webhook_handler)
        app.router.add_get("/ping", lambda _: web.Response(text="OK"))
        
        runner = web.AppRunner(app)
        await runner.setup()
        
        port = int(os.getenv("PORT", 10000))  # Для Render используйте 10000
        site = web.TCPSite(runner, "0.0.0.0", port)
        
        await site.start()
        logger.info(f"🚀 Сервер запущен на порту {port}")

        # Бесконечный цикл
        while True:
            await asyncio.sleep(3600)
            
    except Exception as e:
        logger.error(f"🔥 Ошибка запуска: {e}")
        raise
    finally:
        logger.info("🛑 Завершение работы...")
        await site.stop()
        await runner.cleanup()
        await application.stop()
        await application.shutdown()

if __name__ == "__main__":
    # Проверка обязательных директорий
    required_dirs = ["templates"]
    for directory in required_dirs:
        if not os.path.exists(directory):
            logger.error(f"📂 Отсутствует директория: {directory}!")
            exit(1)
    
    try:
        asyncio.run(run_server())
    except KeyboardInterrupt:
        logger.info("🛑 Бот остановлен")
    except Exception as e:
        logger.critical(f"💥 Критическая ошибка: {e}")
        exit(1)
