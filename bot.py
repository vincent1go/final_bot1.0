import os
import logging
from datetime import datetime
from io import BytesIO

import pytz
from aiogram import Bot, Dispatcher, types
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.utils.executor import start_webhook
from pdfrw import PdfReader, PdfWriter, PageMerge
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter

logging.basicConfig(level=logging.INFO)

API_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not API_TOKEN:
    logging.error("Ошибка: TELEGRAM_BOT_TOKEN не найден в переменных окружения!")
    exit(1)

WEBHOOK_HOST = os.getenv("WEBHOOK_HOST")  # например: https://yourapp.onrender.com
if not WEBHOOK_HOST:
    logging.error("Ошибка: WEBHOOK_HOST не найден в переменных окружения!")
    exit(1)

WEBHOOK_PATH = f"/webhook/{API_TOKEN}"
WEBHOOK_URL = f"{WEBHOOK_HOST}{WEBHOOK_PATH}"

PORT = int(os.getenv("PORT", 8443))

# Путь к вашему PDF шаблону
TEMPLATE_PATH = "template.pdf"

# FSM для диалога
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

def create_filled_pdf(client_name: str, date_str: str) -> bytes:
    """
    Заменяем в шаблоне client_name и date_str (два раза) на 5 странице,
    возвращаем PDF в байтах.
    """
    pdf = PdfReader(TEMPLATE_PATH)
    if len(pdf.pages) < 5:
        raise ValueError("В шаблоне меньше 5 страниц!")

    page = pdf.pages[4]  # 5-я страница, индекс 4

    # Создаем наложение (overlay) с белыми прямоугольниками и новым текстом
    packet = BytesIO()
    can = canvas.Canvas(packet, pagesize=letter)

    # Координаты (примерные, их надо подогнать под твой шаблон):
    # В pdf координаты считаются от низа страницы
    client_x, client_y = 100, 700   # место где написано Client:
    date1_x, date1_y = 100, 680     # первая дата
    date2_x, date2_y = 100, 660     # вторая дата

    rect_width = 300
    rect_height = 20

    # Закрашиваем старый текст белым (стираем)
    can.setFillColorRGB(1, 1, 1)
    can.rect(client_x, client_y - 5, rect_width, rect_height, fill=1, stroke=0)
    can.rect(date1_x, date1_y - 5, rect_width, rect_height, fill=1, stroke=0)
    can.rect(date2_x, date2_y - 5, rect_width, rect_height, fill=1, stroke=0)

    # Пишем новый текст черным цветом
    can.setFillColorRGB(0, 0, 0)
    can.setFont("Helvetica-Bold", 12)
    can.drawString(client_x, client_y, f"Client: {client_name}")
    can.drawString(date1_x, date1_y, f"Date: {date_str}")
    can.drawString(date2_x, date2_y, f"Date: {date_str}")

    can.save()

    packet.seek(0)
    overlay_pdf = PdfReader(packet)
    overlay_page = overlay_pdf.pages[0]

    # Накладываем overlay на 5 страницу
    merger = PageMerge(page)
    merger.add(overlay_page).render()

    output = BytesIO()
    PdfWriter(output, t
