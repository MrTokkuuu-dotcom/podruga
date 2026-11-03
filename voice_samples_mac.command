#!/bin/bash
# Прослушать 8 голосов подряд и выбрать любимый.
cd "$(dirname "$0")"
source .venv/bin/activate
python voice_samples.py
read -p "Нажми Enter, чтобы закрыть"
