#!/bin/bash
# Устанавливаем системные зависимости для weasyprint
apt-get update
apt-get install -y libpango-1.0-0 libpangoft2-1.0-0 libcairo2 libgdk-pixbuf2.0-0 libffi-dev
# Устанавливаем Python-зависимости
pip install -r requirements.txt
