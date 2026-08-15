@echo off
setlocal
chcp 65001 > nul
title Обработка заказов - Веб-дашборд

cd /d "%~dp0"

call :prepare_python
if errorlevel 1 (
    echo.
    pause
    exit /b 1
)

echo.
echo =====================================
echo   Запуск веб-дашборда
echo   Откроется на http://localhost:3000
echo   Для остановки закройте это окно
echo =====================================
echo.

python -m reflex run
set "APP_EXIT=%errorlevel%"
if not "%APP_EXIT%"=="0" (
    echo.
    echo ОШИБКА: дашборд завершился с ошибкой.
)

pause
exit /b %APP_EXIT%

:prepare_python
where python >nul 2>nul
if errorlevel 1 (
    echo.
    echo ОШИБКА: Python не найден.
    echo Установите 64-битный Python 3.10+ с https://python.org
    echo При установке обязательно отметьте "Add python.exe to PATH".
    exit /b 1
)

python -c "import sys; raise SystemExit(0 if (3, 10) <= sys.version_info[:2] <= (3, 14) else 1)" >nul 2>nul
if errorlevel 1 (
    echo.
    echo ОШИБКА: требуется Python версии от 3.10 до 3.14.
    python --version
    exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
    echo Первый запуск: создаю виртуальное окружение...
    python -m venv .venv
    if errorlevel 1 (
        echo ОШИБКА: не удалось создать виртуальное окружение .venv.
        exit /b 1
    )
)

call ".venv\Scripts\activate.bat"
if errorlevel 1 (
    echo ОШИБКА: не удалось активировать виртуальное окружение .venv.
    exit /b 1
)

echo Проверка зависимостей...
python -m pip install --disable-pip-version-check -q -r requirements.txt
if errorlevel 1 (
    echo.
    echo ОШИБКА: не удалось установить зависимости.
    echo Проверьте подключение к интернету и повторите запуск.
    exit /b 1
)

exit /b 0
