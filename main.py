import os
import logging
from telegram.ext import Application, CommandHandler, MessageHandler, filters
from docx_generator import generate_pdf

# Логирование (по желанию для отладки)
logging.basicConfig(level=logging.INFO)

# Обработчик команды /start
async def start(update, context):
    await update.message.reply_text("Введите имя клиента для создания документа:")

# Обработчик текстовых сообщений: считаем любой ввод именем клиента
async def create_document(update, context):
    client_name = update.message.text.strip()
    if not client_name:
        await update.message.reply_text("Имя не может быть пустым.")
        return

    # Получаем текущую дату в нужном формате, например:
    from datetime import datetime
    date_str = datetime.now().strftime("%d.%m.%Y")

    try:
        # Генерируем PDF-файл по DOCX-шаблону
        pdf_bytes = await generate_pdf(client_name, date_str)
        # Отправляем PDF пользователю
        await update.message.reply_document(pdf_bytes, filename=f"Document_{client_name}.pdf")
    except Exception as e:
        logging.exception("Ошибка при генерации документа")
        await update.message.reply_text(f"Ошибка при создании документа: {e}")

def main():
    # Токен бота и URL вебхука (область Render задаётся через переменную окружения)
    TOKEN = os.environ["BOT_TOKEN"]
    SERVICE_URL = os.environ.get("RENDER_SERVICE")  # например, myservice.onrender.com
    PORT = int(os.environ.get("PORT", 443))

    # Сборка приложения с асинхронным запуском
    # Регистрируем функцию on_startup для установки вебхука
    async def on_startup(app):
        webhook_url = f"https://{SERVICE_URL}/{TOKEN}"
        info = await app.bot.get_webhook_info()
        if info.url != webhook_url:
            # Асинхронно устанавливаем вебхук (согласно примеру использования post_init в PTB v21)&#8203;:contentReference[oaicite:0]{index=0}
            await app.bot.set_webhook(url=webhook_url)
            logging.info(f"Webhook установлен: {webhook_url}")

    app = Application.builder().token(TOKEN).post_init(on_startup).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, create_document))

    # Запускаем приложение через Webhook. 
    # Используем url_path (а не webhook_path) и передаём полный webhook_url&#8203;:contentReference[oaicite:1]{index=1}.
    app.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        url_path=TOKEN,                                  # путь URL, совпадает с токеном
        webhook_url=f"https://{SERVICE_URL}/{TOKEN}"
    )

if __name__ == "__main__":
    main()

