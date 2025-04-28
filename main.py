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
    logging.critical("Токен бота не найден! Проверьте переменную окружения BOT_TOKEN")
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
    GENERATE_ANOTHER,
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

def get_main_keyboard():
    """Клавиатура главного меню"""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📄 Создать документ", callback_data="select_template")],
        [InlineKeyboardButton("📁 Мои сохранённые", callback_data="view_bookmarks")]
    ])

def get_action_keyboard():
    """Клавиатура после генерации документа"""
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
    """Удаление временных файлов"""
    for file in files:
        if os.path.exists(file):
            try:
                os.remove(file)
                logger.info(f"Удален файл: {file}")
            except Exception as e:
                logger.error(f"Ошибка удаления {file}: {e}")

def replace_client_and_date(doc_path, client_name, date_str, template_key):
    """Замена данных в шаблоне DOCX"""
    try:
        if not os.path.exists(doc_path):
            raise FileNotFoundError(f"Шаблон {doc_path} не найден")
        
        doc = docx.Document(doc_path)
        
        # Замена имени клиента
        client_replaced = False
        for para in doc.paragraphs:
            if "Client:" in para.text:
                if template_key == "small_world":
                    para.text = f"Client: {client_name}"
                else:
                    para.text = para.text.replace("Client:", f"Client: {client_name}")
                client_replaced = True
                break
        
        # Замена даты
        date_replaced_count = 0
        for para in doc.paragraphs[-4:]:
            if ("Date:" in para.text or "DATE:" in para.text) and date_replaced_count < 2:
                para.text = para.text.replace("Date:", f"Date: {date_str}")
                para.text = para.text.replace("DATE:", f"Date: {date_str}")
                date_replaced_count += 1
        
        # Сохранение временного файла
        temp_path = f"temp_{uuid.uuid4()}.docx"
        doc.save(temp_path)
        return temp_path
    
    except Exception as e:
        logger.error(f"Ошибка обработки документа: {e}")
        raise

def convert_to_pdf(doc_path, client_name):
    """Конвертация DOCX в PDF"""
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
        pdf_path = f"{client_name}.pdf"
        
        if os.path.exists(temp_pdf):
            os.rename(temp_pdf, pdf_path)
            return pdf_path
        raise FileNotFoundError("PDF не создан")
    
    except subprocess.CalledProcessError as e:
        logger.error(f"Ошибка конвертации: {e}")
        raise

async def main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Главное меню"""
    text = "🏠 *Главное меню*\nВыберите действие:"
    if update.message:
        await update.message.reply_text(text, reply_markup=get_main_keyboard(), parse_mode="Markdown")
    else:
        await update.callback_query.message.reply_text(text, reply_markup=get_main_keyboard(), parse_mode="Markdown")
    return MAIN_MENU

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start"""
    await update.message.reply_text("🤖 Добро пожаловать в бота для генерации документов!")
    return await main_menu(update, context)

async def select_template(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Выбор шаблона"""
    query = update.callback_query
    await query.answer()
    
    keyboard = [
        [InlineKeyboardButton("📝 UR Recruitment", callback_data="ur_recruitment")],
        [InlineKeyboardButton("🌍 Small World", callback_data="small_world")],
        [InlineKeyboardButton("⚡ Imperative", callback_data="imperative")],
    ]
    await query.message.reply_text(
        "📂 Выберите шаблон документа:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return SELECT_TEMPLATE

async def handle_template_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка выбора шаблона"""
    query = update.callback_query
    await query.answer()
    
    context.user_data["template_key"] = query.data
    await query.message.reply_text("✏️ Введите имя клиента:")
    return INPUT_NAME

async def generate_document(update, context, new_date=None):
    """Основная логика генерации документа"""
    client_name = update.message.text.strip()
    template_key = context.user_data["template_key"]
    template_path = os.path.join("templates", TEMPLATES[template_key])
    
    # Установка даты
    kyiv_tz = ZoneInfo("Europe/Kiev")
    date_str = new_date or datetime.now(kyiv_tz).strftime("%Y-%m-%d")
    context.user_data.update({
        "client_name": client_name,
        "date": date_str
    })
    
    try:
        await update.message.reply_text("⏳ Идет генерация документа...")
        
        # Генерация и конвертация
        temp_doc = replace_client_and_date(template_path, client_name, date_str, template_key)
        pdf_path = convert_to_pdf(temp_doc, client_name)
        
        # Отправка файла
        with open(pdf_path, "rb") as f:
            await update.message.reply_document(document=f, filename=f"{client_name}.pdf")
        
        # Очистка
        await cleanup_files(temp_doc, pdf_path)
        
        # Ответ с клавиатурой
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
    """Обработка имени клиента"""
    return await generate_document(update, context)

async def bookmark(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Добавление в закладки"""
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
        await query.message.reply_text("✅ Документ добавлен в закладки!")
    except Exception as e:
        logger.error(f"Ошибка сохранения: {e}")
        await query.message.reply_text("❌ Ошибка сохранения!")
    
    return CHANGE_DATE

async def change_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Запрос новой даты"""
    query = update.callback_query
    await query.answer()
    await query.message.reply_text("📆 Введите дату в формате ГГГГ-ММ-ДД:")
    return INPUT_NEW_DATE

async def receive_new_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка новой даты"""
    try:
        parsed_date = parse(update.message.text.strip())
        new_date = parsed_date.strftime("%Y-%m-%d")
        return await generate_document(update, context, new_date)
    except ValueError:
        await update.message.reply_text("❌ Неверный формат даты! Попробуйте снова:")
        return INPUT_NEW_DATE

async def view_bookmarks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Просмотр закладок"""
    user_id = update.effective_user.id
    try:
        with sqlite3.connect("bookmarks.db") as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT client_name, template_name, date FROM bookmarks WHERE user_id = ?",
                (user_id,)
            )
            bookmarks = cursor.fetchall()
        
        if not bookmarks:
            await update.message.reply_text("📭 У вас нет сохранённых документов.")
            return await main_menu(update, context)
        
        keyboard = [
            [InlineKeyboardButton(
                f"📌 {client} ({template}, {date})",
                callback_data=f"bookmark_{client}_{template}_{date}"
            )] for client, template, date in bookmarks
        ]
        keyboard.append([InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu")])
        
        await update.message.reply_text(
            "📚 Ваши сохранённые документы:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return VIEW_BOOKMARKS
    
    except Exception as e:
        logger.error(f"Ошибка загрузки: {e}")
        await update.message.reply_text("❌ Ошибка загрузки!")
        return await main_menu(update, context)

async def regenerate_bookmark(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Повторная генерация из закладок"""
    try:
        query = update.callback_query
        await query.answer()
        
        parts = query.data.split("_", 3)
        if len(parts) != 4:
            raise ValueError("Неверный формат данных закладки")
            
        _, client, template, date = parts
        context.user_data.update({
            "client_name": client,
            "template_key": template,
            "date": date
        })
        
        template_path = os.path.join("templates", TEMPLATES[template])
        await query.message.reply_text("⏳ Восстанавливаю документ...")
        
        temp_doc = replace_client_and_date(template_path, client, date, template)
        pdf_path = convert_to_pdf(temp_doc, client)
        
        with open(pdf_path, "rb") as f:
            await query.message.reply_document(document=f, filename=f"{client}.pdf")
        
        await cleanup_files(temp_doc, pdf_path)
        await query.message.reply_text(
            "✅ Документ восстановлен!",
            reply_markup=get_action_keyboard()
        )
        return CHANGE_DATE
    
    except Exception as e:
        logger.error(f"Ошибка восстановления: {e}")
        await query.message.reply_text("❌ Ошибка восстановления!")
        return await main_menu(update, context)

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отмена операции"""
    await update.message.reply_text("🚫 Операция отменена")
    context.user_data.clear()
    return await main_menu(update, context)

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик ошибок"""
    logger.error(f"Ошибка: {context.error}\n{traceback.format_exc()}")
    if update:
        msg = update.message or update.callback_query.message
        await msg.reply_text("⚠️ Произошла ошибка! Попробуйте снова.")

# Настройка приложения
application = Application.builder().token(BOT_TOKEN).build()

# Настройка диалогов
conv_handler = ConversationHandler(
    entry_points=[
        CommandHandler("start", start),
        CommandHandler("menu", main_menu),
        CommandHandler("templates", select_template),
        CommandHandler("bookmarks", view_bookmarks),
        MessageHandler(filters.Text(["меню", "menu"]), main_menu),
        MessageHandler(filters.Text(["шаблоны", "templates"]), select_template),
        MessageHandler(filters.Text(["закладки", "bookmarks"]), view_bookmarks),
    ],
    states={
        MAIN_MENU: [
            CallbackQueryHandler(select_template, pattern="select_template"),
            CallbackQueryHandler(view_bookmarks, pattern="view_bookmarks"),
        ],
        SELECT_TEMPLATE: [CallbackQueryHandler(handle_template_selection)],
        INPUT_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_name)],
        CHANGE_DATE: [
            CallbackQueryHandler(bookmark, pattern="bookmark"),
            CallbackQueryHandler(change_date, pattern="change_date"),
            CallbackQueryHandler(select_template, pattern="select_template"),
            CallbackQueryHandler(main_menu, pattern="main_menu"),
            MessageHandler(filters.TEXT & ~filters.COMMAND, receive_name),
        ],
        INPUT_NEW_DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_new_date)],
        VIEW_BOOKMARKS: [
            CallbackQueryHandler(regenerate_bookmark, pattern="bookmark_.*"),
            CallbackQueryHandler(main_menu, pattern="main_menu"),
        ],
    },
    fallbacks=[CommandHandler("cancel", cancel)],
    per_message=False
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

async def run_server():
    """Запуск сервера"""
    app = web.Application()
    app.router.add_post("/webhook", webhook_handler)
    app.router.add_get("/ping", lambda _: web.Response(text="OK"))
    
    runner = web.AppRunner(app)
    await runner.setup()
    
    port = int(os.getenv("PORT", 8443))
    site = web.TCPSite(runner, "0.0.0.0", port)
    
    await site.start()
    logger.info(f"Сервер запущен на порту {port}")
    
    while True:
        await asyncio.sleep(3600)

if __name__ == "__main__":
    # Проверка обязательных директорий
    required_dirs = ["templates"]
    for directory in required_dirs:
        if not os.path.exists(directory):
            logger.error(f"Отсутствует обязательная директория: {directory}!")
            exit(1)
    
    try:
        asyncio.run(run_server())
    except KeyboardInterrupt:
        logger.info("Бот остановлен")
    except Exception as e:
        logger.critical(f"Критическая ошибка: {e}")
        exit(1)
