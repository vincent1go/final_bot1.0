import os
import io
import pytz
from datetime import datetime
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
    CallbackQueryHandler
)
from PyPDF2 import PdfReader, PdfWriter
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

# Load environment variables
load_dotenv()

# Constants
TIMEZONE = pytz.timezone('Europe/Kiev')
FONT_PATH = "arial.ttf"  # You need to provide Arial.ttf file
TEMPLATES_DIR = "templates"
TEMP_DIR = "temp"

# Register Arial font
try:
    pdfmetrics.registerFont(TTFont("ArialMT", FONT_PATH))
except:
    print("Warning: Arial font not found. Using default font.")

class PDFBot:
    def __init__(self):
        self.user_data = {}

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Send a message when the command /start is issued."""
        keyboard = [
            [InlineKeyboardButton("📄 Выбрать шаблон", callback_data='select_template')],
            [InlineKeyboardButton("ℹ️ Помощь", callback_data='help')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            '👋 Привет! Я бот для редактирования PDF шаблонов.\n\n'
            'Выберите действие:',
            reply_markup=reply_markup
        )

    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Send a help message."""
        await update.message.reply_text(
            '❓ Помощь:\n\n'
            '1. Нажмите "Выбрать шаблон" для выбора PDF шаблона\n'
            '2. Введите имя клиента\n'
            '3. Получите готовый PDF файл\n'
            '4. При необходимости измените дату или выберите другой шаблон'
        )

    async def list_templates(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """List available templates."""
        templates = [f for f in os.listdir(TEMPLATES_DIR) if f.endswith('.pdf')]
        if not templates:
            await update.callback_query.edit_message_text("Шаблоны не найдены в папке templates/")
            return

        keyboard = []
        for template in templates:
            keyboard.append([InlineKeyboardButton(template, callback_data=f'template_{template}')])
        
        keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data='back_to_start')])
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.callback_query.edit_message_text(
            '📂 Доступные шаблоны:',
            reply_markup=reply_markup
        )

    async def select_template(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle template selection."""
        query = update.callback_query
        template_name = query.data.replace('template_', '')
        
        chat_id = query.message.chat_id
        self.user_data[chat_id] = {'template': template_name}
        
        await query.edit_message_text(
            f'Выбран шаблон: {template_name}\n\n'
            'Теперь введите имя клиента:'
        )

    async def handle_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle user text input (client name)."""
        chat_id = update.message.chat_id
        client_name = update.message.text
        
        if chat_id not in self.user_data or 'template' not in self.user_data[chat_id]:
            await update.message.reply_text("Пожалуйста, сначала выберите шаблон через меню.")
            return
        
        self.user_data[chat_id]['client_name'] = client_name
        
        # Generate PDF
        template_path = os.path.join(TEMPLATES_DIR, self.user_data[chat_id]['template'])
        output_path = os.path.join(TEMP_DIR, f"{client_name}.pdf")
        
        try:
            self.edit_pdf(template_path, output_path, client_name)
            
            with open(output_path, 'rb') as f:
                await update.message.reply_document(
                    document=f,
                    filename=f"{client_name}.pdf",
                    caption=f"Готовый документ для {client_name}"
                )
            
            # Show options after generation
            keyboard = [
                [InlineKeyboardButton("✏️ Изменить дату", callback_data='change_date')],
                [InlineKeyboardButton("📄 Выбрать другой шаблон", callback_data='select_template')],
                [InlineKeyboardButton("🔄 Сгенерировать еще", callback_data='generate_another')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.message.reply_text(
                'Выберите действие:',
                reply_markup=reply_markup
            )
            
        except Exception as e:
            await update.message.reply_text(f"Ошибка при генерации PDF: {str(e)}")

    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle all callback queries."""
        query = update.callback_query
        data = query.data
        
        if data == 'select_template':
            await self.list_templates(update, context)
        elif data == 'help':
            await self.help_command(update, context)
        elif data == 'back_to_start':
            await self.start(update, context)
        elif data.startswith('template_'):
            await self.select_template(update, context)
        elif data == 'change_date':
            await query.edit_message_text("Введите новую дату в любом формате:")
            self.user_data[query.message.chat_id]['awaiting_date'] = True
        elif data == 'generate_another':
            chat_id = query.message.chat_id
            if 'template' in self.user_data.get(chat_id, {}):
                await query.edit_message_text("Введите имя следующего клиента:")
            else:
                await query.edit_message_text("Пожалуйста, сначала выберите шаблон.")
                await self.list_templates(update, context)

    def edit_pdf(self, input_path, output_path, client_name):
        """Edit the PDF with new client name and current date."""
        # Get current date in Kiev timezone
        now = datetime.now(TIMEZONE)
        date_str = now.strftime("%d.%m.%Y")
        date_str_upper = now.strftime("%d.%m.%Y").upper()
        
        # Read the input PDF
        reader = PdfReader(input_path)
        writer = PdfWriter()
        
        # Get first page
        page = reader.pages[0]
        
        # Create a canvas to draw the new text
        packet = io.BytesIO()
        can = canvas.Canvas(packet, pagesize=(page.mediabox.width, page.mediabox.height))
        
        # Set font (Arial MT if available)
        try:
            can.setFont("ArialMT", 12)
        except:
            can.setFont("Helvetica", 12)
        
        # Draw new text at the same positions (adjust coordinates as needed)
        # Client:
        can.drawString(100, 100, f"Client: {client_name}")
        # Date:
        can.drawString(100, 80, f"Date: {date_str}")
        # DATE:
        can.drawString(100, 60, f"DATE: {date_str_upper}")
        
        can.save()
        
        # Move to the beginning of the StringIO buffer
        packet.seek(0)
        overlay = PdfReader(packet).pages[0]
        
        # Merge the overlay with the original page
        page.merge_page(overlay)
        
        # Add the modified page to the writer
        writer.add_page(page)
        
        # Add remaining pages if any
        for p in reader.pages[1:]:
            writer.add_page(p)
        
        # Write the result to the output file
        with open(output_path, 'wb') as f:
            writer.write(f)

def main() -> None:
    """Run the bot."""
    # Create directories if they don't exist
    os.makedirs(TEMPLATES_DIR, exist_ok=True)
    os.makedirs(TEMP_DIR, exist_ok=True)
    
    bot = PDFBot()
    
    application = ApplicationBuilder().token(os.getenv('TELEGRAM_TOKEN')).build()
    
    # Register handlers
    application.add_handler(CommandHandler("start", bot.start))
    application.add_handler(CommandHandler("help", bot.help_command))
    application.add_handler(CallbackQueryHandler(bot.handle_callback))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, bot.handle_text))
    
    # Set up webhook if running on Render
    if 'RENDER' in os.environ:
        webhook_url = os.getenv('WEBHOOK_URL') + '/telegram'
        application.run_webhook(
            listen="0.0.0.0",
            port=int(os.environ.get('PORT', 10000)),
            url_path='telegram',
            webhook_url=webhook_url
        )
    else:
        # For local development
        application.run_polling()

if __name__ == '__main__':
    main()
