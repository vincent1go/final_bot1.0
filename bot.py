import os
import logging
from aiogram import Bot, Dispatcher, types
from aiogram.utils.executor import start_webhook
from datetime import datetime
import pytz
from pdfrw import PdfReader, PdfWriter, PageMerge

API_TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_HOST = os.getenv("WEBHOOK_HOST")  # Например, https://yourapp.onrender.com
WEBHOOK_PATH = f'/webhook/{API_TOKEN}'
WEBHOOK_URL = WEBHOOK_HOST + WEBHOOK_PATH

WEBAPP_HOST = '0.0.0.0'
WEBAPP_PORT = int(os.getenv("PORT", 8000))

logging.basicConfig(level=logging.INFO)

bot = Bot(token=API_TOKEN)
dp = Dispatcher(bot)

# Путь к шаблону PDF (положи шаблон рядом с bot.py)
TEMPLATE_PATH = 'template.pdf'


def replace_text_on_page(page, old_text, new_text):
    """
    Простейшая замена текста в содержимом страницы PDF.
    В pdfrw нельзя просто так заменить текст, 
    поэтому тут пример грубой замены в stream (если текст простой).
    Если надо сложнее — нужна библиотека типа borb, pdfplumber, reportlab.
    """
    if not page.Contents:
        return
    content = page.Contents.stream
    if old_text in content:
        content = content.replace(old_text.encode(), new_text.encode())
        page.Contents.stream = content


def generate_pdf(client_name: str, date_str: str) -> str:
    # Загружаем шаблон
    pdf = PdfReader(TEMPLATE_PATH)

    # Первая страница — замена Client:
    first_page = pdf.pages[0]
    replace_text_on_page(first_page, b"Client:", f"Client: {client_name}".encode())

    # Пятая страница (индекс 4) — два раза заменяем Date:
    fifth_page = pdf.pages[4]
    replace_text_on_page(fifth_page, b"Date: 20.05.2025", f"Date: {date_str}".encode())
    replace_text_on_page(fifth_page, b"Date: 20.05.2025", f"Date: {date_str}".encode())

    # Сохраняем новый файл
    output_filename = f"{client_name}.pdf"
    PdfWriter().write(output_filename, pdf)
    return output_filename


@dp.message_handler(commands=['start'])
async def start(message: types.Message):
    await message.answer(
        "Привет! Введи имя клиента и дату через запятую.\n"
        "Например:\n"
        "Иван Иванов, 07.06.2025\n"
        "Или просто имя — дата будет текущая."
    )


@dp.message_handler()
async def process_input(message: types.Message):
    text = message.text.strip()

    # Парсим имя и дату
    if ',' in text:
        client_name, date_input = map(str.strip, text.split(',', 1))
    else:
        client_name = text
        # Текущая дата по Киеву
        tz = pytz.timezone('Europe/Kiev')
        date_input = datetime.now(tz).strftime('%d.%m.%Y')

    await message.answer(f"Генерирую PDF для клиента: {client_name} с датой: {date_input} ...")

    try:
        pdf_path = generate_pdf(client_name, date_input)
    except Exception as e:
        await message.answer(f"Ошибка при генерации PDF: {e}")
        return

    with open(pdf_path, 'rb') as pdf_file:
        await message.answer_document(pdf_file, caption=f"PDF для {client_name}")

    # Можно удалить файл после отправки, чтобы не засорять диск
    try:
        os.remove(pdf_path)
    except Exception:
        pass


async def on_startup(dp):
    await bot.set_webhook(WEBHOOK_URL)
    logging.info(f"Webhook установлен: {WEBHOOK_URL}")


async def on_shutdown(dp):
    logging.warning("Shutting down..")
    await bot.delete_webhook()
    await bot.session.close()
    logging.warning("Bye!")


if __name__ == '__main__':
    start_webhook(
        dispatcher=dp,
        webhook_path=WEBHOOK_PATH,
        on_startup=on_startup,
        on_shutdown=on_shutdown,
        skip_updates=True,
        host=WEBAPP_HOST,
        port=WEBAPP_PORT,
    )
