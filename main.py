import os
import uuid
import subprocess
import sqlite3
import logging
from datetime import datetime
from zoneinfo import ZoneInfo
from dotenv import load_dotenv

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
    
    for para in doc.paragraphs:
        if "Client:" in para.text or "CLIENT:" in para.text:
            para.text = f"Client: {client_name}"
    
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
        ])
    )
    return CHANGE_DATE

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Привет! Я бот для генерации документов.",
        reply_markup=get_main_keyboard()
    )
    return MAIN_MENU

async def select_template(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    keyboard = [
        [InlineKeyboardButton("Юридический", callback_data="ur_recruitment")],
        [InlineKeyboardButton("Small World", callback_data="small_world")],
        [InlineKeyboardButton("Императив", callback_data="imperative")],
        [InlineKeyboardButton("Назад", callback_data="main_menu")]
    ]
    
    await query.edit_message_text(
        "📝 Выберите шаблон:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return SELECT_TEMPLATE

async def input_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    template_key = query.data
    context.user_data["template_key"] = template_key
    
    await query.edit_message_text("📝 Введите имя клиента:")
    return INPUT_NAME

async def main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    await query.edit_message_text(
        "Главное меню:",
        reply_markup=get_main_keyboard()
    )
    return MAIN_MENU

# Добавьте остальные обработчики по аналогии

def main():
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            MAIN_MENU: [
                CallbackQueryHandler(select_template, pattern="^select_template$"),
                CallbackQueryHandler(view_bookmarks, pattern="^view_bookmarks$"),
            ],
            SELECT_TEMPLATE: [
                CallbackQueryHandler(input_name, pattern="^(ur_recruitment|small_world|imperative)$"),
                CallbackQueryHandler(main_menu, pattern="^main_menu$"),
            ],
            INPUT_NAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, generate_document),
            ],
        },
        fallbacks=[CommandHandler("start", start)],
    )
    
    application.add_handler(conv_handler)
    
    if os.getenv("RENDER"):
        # Настройка вебхука для Render
        async def webhook(request):
            if request.method == "POST":
                update = Update.de_json(await request.json(), application.bot)
                await application.process_update(update)
                return web.Response()
            return web.Response(status=403)
        
        async def setup_webhook():
            url = f"https://{os.getenv('RENDER_EXTERNAL_HOSTNAME')}/{BOT_TOKEN}"
            await application.bot.set_webhook(url)
        
        from aiohttp import web
        app = web.Application()
        app.add_routes([web.post(f"/{BOT_TOKEN}", webhook)])
        
        port = int(os.getenv("PORT", 10000))
        web.run_app(app, port=port, handle_signals=True)
    else:
        # Локальный запуск с поллингом
        application.run_polling()

if __name__ == "__main__":
    main()
