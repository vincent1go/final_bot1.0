import os
import uuid
import subprocess
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

# Настройка логирования
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# Состояния бота
INPUT_NAME, SELECT_TEMPLATE, CHANGE_DATE, INPUT_NEW_DATE, VIEW_BOOKMARKS = range(5)

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

def replace_client_and_date(doc_path, client_name, date_str):
    doc = docx.Document(doc_path)
    
    # Замена Client
    for para in doc.paragraphs:
        if "Client:" in para.text:
            para.text = para.text.replace("Client:", f"Client: {client_name}")
            break
    
    # Замена Date
    for para in doc.paragraphs:
        if "Date:" in para.text:
            para.text = para.text.replace("Date:", f"Date: {date_str}")
        if "DATE:" in para.text:
            para.text = para.text.replace("DATE:", f"Date: {date_str}")
    
    # Сохранение измененного документа
    temp_path = f"temp_{uuid.uuid4()}.docx"
    doc.save(temp_path)
    return temp_path

def convert_to_pdf(doc_path, client_name):
    pdf_path = f"{client_name}.pdf"
    try:
        # Вызов libreoffice для конвертации
        subprocess.run(
            [
                "libreoffice",
                "--headless",
                "--convert-to",
                "pdf",
                "--outdir",
                os.path.dirname(doc_path),
                doc_path
            ],
            check=True
        )
        # Переименование файла
        temp_pdf = os.path.splitext(doc_path)[0] + ".pdf"
        os.rename(temp_pdf, pdf_path)
        return pdf_path
    except subprocess.CalledProcessError as e:
        logger.error(f"Ошибка конвертации в PDF: {e}")
        raise
    except FileNotFoundError:
        logger.error("LibreOffice не найден в системе")
        raise

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Добро пожаловать! Введите имя клиента:"
    )
    return INPUT_NAME

async def receive_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    client_name = update.message.text.strip()
    context.user_data["client_name"] = client_name
    
    keyboard = [
        [InlineKeyboardButton("UR Recruitment", callback_data="ur_recruitment")],
        [InlineKeyboardButton("Small World", callback_data="small_world")],
        [InlineKeyboardButton("Imperative", callback_data="imperative")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        f"Принято! Имя клиента: {client_name}\nВыберите шаблон:",
        reply_markup=reply_markup
    )
    return SELECT_TEMPLATE

async def select_template(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    template_key = query.data
    context.user_data["template_key"] = template_key
    
    client_name = context.user_data["client_name"]
    template_path = os.path.join("templates", TEMPLATES[template_key])
    
    # Получение текущей даты в Киеве
    kyiv_tz = ZoneInfo("Europe/Kiev")
    current_date = datetime.now(kyiv_tz).strftime("%Y-%m-%d")
    context.user_data["date"] = current_date
    
    # Обработка документа
    temp_doc = replace_client_and_date(template_path, client_name, current_date)
    pdf_path = convert_to_pdf(temp_doc, client_name)
    
    # Отправка PDF
    with open(pdf_path, "rb") as f:
        await query.message.reply_document(document=f, filename=f"{client_name}.pdf")
    
    # Очистка временных файлов
    os.remove(temp_doc)
    os.remove(pdf_path)
    
    # Предложение добавить в закладки или изменить дату
    keyboard = [
        [InlineKeyboardButton("Добавить в закладки", callback_data="bookmark")],
        [InlineKeyboardButton("Изменить дату", callback_data="change_date")],
        [InlineKeyboardButton("Начать заново", callback_data="start_over")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.message.reply_text(
        "Документ сгенерирован! Что хотите сделать дальше?",
        reply_markup=reply_markup
    )
    return CHANGE_DATE

async def bookmark(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    client_name = context.user_data["client_name"]
    template_key = context.user_data["template_key"]
    date = context.user_data["date"]
    
    conn = sqlite3.connect("bookmarks.db")
    c = conn.cursor()
    c.execute(
        "INSERT INTO bookmarks (user_id, client_name, template_name, date) VALUES (?, ?, ?, ?)",
        (user_id, client_name, template_key, date)
    )
    conn.commit()
    conn.close()
    
    await query.message.reply_text("Документ успешно добавлен в закладки!")
    return CHANGE_DATE

async def change_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    await query.message.reply_text("Введите новую дату (ГГГГ-ММ-ДД):")
    return INPUT_NEW_DATE

async def receive_new_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    new_date = update.message.text.strip()
    try:
        datetime.strptime(new_date, "%Y-%m-%d")
    except ValueError:
        await update.message.reply_text("Неверный формат даты. Используйте ГГГГ-ММ-ДД:")
        return INPUT_NEW_DATE
    
    context.user_data["date"] = new_date
    client_name = context.user_data["client_name"]
    template_key = context.user_data["template_key"]
    template_path = os.path.join("templates", TEMPLATES[template_key])
    
    # Обработка документа с новой датой
    temp_doc = replace_client_and_date(template_path, client_name, new_date)
    pdf_path = convert_to_pdf(temp_doc, client_name)
    
    # Отправка PDF
    with open(pdf_path, "rb") as f:
        await update.message.reply_document(document=f, filename=f"{client_name}.pdf")
    
    # Очистка временных файлов
    os.remove(temp_doc)
    os.remove(pdf_path)
    
    # Предложение вариантов
    keyboard = [
        [InlineKeyboardButton("Добавить в закладки", callback_data="bookmark")],
        [InlineKeyboardButton("Изменить дату снова", callback_data="change_date")],
        [InlineKeyboardButton("Начать заново", callback_data="start_over")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "Документ обновлен с новой датой! Что хотите сделать дальше?",
        reply_markup=reply_markup
    )
    return CHANGE_DATE

async def start_over(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    context.user_data.clear()
    await query.message.reply_text("Введите имя клиента:")
    return INPUT_NAME

async def view_bookmarks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    conn = sqlite3.connect("bookmarks.db")
    c = conn.cursor()
    c.execute(
        "SELECT client_name, template_name, date FROM bookmarks WHERE user_id = ?",
        (user_id,)
    )
    bookmarks = c.fetchall()
    conn.close()
    
    if not bookmarks:
        await update.message.reply_text("У вас нет сохраненных закладок.")
        return ConversationHandler.END
    
    keyboard = [
        [
            InlineKeyboardButton(
                f"{client_name} ({template_name}, {date})",
                callback_data=f"bookmark_{client_name}_{template_name}_{date}"
            )
        ]
        for client_name, template_name, date in bookmarks
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "Выберите сохраненный документ для повторной генерации:",
        reply_markup=reply_markup
    )
    return VIEW_BOOKMARKS

async def regenerate_bookmark(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    _, client_name, template_key, date = query.data.split("_", 3)
    context.user_data["client_name"] = client_name
    context.user_data["template_key"] = template_key
    context.user_data["date"] = date
    
    template_path = os.path.join("templates", TEMPLATES[template_key])
    temp_doc = replace_client_and_date(template_path, client_name, date)
    pdf_path = convert_to_pdf(temp_doc, client_name)
    
    # Отправка PDF
    with open(pdf_path, "rb") as f:
        await query.message.reply_document(document=f, filename=f"{client_name}.pdf")
    
    # Очистка временных файлов
    os.remove(temp_doc)
    os.remove(pdf_path)
    
    # Предложение вариантов
    keyboard = [
        [InlineKeyboardButton("Добавить в закладки", callback_data="bookmark")],
        [InlineKeyboardButton("Изменить дату", callback_data="change_date")],
        [InlineKeyboardButton("Начать заново", callback_data="start_over")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.message.reply_text(
        "Документ повторно сгенерирован! Что хотите сделать дальше?",
        reply_markup=reply_markup
    )
    return CHANGE_DATE

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Операция отменена.")
    context.user_data.clear()
    return ConversationHandler.END

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Update {update} caused error {context.error}")
    if update and update.message:
        await update.message.reply_text("Произошла ошибка. Пожалуйста, попробуйте снова.")

def main():
    application = (
        Application.builder()
        .token("7677140739:AAF52PAthOfODXrHxcjxlar7bTdL86BEYOE")
        .build()
    )
    
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start), CommandHandler("bookmarks", view_bookmarks)],
        states={
            INPUT_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_name)],
            SELECT_TEMPLATE: [CallbackQueryHandler(select_template)],
            CHANGE_DATE: [
                CallbackQueryHandler(bookmark, pattern="bookmark"),
                CallbackQueryHandler(change_date, pattern="change_date"),
                CallbackQueryHandler(start_over, pattern="start_over"),
            ],
            INPUT_NEW_DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_new_date)],
            VIEW_BOOKMARKS: [CallbackQueryHandler(regenerate_bookmark, pattern="bookmark_.*")],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    
    application.add_handler(conv_handler)
    application.add_error_handler(error_handler)
    
    # Запуск бота с вебхуком
    application.run_webhook(
        listen="0.0.0.0",
        port=int(os.environ.get("PORT", 8443)),
        url_path="/webhook",
        webhook_url=f"https://{os.environ.get('RENDER_EXTERNAL_HOSTNAME')}/webhook"
    )

if __name__ == "__main__":
    main()

if __name__ == "__main__":
    main()
