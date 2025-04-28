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
        "description": """Требуются СОТРУДНИКИ НА ЗАВОД
в международную компанию Coca-Cola Europacific Partners, Великобритания 🇬🇧
Город: Лондон 🏙️

Зарплата:
От 3700 до 4100£/месяц 
Выплаты еженедельно или каждые 2 недели 

Требования:
• Мужчины и женщины 18–55 лет 👨‍🔧👩‍🔧
• Ответственность, аккуратность 
• Базовый английский — желательно, но не обязательно 🇬🇧
• Опыт на производстве — плюс, но не обязателен 

Обязанности:
• Работа на линии розлива и упаковки напитков 
• Контроль качества бутылок и упаковки 
• Упаковка паллет, маркировка 📦
• Поддержание чистоты рабочего места 
• Работа в современном автоматизированном цеху 

График работы:
• Смены по 8–12 часов ⏱️
• 5–6 дней в неделю 

Проживание:
• Предоставляется работодателем 
• 2–3 человека в комнате, жильё рядом с работой"""
    },
    {
        "id": "vac_2",
        "title": "Работники склада Amazon",
        "location": "Манчестер",
        "salary": "3800-4200£",
        "description": """Требуются РАБОТНИКИ СКЛАДА
в компанию Amazon, Великобритания 🇬🇧
Город: Манчестер 🏙️

Зарплата:
От 3800 до 4200£/месяц 

Требования:
• Возраст 18–50 лет
• Физическая выносливость
• Базовый английский приветствуется

Обязанности:
• Комплектация и упаковка заказов
• Работа с системой сканирования
• Погрузочно-разгрузочные работы

График:
• Смены по 9–11 часов
• 5 дней в неделю

Проживание:
• Компенсация 50% стоимости жилья"""
    },
    # Добавьте остальные 28 вакансий по аналогии
    {
        "id": "vac_3",
        "title": "Операторы станков",
        "location": "Бирмингем",
        "salary": "3900-4300£",
        "description": """Требуются ОПЕРАТОРЫ СТАНКОВ
на металлообрабатывающее производство, Великобритания 🇬🇧
Город: Бирмингем 🏙️

Зарплата:
3900-4300£/месяц

Требования:
• Мужчины 20–45 лет
• Опыт работы на станках приветствуется
• Обучение на месте

Обязанности:
• Работа на станках ЧПУ
• Контроль качества продукции
• Поддержание порядка на рабочем месте

График:
• Смены по 8–10 часов
• 5–6 дней в неделю

Проживание:
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
    
    VACANCIES.append({
        "id": f"vac_{i}",
        "title": f"{position.capitalize()} для {company}",
        "location": city,
        "salary": f"{salary_min}-{salary_max}£",
        "description": f"""Требуются {position.upper()}
в компанию {company}, Великобритания 🇬🇧
Город: {city} 🏙️

Зарплата:
{salary_min}-{salary_max}£/месяц

Требования:
• Возраст 18–50 лет
• Физическая выносливость
• Базовый английский приветствуется

Обязанности:
• Работа на производстве/складе
• Соблюдение техники безопасности
• Выполнение рабочих задач

График:
• Смены по {random.choice(['8-10', '9-11', '10-12'])} часов
• {random.choice(['5', '5-6'])} дней в неделю

Проживание:
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
            await update.callback_query.answer()
            await update.callback_query.edit_message_text(
                "📚 Ваши сохранённые документы:",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        else:
            await update.message.reply_text(
                "📚 Ваши сохранённые документы:",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        return VIEW_BOOKMARKS
    
    except Exception as e:
        logger.error(f"Ошибка загрузки: {e}")
        if update.callback_query:
            await update.callback_query.answer()
            await update.callback_query.edit_message_text("❌ Ошибка загрузки!")
        else:
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
        await query.edit_message_text("⏳ Восстанавливаю документ...")
        
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
        await query.edit_message_text("❌ Ошибка восстановления!")
        return await main_menu(update, context)

async def view_vacancies(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Просмотр списка вакансий"""
    query = update.callback_query
    await query.answer()
    
    # Разбиваем вакансии на страницы по 5 штук
    page = context.user_data.get("vacancy_page", 0)
    start_idx = page * 5
    end_idx = start_idx + 5
    current_vacancies = VACANCIES[start_idx:end_idx]
    
    keyboard = []
    for vacancy in current_vacancies:
        keyboard.append([
            InlineKeyboardButton(
                f"{vacancy['title']} | {vacancy['location']} | {vacancy['salary']}",
                callback_data=f"vacancy_{vacancy['id']}"
            )
        ])
    
    # Добавляем кнопки навигации
    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton("⬅️ Назад", callback_data="vac_prev_page"))
    if end_idx < len(VACANCIES):
        nav_buttons.append(InlineKeyboardButton("Вперед ➡️", callback_data="vac_next_page"))
    
    if nav_buttons:
        keyboard.append(nav_buttons)
    
    keyboard.append([InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu")])
    
    await query.edit_message_text(
        "💼 *Доступные вакансии в Великобритании*\n\n"
        "Выберите вакансию для просмотра подробной информации:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )
    return VIEW_VACANCIES

async def handle_vacancy_pagination(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка перелистывания страниц вакансий"""
    query = update.callback_query
    await query.answer()
    
    if query.data == "vac_prev_page":
        context.user_data["vacancy_page"] = context.user_data.get("vacancy_page", 0) - 1
    elif query.data == "vac_next_page":
        context.user_data["vacancy_page"] = context.user_data.get("vacancy_page", 0) + 1
    
    return await view_vacancies(update, context)

async def view_vacancy_details(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Просмотр деталей вакансии"""
    query = update.callback_query
    await query.answer()
    
    vacancy_id = query.data.split("_")[1]
    vacancy = next((v for v in VACANCIES if v["id"] == vacancy_id), None)
    
    if not vacancy:
        await query.edit_message_text("❌ Вакансия не найдена!")
        return await main_menu(update, context)
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔙 Назад к вакансиям", callback_data="view_vacancies")],
        [InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu")]
    ])
    
    await query.edit_message_text(
        vacancy["description"],
        reply_markup=keyboard
    )
    return VIEW_VACANCY_DETAILS

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

# Настройка диалогов
conv_handler = ConversationHandler(
    entry_points=[
        CommandHandler("start", start),
        CommandHandler("menu", main_menu),
        CommandHandler("templates", select_template),
        CommandHandler("bookmarks", view_bookmarks),
        CommandHandler("vacancies", view_vacancies),
        MessageHandler(filters.Text(["меню", "menu"]), main_menu),
        MessageHandler(filters.Text(["шаблоны", "templates"]), select_template),
        MessageHandler(filters.Text(["закладки", "bookmarks"]), view_bookmarks),
        MessageHandler(filters.Text(["вакансии", "vacancies"]), view_vacancies),
    ],
    states={
        MAIN_MENU: [
            CallbackQueryHandler(select_template, pattern="select_template"),
            CallbackQueryHandler(view_bookmarks, pattern="view_bookmarks"),
            CallbackQueryHandler(view_vacancies, pattern="view_vacancies"),
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
        VIEW_VACANCIES: [
            CallbackQueryHandler(view_vacancy_details, pattern="vacancy_.*"),
            CallbackQueryHandler(handle_vacancy_pagination, pattern="vac_(prev|next)_page"),
            CallbackQueryHandler(main_menu, pattern="main_menu"),
        ],
        VIEW_VACANCY_DETAILS: [
            CallbackQueryHandler(view_vacancies, pattern="view_vacancies"),
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
    """Запуск сервера с правильной инициализацией"""
    runner = None
    site = None
    
    try:
        # Инициализация PTB
        await application.initialize()
        await application.start()
        
        # Настройка веб-сервера
        app = web.Application()
        app.router.add_post("/webhook", webhook_handler)
        app.router.add_get("/ping", lambda _: web.Response(text="OK"))
        
        runner = web.AppRunner(app)
        await runner.setup()
        
        port = int(os.getenv("PORT", 10000))
        site = web.TCPSite(runner, "0.0.0.0", port)
        
        await site.start()
        logger.info(f"🚀 Сервер запущен на порту {port}")

        # Бесконечный цикл
        while True:
            await asyncio.sleep(3600)
            
    except Exception as e:
        logger.error(f"🔥 Ошибка запуска: {e}")
        raise
    finally:
        logger.info("🛑 Завершение работы...")
        if site:
            await site.stop()
        if runner:
            await runner.cleanup()
        if application:
            await application.stop()
            await application.shutdown()

if __name__ == "__main__":
    # Проверка обязательных директорий
    required_dirs = ["templates"]
    for directory in required_dirs:
        if not os.path.exists(directory):
            logger.error(f"📂 Отсутствует директория: {directory}!")
            exit(1)
    
    try:
        asyncio.run(run_server())
    except KeyboardInterrupt:
        logger.info("🛑 Бот остановлен")
    except Exception as e:
        logger.critical(f"💥 Критическая ошибка: {e}")
        exit(1)
