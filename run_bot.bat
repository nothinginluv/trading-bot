@echo off
chcp 65001 > nul
title AI Auto Trading Bot (VN30 / DNSE + Telegram)
echo ======================================================
echo    AI AUTO TRADING BOT — PHASE 1: READ-ONLY MVP
echo ======================================================

if not exist .venv (
    echo [INFO] Tao moi moi truong ao Python (.venv)...
    python -m venv .venv
)

call .venv\Scripts\activate.bat

echo [INFO] Kiem tra va cai dat thu vien...
pip install -r requirements.txt --quiet

echo [INFO] Khoi dong bot giao dich...
python main.py

pause
