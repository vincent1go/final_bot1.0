import os
import logging
import asyncio
from aiohttp import web
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, MessageHandler, ContextTypes, filters
)
import config
from docx_generator import generate_pdf

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

SELECTING_TEMPLATE = 1
ENTERING_TEXT = 2

app = Application.builder().token(config.BOT_TOKEN).build()

# Все handlers сюда
app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("generate", generate))
app.add_handler(CallbackQueryHandler(main_menu, pattern="^main_menu$"))
app.add_handler(CallbackQueryHandler(select_template, pattern="^select_template$"))
app.add_handler(CallbackQueryHandler(template_selected, pattern="^template_"))
app.add_handler(CallbackQueryHandler(cancel, pattern="^cancel$"))
app.add_handler(CallbackQueryHandler(cancel, pattern="^about$"))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, receive_text))

# Все async-функции (start, generate, и т.д.) остаются те же!

async def start_server():
    # Установка webhook
    await app.bot.set_webhook(url=config.WEBHOOK_URL)

    # aiohttp приложение для Render
    aio_app = web.Application()
    aio_app.router.add_post("/webhook", app.webhook_handler())

    port = int(os.environ.get("PORT", 5000))
    runner = web.AppRunner(aio_app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()

    logging.info(f"✅ Сервер запущен на порту {port}")
    while True:
        await asyncio.sleep(3600)

if __name__ == "__main__":
    asyncio.run(start_server())
