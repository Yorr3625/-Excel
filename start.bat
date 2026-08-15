@echo off
setlocal
chcp 65001 > nul
title Обработка заказов v1.1

cd /d "%~dp0"

call :prepare_python
if errorlevel 1 (
    echo.
    pause
    exit /b 1
)

:menu
cls
echo.
echo =====================================
echo        ОБРАБОТКА ЗАКАЗОВ v1.1
echo =====================================
echo.
echo 1. Запустить обработку заказа
echo 2. Открыть папку data\orders
echo 3. Открыть data\processed_orders
echo 4. Открыть настройки
echo 5. Выход
echo.
echo =====================================
echo.

set /p choice=Выберите действие:

if "%choice%"=="1" goto start
if "%choice%"=="2" goto orders
if "%choice%"=="3" goto ready
if "%choice%"=="4" goto settings
if "%choice%"=="5" exit /b 0
goto menu

:start
cls
echo.
echo =====================================
echo       Запуск обработки заказа
echo =====================================
echo.

if not exist "main.py" (
    echo.
    echo ОШИБКА: файл main.py не найден.
    echo.
    pause
    goto menu
)

python main.py

echo.
echo =====================================
echo       Обработка завершена
echo =====================================
echo.
pause
goto menu

:orders
if not exist "%~dp0data\orders" mkdir "%~dp0data\orders"
explorer "%~dp0data\orders"
goto menu

:ready
if not exist "%~dp0data\processed_orders" mkdir "%~dp0data\processed_orders"
explorer "%~dp0data\processed_orders"
goto menu

:settings
if not exist "%~dp0config\settings.json" (
    echo {> "%~dp0config\settings.json"
    echo     "open_file_after_processing": true,>> "%~dp0config\settings.json"
    echo     "open_folder_after_processing": false>> "%~dp0config\settings.json"
    echo }>> "%~dp0config\settings.json"
)
notepad "%~dp0config\settings.json"
goto menu

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
