import asyncio
from flask import Flask, request
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)
from io import BytesIO
from fpdf import FPDF
from datetime import datetime

# === ТВОИ ДАННЫЕ ===
TOKEN = "7511704960:AAFKDWgg2-cAzRxywX1gXK47OQRWJi72qGw"
WEBHOOK_URL = "https://final-bot1-0.onrender.com/webhook"
PORT = 5000

# Flask сервер
app = Flask(__name__)

# Telegram приложение
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
        "👋 Привет!\n\nЯ могу сгенерировать красивый PDF файл для тебя!\nВыбери действие ниже 👇",
        reply_markup=reply_markup,
    )

# Генерация PDF
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
    pdf.output(buffer)
    buffer.seek(0)
    return buffer

# Обработка кнопок
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
            "🤖 Этот бот создан для генерации PDF документов на лету!\n\n"
            "Создатель: ТЫ 🔥"
        )
    elif query.data == "generate_pdf":
        user_name = query.from_user.full_name
        pdf_buffer = await generate_pdf
