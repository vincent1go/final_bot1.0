# main.py
import asyncio
from flask import Flask, request
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (Application, CommandHandler, CallbackQueryHandler, ContextTypes)
from io import BytesIO
from fpdf import FPDF
from datetime import datetime
import config

TOKEN = config.BOT_TOKEN
WEBHOOK_URL = config.WEBHOOK_URL
PORT = int(config.PORT)

# Flask app
app = Flask(__name__)

# Telegram app
application = Application.builder().token(TOKEN).build()

# /start handler
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("\U0001F3E0 Главное меню", callback_data="main_menu")],
        [InlineKeyboardButton("\U0001F4C4 Получить PDF", callback_data="generate_pdf")],
        [InlineKeyboardButton("\u2139\ufe0f О боте", callback_data="about_bot")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "\U0001F44B Привет!\n\nЯ могу сгенерировать красивый PDF файл для тебя!\nВыбери действие ниже \u2B07\ufe0f",
        reply_markup=reply_markup,
    )

# PDF генерация
async def generate_pdf(user_name):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=16)

    date_today = datetime.now().strftime("%d.%m.%Y")

    pdf.cell(0, 10, f"Документ для {user_name}", ln=True, align="C")
    pdf.ln(10)
    pdf.set_font("Arial", size=12)
    pdf.cell(0, 10, f"Дата создания: {date_today}", ln=True, align="C")
    pdf.ln(20)
    pdf.set_font("Arial", size=10)
    pdf.multi_cell(0, 10, "Этот документ был автоматически сгенерирован ботом. Спасибо, что пользуетесь нашим сервисом!")

    buffer = BytesIO()
    pdf.output(buffer, dest='F')
    buffer.seek(0)
    return buffer

# Кнопки
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "main_menu":
        await query.edit_message_text(
            "\U0001F3E0 Главное меню\n\nВыберите действие:",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("\U0001F4C4 Получить PDF", callback_data="generate_pdf")],
                [InlineKeyboardButton("\u2139\ufe0f О боте", callback_data="about_bot")],
            ])
        )
    elif query.data == "about_bot":
        await query.edit_message_text(
            "\U0001F916 Этот бот создан для генерации PDF документов на лету!\n\nСоздатель: ТЫ \uD83D\uDD25"
        )
    elif query.data == "generate_pdf":
        user_name = query.from_user.full_name
        pdf_buffer = await generate_pdf(user_name)
        await query.message.reply_document(document=pdf_buffer, filename=f"Документ_{user_name}.pdf")

# Flask webhook обработка
@app.route('/webhook', methods=['POST'])
async def webhook():
    if request.method == "POST":
        data = request.get_json(force=True)
        update = Update.de_json(data, application.bot)
        await application.process_update(update)
    return "ok"

async def main():
    # Установить webhook
    await application.bot.set_webhook(url=WEBHOOK_URL)

    # Регистрация обработчиков
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(button_handler))

    # Запуск Flask сервера
    app.run(host="0.0.0.0", port=PORT)

if __name__ == "__main__":
    asyncio.run(main())
