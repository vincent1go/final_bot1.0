import asyncio
from flask import Flask, request, send_file
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)
from io import BytesIO
from docx import Document

TOKEN = "7511704960:AAFKDWgg2-cAzRxywX1gXK47OQRWJi72qGw"
WEBHOOK_URL = "https://final-bot1-0.onrender.com/webhook"

# Инициализация Flask
app = Flask(__name__)

# Инициализация Telegram-приложения
application = Application.builder().token(TOKEN).build()

# Команда /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu")],
        [InlineKeyboardButton("📄 Получить PDF", callback_data="generate_pdf")],
        [InlineKeyboardButton("ℹ️ О боте", callback_data="about_bot")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "👋 Привет!\n\nЯ — твой помощник. Выбери действие ниже 👇",
        reply_markup=reply_markup,
    )

# Генерация простого PDF (из docx → pdf)
async def generate_pdf():
    doc = Document()
    doc.add_heading('Документ', level=1)
    doc.add_paragraph('Этот документ был сгенерирован автоматически ботом!')

    # Сохраняем DOCX в память
    buffer = BytesIO()
    doc.save(buffer)
    buffer.seek(0)

    return buffer

# Обработка нажатий кнопок
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "main_menu":
        await query.edit_message_text(
            "🏠 Главное меню\n\nВыберите действие:",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📄 Получить PDF", callback_data="generate_pdf")],
                [InlineKeyboardButton("ℹ️ О боте", callback_data="about_bot")]
            ])
        )
    elif query.data == "about_bot":
        await query.edit_message_text(
            "🤖 Этот бот был создан для генерации PDF документов!\n\n"
            "⚡ Работает на Python + Flask + Telegram API.\n"
            "Создан Тобой 🔥"
        )
    elif query.data == "generate_pdf":
        pdf_buffer = await generate_pdf()
        await query.message.reply_document(document=pdf_buffer, filename="document.docx")
        await query.edit_message_text("✅ Документ отправлен!")

# Webhook для Telegram
@app.route('/webhook', methods=['POST'])
async def telegram_webhook():
    update = Update.de_json(request.get_json(force=True), application.bot)
    await application.process_update(update)
    return "ok"

# Установка webhook
async def setup_webhook():
    await application.bot.set_webhook(url=WEBHOOK_URL)

# Главная функция
async def main():
    await setup_webhook()
    app.run(host="0.0.0.0", port=5000)

# Хендлеры
application.add_handler(CommandHandler("start", start))
application.add_handler(CallbackQueryHandler(button_handler))

if __name__ == '__main__':
    asyncio.run(main())

