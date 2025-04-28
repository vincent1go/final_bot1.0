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
    GENERATE_ANOTHER,
    VIEW_BOOKMARKS,
    VIEW_VACANCIES,
    VIEW_VACANCY_DETAILS
) = range(9)

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

# База данных вакансий
VACANCIES = [
    {
        "id": "vac_1",
        "title": "Сотрудники на завод Coca-Cola",
        "location": "Лондон",
        "salary": "3700-4100£",
        "description": """🔹 *Требуются СОТРУДНИКИ НА ЗАВОД* 🔹
        
🏢 *Компания:* Coca-Cola Europacific Partners
🌍 *Локация:* Великобритания, Лондон
💰 *Зарплата:* 3700-4100£/месяц

📌 *Требования:*
• Мужчины и женщины 18–55 лет
• Ответственность, аккуратность
• Базовый английский — желательно
• Опыт на производстве — плюс

📋 *Обязанности:*
• Работа на линии розлива и упаковки
• Контроль качества продукции
• Упаковка паллет, маркировка
• Поддержание чистоты рабочего места

⏱ *График работы:*
• Смены по 8–12 часов
• 5–6 дней в неделю

🏠 *Проживание:*
• Предоставляется работодателем
• 2–3 человека в комнате"""
    },
    {
        "id": "vac_2",
        "title": "Работники склада Amazon",
        "location": "Манчестер",
        "salary": "3800-4200£",
        "description": """🔹 *Требуются РАБОТНИКИ СКЛАДА* 🔹
        
🏢 *Компания:* Amazon
🌍 *Локация:* Великобритания, Манчестер
💰 *Зарплата:* 3800-4200£/месяц

📌 *Требования:*
• Возраст 18–50 лет
• Физическая выносливость
• Базовый английский приветствуется

📋 *Обязанности:*
• Комплектация и упаковка заказов
• Работа с системой сканирования
• Погрузочно-разгрузочные работы

⏱ *График работы:*
• Смены по 9–11 часов
• 5 дней в неделю

🏠 *Проживание:*
• Компенсация 50% стоимости жилья"""
    },
    # Добавьте остальные вакансии по аналогии
    {
        "id": "vac_3",
        "title": "Операторы станков",
        "location": "Бирмингем",
        "salary": "3900-4300£",
        "description": """🔹 *Требуются ОПЕРАТОРЫ СТАНКОВ* 🔹
        
🏢 *Компания:* MetalWorks Ltd
🌍 *Локация:* Великобритания, Бирмингем
💰 *Зарплата:* 3900-4300£/месяц

📌 *Требования:*
• Мужчины 20–45 лет
• Опыт работы на станках приветствуется
• Обучение на месте

📋 *Обязанности:*
• Работа на станках ЧПУ
• Контроль качества продукции
• Поддержание порядка на рабочем месте

⏱ *График работы:*
• Смены по 8–10 часов
• 5–6 дней в неделю

🏠 *Проживание:*
• Предоставляется общежитие"""
    }
]

# Генерация дополнительных вакансий
for i in range(4, 31):
    cities = ["Лондон", "Манчестер", "Бирмингем", "Ливерпуль", "Глазго", "Шеффилд"]
    positions = ["фасовщики", "грузчики", "упаковщики", "операторы", "комплектовщики", "кладовщики"]
    companies = ["Tesco", "Sainsbury's", "Asda", "Morrisons", "IKEA", "DHL"]
    
    city = random.choice(cities)
    position = random.choice(positions)
    company = random.choice(companies)
    salary_min = random.randint(3700, 3900)
    salary_max = salary_min + random.randint(200, 400)
    hours = random.choice(["8-10", "9-11", "10-12"])
    days = random.choice(["5", "5-6"])
    
    VACANCIES.append({
        "id": f"vac_{i}",
        "title": f"{position.capitalize()} для {company}",
        "location": city,
        "salary": f"{salary_min}-{salary_max}£",
        "description": f"""🔹 *Требуются {position.upper()}* 🔹
        
🏢 *Компания:* {company}
🌍 *Локация:* Великобритания, {city}
💰 *Зарплата:* {salary_min}-{salary_max}£/месяц

📌 *Требования:*
• Возраст 18–50 лет
• Физическая выносливость
• Базовый английский приветствуется

📋 *Обязанности:*
• Работа на производстве/складе
• Соблюдение техники безопасности
• Выполнение рабочих задач

⏱ *График работы:*
• Смены по {hours} часов
• {days} дней в неделю

🏠 *Проживание:*
• {random.choice(['Предоставляется работодателем', 'Компенсация 50%', 'Помощь в поиске жилья'])}"""
    })

def get_main_keyboard():
    """Клавиатура главного меню"""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📄 Создать документ", callback_data="select_template")],
        [InlineKeyboardButton("📁 Мои сохранённые", callback_data="view_bookmarks")],
        [InlineKeyboardButton("💼 Вакансии в UK", callback_data="view_vacancies")]
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
    """Замена данных в шаблоне DOCX с сохранением подписи и печати"""
    try:
        if not os.path.exists(doc_path):
            raise FileNotFoundError(f"Шаблон {doc_path} не найден")
        
        doc = docx.Document(doc_path)
        
        # Замена имени клиента
        client_replaced = False
        for para in doc.paragraphs:
            if "Client:" in para.text:
                if template_key == "small_world":
                    # Для Small World сохраняем оригинальный формат
                    para.text = para.text.replace("Client:", f"Client: {client_name}")
                else:
                    para.text = para.text.replace("Client:", f"Client: {client_name}")
                client_replaced = True
                break
        
        # Замена даты с сохранением подписи и печати
        date_replaced_count = 0
        for para in doc.paragraphs[-6:]:  # Ищем в последних 6 параграфах
            if ("Date:" in para.text or "DATE:" in para.text) and date_replaced_count < 2:
                if template_key == "small_world":
                    # Для Small World сохраняем подпись и печать
                    if "Date:" in para.text:
                        para.text = para.text.replace("Date:", f"Date: {date_str}")
                        # Добавляем отступ для подписи и печати
                        next_para = doc.paragraphs[doc.paragraphs.index(para)+1]
                        next_para.text = "\t\t\t\t\t\t\t___________________\n\t\t\t\t\t\t\tSignature & Stamp"
                elif template_key == "imperative":
                    # Для Imperative заменяем DATE:
                    para.text = para.text.replace("DATE:", f"DATE: {date_str}")
                else:
                    # Для остальных шаблонов стандартная замена
                    para.text = para.text.replace("Date:", f"Date: {date_str}")
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
        await update.callback_query.edit_message_text(text, reply_markup=get_main_keyboard(), parse_mode="Markdown")
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
    await query.edit_message_text(
        "📂 Выберите шаблон документа:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return SELECT_TEMPLATE

async def handle_template_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка выбора шаблона"""
    query = update.callback_query
    await query.answer()
    
    context.user_data["template_key"] = query.data
    await query.edit_message_text("✏️ Введите имя клиента:")
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
        await query.edit_message_text("✅ Документ добавлен в закладки!")
    except Exception as e:
        logger.error(f"Ошибка сохранения: {e}")
        await query.edit_message_text("❌ Ошибка сохранения!")
    
    return CHANGE_DATE

async def change_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Запрос новой даты"""
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("📆 Введите дату в формате ГГГГ-ММ-ДД:")
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
            if update.callback_query:
                await update.callback_query.answer()
                await update.callback_query.edit_message_text("📭 У вас нет сохранённых документов.")
            else:
                await update.message.reply_text("📭 У вас нет сохранённых документов.")
            return await main_menu(update, context)
        
        keyboard = [
            [InlineKeyboardButton(
                f"📌 {client} ({template}, {date})",
                callback_data=f"bookmark_{client}_{template}_{date}"
            )] for client, template, date in bookmarks
        ]
        keyboard.append([InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu")])
        
        if update.callback_query:
            await update.callback_query.answer
