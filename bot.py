import os
import logging
from io import BytesIO
from datetime import datetime

import pytz
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
    pdf = PdfReader(TEMPLATE_PATH)
    if len(pdf.pages) < 5:
        raise ValueError("В шаблоне меньше 5 страниц!")

    # 1-я страница (индекс 0) — заменить Client:
    page1 = pdf.pages[0]
    # 5-я страница (индекс 4) — заменить два Date:
    page5 = pdf.pages[4]

    # Координаты — примерные, надо подгонять под твой шаблон:
    # На первой странице (Client)
    client_x, client_y = 100, 700
    # На пятой странице (Date - два раза)
    date1_x, date1_y = 100, 680
    date2_x, date2_y = 100, 660

    rect_w, rect_h = 300, 20

    # Создаем наложения с reportlab для стирания и нового текста

    def create_overlay_text(x, y, text):
        packet = BytesIO()
        c = canvas.Canvas(packet, pagesize=letter)
        c.setFillColorRGB(1, 1, 1)  # белый фон для "стирания"
        c.rect(x, y - 5, rect_w, rect_h, fill=1, stroke=0)
        c.setFillColorRGB(0, 0, 0)
        c.setFont("Helvetica-Bold", 12)
        c.drawString(x, y, text)
        c.save()
        packet.seek(0)
        return PdfReader(packet).pages[0]

    # Наложение на 1 страницу (Client)
    overlay1 = create_overlay_text(client_x, client_y, f"Client: {client_name}")
    merger1 = PageMerge(page1)
    merger1.add(overlay1).ren
