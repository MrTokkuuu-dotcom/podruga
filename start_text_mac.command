#!/bin/bash
# Проверка без микрофона: переписка в окне.
cd "$(dirname "$0")"
source .venv/bin/activate
python main.py --text
read -p "Нажми Enter, чтобы закрыть"
