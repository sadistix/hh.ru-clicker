@echo off
REM Скрипт запуска Telegram бота с виртуальным окружением (Windows)

REM Проверка наличия виртуального окружения
if not exist venv (
    echo ❌ Виртуальное окружение не найдено!
    echo Запустите сначала: setup.bat
    pause
    exit /b 1
)

REM Активация виртуального окружения
call venv\Scripts\activate.bat

REM Проверка токена
if "%TELEGRAM_BOT_TOKEN%"=="" (
    echo ⚠️  TELEGRAM_BOT_TOKEN не установлен!
    echo Установите токен: set TELEGRAM_BOT_TOKEN=ваш_токен
    echo.
    set /p token="Введите токен Telegram бота: "
    set TELEGRAM_BOT_TOKEN=%token%
)

REM Запуск бота
echo 🤖 Запускаю Telegram бота...
python telegram_bot.py

pause
