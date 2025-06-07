import os
import logging
from datetime import datetime
import pytz

from aiogram import Bot, Dispatcher, types
from aiogram.contrib.middlewares.logging import LoggingMiddleware
from aiogram.types import ParseMode
from aiogram.utils.executor import start_webhook
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.dispatcher import FSMContext
from aiogram.contrib.fsm_storage.memory import MemoryStorage

import fitz  # PyMuPDF

# -------- Конфіг --------
API_TOKEN = os.getenv("TELEGRAM_TOKEN")
WEBHOOK_HOST = os.getenv("WEBHOOK_HOST")  # наприклад: https://yourapp.onrender.com
WEBHOOK_PATH = "/webhook"
WEBHOOK_URL = WEBHOOK_HOST + WEBHOOK_PATH
PORT = int(os.getenv("PORT", 8000))

TEMPLATE_PATH = "template.pdf"
OUTPUT_DIR = "generated"
os.makedirs(OUTPUT_DIR, exist_ok=True)

# -------- Логування --------
logging.basicConfig(level=logging.INFO)

# -------- Ініціалізація бота --------
bot = Bot(token=API_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)
dp.middleware.setup(LoggingMiddleware())


# -------- Стан машини --------
class Form(StatesGroup):
    waiting_for_client_name = State()
    waiting_for_date = State()


# -------- Генерація PDF --------
def replace_text_in_pdf(client_name: str, date_str: str) -> str:
    doc = fitz.open(TEMPLATE_PATH)

    # --- Заміна "Client:" на сторінці 1 ---
    page1 = doc[0]
    for inst in page1.search_for("Client:"):
        page1.draw_rect(inst, color=(1, 1, 1), fill=(1, 1, 1))
        page1.insert_text(inst.tl, f"Client: {client_name}", fontsize=12, color=(0, 0, 0))

    # --- Заміна дати на сторінці 5 ---
    page5 = doc[4]
    for inst in page5.search_for("Date: 20.05.2025"):
        page5.draw_rect(inst, color=(1, 1, 1), fill=(1, 1, 1))
        page5.insert_text(inst.tl, f"Date: {date_str}", fontsize=12, color=(0, 0, 0))

    filename = f"{client_name}_{date_str.replace('.', '-')}.pdf"
    output_path = os.path.join(OUTPUT_DIR, filename)
    doc.save(output_path)
    doc.close()

    return output_path


# -------- Хендлери --------

@dp.message_handler(commands=["start"])
async def cmd_start(message: types.Message):
    await message.answer("Привіт! Введіть ім’я клієнта:", reply_markup=types.ForceReply(selective=True))
    await Form.waiting_for_client_name.set()


@dp.message_handler(state=Form.waiting_for_client_name, content_types=types.ContentTypes.TEXT)
async def handle_client_name(message: types.Message, state: FSMContext):
    name = message.text.strip()
    if not name:
        await message.answer("Ім’я не може бути порожнім. Введіть ще раз:")
        return

    await state.update_data(client_name=name)

    now = datetime.now(pytz.timezone("Europe/Kiev")).strftime("%d.%m.%Y")
    await message.answer(
        f"Введіть дату у форматі ДД.ММ.РРРР або /today (сьогоднішня: {now}):",
        reply_markup=types.ForceReply(selective=True),
    )
    await Form.waiting_for_date.set()


@dp.message_handler(state=Form.waiting_for_date, content_types=types.ContentTypes.TEXT)
async def handle_date(message: types.Message, state: FSMContext):
    raw_date = message.text.strip()
    if raw_date.lower() == "/today":
        date_str = datetime.now(pytz.timezone("Europe/Kiev")).strftime("%d.%m.%Y")
    else:
        try:
            datetime.strptime(raw_date, "%d.%m.%Y")
            date_str = raw_date
        except ValueError:
            await message.answer("Невірний формат дати. Введіть у форматі ДД.ММ.РРРР або /today:")
            return

    data = await state.get_data()
    client_name = data.get("client_name")

    await message.answer("Генерую PDF, зачекайте...")

    try:
        pdf_path = replace_text_in_pdf(client_name, date_str)
    except Exception as e:
        logging.error(f"Помилка при генерації PDF: {e}")
        await message.answer("Сталася помилка при створенні PDF. Спробуйте пізніше.")
        await state.finish()
        return

    with open(pdf_path, "rb") as file:
        await message.answer_document(file, caption=f"{client_name}, дата {date_str}")

    await message.answer("Готово! Введіть ім’я наступного клієнта:")
    await Form.waiting_for_client_name.set()


@dp.message_handler()
async def handle_unknown(message: types.Message):
    await message.answer("Натисніть /start для початку.")


# -------- Webhook --------
async def on_startup(dp):
    await bot.set_webhook(WEBHOOK_URL)
    logging.info(f"Webhook встановлено: {WEBHOOK_URL}")


async def on_shutdown(dp):
    logging.warning("Вимикаємося...")
    await bot.delete_webhook()
    await dp.storage.close()
    await dp.storage.wait_closed()
    logging.warning("Бот вимкнено.")


if __name__ == "__main__":
    start_webhook(
        dispatcher=dp,
        webhook_path=WEBHOOK_PATH,
        on_startup=on_startup,
        on_shutdown=on_shutdown,
        skip_updates=True,
        host="0.0.0.0",
        port=PORT,
    )
