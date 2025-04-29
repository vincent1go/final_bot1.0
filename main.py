import os
import uuid
import subprocess
import sqlite3
import logging
from datetime import datetime
from zoneinfo import ZoneInfo
from dotenv import load_dotenv
import random

import docx
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

# Загрузка переменных окружения
load_dotenv()

# Проверка токена
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    logging.critical("❌ Токен бота не найден!")
    exit(1)

# Настройка логирования
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Инициализация бота
application = Application.builder().token(BOT_TOKEN).build()

# Состояния диалога
(MAIN_MENU, SELECT_TEMPLATE, INPUT_NAME, CHANGE_DATE, INPUT_NEW_DATE, VIEW_BOOKMARKS) = range(6)

# База данных
def init_db():
    with sqlite3.connect("bookmarks.db") as conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS bookmarks
                       (user_id INTEGER, client_name TEXT, template_name TEXT, date TEXT)""")

init_db()

# Шаблоны
TEMPLATES = {
    "ur_recruitment": "template_ur.docx",
    "small_world": "template_small_world.docx",
    "imperative": "template_imperative.docx",
}

def get_main_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📄 Создать документ", callback_data="select_template")],
        [InlineKeyboardButton("📁 Мои сохранённые", callback_data="view_bookmarks")],
    ])

def replace_client_and_date(doc_path, client_name, date_str, template_key):
    doc = docx.Document(doc_path)
    
    # Замена имени
    for para in doc.paragraphs:
        if "Client:" in para.text or "CLIENT:" in para.text:
            para.text = f"Client: {client_name}"
    
    # Замена даты (все варианты)
    for para in doc.paragraphs:
        if any(marker in para.text for marker in ["Date:", "DATE:"]):
            para.text = f"Date: {date_str}"
            if template_key == "small_world":
                para.add_run().add_picture("signature.png", width=docx.shared.Cm(4))
    
    temp_path = f"temp_{uuid.uuid4()}.docx"
    doc.save(temp_path)
    return temp_path

async def generate_document(update, context, new_date=None):
    client_name = update.message.text.strip()
    template_key = context.user_data["template_key"]
    
    date_str = new_date or datetime.now(ZoneInfo("Europe/Kiev")).strftime("%Y-%m-%d")
    temp_doc = replace_client_and_date(
        f"templates/{TEMPLATES[template_key]}",
        client_name,
        date_str,
        template_key
    )
    
    pdf_path = f"{client_name}.pdf"
    subprocess.run(["libreoffice", "--headless", "--convert-to", "pdf", temp_doc], check=True)
    os.rename(os.path.splitext(temp_doc)[0] + ".pdf", pdf_path)
    
    await update.message.reply_document(document=open(pdf_path, "rb"))
    os.remove(temp_doc)
    os.remove(pdf_path)
    
    await update.message.reply_text(
        "✅ Документ готов!",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("⭐ В закладки", callback_data="bookmark")],
            [InlineKeyboardButton("🏠 Меню", callback_data="main_menu")]
        ])  # Здесь была ошибка - не хватало закрывающей квадратной скобки
    )
    return CHANGE_DATE

# Остальные обработчики остаются без изменений (как в вашем исходном коде)
# ...

if __name__ == "__main__":
    # Webhook для Render
    if os.getenv("RENDER"):
        from aiohttp import web
        
        async def handle(request):
            return web.Response(text="Bot is running")
        
        app = web.Application()
        app.add_routes([web.get('/', handle)])
        
        port = int(os.getenv("PORT", 10000))
        web.run_app(app, port=port)
    else:
        application.run_polling()
