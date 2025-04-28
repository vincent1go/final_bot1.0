import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Updater, CommandHandler, CallbackQueryHandler, MessageHandler, Filters, ConversationHandler, CallbackContext
import datetime
import pytz
import mammoth
from bs4 import BeautifulSoup
from weasyprint import HTML
import os

# Константы
TOKEN = "7511704960:AAFKDWgg2-cAzRxywX1gXK47OQRWJi72qGw"
WEBHOOK_URL = "https://final-bot1-0.onrender.com/webhook"
PORT = 5000

# Настройка логирования
logging.basicConfig(format='%(asctime)s - %(name)s - %(levellevel)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# Состояния диалога
CHOOSING_TEMPLATE, ENTERING_CLIENT_NAME, CHOOSING_DATE_OPTION, ENTERING_DATE = range(4)

def start(update: Update, context: CallbackContext) -> int:
    """Начать диалог и позволить пользователю выбрать шаблон."""
    keyboard = [
        [InlineKeyboardButton("Императив", callback_data='template_imperative')],
        [InlineKeyboardButton("УР", callback_data='template_ur')],
        [InlineKeyboardButton("Маленький мир", callback_data='template_small_world')],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    update.message.reply_text('Пожалуйста, выберите шаблон:', reply_markup=reply_markup)
    return CHOOSING_TEMPLATE

def choose_template(update: Update, context: CallbackContext) -> int:
    """Обработать выбор шаблона."""
    query = update.callback_query
    query.answer()
    template_choice = query.data
    context.user_data['template'] = template_choice
    query.edit_message_text(text=f"Выбранный шаблон: {template_choice}")
    query.message.reply_text('Введите имя клиента:')
    return ENTERING_CLIENT_NAME

def enter_client_name(update: Update, context: CallbackContext) -> int:
    """Сохранить имя клиента и спросить о предпочтении даты."""
    client_name = update.message.text
    context.user_data['client_name'] = client_name
    keyboard = [
        [InlineKeyboardButton("Использовать текущую дату", callback_data='current_date')],
        [InlineKeyboardButton("Указать дату", callback_data='specific_date')],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    update.message.reply_text('Желаете использовать текущую дату или указать свою?', reply_markup=reply_markup)
    return CHOOSING_DATE_OPTION

def choose_date_option(update: Update, context: CallbackContext) -> int:
    """Обработать выбор опции даты."""
    query = update.callback_query
    query.answer()
    date_option = query.data
    if date_option == 'current_date':
        kiev_tz = pytz.timezone('Europe/Kiev')
        current_date = datetime.datetime.now(kiev_tz).strftime('%Y-%m-%d')
        context.user_data['date'] = current_date
        generate_pdf(update, context)
        return ConversationHandler.END
    else:
        query.message.reply_text('Введите дату в формате ГГГГ-ММ-ДД:')
        return ENTERING_DATE

def enter_date(update: Update, context: CallbackContext) -> int:
    """Проверить и сохранить указанную дату, затем сгенерировать PDF."""
    date_str = update.message.text
    try:
        date = datetime.datetime.strptime(date_str, '%Y-%m-%d').strftime('%Y-%m-%d')
        context.user_data['date'] = date
        generate_pdf(update, context)
        return ConversationHandler.END
    except ValueError:
        update.message.reply_text('Неверный формат даты. Введите дату в формате ГГГГ-ММ-ДД:')
        return ENTERING_DATE

def replace_text_in_html(html, client_name, date):
    """Заменить имя клиента и дату в HTML."""
    soup = BeautifulSoup(html, 'html.parser')
    for p in soup.find_all('p'):
        text = p.get_text()
        if 'Client:' in text:
            parts = text.split('Client:', 1)
            if len(parts) > 1:
                p.string = 'Client: ' + client_name
        elif 'Date:' in text or 'DATE:' in text:
            if 'Date:' in text:
                parts = text.split('Date:', 1)
            else:
                parts = text.split('DATE:', 1)
            if len(parts) > 1:
                p.string = parts[0] + date
    return str(soup)

def generate_pdf(update: Update, context: CallbackContext):
    """Сгенерировать PDF из измененного шаблона."""
    try:
        template_name = context.user_data['template']
        client_name = context.user_data['client_name']
        date = context.user_data['date']
        
        template_path = f'templates/{template_name}.docx'
        
        if not os.path.exists(template_path):
            update.message.reply_text('Шаблон не найден.')
            return
        
        with open(template_path, 'rb') as docx_file:
            result = mammoth.convert_to_html(docx_file)
            html = result.value
        
        modified_html = replace_text_in_html(html, client_name, date)
        
        pdf_path = '/tmp/output.pdf'
        HTML(string=modified_html).write_pdf(pdf_path)
        
        with open(pdf_path, 'rb') as pdf_file:
            update.message.reply_document(pdf_file, filename=f'{template_name}_modified.pdf')
        
        os.remove(pdf_path)
    except Exception as e:
        logger.error(f'Ошибка при генерации PDF: {e}')
        update.message.reply_text('Возникла ошибка при генерации PDF.')

def main():
    """Настроить и запустить бота с вебхуком."""
    updater = Updater(TOKEN, use_context=True)
    dp = updater.dispatcher
    
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            CHOOSING_TEMPLATE: [CallbackQueryHandler(choose_template)],
            ENTERING_CLIENT_NAME: [MessageHandler(Filters.text & ~Filters.command, enter_client_name)],
            CHOOSING_DATE_OPTION: [CallbackQueryHandler(choose_date_option)],
            ENTERING_DATE: [MessageHandler(Filters.text & ~Filters.command, enter_date)],
        },
        fallbacks=[],
    )
    
    dp.add_handler(conv_handler)
    
    updater.start_webhook(listen="0.0.0.0",
                          port=PORT,
                          url_path="webhook/" + TOKEN,
                          webhook_url=WEBHOOK_URL + "/" + TOKEN)
    
    updater.idle()

if __name__ == '__main__':
    main()
