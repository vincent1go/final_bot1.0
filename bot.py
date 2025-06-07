import os
import logging
from aiogram import Bot, Dispatcher, types, executor
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
from datetime import datetime
import pytz
from pdfrw import PdfReader, PdfWriter

logging.basicConfig(level=logging.INFO)

API_TOKEN = os.getenv('BOT_TOKEN')
if not API_TOKEN:
    raise RuntimeError("BOT_TOKEN не найден в переменных окружения")

bot = Bot(token=API_TOKEN)
dp = Dispatcher(bot)

# Путь к шаблону PDF (загрузите на Render рядом с ботом)
PDF_TEMPLATE_PATH = 'template.pdf'

# Ключи состояний для хранения данных между сообщениями
USER_DATA = {}

# Функция для замены текста в PDF контенте страницы (очень упрощенный пример)
def replace_text_in_pdf(input_path, output_path, client_name, date_str):
    pdf = PdfReader(input_path)
    # Первая страница - меняем Client:
    page1 = pdf.pages[0]
    content1 = page1.Contents.stream
    # Заменим "Client:" на "Client: {client_name}"
    # Предположим, что в шаблоне "Client:" в точности так написано
    content1 = content1.replace(b'Client:', f'Client: {client_name}'.encode('utf-8'))
    page1.Contents.stream = content1

    # Пятая страница (индекс 4) - меняем два раза дату
    page5 = pdf.pages[4]
    content5 = page5.Contents.stream
    # Заменяем все вхождения "Date: 20.05.2025" на "Date: {date_str}"
    content5 = content5.replace(b'Date: 20.05.2025', f'Date: {date_str}'.encode('utf-8'))
    page5.Contents.stream = content5

    PdfWriter(output_path, trailer=pdf).write()

# Хэндлер /start
@dp.message_handler(commands=['start'])
async def start_handler(message: types.Message):
    await message.answer(
        "Привет! Введите имя клиента, чтобы получить PDF с заполненным шаблоном."
    )

# Принимаем имя клиента
@dp.message_handler(lambda message: message.text and message.text.strip() != '')
async def client_name_handler(message: types.Message):
    client_name = message.text.strip()
    USER_DATA[message.from_user.id] = {'client_name': client_name}

    # Получаем текущую дату по Киеву
    tz = pytz.timezone('Europe/Kiev')
    now = datetime.now(tz)
    date_str = now.strftime('%d.%m.%Y')
    USER_DATA[message.from_user.id]['date'] = date_str

    # Спрашиваем пользователя, менять ли дату
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    keyboard.add(KeyboardButton('Использовать текущую дату'))
    keyboard.add(KeyboardButton('Ввести дату вручную'))

    await message.answer(
        f"Имя клиента: {client_name}\n"
        f"Дата по умолчанию: {date_str}\n"
        f"Хотите использовать эту дату или ввести свою?",
        reply_markup=keyboard
    )

# Обработка ответа на выбор даты
@dp.message_handler(lambda message: message.text in ['Использовать текущую дату', 'Ввести дату вручную'])
async def date_choice_handler(message: types.Message):
    if message.text == 'Использовать текущую дату':
        user_id = message.from_user.id
        data = USER_DATA.get(user_id)
        if not data:
            await message.answer("Сначала введите имя клиента /start")
            return

        # Генерируем и отправляем PDF
        await generate_and_send_pdf(message, data['client_name'], data['date'])
        await message.answer("Готово! Введите имя следующего клиента.", reply_markup=ReplyKeyboardRemove())
        USER_DATA.pop(user_id, None)

    else:
        # Запрашиваем дату в формате ДД.ММ.ГГГГ
        await message.answer("Введите дату в формате ДД.ММ.ГГГГ (например, 20.05.2025):")

        # Помечаем, что сейчас ждем дату
        USER_DATA[message.from_user.id]['await_date'] = True

# Принимаем дату от пользователя
@dp.message_handler(lambda message: True)
async def date_input_handler(message: types.Message):
    user_id = message.from_user.id
    data = USER_DATA.get(user_id)
    if data and data.get('await_date'):
        date_text = message.text.strip()

        # Проверяем формат даты
        try:
            datetime.strptime(date_text, '%d.%m.%Y')
        except ValueError:
            await message.answer("Неверный формат даты. Попробуйте снова в формате ДД.ММ.ГГГГ:")
            return

        # Сохраняем дату и удаляем ожидание
        data['date'] = date_text
        data.pop('await_date')

        # Генерируем и отправляем PDF
        await generate_and_send_pdf(message, data['client_name'], data['date'])
        await message.answer("Готово! Введите имя следующего клиента.", reply_markup=ReplyKeyboardRemove())
        USER_DATA.pop(user_id, None)
        return

    # Если не ждем дату, значит пользователь вводит новое имя клиента
    client_name = message.text.strip()
    USER_DATA[user_id] = {'client_name': client_name}

    # Получаем текущую дату по Киеву
    tz = pytz.timezone('Europe/Kiev')
    now = datetime.now(tz)
    date_str = now.strftime('%d.%m.%Y')
    USER_DATA[user_id]['date'] = date_str

    keyboard = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    keyboard.add(KeyboardButton('Использовать текущую дату'))
    keyboard.add(KeyboardButton('Ввести дату вручную'))

    await message.answer(
        f"Имя клиента: {client_name}\n"
        f"Дата по умолчанию: {date_str}\n"
        f"Хотите использовать эту дату или ввести свою?",
        reply_markup=keyboard
    )

async def generate_and_send_pdf(message, client_name, date_str):
    user_id = message.from_user.id
    out_path = f'temp_{user_id}.pdf'
    try:
        replace_text_in_pdf(PDF_TEMPLATE_PATH, out_path, client_name, date_str)
        # Отправляем файл
        with open(out_path, 'rb') as f:
            await message.answer_document(f, caption=f"PDF для клиента: {client_name}\nДата: {date_str}")
    except Exception as e:
        logging.error(f"Ошибка при генерации PDF: {e}")
        await message.answer("Произошла ошибка при генерации PDF. Попробуйте снова позже.")

if __name__ == '__main__':
    executor.start_polling(dp, skip_updates=True)
