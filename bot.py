import os
import logging
from datetime import datetime
from aiogram import Bot, Dispatcher, types
from aiogram.utils.executor import start_webhook
from aiogram.types import ParseMode
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext

from pdfrw import PdfReader, PdfWriter, PageMerge
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from io import BytesIO
import pytz

# --- Настройка логирования ---
logging.basicConfig(level=logging.INFO)

# --- Переменные окружения ---
API_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
if not API_TOKEN:
    logging.error("TELEGRAM_BOT_TOKEN не установлен в переменных окружения!")
    exit(1)

# --- Вебхук URL и порт для Render ---
WEBHOOK_HOST = os.environ.get("WEBHOOK_HOST")  # Например: https://yourapp.onrender.com
WEBHOOK_PATH = f"/webhook/{API_TOKEN}"
WEBHOOK_URL = f"{WEBHOOK_HOST}{WEBHOOK_PATH}"

# Порт Render даёт в переменной PORT
PORT = int(os.environ.get("PORT", 8443))

# --- FSM States ---
class Form(StatesGroup):
    waiting_for_name = State()
    waiting_for_date = State()

# --- Инициализация бота и диспетчера ---
bot = Bot(token=API_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)

# --- Путь к шаблону PDF ---
TEMPLATE_PATH = "template.pdf"  # Загрузите ваш шаблон сюда рядом с кодом


# --- Функция для замены текста в PDF ---
def create_filled_pdf(client_name: str, date_str: str) -> bytes:
    """
    Берёт шаблон template.pdf,
    заменяет в нём текст Client: и Date: на client_name и date_str,
    возвращает PDF в байтах.
    """
    # Читаем шаблон
    template_pdf = PdfReader(TEMPLATE_PATH)
    page = template_pdf.pages[0]

    # Создаем слой с белым прямоугольником для удаления старого текста (замазываем)
    packet = BytesIO()
    can = canvas.Canvas(packet, pagesize=letter)

    # Позиции текста на странице (пример, подберите под ваш шаблон)
    # В pdf координаты считаются от нижнего левого угла:
    client_x = 100
    client_y = 700

    date_x = 100
    date_y = 680

    rect_width = 300
    rect_height = 20

    # Закрашиваем старый текст белым прямоугольником
    can.setFillColorRGB(1, 1, 1)  # белый
    can.rect(client_x, client_y - 5, rect_width, rect_height, fill=1, stroke=0)
    can.rect(date_x, date_y - 5, rect_width, rect_height, fill=1, stroke=0)

    # Добавляем новый текст
    can.setFillColorRGB(0, 0, 0)  # черный
    can.setFont("Helvetica-Bold", 12)
    can.drawString(client_x, client_y, f"Client: {client_name}")
    can.drawString(date_x, date_y, f"Date: {date_str}")

    can.save()

    # Перемещаемся в начало BytesIO
    packet.seek(0)

    # Читаем созданный PDF слой
    new_pdf = PdfReader(packet)
    overlay = new_pdf.pages[0]

    # Накладываем новый слой поверх шаблона
    merger = PageMerge(page)
    merger.add(overlay).render()

    # Сохраняем результат в BytesIO
    output = BytesIO()
    PdfWriter(output, trailer=template_pdf).write()
    return output.getvalue()

# --- Получаем текущую дату по Киеву ---
def get_current_date_kiev() -> str:
    tz = pytz.timezone("Europe/Kiev")
    now = datetime.now(tz)
    return now.strftime("%d.%m.%Y")


# --- Хендлеры бота ---

@dp.message_handler(commands=["start"])
async def cmd_start(message: types.Message):
    await message.answer(
        "Привет! Введите имя клиента, чтобы получить заполненный PDF.\n\n"
        "Например: Иван Иванов"
    )
    await Form.waiting_for_name.set()


@dp.message_handler(state=Form.waiting_for_name)
async def process_name(message: types.Message, state: FSMContext):
    client_name = message.text.strip()
    if not client_name:
        await message.answer("Пожалуйста, введите корректное имя клиента.")
        return

    await state.update_data(client_name=client_name)
    await message.answer(
        "Введите дату в формате ДД.ММ.ГГГГ или отправьте слово 'сейчас' для текущей даты."
    )
    await Form.waiting_for_date.set()


@dp.message_handler(state=Form.waiting_for_date)
async def process_date(message: types.Message, state: FSMContext):
    date_text = message.text.strip()
    if date_text.lower() == "сейчас":
        date_str = get_current_date_kiev()
    else:
        # Проверяем формат даты
        try:
            datetime.strptime(date_text, "%d.%m.%Y")
            date_str = date_text
        except ValueError:
            await message.answer("Неверный формат даты. Введите ДД.ММ.ГГГГ или 'сейчас'.")
            return

    user_data = await state.get_data()
    client_name = user_data.get("client_name")

    try:
        pdf_bytes = create_filled_pdf(client_name, date_str)
    except Exception as e:
        logging.exception("Ошибка при создании PDF")
        await message.answer("Произошла ошибка при создании PDF. Попробуйте позже.")
        await state.finish()
        return

    # Отправляем файл пользователю
    file_name = f"{client_name}.pdf"
    await message.answer_document(document=pdf_bytes, filename=file_name)

    # Готовы к следующему клиенту
    await message.answer("Введите имя следующего клиента или /start для начала.")
    await Form.waiting_for_name.set()


# --- Настройка вебхука для Render ---

async def on_startup(dp):
    await bot.set_webhook(WEBHOOK_URL)
    logging.info(f"Webhook установлен: {WEBHOOK_URL}")

async def on_shutdown(dp):
    logging.info("Шатдаун")

# --- Запуск ---
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
