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

# Инициализация приложения Telegram
application = Application.builder().token(BOT_TOKEN).build()

# Состояния диалога
(
    MAIN_MENU,
    SELECT_TEMPLATE,
    INPUT_NAME,
    CHANGE_DATE,
    INPUT_NEW_DATE,
    VIEW_BOOKMARKS,
    VIEW_VACANCIES,
    VIEW_VACANCY_DETAILS
) = range(8)

# Инициализация базы данных
def init_db():
    with sqlite3.connect("bookmarks.db") as conn:
        c = conn.cursor()
        c.execute("""CREATE TABLE IF NOT EXISTS bookmarks
                    (id INTEGER PRIMARY KEY AUTOINCREMENT,
                     user_id INTEGER NOT NULL,
                     client_name TEXT NOT NULL,
                     template_name TEXT NOT NULL,
                     date TEXT NOT NULL,
                     created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
        conn.commit()

init_db()

# Шаблоны документов
TEMPLATES = {
    "ur_recruitment": {
        "file": "template_ur.docx",
        "date_format": "Date:"
    },
    "small_world": {
        "file": "template_small_world.docx",
        "date_format": "Date:",
        "signature": True
    },
    "imperative": {
        "file": "template_imperative.docx",
        "date_format": "DATE:"
    }
}

# База данных вакансий (30 примеров)
VACANCIES = [
    {
        "id": f"vac_{i}",
        "title": f"{random.choice(['Работник', 'Оператор', 'Специалист'])} {random.choice(['склада', 'производства', 'цеха'])}",
        "location": random.choice(["Лондон", "Манчестер", "Бирмингем"]),
        "salary": f"{random.randint(3700, 3900)}-{random.randint(4000, 4500)}£",
        "description": f"""🔹 *{random.choice(['Требуются', 'Нужны'])} {random.choice(['работники', 'сотрудники', 'специалисты'])}* 🔹

🏢 *Компания:* {random.choice(['Amazon', 'Tesco', 'Coca-Cola', 'DHL'])}
🌍 *Локация:* Великобритания, {random.choice(['Лондон', 'Манчестер', 'Бирмингем'])}
💰 *Зарплата:* {random.randint(3700, 3900)}-{random.randint(4000, 4500)}£/месяц

📌 *Требования:*
• Возраст 18–50 лет
• Физическая выносливость
• Базовый английский приветствуется

📋 *Обязанности:*
• {random.choice(['Работа на производстве', 'Работа со складскими системами'])}
• Соблюдение техники безопасности
• Выполнение рабочих задач

⏱ *График работы:*
• Смены по {random.choice(['8-10', '9-11', '10-12'])} часов
• {random.choice(['5', '5-6'])} дней в неделю

🏠 *Проживание:*
• {random.choice(['Предоставляется', 'Компенсация 50%', 'Помощь в поиске'])}"""
    } for i in range(1, 31)
]

def get_main_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📄 Создать документ", callback_data="select_template")],
        [InlineKeyboardButton("📁 Мои сохранённые", callback_data="view_bookmarks")],
        [InlineKeyboardButton("💼 Вакансии в UK", callback_data="view_vacancies")]
    ])

def get_action_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⭐ В закладки", callback_data="bookmark")],
        [InlineKeyboardButton("📅 Изменить дату", callback_data="change_date")],
        [InlineKeyboardButton("🔄 Создать ещё", callback_data="select_template")],
        [InlineKeyboardButton("🏠 В меню", callback_data="main_menu")]
    ])

async def cleanup_files(*files):
    for file in files:
        try:
            if file and os.path.exists(file):
                os.remove(file)
                logger.info(f"Удален файл: {file}")
        except Exception as e:
            logger.error(f"Ошибка удаления файла {file}: {e}")

def process_template(doc_path, client_name, date_str, template_key):
    doc = docx.Document(doc_path)
    template_config = TEMPLATES[template_key]
    
    # Замена клиента
    for para in doc.paragraphs:
        if "Client:" in para.text:
            para.text = para.text.replace("Client:", f"Client: {client_name}")
            break
    
    # Замена даты
    date_replaced = False
    for para in doc.paragraphs[-6:]:
        if template_config["date_format"] in para.text:
            para.text = para.text.replace(
                template_config["date_format"], 
                f"{template_config['date_format']} {date_str}"
            )
            
            # Добавление подписи
            if template_config.get("signature"):
                if os.path.exists("signature.png"):
                    para.add_run().add_picture("signature.png", width=Inches(1.5))
                    para.alignment = WD_PARAGRAPH_ALIGNMENT.RIGHT
                else:
                    para.add_run("\t[Подпись и печать]")
            
            date_replaced = True
            break
    
    if not date_replaced:
        raise ValueError("Поле для даты не найдено в шаблоне")
    
    temp_path = f"temp_{uuid.uuid4()}.docx"
    doc.save(temp_path)
    return temp_path

def convert_to_pdf(doc_path, output_name):
    try:
        subprocess.run(
            [
                "libreoffice",
                "--headless",
                "--nofirststartwizard",
                "--convert-to",
                "pdf",
                "--outdir",
                os.path.dirname(doc_path) or ".",
                doc_path
            ],
            check=True,
            timeout=60
        )
        
        temp_pdf = os.path.splitext(doc_path)[0] + ".pdf"
        pdf_path = f"{output_name}.pdf"
        
        if os.path.exists(temp_pdf):
            os.rename(temp_pdf, pdf_path)
            return pdf_path
        raise FileNotFoundError("PDF не создан")
    except Exception as e:
        logger.error(f"Ошибка конвертации: {e}")
        raise

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 Добро пожаловать в бота для генерации документов!",
        reply_markup=get_main_keyboard()
    )
    return MAIN_MENU

async def main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
        await query.edit_message_text(
            "🏠 Главное меню:",
            reply_markup=get_main_keyboard()
        )
    else:
        await update.message.reply_text(
            "🏠 Главное меню:",
            reply_markup=get_main_keyboard()
        )
    return MAIN_MENU

async def select_template(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    keyboard = [
        [InlineKeyboardButton("📝 UR Recruitment", callback_data="ur_recruitment")],
        [InlineKeyboardButton("🌍 Small World", callback_data="small_world")],
        [InlineKeyboardButton("⚡ Imperative", callback_data="imperative")],
        [InlineKeyboardButton("🔙 Назад", callback_data="main_menu")]
    ]
    
    await query.edit_message_text(
        "📂 Выберите шаблон документа:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return SELECT_TEMPLATE

async def handle_template_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    template_key = query.data
    if template_key not in TEMPLATES:
        await query.edit_message_text("❌ Шаблон не найден!")
        return await main_menu(update, context)
    
    context.user_data["template_key"] = template_key
    await query.edit_message_text("✏️ Введите имя клиента:")
    return INPUT_NAME

async def generate_document(update: Update, context: ContextTypes.DEFAULT_TYPE, new_date=None):
    client_name = update.message.text.strip()
    template_key = context.user_data["template_key"]
    template_path = os.path.join("templates", TEMPLATES[template_key]["file"])
    
    kyiv_tz = ZoneInfo("Europe/Kiev")
    date_str = new_date or datetime.now(kyiv_tz).strftime("%Y-%m-%d")
    
    try:
        await update.message.reply_text("⏳ Идет генерация документа...")
        
        temp_doc = process_template(template_path, client_name, date_str, template_key)
        pdf_path = convert_to_pdf(temp_doc, client_name)
        
        with open(pdf_path, "rb") as f:
            await update.message.reply_document(
                document=f,
                caption=f"✅ Документ для {client_name} готов!",
                filename=f"{client_name}.pdf"
            )
        
        await cleanup_files(temp_doc, pdf_path)
        
        context.user_data.update({
            "client_name": client_name,
            "date": date_str
        })
        
        await update.message.reply_text(
            "Выберите действие:",
            reply_markup=get_action_keyboard()
        )
        return CHANGE_DATE
        
    except Exception as e:
        logger.error(f"Ошибка генерации: {e}")
        await update.message.reply_text("❌ Ошибка при создании документа!")
        return await main_menu(update, context)

async def receive_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    return await generate_document(update, context)

async def bookmark(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_data = context.user_data
    try:
        with sqlite3.connect("bookmarks.db") as conn:
            conn.execute(
                "INSERT INTO bookmarks (user_id, client_name, template_name, date) VALUES (?, ?, ?, ?)",
                (query.from_user.id, user_data["client_name"], user_data["template_key"], user_data["date"])
            )
        await query.edit_message_text("✅ Документ добавлен в закладки!")
    except Exception as e:
        logger.error(f"Ошибка сохранения: {e}")
        await query.edit_message_text("❌ Ошибка при сохранении!")
    
    return CHANGE_DATE

async def change_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("📆 Введите новую дату в формате ГГГГ-ММ-ДД:")
    return INPUT_NEW_DATE

async def receive_new_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        parsed_date = parse(update.message.text.strip())
        new_date = parsed_date.strftime("%Y-%m-%d")
        return await generate_document(update, context, new_date)
    except ValueError:
        await update.message.reply_text("❌ Неверный формат даты! Попробуйте снова:")
        return INPUT_NEW_DATE

async def view_bookmarks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    try:
        with sqlite3.connect("bookmarks.db") as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT client_name, template_name, date FROM bookmarks WHERE user_id = ? ORDER BY created_at DESC",
                (user_id,)
            )
            bookmarks = cursor.fetchall()
        
        if not bookmarks:
            await update.message.reply_text("📭 У вас нет сохранённых документов.")
            return await main_menu(update, context)
        
        keyboard = [
            [InlineKeyboardButton(
                f"📌 {client} ({template}, {date})",
                callback_data=f"load_bookmark_{i}"
            )] for i, (client, template, date) in enumerate(bookmarks)
        ]
        keyboard.append([InlineKeyboardButton("🏠 В меню", callback_data="main_menu")])
        
        await update.message.reply_text(
            "📚 Ваши сохранённые документы:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return VIEW_BOOKMARKS
    
    except Exception as e:
        logger.error(f"Ошибка загрузки закладок: {e}")
        await update.message.reply_text("❌ Ошибка при загрузке закладок!")
        return await main_menu(update, context)

async def view_vacancies(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    keyboard = [
        [InlineKeyboardButton(
            f"{vac['title']} | {vac['location']} | {vac['salary']}",
            callback_data=f"vacancy_{vac['id']}"
        )] for vac in VACANCIES[:10]  # Первые 10 вакансий
    ]
    keyboard.append([InlineKeyboardButton("🏠 В меню", callback_data="main_menu")])
    
    await query.edit_message_text(
        "💼 Доступные вакансии в Великобритании:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return VIEW_VACANCIES

async def view_vacancy_details(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    vac_id = query.data.split("_")[1]
    vacancy = next((v for v in VACANCIES if v["id"] == vac_id), None)
    
    if not vacancy:
        await query.edit_message_text("❌ Вакансия не найдена!")
        return await main_menu(update, context)
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔙 Назад к вакансиям", callback_data="view_vacancies")],
        [InlineKeyboardButton("🏠 В меню", callback_data="main_menu")]
    ])
    
    await query.edit_message_text(
        vacancy["description"],
        parse_mode="Markdown",
        reply_markup=keyboard
    )
    return VIEW_VACANCY_DETAILS

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🚫 Операция отменена")
    return await main_menu(update, context)

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Ошибка: {context.error}\n{traceback.format_exc()}")
    if update:
        msg = update.message or update.callback_query.message
        await msg.reply_text("⚠️ Произошла ошибка! Попробуйте снова.")

# Настройка обработчиков
conv_handler = ConversationHandler(
    entry_points=[
        CommandHandler("start", start),
        CommandHandler("menu", main_menu),
        CommandHandler("templates", select_template),
        CommandHandler("bookmarks", view_bookmarks),
        CommandHandler("vacancies", view_vacancies),
        MessageHandler(filters.TEXT & ~filters.COMMAND, main_menu)
    ],
    states={
        MAIN_MENU: [
            CallbackQueryHandler(select_template, pattern="^select_template$"),
            CallbackQueryHandler(view_bookmarks, pattern="^view_bookmarks$"),
            CallbackQueryHandler(view_vacancies, pattern="^view_vacancies$"),
        ],
        SELECT_TEMPLATE: [
            CallbackQueryHandler(handle_template_selection, pattern="^(ur_recruitment|small_world|imperative)$"),
            CallbackQueryHandler(main_menu, pattern="^main_menu$")
        ],
        INPUT_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_name)],
        CHANGE_DATE: [
            CallbackQueryHandler(bookmark, pattern="^bookmark$"),
            CallbackQueryHandler(change_date, pattern="^change_date$"),
            CallbackQueryHandler(select_template, pattern="^select_template$"),
            CallbackQueryHandler(main_menu, pattern="^main_menu$"),
            MessageHandler(filters.TEXT & ~filters.COMMAND, receive_name),
        ],
        INPUT_NEW_DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_new_date)],
        VIEW_BOOKMARKS: [
            CallbackQueryHandler(main_menu, pattern="^main_menu$"),
            MessageHandler(filters.TEXT & ~filters.COMMAND, main_menu)
        ],
        VIEW_VACANCIES: [
            CallbackQueryHandler(view_vacancy_details, pattern="^vacancy_"),
            CallbackQueryHandler(main_menu, pattern="^main_menu$"),
            MessageHandler(filters.TEXT & ~filters.COMMAND, main_menu)
        ],
        VIEW_VACANCY_DETAILS: [
            CallbackQueryHandler(view_vacancies, pattern="^view_vacancies$"),
            CallbackQueryHandler(main_menu, pattern="^main_menu$"),
            MessageHandler(filters.TEXT & ~filters.COMMAND, main_menu)
        ]
    },
    fallbacks=[CommandHandler("cancel", cancel)],
    per_message=True
)

application.add_handler(conv_handler)
application.add_error_handler(error_handler)

# Вебхук
async def webhook_handler(request):
    try:
        update = telegram.Update.de_json(await request.json(), application.bot)
        await application.process_update(update)
        return web.Response(status=200)
    except Exception as e:
        logger.error(f"Ошибка вебхука: {e}")
        return web.Response(status=500)

async def set_webhook():
    webhook_url = f"https://{os.getenv('RENDER_EXTERNAL_HOSTNAME')}/webhook"
    await application.bot.set_webhook(webhook_url)

async def run_server():
    """Запуск сервера с правильной инициализацией"""
    await application.initialize()
    await application.start()
    await set_webhook()
    
    app = web.Application()
    app.router.add_post("/webhook", webhook_handler)
    app.router.add_get("/ping", lambda _: web.Response(text="OK"))
    
    runner = web.AppRunner(app)
    await runner.setup()
    
    port = int(os.getenv("PORT", 10000))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    
    logger.info(f"🚀 Сервер запущен на порту {port}")
    logger.info(f"🤖 Webhook установлен: {await application.bot.get_webhook_info()}")

    # Бесконечный цикл
    while True:
        await asyncio.sleep(3600)

if __name__ == "__main__":
    # Проверка директорий
    required_dirs = ["templates"]
    for directory in required_dirs:
        if not os.path.exists(directory):
            logger.error(f"❌ Отсутствует директория: {directory}!")
            exit(1)
    
    try:
        asyncio.run(run_server())
    except KeyboardInterrupt:
        logger.info("🛑 Бот остановлен")
    except Exception as e:
        logger.critical(f"💥 Критическая ошибка: {e}")
        exit(1)
