# 📄 Telegram DOCX to PDF Bot

Генератор PDF-документов по шаблонам Word (.docx) через Telegram-бота!

## 🚀 Возможности:

- Выбор шаблона через Telegram.
- Ввод имени клиента.
- Автоматическая генерация готового PDF-документа.
- Хостинг через Docker и Render.

## 📦 Структура:

- `main.py` — основной код бота.
- `docx_generator.py` — генерация PDF из шаблонов DOCX.
- `config.py` — конфигурации токена, webhook и шаблонов.
- `templates/` — все DOCX шаблоны.

## 🛠️ Установка:

```bash
docker build -t telegram-docx-bot .
docker run -d -p 5000:8080 telegram-docx-bot
