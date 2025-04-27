import os
import sqlite3
import subprocess
import tempfile
import shutil
from datetime import datetime
import pytz
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Updater, CommandHandler, CallbackQueryHandler, MessageHandler,
    Filters, ConversationHandler, CallbackContext
)
from docx import Document
from flask import Flask, request
import logging

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Flask-приложение для вебхуков
app = Flask(__name__)

# Глобальные переменные
updater = None
dispatcher = None

# Токен бота и вебхук
TOKEN = os.environ.get('BOT_TOKEN', '7511704960:AAFKDWgg2-cAzRxywX1gXK47OQRWJi72qGw')
WEBHOOK_URL = os.environ.get('WEBHOOK_URL', 'https://final-bot1-0.onrender.com/webhook')

# Состояния диалога
SELECT_TEMPLATE, INPUT_NAME, CHOOSE_DATE, INPUT_CUSTOM_DATE, ASK_SAVE = range(5)

# Часовой пояс Киева
kiev_tz = pytz.timezone('Europe/Kiev')

# Соответствие шаблонов
TEMPLATE_FILES = {
    'template_imperative': 'templates/template_imperative.docx',
    'template_ur': 'templates/template_ur.docx',
    'template_small_world': 'templates/template_small_world.docx',
}

# Все твои функции (замены текста, генерация документов, обработка команд /generate, /start, выбор шаблона, ввод имени и даты) остались без изменений

# -- ВАЖНАЯ ВСТАВКА: обработка вебхука --

@app.route('/webhook', methods=['POST'])
def webhook():
    """Обработка входящих обновлений Telegram."""
    global dispatcher
    try:
        update_data = request.get_json(force=True)
        logger.info(f"Received update: {update_data}")
        update = Update.de_json(update_data, updater.bot)
        if update and dispatcher:
            dispatcher.process_update(update)
            logger.info("Update processed successfully")
        else:
            logger.error("Failed to parse update or dispatcher not initialized")
        return 'OK'
    except Exception as e:
        logger.error(f"Webhook error: {str(e)}")
        return 'OK', 200

# -- Пинг эндпоинт для UptimeRobot --

@app.route('/ping')
def ping():
    logger.info("Received ping request")
    return 'OK'

# -- Основная функция запуска --

def main():
    """Основная функция для запуска бота."""
    logger.info("Starting bot...")

    # Инициализация базы данных
    conn = sqlite3.connect('database.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS saved_documents
                 (id INTEGER PRIMARY KEY, user_id INTEGER, template TEXT, client_name TEXT, date TEXT)''')
    conn.commit()
    conn.close()
    logger.info("Database initialized")

    # Проверка наличия шаблонов
    try:
        check_templates()
    except FileNotFoundError as e:
        logger.error(f"Template check failed: {str(e)}")
        exit(1)

    # Настройка бота
    global updater, dispatcher
    updater = Updater(token=TOKEN, use_context=True)
    dispatcher = updater.dispatcher
    logger.info("Updater and dispatcher initialized")

    # Регистрация всех handlers
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('generate', start_generate)],
        states={
            SELECT_TEMPLATE: [CallbackQueryHandler(template_selected)],
            INPUT_NAME: [MessageHandler(Filters.text & ~Filters.command, name_input)],
            CHOOSE_DATE: [CallbackQueryHandler(date_chosen)],
            INPUT_CUSTOM_DATE: [MessageHandler(Filters.text & ~Filters.command, input_custom_date)],
            ASK_SAVE: [CallbackQueryHandler(save_decision)],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
        per_message=True
    )

    dispatcher.add_handler(CommandHandler('start', start))
    dispatcher.add_handler(conv_handler)
    dispatcher.add_handler(CommandHandler('list_saved', list_saved))
    logger.info("Handlers registered")

    # Установка вебхука
    try:
        updater.bot.set_webhook(url=WEBHOOK_URL)
        logger.info(f"Webhook set to {WEBHOOK_URL}")
    except Exception as e:
        logger.error(f"Failed to set webhook: {str(e)}")
        exit(1)

    # Запуск Flask
    port = int(os.environ.get('PORT', 5000))
    logger.info(f"Starting Flask on port {port}")
    app.run(host='0.0.0.0', port=port)

if __name__ == '__main__':
    main()

