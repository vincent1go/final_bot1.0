import os
import tempfile
import subprocess
from docx import Document
import asyncio

async def generate_pdf(client_name: str, date_str: str) -> bytes:
    """
    Создаёт .docx по шаблону, подставляет переменные и конвертирует в PDF.
    Возвращает PDF в виде байтового потока.
    """

    # Путь до шаблона .docx (он должен лежать рядом с этим скриптом)
    template_path = os.path.join(os.path.dirname(__file__), "template.docx")

    # Загружаем шаблон
    doc = Document(template_path)

    # Заменяем плейсхолдеры {CLIENT} и {DATE} во всех абзацах
    for paragraph in doc.paragraphs:
        if "{CLIENT}" in paragraph.text or "{DATE}" in paragraph.text:
            for run in paragraph.runs:
                run.text = run.text.replace("{CLIENT}", client_name).replace("{DATE}", date_str)

    # При необходимости заменить и в таблицах
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                for paragraph in cell.paragraphs:
                    if "{CLIENT}" in paragraph.text or "{DATE}" in paragraph.text:
                        for run in paragraph.runs:
                            run.text = run.text.replace("{CLIENT}", client_name).replace("{DATE}", date_str)

    # Сохраняем результат во временный .docx-файл
    with tempfile.NamedTemporaryFile(delete=False, suffix=".docx") as tmp_docx:
        doc.save(tmp_docx.name)
        temp_docx_path = tmp_docx.name

    # Создаём временную директорию для конвертации
    with tempfile.TemporaryDirectory() as tmp_dir:
        # Запускаем конвертацию LibreOffice (headless) в фоновом потоке
        loop = asyncio.get_running_loop()
        cmd = [
            "soffice", "--headless", "--convert-to", "pdf", 
            "--outdir", tmp_dir, temp_docx_path
        ]
        # Выполняем синхронный вызов в отдельном потоке, чтобы не блокировать asyncio
        await loop.run_in_executor(None, subprocess.run, cmd, {"check": True})

        # Ищем сгенерированный PDF (имя совпадает с .docx, но .pdf)
        base = os.path.splitext(os.path.basename(temp_docx_path))[0]
        pdf_path = os.path.join(tmp_dir, base + ".pdf")

        # Читаем PDF как байты
        with open(pdf_path, "rb") as f:
            pdf_bytes = f.read()

    # Удаляем временный .docx-файл
    try:
        os.remove(temp_docx_path)
    except OSError:
        pass

    return pdf_bytes

