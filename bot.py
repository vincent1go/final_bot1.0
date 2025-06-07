import os
import logging
from datetime import datetime
import pytz

from aiogram import Bot, Dispatcher, types
from aiogram.contrib.middlewares.logging import LoggingMiddleware
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.dispatcher import FSMContext
from aiogram.contrib.fsm_storage.memory import MemoryStorage

import fitz  # PyMuPDF
from aiohttp import web

API_TOKEN = os.getenv("TELEGRAM_TOKEN")
WEBHOOK_HOST = os.getenv("WEBHOOK_HOST")
WEBHOOK_PATH = "/webhook"
WEBHOOK_URL = WEBHOOK_HOST + WEBHOOK_PATH
PORT = int(os.getenv("PORT", 8000))

TEMPLATE_PATH = "template.pdf"
OUTPUT_DIR = "generated"
os.makedirs(OUTPUT_DIR, exist_ok=True)

logging.basicConfig(level=logging.INFO)

bot = Bot(token=API_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)
dp.middleware.setup(LoggingMiddleware())

class Form(StatesGroup):
    waiting_for_client_name = State()
    waiting_for_date = State()

def replace_text_in_pdf(client_name: str, date_str: str) -> str:
    doc = fitz.open(TEMPLATE_PATH)
    page1 = doc[0]
    for inst in page1.search_for("Client:"):
        page1.draw_rect(inst, color=(1,1,1), fill=(1,1,1))
        page1.insert_text(inst.tl, f"Client: {client_name}", fontsize=12, color=(0,0,0))
    page5 = doc[4]
    for inst in page5.search_for("Date: 20.05.2025"):
        new_position = fitz.Point(inst.tl.x, inst.tl.y + 5)
        page5.draw_rect(inst, color=(1,1,1), fill=(1,1,1))
        page5.insert_text(new_position, f"Date: {date_str}", fontsize=12, color=(0,0,0))
    filename = f"{client_name}_{date_str.replace('.', '-')}.pdf"
    output_path = os.path.join(OUTPUT_DIR, filename)
    doc.save(output_path)
    doc.close()
    return output_path

@dp.message_handler(commands=["start"])
async def cmd_start(message: types.Message):
    await message.answer("👋 Привет! Введи имя клиента:", reply_markup=types.ForceReply(selective=True))
    await Form.waiting_for_client_name.set()

@dp.message_handler(state=Form.waiting_for_client_name, content_types=types.ContentTypes.TEXT)
async def handle_client_name(message: types.Message, state: FSMContext):
    name = message.text.strip()
    if not name:
        await message.answer("⚠️ Имя не может быть пустым. Введи его ещё раз:")
        return
    await state.update_data(client_name=name)
    now = datetime.now(pytz.timezone("Europe/Kiev")).strftime("%d.%m.%Y")
    await message.answer(
        f"📅 Введи дату в формате ДД.ММ.ГГГГ или отправь /today (сегодня: {now}):",
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
            await message.answer("❌ Неверный формат даты. Введи в формате ДД.ММ.ГГГГ или /today:")
            return
    data = await state.get_data()
    client_name = data.get("client_name")
    await message.answer("🛠 Генерирую PDF, пожалуйста подожди...")
    try:
        pdf_path = replace_text_in_pdf(client_name, date_str)
    except Exception as e:
        logging.error(f"Ошибка при генерации PDF: {e}")
        await message.answer("💥 Произошла ошибка при создании PDF. Попробуй позже.")
        await state.finish()
        return
    with open(pdf_path, "rb") as file:
        await message.answer_document(file, caption=f"📄 PDF для {client_name}, дата {date_str}")
    await message.answer("✅ Готово! Введи имя следующего клиента:")
    await Form.waiting_for_client_name.set()

@dp.message_handler()
async def handle_unknown(message: types.Message):
    await message.answer("ℹ️ Напиши /start для начала работы.")

async def on_startup(app):
    await bot.set_webhook(WEBHOOK_URL)
    logging.info(f"Webhook установлен: {WEBHOOK_URL}")

async def on_shutdown(app):
    logging.warning("Отключение...")
    await bot.delete_webhook()
    await dp.storage.close()
    await dp.storage.wait_closed()
    logging.warning("Бот остановлен.")

async def health_check(request):
    return web.Response(text="OK")

def setup_health_route(app):
    app.router.add_get("/ping", health_check)

if __name__ == "__main__":
    app = web.Application()
    setup_health_route(app)

    async def handle_webhook(request):
        try:
            update = await request.json()
            update_obj = types.Update.to_object(update)
            Bot.set_current(bot)  # <- вот здесь!
            await dp.process_update(update_obj)
            return web.Response(text="OK")
        except Exception as e:
            logging.error(f"Error in webhook handler: {e}")
            return web.Response(status=500, text="Internal Server Error")

    app.router.add_post(WEBHOOK_PATH, handle_webhook)

    app.on_startup.append(on_startup)
    app.on_shutdown.append(on_shutdown)

    web.run_app(app, host="0_
