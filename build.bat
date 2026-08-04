@echo off
chcp 65001 > nul
title Сборка .exe

cd /d "%~dp0"

echo =====================================
echo   Сборка ОбработкаЗаказов.exe
echo =====================================
echo.

echo Устанавливаю PyInstaller (если ещё не установлен)...
pip install pyinstaller openpyxl

echo.
echo Собираю exe из gui.py...
pyinstaller --onefile --windowed --name "ОбработкаЗаказов" gui.py

echo.
echo =====================================
echo Готово!
echo.
echo Файл: dist\ОбработкаЗаказов.exe
echo.
echo Перед запуском положите рядом с exe:
echo   - settings.json
echo   - stores.json
echo Папки orders, processed_orders и logs
echo создадутся автоматически при первом запуске.
echo =====================================
echo.

pause
