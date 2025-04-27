import os
import re
from docx import Document
from datetime import datetime
import pytz
import subprocess

def текущая_дата_лондон():
    return datetime.now(pytz.timezone("Europe/London")).strftime("%d.%m.%Y")

def очистить_имя_файла(text):
    return re.sub(r"[^\w\s-]", "", text, flags=re.UNICODE).strip()

def generate_pdf(путь_к_шаблону: str, текст: str) -> str:
    дата = текущая_дата_лондон()
    имя_файла = очистить_имя_файла(текст) or "результат"
    путь_к_временному_файлу = f"{имя_файла}.docx"
    путь_к_выходному_файлу = f"{имя_файла}.pdf"

    doc = Document(путь_к_шаблону)

    for параграф in doc.paragraphs:
        if "{CLIENT}" in параграф.text:
            параграф.text = параграф.text.replace("{CLIENT}", текст)
        if "{DATE}" in параграф.text:
            параграф.text = параграф.text.replace("{DATE}", дата)

    for таблица in doc.tables:
        for строка in таблица.rows:
            for ячейка in строка.cells:
                if "{CLIENT}" in ячейка.text:
                    ячейка.text = ячейка.text.replace("{CLIENT}", текст)
                if "{DATE}" in ячейка.text:
                    ячейка.text = ячейка.text.replace("{DATE}", дата)

    doc.save(путь_к_временному_файлу)

    try:
        subprocess.run([
            "libreoffice",
            "--headless",
            "--convert-to",
            "pdf",
            "--outdir",
            ".",
            путь_к_временному_файлу
        ], check=True)
    except subprocess.CalledProcessError as e:
        raise Exception(f"Ошибка конвертации в PDF: {e}")

    if os.path.exists(путь_к_временному_файлу):
        os.remove(путь_к_временному_файлу)

    return путь_к_выходному_файлу
