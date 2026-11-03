#!/bin/bash
# Запуск с микрофоном и голосом. Лучше в наушниках.
cd "$(dirname "$0")"
source .venv/bin/activate
python main.py
read -p "Нажми Enter, чтобы закрыть"
