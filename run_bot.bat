@echo off
cd /d "%~dp0"
chcp 65001 > nul
title AI Auto Trading Bot (VN30 / DNSE + Telegram)

echo ======================================================
echo    AI AUTO TRADING BOT - PHASE 1: READ-ONLY MVP
echo ======================================================

if not exist ".venv\Scripts\python.exe" (
    echo [INFO] Dang khoi tao moi truong ao Python .venv...
    python -m venv .venv
    if errorlevel 1 (
        echo [LOI] Khong the tao .venv. Vui long kiem tra Python.
        pause
        exit /b 1
    )
)

call ".venv\Scripts\activate.bat"

echo [INFO] Dang kiem tra va cap nhat thu vien...
python -m pip install -r requirements.txt --quiet

echo [INFO] Dang khoi dong Bot giao dich chung khoan DNSE...
echo [INFO] Nhan Ctrl+C de dung bot.
python main.py

echo.
echo [INFO] Ung dung da dung. Nhan phim bat ky de dong cua so...
pause
