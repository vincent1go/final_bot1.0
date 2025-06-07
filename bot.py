import os
import logging
from io import BytesIO
from datetime import datetime

import pytz
import pdfplumber
from aiogram import Bot, Dispatcher, types
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.dispatcher import FSMContext
from aiogram.utils.executor import start_webhook
from pdfrw import PdfReader, PdfWriter, PageMerge
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter

logging.basicConfig(level=logging.INFO)

API_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
WEBHOOK_HOST = os.getenv("WEBHOOK_HOST")  # например, https://mybot.onrender.com
PORT = int(os.getenv("PORT", 8443))

if not API_TOKEN or not WEBHOOK_HOST:
    logging.error("Переменные окружения TELEGRAM_BOT_TOKEN и WEBHOOK_HOST обязательны!")
    exit(1)

WEBHOOK_PATH = f"/webhook/{API_TOKEN}"
WEBHOOK_URL = f"{WEBHOOK_HOST}{WEBHOOK_PATH}"

TEMPLATE_PATH = "template.pdf"

class Form(StatesGroup):
    waiting_for_name = State()
    waiting_for_date = State()

bot = Bot(token=API_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)

def get_current_date_kiev():
    tz = pytz.timezone("Europe/Kiev")
    now = datetime.now(tz)
    return now.strftime("%d.%m.%Y")

def find_text_positions(pdf_path, page_num, search_text):
    """Найти все позиции search_text на странице page_num (0-based) с помощью pdfplumber"""
    positions = []
    with pdfplumber.open(pdf_path) as pdf:
        page = pdf.pages[page_num]
        # Поиск в тексте страницы
        words = page.extract_words()
        for word in words:
            if search_text in word['text']:
                # Координаты: x0,y0,x1,y1 (нижний левый и верхний правый угол)
                positions.append((word['x0'], word['top'], word['x1'], word['bottom']))
    return positions

def create_overlay(x0, y0, x1, y1, text):
    """Создаем PDF-страницу с белым прямоугольником и новым текстом поверх (координаты в pdfplumber — в точках, reportlab рисует с нижнего левого угла)"""
    packet = BytesIO()
    c = canvas.Canvas(packet, pagesize=letter)
    rect_width = x1 - x0
    rect_height = y1 - y0

    # reportlab и pdfplumber имеют разные системы координат — надо конвертировать Y
    # letter height
    page_height = letter[1]
    c.setFillColorRGB(1, 1, 1)  # белый прямоугольник
    c.rect(x0, page_height - y1, rect_width, rect_height, fill=1, stroke=0)

    c.setFillColorRGB(0, 0, 0)
    c.setFont("Helvetica-Bold", 12)
    c.drawString(x0, page_height - y1 + 3, text)  # с небольшим сдвигом по Y
    c.save()
    packet.seek(0)
    return PdfReader(packet).pages[0]

def create_filled_pdf(client_name: str, date_str: str) -> bytes:
    pdf = PdfReader(TEMPLATE_PATH)

    # Поиск и замена Client: на странице 0
    client_positions = find_text_positions(TEMPLATE_PATH, 0, "Client:")
    if not client_positions:
        raise ValueError("Не найден текст 'Client:' на странице 1")
    page1 = pdf.pages[0]
    merger1 = PageMerge(page1)
    for pos in client_positions:
        overlay = create_overlay(*pos, f"Client: {client_name}")
        merger1.add(overlay).render()

    # Поиск и замена Date: на странице 4 (пятая страница, 0-based)
    date_positions = find_text_positions(TEMPLATE_PATH, 4, "Date:")
    if len(date_positions) < 2:
        raise ValueError("Не найдено два поля 'Date:' на странице 5")
    page5 = pdf.pages[4]
    merger5 = PageMerge(page5)
    for pos in date_positions:
        overlay = create_overlay(*pos, f"Date: {date_str}")
        merger5.add(overlay).render()

    output = BytesIO()
    PdfWriter(output, trailer=pdf).write()
    return output.getvalue()

@dp.message_handler(commands=["start"])
async def cmd_start(message: types.Message):
    await message.answer(
        "Привет!\nВведите имя клиента для генерации PDF."
    )
    await Form.waiting_for_name.set()

@dp.message_handler(state=Form.waiting_for_name)
async def process_name(message: types.Message, state: FSMContext):
    name = message.text.strip()
    if not name:
        await message.answer("Имя не может быть пустым, попробуйте ещё раз.")
        return
    await state.update_data(client_name=name)
    await message.answer("Введите дату в формате ДД.ММ.ГГГГ или 'сейчас' для текущей даты по Киеву.")
    await Form.waiting_for_date.set()

@dp.message_handler(state=Form.waiting_for_date)
async def process_date(message: types.Message, state: FSMContext):
    date_text = message.text.strip()
    if date_text.lower() == "сейчас":
        date_val = get_current_date_kiev()
    else:
        try:
            datetime.strptime(date_text, "%d.%m.%Y")
            date_val = date_text
        except Exception:
            await message.answer("Неверный формат даты. Введите ДД.ММ.ГГГГ или 'сейчас'.")
            return

    data = await state.get_data()
    client_name = data.get("client_name")

    try:
        pdf_data = create_filled_pdf(client_name, date_val)
    except Exception as e:
        logging.error(f"Ошибка генерации PDF: {e}")
        await message.answer("Ошибка при создании PDF. Попробуйте позже.")
        await state.finish()
        return

    await message.answer_document(pdf_data, filename=f"{client_name}.pdf")
    await message.answer("Готово! Введите имя следующего клиента или /start для начала заново.")
    await Form.waiting_for_name.set()

async def on_startup(dp):
    await bot.set_webhook(WEBHOOK_URL)
    logging.info(f"Webhook установлен: {WEBHOOK_URL}")

async def on_shutdown(dp):
    logging.info("Завершение работы бота")
    await bot.delete_webhook()

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
