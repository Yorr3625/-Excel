@echo off
chcp 65001 > nul
title Обработка заказов v1.1

cd /d "%~dp0"


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
if "%choice%"=="5" exit


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
    echo ОШИБКА!
    echo Файл main.py не найден.
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

if not exist "%~dp0data\orders" (

    mkdir "%~dp0data\orders"

)


explorer "%~dp0data\orders"


goto menu



:ready

if not exist "%~dp0data\processed_orders" (

    mkdir "%~dp0data\processed_orders"

)


explorer "%~dp0data\processed_orders"


goto menu



:settings

if not exist "%~dp0config\settings.json" (

    echo {
    echo     "open_file_after_processing": true,
    echo     "open_folder_after_processing": false
    echo } > "%~dp0config\settings.json"

)


notepad "%~dp0config\settings.json"


goto menu