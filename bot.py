import os
import logging
from datetime import datetime
import pytz

from aiogram import Bot, Dispatcher, types
from aiogram.contrib.middlewares.logging import LoggingMiddleware
from aiogram.types import ParseMode
from aiogram.utils.executor import start_webhook

import fitz  # PyMuPDF

# -------- НАСТРОЙКИ --------
API_TOKEN = os.getenv("TELEGRAM_TOKEN")
WEBHOOK_HOST = os.getenv("WEBHOOK_HOST")  # Например: https://yourapp.onrender.com
WEBHOOK_PATH = "/webhook"
WEBHOOK_URL = WEBHOOK_HOST + WEBHOOK_PATH
PORT = int(os.getenv("PORT", 8000))

# Путь к шаблону
TEMPLATE_PATH = "template.pdf"
OUTPUT_DIR = "generated"
os.makedirs(OUTPUT_DIR, exist_ok=True)

# Логирование
logging.basicConfig(level=logging.INFO)

bot = Bot(token=API_TOKEN)
dp = Dispatcher(bot)
dp.middleware.setup(LoggingMiddleware())

# ---- Работа с состояниями (FSM) ----
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext

storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)


class Form(StatesGroup):
    waiting_for_client_name = State()
    waiting_for_date = State()


# ---- Функции для работы с PDF ----
def replace_text_in_pdf(client_name: str, date_str: str) -> str:
    """
    Заменить текст в PDF: 
    - На 1 странице: 'Client:' -> 'Client: <client_name>'
    - На 5 странице (две даты): 'Date: 20.05.2025' -> 'Date: <date_str>'
    Возвращает путь к сгенерированному PDF.
    """

    doc = fitz.open(TEMPLATE_PATH)

    # 1 страница: меняем client
    page1 = doc[0]
    # Удаляем старый текст Client: (стираем прямоугольник, где он был)
    # Т.к. координаты не даем, пробуем найти текст и очистить область вокруг него.

    # Найдем все вхождения "Client:"
    for inst in page1.search_for("Client:"):
        # Стираем прямоугольник (заливка белым)
        page1.draw_rect(inst, color=(1, 1, 1), fill=(1, 1, 1))

        # Пишем новый текст вместо Client: <client_name>
        # Ставим текст в ту же позицию с тем же размером
        page1.insert_text(inst.tl, f"Client: {client_name}", fontsize=12, color=(0, 0, 0))

    # 5 страница: меняем дату 2 раза
    page5 = doc[4]

    for inst in page5.search_for("Date: 20.05.2025"):
        page5.draw_rect(inst, color=(1, 1, 1), fill=(1, 1, 1))
        page5.insert_text(inst.tl, f"Date: {date_str}", fontsize=12, color=(0, 0, 0))

    # Сохраняем файл
    output_pdf = os.path.join(OUTPUT_DIR, f"{client_name}_{date_str.replace('.', '-')}.pdf")
    doc.save(output_pdf)
    doc.close()

    return output_pdf


# ---- Хэндлеры ----

@dp.message_handler(commands=['start'])
async def cmd_start(message: types.Message):
    await message.answer(
        "Привет! Я бот для генерации PDF.\n"
        "Введите имя клиента:",
        reply_markup=types.ForceReply(selective=True),
    )
    await Form.waiting_for_client_name.set()


@dp.message_handler(state=Form.waiting_for_client_name, content_types=types.ContentTypes.TEXT)
async def process_client_name(message: types.Message, state: FSMContext):
    client_name = message.text.strip()
    if not client_name:
        await message.answer("Имя клиента не может быть пустым. Введите имя еще раз:")
        return

    await state.update_data(client_name=client_name)

    # Предлагаем ввести дату или использовать текущую по Киеву
    tz = pytz.timezone("Europe/Kiev")
    now_kiev = datetime.now(tz).strftime("%d.%m.%Y")

    await message.answer(
        f"Введите дату в формате ДД.ММ.ГГГГ или отправьте /today, чтобы использовать текущую дату ({now_kiev}):",
        reply_markup=types.ForceReply(selective=True),
    )
    await Form.waiting_for_date.set()


@dp.message_handler(state=Form.waiting_for_date, content_types=types.ContentTypes.TEXT)
async def process_date(message: types.Message, state: FSMContext):
    date_text = message.text.strip()

    # Специальная команда /today для текущей даты
    if date_text.lower() == "/today":
        tz = pytz.timezone("Europe/Kiev")
        date_text = datetime.now(tz).strftime("%d.%m.%Y")

    # Проверка формата даты
    try:
        datetime.strptime(date_text, "%d.%m.%Y")
    except ValueError:
        await message.answer("Неверный формат даты. Введите в формате ДД.ММ.ГГГГ или /today:")
        return

    user_data = await state.get_data()
    client_name = user_data.get("client_name")

    # Генерируем PDF
    await message.answer("Генерирую PDF, подождите...")

    try:
        output_pdf = replace_text_in_pdf(client_name, date_text)
    except Exception as e:
        logging.error(f"Ошибка при генерации PDF: {e}")
        await message.answer("Произошла ошибка при генерации PDF. Попробуйте позже.")
        await state.finish()
        return

    # Отправляем файл
    with open(output_pdf, "rb") as f:
        await message.answer_document(f, caption=f"PDF для клиента {client_name}, дата {date_text}")

    await message.answer("Готово! Введите имя следующего клиента:")

    await Form.waiting_for_client_name.set()


@dp.message_handler()
async def fallback(message: types.Message):
    await message.answer("Введите /start для начала работы с ботом.")


# --- Webhook settings для Render ---

async def on_startup(dp):
    await bot.set_webhook(WEBHOOK_URL)
    logging.info(f"Webhook установлен на {WEBHOOK_URL}")

async def on_shutdown(dp):
    logging.warning("Shutting down..")
    await bot.delete_webhook()
    await dp.storage.close()
    await dp.storage.wait_closed()
    logging.warning("Shutdown complete.")


if __name__ == '__main__':
    start_webhook(
        dispatcher=dp,
        webhook_path=WEBHOOK_PATH,
        on_startup=on_startup,
        on_shutdown=on_shutdown,
        skip_updates=True,
        host="0.0.0.0",
        port=PORT,
    )
