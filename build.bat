@echo off
chcp 65001 > nul
title Сборка Обработка заказов.exe

cd /d "%~dp0"

echo.
echo =====================================
echo      Сборка Обработка заказов.exe
echo =====================================
echo.

echo Проверка PyInstaller (если не установлен)...
pip install pyinstaller openpyxl

echo.
echo Создание exe из gui.py...
pyinstaller --onefile --windowed --name "Обработка заказов" gui.py

echo.
echo =====================================
echo Готово!
echo.
echo Файл создан:
echo dist\Обработка заказов.exe
echo.
echo Не забудьте положить рядом с exe:
echo   - settings.json
echo   - stores.json
echo.
echo Также необходимы папки:
echo   - orders
echo   - processed_orders
echo   - logs
echo.
echo Нажмите любую клавишу для выхода.
echo =====================================
echo.

pause