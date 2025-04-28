import os
import uuid
import subprocess
import traceback
from datetime import datetime
from zoneinfo import ZoneInfo
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
import sqlite3
import logging
from dateutil.parser import parse

# Настройка логирования
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# Состояния бота
MAIN_MENU, SELECT_TEMPLATE, INPUT_NAME, AFTER_GENERATION, CHANGE_DATE, INPUT_NEW_DATE, VIEW_BOOKMARKS = range(7)

# Настройка базы данных
def init_db():
    conn = sqlite3.connect("bookmarks.db")
    c = conn.cursor()
    c.execute(
        """CREATE TABLE IF NOT EXISTS bookmarks
                 (user_id INTEGER, client_name TEXT, template_name TEXT, date TEXT)"""
    )
    conn.commit()
    conn.close()

# Инициализация базы данных
init_db()

# Сопоставление шаблонов
TEMPLATES = {
    "ur_recruitment": "template_ur.docx",
    "small_world": "template_small_world.docx",
    "imperative": "template_imperative.docx",
}

def replace_client_and_date(doc_path, client_name, date_str, template_key):
    try:
        if not os.path.exists(doc_path):
            raise FileNotFoundError(f"Шаблон {doc_path} не найден")
        
        doc = docx.Document(doc_path)
        
        # Замена Client
        client_replaced = False
        for para in doc.paragraphs:
            if "Client:" in para.text:
                if template_key == "small_world":
                    para.text = f"Client: {client_name}"
                else:
                    para.text = para.text.replace("Client:", f"Client: {client_name}")
                client_replaced = True
                break
        if not client_replaced:
            logger.warning(f"Поле 'Client:' не найдено в {doc_path}")
        
        # Замена Date (дважды на последней странице)
        date_replaced_count = 0
        last_page_paragraphs = []
        current_page = []
        
        for para in doc.paragraphs:
            current_page.append(para)
        last_page_paragraphs = current_page
        
        for para in last_page_paragraphs:
            if ("Date:" in para.text or "DATE:" in para.text) and date_replaced_count < 2:
                para.text = para.text.replace("Date:", f"Date: {date_str}")
                para.text = para.text.replace("DATE:", f"Date: {date_str}")
                date_replaced_count += 1
        if date_replaced_count != 2:
            logger.warning(f"Ожидалось 2 замены даты, выполнено {date_replaced_count} в {doc_path}")
        
        # Сохранение измененного документа
        temp_path = f"temp_{uuid.uuid4()}.docx"
        doc.save(temp_path)
        logger.info(f"Создан временный файл: {temp_path}")
        return temp_path
    except Exception as e:
        logger.error(f"Ошибка при обработке документа {doc_path}: {e}")
        raise

def convert_to_pdf(doc_path, client_name):
    pdf_path = f"{client_name}.pdf"
    try:
        if not os.path.exists(doc_path):
            raise FileNotFoundError(f"Временный файл {doc_path} не найден")
        
        logger.info(f"Запуск конвертации {doc_path} в PDF")
        subprocess.run(
            [
                "libreoffice",
                "--headless",
                "--norestore",
                "--nofirststartwizard",
                "--convert-to",
                "pdf",
                "--outdir",
                os.path.dirname(doc_path) or ".",
                doc_path
            ],
            check=True,
            timeout=30
        )
        temp_pdf = os.path.splitext(doc_path)[0] + ".pdf"
        if not os.path.exists(temp_pdf):
            raise FileNotFoundError(f"PDF-файл {temp_pdf} не создан")
        
        os.rename(temp_pdf, pdf_path)
        logger.info(f"PDF создан: {pdf_path}")
        return pdf_path
    except subprocess.CalledProcessError as e:
        logger.error(f"Ошибка конвертации в PDF: {e}")
        raise
    except FileNotFoundError as e:
        logger.error(f"Файл не найден: {e}")
        raise
    except subprocess.TimeoutExpired:
        logger.error("Превышено время ожидания для конвертации LibreOffice")
        raise
    except Exception as e:
        logger.error(f"Неизвестная ошибка при конвертации: {e}")
        raise

# Главное меню
async def main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("Шаблон", callback_data="select_template")],
        [InlineKeyboardButton("Сохранённые", callback_data="view_bookmarks")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if update.message:
        await update.message.reply_text(
            "Добро пожаловать! Выберите действие:",
            reply_markup=reply_markup
        )
    else:
        await update.callback_query.message.reply_text(
            "Добро пожаловать! Выберите действие:",
            reply_markup=reply_markup
        )
    return MAIN_MENU

# Обработчик команды /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    return await main_menu(update, context)

# Выбор шаблона
async def select_template(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    keyboard = [
        [InlineKeyboardButton("UR Recruitment", callback_data="ur_recruitment")],
        [InlineKeyboardButton("Small World", callback_data="small_world")],
        [InlineKeyboardButton("Imperative", callback_data="imperative")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.message.reply_text(
        "Выберите шаблон:",
        reply_markup=reply_markup
    )
    return SELECT_TEMPLATE

# Обработчик выбора шаблона
async def handle_template_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    template_key = query.data
    context.user_data["template_key"] = template_key
    
    await query.message.reply_text("Введите имя клиента:")
    return INPUT_NAME

# Генерация документа
async def generate_document(update: Update, context: ContextTypes.DEFAULT_TYPE, client_name, template_key, date_str):
    if update.message:
        reply_func = update.message.reply_text
        send_doc_func = update.message.reply_document
    elif update.callback_query:
        reply_func = update.callback_query.message.reply_text
        send_doc_func = update.callback_query.message.reply_document
    else:
        raise ValueError("Update должен содержать message или callback_query")

    template_path = os.path.join("templates", TEMPLATES[template_key])
    
    try:
        await reply_func("Ожидайте, ваш документ генерируется...")
        temp_doc = replace_client_and_date(template_path, client_name, date_str, template_key)
        pdf_path = convert_to_pdf(temp_doc, client_name)
        
        with open(pdf_path, "rb") as f:
            await send_doc_func(document=f, filename=f"{client_name}.pdf")
        
        os.remove(temp_doc)
        os.remove(pdf_path)
        logger.info(f"Временные файлы удалены: {temp_doc}, {pdf_path}")
        
        keyboard = [
            [InlineKeyboardButton("Сохранить", callback_data="bookmark")],
            [InlineKeyboardButton("Изменить дату", callback_data="change_date")],
            [InlineKeyboardButton("К шаблонам", callback_data="select_template")],
            [InlineKeyboardButton("Меню", callback_data="main_menu")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await reply_func(
            "Документ сгенерирован! Что хотите сделать дальше?\n"
            "Или введите имя нового клиента для генерации документа по текущему шаблону.",
            reply_markup=reply_markup
        )
        return AFTER_GENERATION
    except FileNotFoundError as e:
        logger.error(f"Файл не найден: {e}")
        await reply_func("Шаблон или файл не найден. Свяжитесь с поддержкой.")
        return ConversationHandler.END
    except subprocess.CalledProcessError as e:
        logger.error(f"Ошибка конвертации в PDF: {e}")
        await reply_func("Ошибка при создании PDF. Попробуйте снова позже.")
        return ConversationHandler.END
    except Exception as e:
        logger.error(f"Неизвестная ошибка: {e}\nПолный traceback: {traceback.format_exc()}")
        await reply_func("Произошла ошибка. Попробуйте снова или свяжитесь с поддержкой.")
        return ConversationHandler.END

# Обработчик ввода имени клиента
async def receive_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    client_name = update.message.text.strip()
    context.user_data["client_name"] = client_name
    
    template_key = context.user_data["template_key"]
    kyiv_tz = ZoneInfo("Europe/Kiev")
    current_date = datetime.now(kyiv_tz).strftime("%Y-%m-%d")
    context.user_data["date"] = current_date
    
    return await generate_document(update, context, client_name, template_key, current_date)

# Обработчик ввода нового имени клиента после генерации
async def receive_another_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    client_name = update.message.text.strip()
    context.user_data["client_name"] = client_name
    
    template_key = context.user_data["template_key"]
    date = context.user_data["date"]
    
    return await generate_document(update, context, client_name, template_key, date)

# Сохранение в закладки
async def bookmark(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    client_name = context.user_data["client_name"]
    template_key = context.user_data["template_key"]
    date = context.user_data["date"]
    
    try:
        conn = sqlite3.connect("bookmarks.db")
        c = conn.cursor()
        c.execute(
            "INSERT INTO bookmarks (user_id, client_name, template_name, date) VALUES (?, ?, ?, ?)",
            (user_id, client_name, template_key, date)
        )
        conn.commit()
        conn.close()
        await query.message.reply_text("Документ успешно добавлен в закладки!")
    except Exception as e:
        logger.error(f"Ошибка при добавлении закладки: {e}")
        await query.message.reply_text("Ошибка при сохранении закладки. Попробуйте снова.")
    

if __name__ == "__main__":
    main()
    
