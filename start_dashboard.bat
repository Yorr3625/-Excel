@echo off
chcp 65001 > nul
title Обработка заказов - Веб-дашборд

cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 (
    echo.
    echo ОШИБКА: Python не найден.
    echo Установите Python 3.10+ с https://python.org
    echo При установке обязательно отметьте "Add python.exe to PATH".
    echo.
    pause
    exit /b 1
)

if not exist ".venv" (
    echo Первый запуск: создаю виртуальное окружение...
    python -m venv .venv
)

call ".venv\Scripts\activate.bat"

echo Проверка зависимостей...
pip install -q -r requirements.txt

echo.
echo =====================================
echo   Запуск веб-дашборда
echo   Откроется на http://localhost:3000
echo   Для остановки закройте это окно
echo =====================================
echo.

python -m reflex run

pause
