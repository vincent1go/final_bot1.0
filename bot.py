import os
import pytz
from datetime import datetime
from aiogram import Bot, Dispatcher, types
from aiogram.utils import executor
from aiogram.contrib.middlewares.logging import LoggingMiddleware
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.dispatcher import FSMContext
from aiogram.contrib.fsm_storage.memory import MemoryStorage

from pdfrw import PdfReader, PdfWriter, PdfDict, PdfName
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter

import io

# Токен бота из переменной окружения
API_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not API_TOKEN:
    raise RuntimeError("TELEGRAM_BOT_TOKEN environment variable is not set!")

bot = Bot(token=API_TOKEN)
dp = Dispatcher(bot, storage=MemoryStorage())
dp.middleware.setup(LoggingMiddleware())

# Путь к шаблону PDF (должен быть в проекте рядом с ботом)
TEMPLATE_PATH = "template.pdf"

# Состояния для FSM
class Form(StatesGroup):
    waiting_for_client_name = State()
    waiting_for_date = State()

def get_kiev_time():
    tz = pytz.timezone("Europe/Kiev")
    return datetime.now(tz)

def create_overlay(client_name: str, date_str: str):
    """Создает PDF с измененными текстами client_name и date_str в нужных позициях"""
    packet = io.BytesIO()
    can = canvas.Canvas(packet, pagesize=letter)

    # Координаты и шрифты нужно подстроить под твой шаблон, пример:
    # Поле Client: примерно в левом верхнем углу
    can.setFont("Helvetica-Bold", 12)
    can.drawString(70, 720, f"Client: {client_name}")

    # Поле Date: примерно справа сверху
    can.setFont("Helvetica", 12)
    can.drawString(400, 720, f"Date: {date_str}")

    can.save()
    packet.seek(0)
    return PdfReader(packet)

def merge_pdfs(template_path, overlay_pdf):
    template_pdf = PdfReader(template_path)
    for page_num in range(len(template_pdf.pages)):
        overlay_page = overlay_pdf.pages[0]  # накладываем один оверлей на все страницы, если нужно
        template_page = template_pdf.pages[page_num]
        if "/Contents" in template_page:
            contents = template_page.Contents
            if isinstance(contents, list):
                contents.append(overlay_page.Contents)
            else:
                template_page.Contents = [contents, overlay_page.Contents]
        else:
            template_page.Contents = overlay_page.Contents
    output_stream = io.BytesIO()
    PdfWriter(output_stream, trailer=template_pdf).write()
    output_stream.seek(0)
    return output_stream

@dp.message_handler(commands=['start'])
async def cmd_start(message: types.Message):
    await message.answer("Привет! Введи имя клиента, чтобы получить готовый PDF.")
    await Form.waiting_for_client_name.set()

@dp.message_handler(state=Form.waiting_for_client_name)
async def process_client_name(message: types.Message, state: FSMContext):
    client_name = message.text.strip()
    if not client_name:
        await message.answer("Имя клиента не может быть пустым. Попробуй еще раз.")
        return

    # Сохраняем имя клиента
    await state.update_data(client_name=client_name)

    # Получаем текущее время по Киеву
    date_str = get_kiev_time().strftime("%d.%m.%Y")

    # Создаем PDF с заменами
    try:
        overlay_pdf = create_overlay(client_name, date_str)
        pdf_file = merge_pdfs(TEMPLATE_PATH, overlay_pdf)
    except Exception as e:
        await message.answer(f"Ошибка при создании PDF: {e}")
        await state.finish()
        return

    await message.answer_document(types.InputFile(pdf_file, filename=f"{client_name}.pdf"), caption=f"Вот PDF для клиента {client_name} с датой {date_str}.")

    await message.answer("Если хочешь указать другую дату, введи ее в формате ДД.ММ.ГГГГ, или отправь /skip чтобы оставить текущую.")
    await Form.waiting_for_date.set()

@dp.message_handler(commands=['skip'], state=Form.waiting_for_date)
async def skip_date(message: types.Message, state: FSMContext):
    await message.answer("Хорошо, оставляем текущую дату.")
    await state.finish()
    await message.answer("Если хочешь создать еще один PDF, введи имя клиента.")

@dp.message_handler(state=Form.waiting_for_date)
async def process_date(message: types.Message, state: FSMContext):
    date_input = message.text.strip()
    try:
        # Проверяем корректность формата даты
        date_obj = datetime.strptime(date_input, "%d.%m.%Y")
        date_str = date_obj.strftime("%d.%m.%Y")
    except ValueError:
        await message.answer("Неверный формат даты! Пожалуйста, введи дату в формате ДД.ММ.ГГГГ или отправь /skip.")
        return

    data = await state.get_data()
    client_name = data.get("client_name")
    if not client_name:
        await message.answer("Произошла ошибка: имя клиента не найдено. Пожалуйста, начни заново командой /start.")
        await state.finish()
        return

    try:
        overlay_pdf = create_overlay(client_name, date_str)
        pdf_file = merge_pdfs(TEMPLATE_PATH, overlay_pdf)
    except Exception as e:
        await message.answer(f"Ошибка при создании PDF: {e}")
        await state.finish()
        return

    await message.answer_document(types.InputFile(pdf_file, filename=f"{client_name}.pdf"), caption=f"PDF для клиента {client_name} с новой датой {date_str}.")

    await state.finish()
    await message.answer("Если хочешь создать еще один PDF, введи имя клиента.")

@dp.errors_handler()
async def global_error_handler(update, exception):
    print(f"Произошла ошибка: {exception}")
    return True  # ошибка обработана, чтобы бот не крашился

if __name__ == '__main__':
    # Запуск бота
    executor.start_polling(dp, skip_updates=True)
