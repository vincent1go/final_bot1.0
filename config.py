import os

# Конфигурация бота
BOT_TOKEN = os.environ.get('BOT_TOKEN', "7511704960:AAFKDWgg2-cAzRxywX1gXK47OQRWJi72qGw")
WEBHOOK_URL = os.environ.get('WEBHOOK_URL', "https://final-bot1-0.onrender.com/webhook")
ADMIN_ID = os.environ.get('ADMIN_ID', "")

# Путь к шаблонам DOCX
TEMPLATES = {
    "UR Recruitment LTD": "templates/template_ur.docx",
    "SMALL WORLD RECRUITMENT LTD": "templates/template_small_world.docx",
    "IMPERATIVE CONSULTANTS LTD": "templates/template_imperative.docx"
}

# Проверка существования шаблонов
for name, path in TEMPLATES.items():
    if not os.path.exists(path):
        raise FileNotFoundError(f"Шаблон не найден: {path}")
