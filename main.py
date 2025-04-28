import os
import uuid
import traceback
import subprocess
from datetime import datetime
from zoneinfo import ZoneInfo
import docx
from docx.oxml.ns import qn
from docx.text.run import Run
from docx.shared import Inches
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

def set_page_margins(doc, top=1.0, bottom=1.0, left=1.0, right=1.0):
    """Устанавливает поля страницы в дюймах."""
    for section in doc.sections:
        section.top_margin = Inches(top)
        section.bottom_margin = Inches(bottom)
        section.left_margin = Inches(left)
        section.right_margin = Inches(right)
        logger.info(f"Установлены поля страницы: top={top}, bottom={bottom}, left={left}, right={right}")

def replace_text_in_new_paragraph(doc, para, search_text, new_text):
    """Создаёт новый параграф для редактируемого текста и переносит его туда."""
    # Создаём новый параграф
    new_para = doc.add_paragraph()
    
    # Перемещаем новый параграф сразу после текущего
    para_xml = para._element
    doc_xml = para_xml.getparent()
    doc_xml.insert(doc_xml.index(para_xml) + 1, new_para._element)
    
    # Добавляем новый текст в новый параграф
    new_run = new_para.add_run(new_text)
    # Копируем форматирование из первого run текущего параграфа
    if para.runs:
        first_run = para.runs[0]
        new_run.bold = first_run.bold
        new_run.italic = first_run.italic
        new_run.underline = first_run.underline
        new_run.font.size = first_run.font.size
    
    # Удаляем искомый текст из старого параграфа
    for run in para.runs:
        if search_text in run.text:
            run.text = run.text.replace(search_text, "")

def replace_client_and_date(doc_path, client_name, date_str, template_key):
    try:
        if not os.path.exists(doc_path):
            raise FileNotFoundError(f"Шаблон {doc_path} не найден")
        
        doc = docx.Document(doc_path)
        
        # Устанавливаем поля страницы, чтобы гарантировать, что элементы не обрезаются
        set_page_margins(doc, top=0.5, bottom=0.5, left=0.5, right=0.5)
        
        # Замена Client
        client_replaced = False
        for para in doc.paragraphs:
            if "Client:" in para.text:
                # Проверяем, содержит ли параграф только "Client:" (без других символов, кроме пробелов)
                if para.text.replace(" ", "").replace("\t", "") != "Client:":
                    logger.info(f"Client: не в отдельном параграфе в {doc_path}: '{para.text}'")
                    # Создаём новый параграф для Client:
                    replace_text_in_new_paragraph(doc, para, "Client:", f"Client: {client_name}")
                else:
                    # Если Client: уже в отдельном параграфе, заменяем текст
                    new_runs = []
                    for run in para.runs:
                        if "Client:" in run.text:
                            run.text = run.text.replace("Client:", f"Client: {client_name}")
                        new_runs.append(run)
                    para.clear()
                    for run in new_runs:
                        new_run = para.add_run(run.text)
                        new_run.bold = run.bold
                        new_run.italic = run.italic
                        new_run.underline = run.underline
                        new_run.font.size = run.font.size
                client_replaced = True
                break
        if not client_replaced:
            logger.warning(f"Поле 'Client:' не найдено в {doc_path}")
        
        # Замена Date (дважды на последней странице)
        date_replaced_count = 0
        for para in doc.paragraphs:
            if ("Date:" in para.text or "DATE:" in para.text) and date_replaced_count < 2:
                date_field = "Date:" if "Date:" in para.text else "DATE:"
                # Проверяем, содержит ли параграф только "Date:" или "DATE:" (без других символов, кроме пробелов)
                if para.text.replace(" ", "").replace("\t", "") not in ["Date:", "DATE:"]:
                    logger.info(f"Date: не в отдельном параграфе в {doc_path}: '{para.text}'")
                    # Создаём новый параграф для Date:
                    replace_text_in_new_paragraph(doc, para, date_field, f"Date: {date_str}")
                else:
                    # Если Date: уже в отдельном параграфе, заменяем текст
                    new_runs = []
                    has_image = False
                    for run in para.runs:
                        if run._element.xpath('.//w:drawing') or run._element.xpath('.//w:pict'):
                            has_image = True
                            logger.info(f"Найдено изображение в параграфе с Date: {para.text}")
                        if "Date:" in run.text:
                            run.text = run.text.replace("Date:", f"Date: {date_str}")
                        elif "DATE:" in run.text:
                            run.text = run.text.replace("DATE:", f"Date: {date_str}")
                        new_runs.append(run)
                    para.clear()
                    for run in new_runs:
                        new_run = para.add_run(run.text)
                        new_run.bold = run.bold
                        new_run.italic = run.italic
                        new_run.underline = run.underline
                        new_run.font.size = run.font.size
                    if has_image:
                        logger.info(f"Сохранены изображения в параграфе с Date: {para.text}")
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
        # Используем LibreOffice для конвертации
        cmd = [
            "soffice",
            "--headless",
            "--convert-to",
            "pdf",
            "--outdir",
            os.path.dirname(pdf_path),
            doc_path,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        logger.info(f"PDF создан: {pdf_path}\nLibreOffice output: {result.stdout}")
        
        # Проверяем, создан ли PDF
        generated_pdf = os.path.join(os.path.dirname(pdf_path), os.path.basename(doc_path).replace(".docx", ".pdf"))
        if not os.path.exists(generated_pdf):
            raise FileNotFoundError(f"PDF-файл {generated_pdf} не создан")
        
        # Переименовываем файл в нужное имя
        os.rename(generated_pdf, pdf_path)
        return pdf_path
    except subprocess.CalledProcessError as e:
        logger.error(f"Ошибка LibreOffice: {e}\nStderr: {e.stderr}")
        raise
    except Exception as e:
        logger.error(f"Ошибка конвертации в PDF: {e}")
        raise

# Главное меню
async def main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("Создать документ", callback_data="select_template")],
        [InlineKeyboardButton("Мои сохранённые", callback_data="view_bookmarks")],
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
        "Выберите шаблон документа:",
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
        await reply_func("Генерируем ваш документ, пожалуйста, подождите...")
        temp_doc = replace_client_and_date(template_path, client_name, date_str, template_key)
        pdf_path = convert_to_pdf(temp_doc, client_name)
        
        with open(pdf_path, "rb") as f:
            await send_doc_func(document=f, filename=f"{client_name}.pdf")
        
        os.remove(temp_doc)
        os.remove(pdf_path)
        logger.info(f"Временные файлы удалены: {temp_doc}, {pdf_path}")
        
        keyboard = [
            [InlineKeyboardButton("Сохранить документ", callback_data="bookmark")],
            [InlineKeyboardButton("Изменить дату", callback_data="change_date")],
            [InlineKeyboardButton("Другие шаблоны", callback_data="select_template")],
            [InlineKeyboardButton("Главное меню", callback_data="main_menu")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await reply_func(
            "Ваш документ готов! Что хотите сделать дальше?\n"
            "Или введите имя нового клиента для создания другого документа с текущим шаблоном.",
            reply_markup=reply_markup
        )
        return AFTER_GENERATION
    except FileNotFoundError as e:
        logger.error(f"Файл не найден: {e}")
        await reply_func("Ошибка: шаблон не найден. Попробуйте снова или свяжитесь с поддержкой.")
        return ConversationHandler.END
    except Exception as e:
        logger.error(f"Неизвестная ошибка: {e}\nПолный traceback: {traceback.format_exc()}")
        await reply_func("Произошла ошибка при создании документа. Попробуйте снова.")
        return ConversationHandler.END

# Обработчик ввода имени клиента
async def receive_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    client_name = update.message.text.strip()
    if not client_name:
        await update.message.reply_text("Имя клиента не может быть пустым. Пожалуйста, введите имя:")
        return INPUT_NAME
    context.user_data["client_name"] = client_name
    
    template_key = context.user_data["template_key"]
    kyiv_tz = ZoneInfo("Europe/Kiev")
    current_date = datetime.now(kyiv_tz).strftime("%Y-%m-%d")
    context.user_data["date"] = current_date
    
    return await generate_document(update, context, client_name, template_key, current_date)

# Обработчик ввода нового имени клиента после генерации
async def receive_another_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    client_name = update.message.text.strip()
    if not client_name:
        await update.message.reply_text("Имя клиента не может быть пустым. Пожалуйста, введите имя:")
        return AFTER_GENERATION
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
        logger.info(f"Сохранение закладки: user_id={user_id}, client_name={client_name}, template_key={template_key}, date={date}")
        c.execute(
            "INSERT INTO bookmarks (user_id, client_name, template_name, date) VALUES (?, ?, ?, ?)",
            (user_id, client_name, template_key, date)
        )
        conn.commit()
        conn.close()
        await query.message.reply_text("Документ сохранён в закладки!")
    except Exception as e:
        logger.error(f"Ошибка при добавлении закладки: {e}")
        await query.message.reply_text("Не удалось сохранить документ. Попробуйте снова.")
    
    return AFTER_GENERATION

# Изменение даты
async def change_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    await query.message.reply_text("Введите новую дату (например, 2025-04-28, 28.04.2025, 28/04/2025):")
    return INPUT_NEW_DATE

async def receive_new_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    new_date_input = update.message.text.strip()
    try:
        parsed_date = parse(new_date_input)
        new_date = parsed_date.strftime("%Y-%m-%d")
    except ValueError:
        await update.message.reply_text("Неверный формат даты. Используйте, например, 2025-04-28 или 28.04.2025:")
        return INPUT_NEW_DATE
    
    context.user_data["date"] = new_date
    client_name = context.user_data["client_name"]
    template_key = context.user_data["template_key"]
    
    return await generate_document(update, context, client_name, template_key, new_date)

# Просмотр сохранённых документов
async def view_bookmarks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id if update.message else update.callback_query.from_user.id
    try:
        conn = sqlite3.connect("bookmarks.db")
        c = conn.cursor()
        c.execute(
            "SELECT client_name, template_name, date FROM bookmarks WHERE user_id = ?",
            (user_id,)
        )
        bookmarks = c.fetchall()
        conn.close()
        
        if not bookmarks:
            if update.message:
                await update.message.reply_text("У вас нет сохранённых документов.")
            else:
                await update.callback_query.message.reply_text("У вас нет сохранённых документов.")
            return await main_menu(update, context)
        
        logger.info(f"Извлечённые закладки: {bookmarks}")
        keyboard = [
            [
                InlineKeyboardButton(
                    f"{client_name} ({template_name}, {date})",
                    callback_data=f"bookmark_{client_name}_{template_name}_{date}"
                )
            ]
            for client_name, template_name, date in bookmarks
        ]
        keyboard.append([InlineKeyboardButton("Главное меню", callback_data="main_menu")])
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        if update.message:
            await update.message.reply_text(
                "Выберите документ для повторного создания:",
                reply_markup=reply_markup
            )
        else:
            await update.callback_query.message.reply_text(
                "Выберите документ для повторного создания:",
                reply_markup=reply_markup
            )
        return VIEW_BOOKMARKS
    except Exception as e:
        logger.error(f"Ошибка при просмотре закладок: {e}")
        if update.message:
            await update.message.reply_text("Не удалось загрузить сохранённые документы. Попробуйте снова.")
        else:
            await update.callback_query.message.reply_text("Не удалось загрузить сохранённые документы. Попробуйте снова.")
        return await main_menu(update, context)

# Повторная генерация из закладок
async def regenerate_bookmark(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    _, client_name, template_key, date = query.data.split("_", 3)
    logger.info(f"Повторная генерация: client_name={client_name}, template_key={template_key}, date={date}")
    context.user_data["client_name"] = client_name
    context.user_data["template_key"] = template_key
    context.user_data["date"] = date
    
    return await generate_document(update, context, client_name, template_key, date)

# Обработчик команды /ping
async def ping(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Bot is alive!")
    return ConversationHandler.END

# Обработчик команды /help
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = (
        "Как использовать бота:\n"
        "1. Нажмите /start, чтобы начать.\n"
        "2. Выберите 'Создать документ' и выберите шаблон.\n"
        "3. Введите имя клиента.\n"
        "4. После создания документа выберите: сохранить, изменить дату или создать новый.\n"
        "5. В разделе 'Мои сохранённые' можно повторить создание старых документов.\n"
        "Если возникли проблемы, напишите в поддержку!"
    )
    await update.message.reply_text(help_text)
    return await main_menu(update, context)

# Обработчик отмены
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Операция отменена.")
    context.user_data.clear()
    return await main_menu(update, context)

# Обработчик ошибок
async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Update {update} вызвал ошибку: {context.error}\nПолный traceback: {traceback.format_exc()}")
    if update:
        if update.message:
            await update.message.reply_text("Произошла ошибка. Попробуйте снова или свяжитесь с поддержкой.")
        elif update.callback_query:
            await update.callback_query.message.reply_text("Произошла ошибка. Попробуйте снова или свяжитесь с поддержкой.")

def main():
    try:
        application = (
            Application.builder()
            .token("7677140739:AAF52PAthOfODXrHxcjxlar7bTdL86BEYOE")
            .build()
        )
        
        conv_handler = ConversationHandler(
            entry_points=[
                CommandHandler("start", start),
                CommandHandler("ping", ping),
                CommandHandler("help", help_command),
            ],
            states={
                MAIN_MENU: [
                    CallbackQueryHandler(select_template, pattern="select_template"),
                    CallbackQueryHandler(view_bookmarks, pattern="view_bookmarks"),
                    CallbackQueryHandler(main_menu, pattern="main_menu"),
                ],
                SELECT_TEMPLATE: [CallbackQueryHandler(handle_template_selection)],
                INPUT_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_name)],
                AFTER_GENERATION: [
                    CallbackQueryHandler(bookmark, pattern="bookmark"),
                    CallbackQueryHandler(change_date, pattern="change_date"),
                    CallbackQueryHandler(select_template, pattern="select_template"),
                    CallbackQueryHandler(main_menu, pattern="main_menu"),
                    MessageHandler(filters.TEXT & ~filters.COMMAND, receive_another_name),
                ],
                CHANGE_DATE: [CallbackQueryHandler(change_date, pattern="change_date")],
                INPUT_NEW_DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_new_date)],
                VIEW_BOOKMARKS: [
                    CallbackQueryHandler(regenerate_bookmark, pattern="bookmark_.*"),
                    CallbackQueryHandler(main_menu, pattern="main_menu"),
                ],
            },
            fallbacks=[CommandHandler("cancel", cancel)],
            per_message=True,  # Добавляем per_message=True, чтобы устранить предупреждение
        )
        
        application.add_handler(conv_handler)
        application.add_error_handler(error_handler)
        
        if not os.path.exists("templates"):
            logger.error("Директория templates не найдена")
            raise FileNotFoundError("Директория templates не найдена")
        
        logger.info("Запуск приложения с вебхуком")
        application.run_webhook(
            listen="0.0.0.0",
            port=int(os.environ.get("PORT", 8443)),
            url_path="/webhook",
            webhook_url=f"https://{os.environ.get('RENDER_EXTERNAL_HOSTNAME')}/webhook"
        )
    except Exception as e:
        logger.error(f"Ошибка при запуске приложения: {e}\nПолный traceback: {traceback.format_exc()}")
        raise

if __name__ == "__main__":
    main()
