import os
import re
import pytz
from datetime import datetime
from docx import Document
import subprocess
import logging

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def текущая_дата_лондон():
    return datetime.now(pytz.timezone("Europe/London")).strftime("%d.%m.%Y")

def очистить_имя_файла(text):
    return re.sub(r"[^\w\s-]", "", text, flags=re.UNICODE).strip()

def заменить_плейсхолдеры(doc: Document, текст: str, дата: str):
    for параграф in doc.paragraphs:
        if "Client:" in параграф.text:
            параграф.text = параграф.text.replace("Client:", f"Client: {текст}")
        if "Date:" in параграф.text:
            параграф.text = параграф.text.replace("Date:", f"Date: {дата}")
    for таблица in doc.tables:
        for строка in таблица.rows:
            for ячейка in строка.cells:
                if "Client:" in ячейка.text:
                    ячейка.text = ячейка.text.replace("Client:", f"Client: {текст}")
                if "Date:" in ячейка.text:
                    ячейка.text = ячейка.text.replace("Date:", f"Date: {дата}")

def generate_pdf(путь_к_шаблону: str, текст: str) -> str:
    """
    Заполняет DOCX шаблон, конвертирует его в PDF и сохраняет.
    """
    дата = текущая_дата_лондон()
    имя_файла = очистить_имя_файла(текст) or "результат"
    путь_к_docx = f"{имя_файла}.docx"
    путь_к_pdf = f"{имя_файла}.pdf"

    try:
        doc = Document(путь_к_шаблону)
    except Exception as e:
        logger.error(f"Ошибка открытия шаблона DOCX '{путь_к_шаблону}': {e}")
        raise

    заменить_плейсхолдеры(doc, текст, дата)

    doc.save(путь_к_docx)
    logger.info(f"DOCX файл сохранён: {путь_к_docx}")

    try:
        subprocess.run(
            ["libreoffice", "--headless", "--convert-to", "pdf", путь_к_docx, "--outdir", "."],
            check=True
        )
        logger.info(f"Преобразование в PDF успешно: {путь_к_pdf}")
    except Exception as e:
        logger.error(f"Ошибка конвертации DOCX в PDF: {e}")
        raise

    if not os.path.exists(путь_к_pdf):
        raise FileNotFoundError(f"Файл PDF '{путь_к_pdf}' не найден после конвертации.")

    return путь_к_pdf
