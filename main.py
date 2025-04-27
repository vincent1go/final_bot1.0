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

# Создаем объект Application
application = Application.builder().token(config.BOT_TOKEN).build()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "👋 *Привет! Чтобы создать документ, напиши /generate.*",
        parse_mode="Markdown"
    )

async def generate(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = "📄 *Выберите шаблон:*"
    keyboard = [[InlineKeyboardButton(name, callback_data=f"template_{name}")] for name in config.TEMPLATES.keys()]
    keyboard.append([InlineKeyboardButton("❌ Отмена", callback_data="cancel")])
    await update.message.reply_text(message, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))
    context.user_data["state"] = SELECTING_TEMPLATE

async def main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    message = "🏠 *Главное меню*\n\nВыберите действие:"
    keyboard = [
        [InlineKeyboardButton("📄 Выбрать шаблон", callback_data="select_template")],
        [InlineKeyboardButton("ℹ️ О боте", callback_data="about")]
    ]
    await query.message.edit_text(message, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

async def select_template(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    message = "📄 *Выберите шаблон:*"
    keyboard = [[InlineKeyboardButton(name, callback_data=f"template_{name}")] for name in config.TEMPLATES.keys()]
    keyboard.append([InlineKeyboardButton("❌ Отмена", callback_data="cancel")])
    await query.message.edit_text(message, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))
    context.user_data["state"] = SELECTING_TEMPLATE

async def template_selected(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    name = query.data.replace("template_", "")
    if name not in config.TEMPLATES:
        await query.message.edit_text("⚠️ Ошибка: Шаблон не найден.")
        return
    context.user_data["template"] = name
    context.user_data["state"] = ENTERING_TEXT
    await query.message.edit_text(
        f"✅ Выбран шаблон: *{name}*\n\nВведите имя клиента:",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔄 Сменить шаблон", callback_data="select_template")],
            [InlineKeyboardButton("❌ Отмена", callback_data="cancel")],
        ])
    )

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    context.user_data.clear()
    await query.message.edit_text(
        "❌ Отменено. Выберите действие:",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("📄 Выбрать шаблон", callback_data="select_template")],
            [InlineKeyboardButton("ℹ️ О боте", callback_data="about")]
        ])
    )

async def receive_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if "template" not in context.user_data:
        await update.message.reply_text(
            "⚠️ Сначала выберите шаблон через меню.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🏠 Главное меню", callback_data="main_menu")]
            ])
        )
        return

    client_name = update.message.text.strip()
    template_name = context.user_data["template"]
    try:
        template_path = config.TEMPLATES[template_name]
        pdf_path = generate_pdf(template_path, client_name)
        filename = f"{client_name}.pdf"
        with open(pdf_path, "rb") as f:
            await update.message.reply_document(document=f, filename=filename)

        if os.path.exists(pdf_path):
            os.remove(pdf_path)

        await update.message.reply_text(
            "✅ Документ успешно создан!\n\nМожете ввести другое имя клиента для создания нового документа.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📄 Сменить шаблон", callback_data="select_template")],
                [InlineKeyboardButton("🏠 Главное меню", callback
