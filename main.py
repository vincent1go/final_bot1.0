import os
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters
)
import config
from docx_generator import generate_pdf

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Состояния для контекста пользователя
SELECTING_TEMPLATE = 1
ENTERING_TEXT = 2

# --- Обработчики команд и колбэков ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "👋 *Привет! Чтобы создать документ, напиши /generate.*",
        parse_mode="Markdown"
    )

async def generate(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    keyboard = [[InlineKeyboardButton(name, callback_data=f"template_{name}")] for name in config.TEMPLATES]
    keyboard.append([InlineKeyboardButton("❌ Отмена", callback_data="cancel")])
    await update.message.reply_text(
        "📄 *Выберите шаблон:*",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    context.user_data["state"] = SELECTING_TEMPLATE

async def select_template(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    keyboard = [[InlineKeyboardButton(name, callback_data=f"template_{name}")] for name in config.TEMPLATES]
    keyboard.append([InlineKeyboardButton("❌ Отмена", callback_data="cancel")])
    await query.message.edit_text(
        "📄 *Выберите шаблон:*",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
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
        "❌ Отменено. Чтобы начать снова, нажмите /start",
        parse_mode="Markdown"
    )

async def receive_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if "template" not in context.user_data:
        await update.message.reply_text(
            "⚠️ Сначала выберите шаблон через /generate.",
            parse_mode="Markdown"
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
        os.remove(pdf_path)
        await update.message.reply_text(
            "✅ Документ успешно создан! Напишите новое имя клиента или /generate для смены шаблона.",
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.error(f"Ошибка при создании документа: {e}")
        await update.message.reply_text("❌ Ошибка при создании документа.")

# --- Запуск бота с webhook ---
def main() -> None:
    # Создаем приложение
    application = Application.builder().token(config.BOT_TOKEN).build()

    # Регистрируем обработчики
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("generate", generate))
    application.add_handler(CallbackQueryHandler(select_template, pattern="^select_template$"))
    application.add_handler(CallbackQueryHandler(template_selected, pattern="^template_"))
    application.add_handler(CallbackQueryHandler(cancel, pattern="^cancel$"))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, receive_text))

    # Устанавливаем webhook
    application.bot.set_webhook(url=config.WEBHOOK_URL)
    port = int(os.environ.get("PORT", 5000))

    # Запускаем webhook-сервер
    application.run_webhook(
        listen="0.0.0.0",
        port=port,
        webhook_path="/webhook"
    )

if __name__ == "__main__":
    main()

