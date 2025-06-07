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

# --- Конфигурация ---
API_TOKEN = os.getenv("TELEGRAM_TOKEN")
WEBHOOK_HOST = os.getenv("WEBHOOK_HOST")
WEBHOOK_PATH = "/webhook"
WEBHOOK_URL = WEBHOOK_HOST + WEBHOOK_PATH
PORT = int(os.getenv("PORT", 8000))
TEMPLATE_PATH = "template.pdf"
OUTPUT_DIR = "generated"
LOG_PATH = "bot.log"

# --- Логирование ---
os.makedirs(OUTPUT_DIR, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler(LOG_PATH, encoding="utf-8"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# --- Инициализация бота ---
bot = Bot(token=API_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)
dp.middleware.setup(LoggingMiddleware())

# --- FSM ---
class Form(StatesGroup):
    waiting_for_client_name = State()
    waiting_for_date = State()

# --- PDF генерация ---
def replace_text_in_pdf(client_name: str, date_str: str) -> str:
    logger.info(f"Генерация PDF для клиента '{client_name}' с датой '{date_str}'")
    doc = fitz.open(TEMPLATE_PATH)
    try:
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
        logger.info(f"PDF сохранён: {output_path}")
        return output_path
    finally:
        doc.close()

# --- Хендлеры ---
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
        logger.exception("Ошибка при генерации PDF")
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

# --- Запуск и вебхук ---
async def on_startup(app):
    await bot.set_webhook(WEBHOOK_URL)
    logger.info(f"Webhook установлен: {WEBHOOK_URL}")

async def on_shutdown(app):
    logger.warning("Отключение...")
    await bot.delete_webhook()
    await dp.storage.close()
    await dp.storage.wait_closed()
    logger.warning("Бот остановлен.")

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
            Bot.set_current(bot)
            await dp.process_update(update_obj)
            return web.Response(text="OK")
        except Exception as e:
            logger.exception("Ошибка в обработчике вебхука")
            return web.Response(status=500, text="Internal Server Error")

    app.router.add_post(WEBHOOK_PATH, handle_webhook)
    app.on_startup.append(on_startup)
    app.on_shutdown.append(on_shutdown)
    web.run_app(app, host="0.0.0.0", port=PORT)
