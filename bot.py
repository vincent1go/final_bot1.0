import os
import pytz
from datetime import datetime
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackContext
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

# Функция для генерации PDF
def generate_pdf(client_name, date_str):
    filename = f"{client_name}.pdf"
    c = canvas.Canvas(filename, pagesize=letter)
    y = 750  # Начальная позиция по Y
    line_height = 15  # Высота строки

    # Заголовок и информация о компании
    c.drawString(100, y, "RAFIQ Uziyan")
    y -= line_height
    c.drawString(100, y, "Company number: 14593456")
    y -= line_height
    c.drawString(100, y, "38 Brockhurst Road, Birmingham, England, B36 8JB")
    y -= line_height
    c.drawString(100, y, "https://ur-recruitment.com/")
    y -= line_height
    c.drawString(100, y, "UR RECRUITMENT LTD")
    y -= line_height
    c.drawString(100, y, "CONTRACT")
    y -= line_height * 2

    # Предмет договора
    c.drawString(100, y, "SUBJECT OF THE AGREEMENT")
    y -= line_height
    c.drawString(100, y, "1.1. Pursuant to this Agreement:")
    y -= line_height
    c.drawString(100, y, "Contractor - UR RECRUITMENT LTD")
    y -= line_height
    c.drawString(100, y, "Company number 14593456, 38 Brockhurst Road, Birmingham, England, B36 8JB")
    y -= line_height
    c.drawString(100, y, f"Client: {client_name}")
    y -= line_height
    c.drawString(100, y, "The Contractor personally, at its own risk, provides the Client with services listed")
    y -= line_height
    c.drawString(100, y, "in paragraph 1.2 of this Agreement (hereinafter referred to as 'Services') within")
    y -= line_height
    c.drawString(100, y, "the period agreed by the Parties. The Client accepts the Services provided by")
    y -= line_height
    c.drawString(100, y, "the Contractor and pays for the Services within the time, manner, and amount")
    y -= line_height
    c.drawString(100, y, "established by this Agreement.")
    y -= line_height
    c.drawString(100, y, "1.2. Services provided by the Contractor to the Client in accordance with")
    y -= line_height
    c.drawString(100, y, "paragraph 1.1 of this Agreement:")
    y -= line_height
    c.drawString(100, y, "1.2.1. Assistance in employment abroad.")
    y -= line_height * 2

    # Процедура выполнения
    c.drawString(100, y, "PROCEDURE FOR PERFORMANCE OF THE AGREEMENT")
    y -= line_height
    c.drawString(100, y, "2.1. The Contractor collects the information required for the provision of")
    y -= line_height
    c.drawString(100, y, "Services through its independent search, selection, systematization, and analysis.")
    # Добавьте остальной текст аналогично (для краткости опущены дополнительные страницы)

    # Дата внизу
    c.drawString(100, 100, f"Date: {date_str}")
    c.save()
    return filename

# Команда /start
def start(update: Update, context: CallbackContext) -> None:
    reply_keyboard = [['📄 Сгенерировать PDF']]
    update.message.reply_text(
        '👋 Привет! Я бот для создания PDF-договоров.\n'
        'Нажми "📄 Сгенерировать PDF", чтобы начать!',
        reply_markup=ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True, resize_keyboard=True)
    )

# Обработка сообщений
def handle_message(update: Update, context: CallbackContext) -> None:
    text = update.message.text
    step = context.user_data.get('step', '')

    try:
        if text == '📄 Сгенерировать PDF':
            update.message.reply_text(
                '✍️ Введите имя клиента:',
                reply_markup=ReplyKeyboardRemove()
            )
            context.user_data['step'] = 'waiting_for_name'

        elif step == 'waiting_for_name':
            context.user_data['client_name'] = text.strip()
            update.message.reply_text(
                '📅 Введите дату (ДД.ММ.ГГГГ) или напишите /now для текущей даты по Киеву:'
            )
            context.user_data['step'] = 'waiting_for_date'

        elif step == 'waiting_for_date':
            if text == '/now':
                tz = pytz.timezone('Europe/Kiev')
                date_str = datetime.now(tz).strftime('%d.%m.%Y')
            else:
                # Простая проверка формата даты
                try:
                    datetime.strptime(text, '%d.%m.%Y')
                    date_str = text
                except ValueError:
                    update.message.reply_text('❌ Неверный формат даты! Используйте ДД.ММ.ГГГГ или /now.')
                    return

            client_name = context.user_data['client_name']
            update.message.reply_text('⏳ Генерирую PDF...')
            pdf_filename = generate_pdf(client_name, date_str)
            with open(pdf_filename, 'rb') as pdf_file:
                update.message.reply_document(pdf_file, filename=f"{client_name}.pdf")
            os.remove(pdf_filename)
            update.message.reply_text('✅ PDF готов! Можете создать ещё один.')
            context.user_data.clear()
            start(update, context)

    except Exception as e:
        update.message.reply_text('⚠️ Произошла ошибка. Попробуйте снова.')
        start(update, context)

# Основная функция
def main() -> None:
    updater = Updater(os.getenv('TELEGRAM_BOT_TOKEN'))
    dispatcher = updater.dispatcher
    dispatcher.add_handler(CommandHandler("start", start))
    dispatcher.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_message))
    updater.start_polling()
    updater.idle()

if __name__ == '__main__':
    main()
