import os
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackQueryHandler, ContextTypes
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from datetime import datetime
import pytz

# Настройка логирования
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# Токен берется из переменной окружения
TOKEN = os.getenv('TOKEN')

# Состояние пользователя
user_data = {}

# Шаблон договора (основные данные)
CONTRACTOR_INFO = """
UR RECRUITMENT LTD
Company number: 14593456
38 Brockhurst Road, Birmingham, England, B36 8JB
https://ur-recruitment.com/
"""

# Функция генерации PDF
def generate_pdf(client_name, date, filename):
    try:
        c = canvas.Canvas(filename, pagesize=letter)
        y = 750  # Начальная позиция Y
        line_height = 20

        # Заголовок
        c.setFont("Helvetica-Bold", 14)
        c.drawString(100, y, "CONTRACT")
        y -= line_height * 2

        # Информация о подрядчике
        c.setFont("Helvetica", 12)
        for line in CONTRACTOR_INFO.split('\n'):
            c.drawString(100, y, line.strip())
            y -= line_height

        # Клиент и дата
        c.drawString(100, y, f"Client: {client_name}")
        y -= line_height
        c.drawString(100, y, f"Date: {date}")
        y -= line_height * 2

        # Основной текст (сокращен для примера)
        c.drawString(100, y, "SUBJECT OF THE AGREEMENT")
        y -= line_height
        c.drawString(100, y, "1.1. Pursuant to this Agreement:")
        # Добавьте полный текст договора по необходимости

        c.save()
        return True
    except Exception as e:
        logger.error(f"Ошибка при генерации PDF: {e}")
        return False

# Стартовая команда
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("Ввести имя клиента", callback_data='input_name')],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        '👋 Привет! Я помогу создать PDF-договор.\nНажми кнопку, чтобы начать!',
        reply_markup=reply_markup
    )

# Обработка кнопок
async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    if query.data == 'input_name':
        await query.edit_message_text('✍️ Введи имя клиента:')
        user_data[user_id] = {'step': 'name'}
    elif query.data == 'set_date':
        kyiv_tz = pytz.timezone('Europe/Kiev')
        current_date = datetime.now(kyiv_tz).strftime("%d.%m.%Y")
        keyboard = [
            [InlineKeyboardButton(f"Сегодня ({current_date})", callback_data='date_today')],
            [InlineKeyboardButton("Выбрать другую дату", callback_data='date_custom')],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text('📅 Выбери дату:', reply_markup=reply_markup)
    elif query.data == 'date_today':
        kyiv_tz = pytz.timezone('Europe/Kiev')
        user_data[user_id]['date'] = datetime.now(kyiv_tz).strftime("%d.%m.%Y")
        await generate_and_send_pdf(query, context, user_id)
    elif query.data == 'date_custom':
        await query.edit_message_text('📅 Введи дату в формате ДД.ММ.ГГГГ (например, 15.10.2023):')
        user_data[user_id]['step'] = 'date'

# Обработка текстовых сообщений
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    text = update.message.text

    if user_id not in user_data or 'step' not in user_data[user_id]:
        await start(update, context)
        return

    step = user_data[user_id]['step']
    try:
        if step == 'name':
            user_data[user_id]['name'] = text
            keyboard = [[InlineKeyboardButton("Выбрать дату", callback_data='set_date')]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text(
                f'✅ Имя клиента: {text}\nТеперь выбери дату:',
                reply_markup=reply_markup
            )
        elif step == 'date':
            # Проверка формата даты
            datetime.strptime(text, "%d.%m.%Y")
            user_data[user_id]['date'] = text
            await generate_and_send_pdf_from_message(update, context, user_id)
    except ValueError:
        await update.message.reply_text('❌ Неверный формат даты! Используй ДД.ММ.ГГГГ (например, 15.10.2023).')
    except Exception as e:
        logger.error(f"Ошибка обработки сообщения: {e}")
        await update.message.reply_text('❌ Произошла ошибка. Попробуй снова.')

# Генерация и отправка PDF из сообщения
async def generate_and_send_pdf_from_message(update, context, user_id):
    client_name = user_data[user_id]['name']
    date = user_data[user_id]['date']
    filename = f"{client_name}.pdf"
    
    if generate_pdf(client_name, date, filename):
        with open(filename, 'rb') as file:
            await update.message.reply_document(file, filename=filename)
        os.remove(filename)
        await restart(update, context, user_id)
    else:
        await update.message.reply_text('❌ Ошибка при создании PDF. Попробуй снова.')

# Генерация и отправка PDF из callback
async def generate_and_send_pdf(query, context, user_id):
    client_name = user_data[user_id]['name']
    date = user_data[user_id]['date']
    filename = f"{client_name}.pdf"
    
    if generate_pdf(client_name, date, filename):
        with open(filename, 'rb') as file:
            await query.message.reply_document(file, filename=filename)
        os.remove(filename)
        await restart_from_callback(query, context, user_id)
    else:
        await query.edit_message_text('❌ Ошибка при создании PDF. Попробуй снова.')

# Перезапуск после генерации
async def restart(update, context, user_id):
    keyboard = [[InlineKeyboardButton("Создать новый PDF", callback_data='input_name')]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text('✅ PDF успешно создан! Хочешь создать еще один?', reply_markup=reply_markup)
    user_data.pop(user_id, None)

async def restart_from_callback(query, context, user_id):
    keyboard = [[InlineKeyboardButton("Создать новый PDF", callback_data='input_name')]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text('✅ PDF успешно создан! Хочешь создать еще один?', reply_markup=reply_markup)
    user_data.pop(user_id, None)

# Обработка ошибок
async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Ошибка: {context.error}")
    if update and hasattr(update, 'message'):
        await update.message.reply_text('❌ Произошла ошибка. Попробуй снова с /start.')

def main():
    try:
        application = Application.builder().token(TOKEN).build()
        application.add_handler(CommandHandler("start", start))
        application.add_handler(CallbackQueryHandler(button))
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
        application.add_error_handler(error_handler)
        application.run_polling(allowed_updates=Update.ALL_TYPES)
    except Exception as e:
        logger.error(f"Критическая ошибка запуска: {e}")

if __name__ == '__main__':
    main()
