#!/bin/bash
# Подбор порога микрофона. Выход — Ctrl+C.
cd "$(dirname "$0")"
source .venv/bin/activate
python mic_test.py
