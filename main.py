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
import random
from docx.shared import Inches
from docx.enum.text import WD_PARAGRAPH_ALIGNMENT

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

# Инициализация
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    logging.critical("❌ Токен бота не найден!")
    exit(1)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Состояния
STATES = range(8)

# Инициализация базы данных
def init_db():
    with sqlite3.connect("bookmarks.db") as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS bookmarks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                client_name TEXT NOT NULL,
                template_name TEXT NOT NULL,
                date TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

init_db()

# Шаблоны
TEMPLATES = {
    "ur_recruitment": {"file": "template_ur.docx", "date_format": "Date:"},
    "small_world": {"file": "template_small_world.docx", "date_format": "Date:", "signature": True},
    "imperative": {"file": "template_imperative.docx", "date_format": "DATE:"}
}

# Вакансии (30 примеров)
VACANCIES = [
    {
        "id": f"vac_{i}",
        "title": f"{random.choice(['Работник', 'Оператор'])} {random.choice(['склада', 'цеха'])}",
        "location": random.choice(["Лондон", "Манчестер"]),
        "salary": f"{random.randint(3700, 4500)}£",
        "description": f"Описание вакансии {i}"
    } for i in range(1, 31)
]

# Клавиатуры
def get_main_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📄 Создать документ", callback_data="select_template")],
        [InlineKeyboardButton("📁 Мои сохранённые", callback_data="view_bookmarks")],
        [InlineKeyboardButton("💼 Вакансии в UK", callback_data="view_vacancies")]
    ])

def get_action_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⭐ В закладки", callback_data="bookmark")],
        [InlineKeyboardButton("🔄 Создать ещё", callback_data="select_template")],
        [InlineKeyboardButton("🏠 В меню", callback_data="main_menu")]
    ])

# Основные функции
async def cleanup_files(*files):
    for file in files:
        try:
            if file and os.path.exists(file):
                os.remove(file)
        except Exception as e:
            logger.error(f"Ошибка удаления файла: {e}")

def process_template(doc_path, client_name, date_str, template_key):
    doc = docx.Document(doc_path)
    config = TEMPLATES[template_key]
    
    for para in doc.paragraphs:
        if "Client:" in para.text:
            para.text = f"Client: {client_name}"
            break
    
    for para in doc.paragraphs[-6:]:
        if config["date_format"] in para.text:
            para.text = f"{config['date_format']} {date_str}"
            if config.get("signature"):
                para.add_run("\t[Подпись]")
            break
    
    temp_path = f"temp_{uuid.uuid4()}.docx"
    doc.save(temp_path)
    return temp_path

def convert_to_pdf(doc_path, output_name):
    try:
        subprocess.run([
            "libreoffice", "--headless", "--convert-to", "pdf",
            "--outdir", os.path.dirname(doc_path) or ".", doc_path
        ], check=True, timeout=60)
        
        pdf_path = f"{output_name}.pdf"
        os.rename(os.path.splitext(doc_path)[0] + ".pdf", pdf_path)
        return pdf_path
    except Exception as e:
        logger.error(f"Ошибка конвертации: {e}")
        raise

# Обработчики команд
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 Добро пожаловать в бота для генерации документов!",
        reply_markup=get_main_kb()
    )
    return 0

async def main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.edit_message_text("🏠 Главное меню:", reply_markup=get_main_kb())
    else:
        await update.message.reply_text("🏠 Главное меню:", reply_markup=get_main_kb())
    return 0

async def select_template(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton(n, callback_data=k)]
        for k, n in [("ur_recruitment", "📝 UR Recruitment"), 
                    ("small_world", "🌍 Small World"),
                    ("imperative", "⚡ Imperative")]
    ]
    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="main_menu")])
    
    await update.callback_query.edit_message_text(
        "📂 Выберите шаблон:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return 1

async def handle_template(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    template_key = query.data
    
    if template_key not in TEMPLATES:
        await query.answer("❌ Шаблон не найден!")
        return await main_menu(update, context)
    
    context.user_data["template"] = template_key
    await query.edit_message_text("✏️ Введите имя клиента:")
    return 2

async def generate_doc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    client = update.message.text.strip()
    template = context.user_data["template"]
    date = datetime.now(ZoneInfo("Europe/Kiev")).strftime("%Y-%m-%d")
    
    try:
        await update.message.reply_text("⏳ Генерация документа...")
        
        doc_path = os.path.join("templates", TEMPLATES[template]["file"])
        temp_doc = process_template(doc_path, client, date, template)
        pdf_path = convert_to_pdf(temp_doc, client)
        
        with open(pdf_path, "rb") as f:
            await update.message.reply_document(
                f,
                caption=f"✅ Документ для {client} готов!",
                filename=f"{client}.pdf"
            )
        
        await cleanup_files(temp_doc, pdf_path)
        await update.message.reply_text("Выберите действие:", reply_markup=get_action_kb())
        
        context.user_data["client"] = client
        context.user_data["date"] = date
        return 3
        
    except Exception as e:
        logger.error(f"Ошибка: {e}")
        await update.message.reply_text("❌ Ошибка генерации!")
        return await main_menu(update, context)

async def bookmark_doc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.callback_query.from_user.id
    data = context.user_data
    
    try:
        with sqlite3.connect("bookmarks.db") as conn:
            conn.execute(
                "INSERT INTO bookmarks (user_id, client_name, template_name, date) VALUES (?, ?, ?, ?)",
                (user, data["client"], data["template"], data["date"])
            )
        await update.callback_query.answer("✅ Добавлено в закладки!")
    except Exception as e:
        logger.error(f"Ошибка БД: {e}")
        await update.callback_query.answer("❌ Ошибка сохранения!")
    
    return 3

# Вебхук и запуск
async def webhook_handler(request):
    try:
        update = telegram.Update.de_json(await request.json(), application.bot)
        await application.process_update(update)
        return web.Response()
    except Exception as e:
        logger.error(f"Webhook error: {e}")
        return web.Response(status=500)

async def set_webhook():
    url = f"https://{os.getenv('RENDER_EXTERNAL_HOSTNAME')}/webhook"
    await application.bot.set_webhook(url)

async def run():
    await application.initialize()
    await application.start()
    await set_webhook()
    
    app = web.Application()
    app.router.add_post("/webhook", webhook_handler)
    app.router.add_get("/ping", lambda _: web.Response(text="OK"))
    
    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", int(os.getenv("PORT", 10000))).start()
    
    logger.info("🚀 Бот запущен")
    while True:
        await asyncio.sleep(3600)

# Настройка обработчиков
if __name__ == "__main__":
    application = Application.builder().token(BOT_TOKEN).build()
    
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            0: [
                CallbackQueryHandler(select_template, pattern="^select_template$"),
                CallbackQueryHandler(lambda u,c: main_menu(u,c), pattern="^main_menu$")
            ],
            1: [
                CallbackQueryHandler(handle_template, pattern="^(ur_recruitment|small_world|imperative)$"),
                CallbackQueryHandler(main_menu, pattern="^main_menu$")
            ],
            2: [MessageHandler(filters.TEXT & ~filters.COMMAND, generate_doc)],
            3: [
                CallbackQueryHandler(bookmark_doc, pattern="^bookmark$"),
                CallbackQueryHandler(select_template, pattern="^select_template$"),
                CallbackQueryHandler(main_menu, pattern="^main_menu$")
            ]
        },
        fallbacks=[CommandHandler("cancel", lambda u,c: main_menu(u,c))]
    )
    
    application.add_handler(conv_handler)
    application.add_error_handler(lambda u,c: logger.error(f"Error: {c.error}"))
    
    try:
        asyncio.run(run())
    except (KeyboardInterrupt, SystemExit):
        logger.info("🛑 Бот остановлен")
    except Exception as e:
        logger.critical(f"💥 Ошибка: {e}")
