import os
import uuid
import subprocess
import sqlite3
import logging
import asyncio
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
) = range(6)

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

def get_main_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📄 Создать документ", callback_data="select_template")],
        [InlineKeyboardButton("📁 Мои сохранённые", callback_data="view_bookmarks")],
        [InlineKeyboardButton("💼 Вакансии в UK", callback_data="view_vacancies")]
    ])

def get_action_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("⭐ В закладки", callback_data="bookmark"),
            InlineKeyboardButton("📅 Изменить дату", callback_data="change_date")
        ],
        [
            InlineKeyboardButton("📋 К шаблонам", callback_data="select_template"),
            InlineKeyboardButton("🏠 Меню", callback_data="main_menu")
        ]
    ])

async def cleanup_files(*files):
    for file in files:
        if os.path.exists(file):
            try:
                os.remove(file)
                logger.info(f"Удален файл: {file}")
            except Exception as e:
                logger.error(f"Ошибка удаления {file}: {e}")

def replace_client_and_date(doc_path, client_name, date_str, template_key):
    try:
        if not os.path.exists(doc_path):
            raise FileNotFoundError(f"Шаблон {doc_path} не найден")
        
        doc = docx.Document(doc_path)
        
        # Замена имени клиента
        for para in doc.paragraphs:
            if "Client:" in para.text:
                para.text = f"Client: {client_name}"
                break
        
        # Замена даты (учитывает Date:, DATE: и другие варианты)
        for para in doc.paragraphs:
            if any(marker in para.text for marker in ["Date:", "DATE:"]):
                para.text = f"Date: {date_str}"
        
        # Добавление подписи для small_world
        if template_key == "small_world":
            # Добавляем подпись после даты
            for para in doc.paragraphs:
                if "Date:" in para.text:
                    para.add_run().add_picture("signature.png", width=docx.shared.Cm(4))
                    break
        
        temp_path = f"temp_{uuid.uuid4()}.docx"
        doc.save(temp_path)
        return temp_path
    
    except Exception as e:
        logger.error(f"Ошибка обработки документа: {e}")
        raise

def convert_to_pdf(doc_path, client_name):
    try:
        result = subprocess.run(
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
            timeout=60,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        
        temp_pdf = os.path.splitext(doc_path)[0] + ".pdf"
        pdf_path = f"{client_name}.pdf"
        
        if os.path.exists(temp_pdf):
            os.rename(temp_pdf, pdf_path)
            return pdf_path
        raise FileNotFoundError("PDF не создан")
    
    except subprocess.CalledProcessError as e:
        logger.error(f"Ошибка конвертации: {e.stderr.decode()}")
        raise
    except subprocess.TimeoutExpired:
        logger.error("Таймаут конвертации документа")
        raise

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🤖 Добро пожаловать в бота для генерации документов!")
    return await main_menu(update, context)

async def main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = "🏠 *Главное меню*\nВыберите действие:"
    if update.message:
        await update.message.reply_text(text, reply_markup=get_main_keyboard(), parse_mode="Markdown")
    else:
        await update.callback_query.edit_message_text(text, reply_markup=get_main_keyboard(), parse_mode="Markdown")
    return MAIN_MENU

async def select_template(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    keyboard = [
        [InlineKeyboardButton("📝 UR Recruitment", callback_data="ur_recruitment")],
        [InlineKeyboardButton("🌍 Small World", callback_data="small_world")],
        [InlineKeyboardButton("⚡ Imperative", callback_data="imperative")],
    ]
    await query.edit_message_text(
        "📂 Выберите шаблон документа:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return SELECT_TEMPLATE

async def handle_template_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    context.user_data["template_key"] = query.data
    await query.edit_message_text("✏️ Введите имя клиента:")
    return INPUT_NAME

async def generate_document(update, context, new_date=None):
    client_name = update.message.text.strip()
    template_key = context.user_data["template_key"]
    template_path = os.path.join("templates", TEMPLATES[template_key])
    
    kyiv_tz = ZoneInfo("Europe/Kiev")
    date_str = new_date or datetime.now(kyiv_tz).strftime("%Y-%m-%d")
    context.user_data.update({
        "client_name": client_name,
        "date": date_str
    })
    
    try:
        await update.message.reply_text("⏳ Идет генерация документа...")
        
        temp_doc = replace_client_and_date(template_path, client_name, date_str, template_key)
        pdf_path = convert_to_pdf(temp_doc, client_name)
        
        with open(pdf_path, "rb") as f:
            await update.message.reply_document(document=f, filename=f"{client_name}.pdf")
        
        await cleanup_files(temp_doc, pdf_path)
        
        await update.message.reply_text(
            "✅ Документ готов! Выберите действие:",
            reply_markup=get_action_keyboard()
        )
        return CHANGE_DATE
    
    except Exception as e:
        logger.error(f"Ошибка генерации: {e}")
        await update.message.reply_text("❌ Ошибка генерации! Попробуйте снова.")
        return ConversationHandler.END

async def receive_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    return await generate_document(update, context)

async def bookmark(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_data = {
        "user_id": query.from_user.id,
        "client_name": context.user_data["client_name"],
        "template_key": context.user_data["template_key"],
        "date": context.user_data["date"]
    }
    
    try:
        with sqlite3.connect("bookmarks.db") as conn:
            conn.execute(
                "INSERT INTO bookmarks VALUES (?, ?, ?, ?)",
                (user_data["user_id"], user_data["client_name"], 
                 user_data["template_key"], user_data["date"])
            )
        await query.edit_message_text("✅ Документ добавлен в закладки!")
    except Exception as e:
        logger.error(f"Ошибка сохранения: {e}")
        await query.edit_message_text("❌ Ошибка сохранения!")
    
    return CHANGE_DATE

async def change_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("📆 Введите дату в формате ГГГГ-ММ-ДД:")
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
    try:
        user_id = update.effective_user.id
        
        with sqlite3.connect("bookmarks.db") as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT client_name, template_name, date FROM bookmarks WHERE user_id = ?",
                (user_id,)
            )
            bookmarks = cursor.fetchall()
        
        if not bookmarks:
            await update.callback_query.edit_message_text("📭 У вас нет сохранённых документов.")
            return await main_menu(update, context)
        
        keyboard = [
            [InlineKeyboardButton(
                f"📌 {client} ({template}, {date})",
                callback_data=f"bookmark_{client}_{template}_{date}"
            )] for client, template, date in bookmarks
        ]
        keyboard.append([InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu")])
        
        await update.callback_query.edit_message_text(
            "📚 Ваши сохранённые документы:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return VIEW_BOOKMARKS
    
    except Exception as e:
        logger.error(f"Ошибка при просмотре закладок: {e}")
        await update.callback_query.answer("❌ Произошла ошибка!", show_alert=True)
        return await main_menu(update, context)

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Операция отменена.")
    return await main_menu(update, context)

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Ошибка: {context.error}")
    if update and update.callback_query:
        await update.callback_query.answer("❌ Произошла ошибка!", show_alert=True)
    return ConversationHandler.END

def main():
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            MAIN_MENU: [
                CallbackQueryHandler(select_template, pattern="^select_template$"),
                CallbackQueryHandler(view_bookmarks, pattern="^view_bookmarks$"),
            ],
            SELECT_TEMPLATE: [
                CallbackQueryHandler(handle_template_selection, pattern="^(ur_recruitment|small_world|imperative)$")
            ],
            INPUT_NAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_name)
            ],
            CHANGE_DATE: [
                CallbackQueryHandler(bookmark, pattern="^bookmark$"),
                CallbackQueryHandler(change_date, pattern="^change_date$"),
                CallbackQueryHandler(select_template, pattern="^select_template$"),
                CallbackQueryHandler(main_menu, pattern="^main_menu$"),
            ],
            INPUT_NEW_DATE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_new_date)
            ],
            VIEW_BOOKMARKS: [
                CallbackQueryHandler(main_menu, pattern="^main_menu$")
            ]
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    application.add_handler(conv_handler)
    application.add_error_handler(error_handler)
    
    application.run_polling()

if __name__ == "__main__":
    main()
