@echo off
setlocal
chcp 65001 > nul
title Доступ к дашборду с другого компьютера

cd /d "%~dp0"

call :prepare_python
if errorlevel 1 (
    echo.
    pause
    exit /b 1
)

if not exist "tools" mkdir "tools"

if not exist "tools\cloudflared.exe" (
    echo.
    echo Первый запуск: скачиваю cloudflared - утилиту для временной ссылки...
    curl -L -o "tools\cloudflared.exe" "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe"
    if errorlevel 1 (
        echo.
        echo ОШИБКА: не удалось скачать cloudflared. Проверьте подключение к интернету.
        pause
        exit /b 1
    )
)

echo.
echo =====================================
echo   Собираю дашборд для раздачи...
echo   Это медленнее обычного запуска - подождите.
echo =====================================
echo.

start "Дашборд (не закрывайте это окно)" cmd /k "python -m reflex run --env prod --single-port --backend-port 8080"

echo Жду, пока дашборд поднимется на порту 8080...

set /a WAIT_COUNT=0
:wait_loop
curl -sf http://localhost:8080/ping >nul 2>nul
if not errorlevel 1 goto wait_done
set /a WAIT_COUNT+=1
if %WAIT_COUNT% GEQ 100 (
    echo.
    echo Дашборд долго не отвечает на порту 8080.
    echo Первая сборка может занимать несколько минут - если окно
    echo "Дашборд" ещё собирает и не показывает ошибку, просто
    echo подождите и запустите share_dashboard.bat ещё раз.
    pause
    exit /b 1
)
timeout /t 3 >nul
goto wait_loop
:wait_done

echo.
echo =====================================
echo   Готово. Открываю временную ссылку...
echo   Адрес появится ниже, вида https://....trycloudflare.com
echo   Откройте его на другом компьютере или телефоне.
echo.
echo   Ссылка работает, пока открыты ЭТО окно и окно "Дашборд".
echo   Закройте оба окна, чтобы остановить общий доступ.
echo =====================================
echo.

"tools\cloudflared.exe" tunnel --url http://localhost:8080

pause
exit /b 0

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
