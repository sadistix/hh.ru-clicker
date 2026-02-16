# Виртуальное окружение

## Зачем нужно виртуальное окружение?

Виртуальное окружение изолирует зависимости проекта от системных библиотек Python. Это позволяет:
- Избежать конфликтов версий пакетов
- Легко воспроизвести окружение на другой машине
- Сохранить систему в чистоте

## Быстрая установка

### Автоматическая установка (рекомендуется)

**Linux/Mac:**
```bash
chmod +x setup.sh
./setup.sh
```

**Windows:**
```bash
setup.bat
```

Скрипт автоматически создаст виртуальное окружение и установит все зависимости.

## Ручная установка

### 1. Создание виртуального окружения

**Linux/Mac:**
```bash
python3 -m venv venv
```

**Windows:**
```bash
python -m venv venv
```

### 2. Активация виртуального окружения

**Linux/Mac:**
```bash
source venv/bin/activate
```

**Windows:**
```bash
venv\Scripts\activate
```

После активации в начале строки терминала появится `(venv)`.

### 3. Установка зависимостей

```bash
pip install --upgrade pip
pip install -r requirements.txt
playwright install chromium
```

### 4. Деактивация виртуального окружения

```bash
deactivate
```

## Использование

После активации виртуального окружения все команды Python будут использовать пакеты из `venv`.

### Запуск бота

```bash
# Активируйте окружение
source venv/bin/activate  # Linux/Mac
# или
venv\Scripts\activate      # Windows

# Установите токен
export TELEGRAM_BOT_TOKEN='ваш_токен'  # Linux/Mac
set TELEGRAM_BOT_TOKEN=ваш_токен        # Windows

# Запустите бота
python telegram_bot.py
```

### Использование скриптов запуска

Для удобства можно использовать готовые скрипты:

**Linux/Mac:**
```bash
./run.sh
```

**Windows:**
```bash
run.bat
```

Скрипты автоматически активируют виртуальное окружение и запустят бота.

## Удаление виртуального окружения

Если нужно переустановить окружение:

**Linux/Mac:**
```bash
rm -rf venv
./setup.sh
```

**Windows:**
```bash
rmdir /s /q venv
setup.bat
```

## Структура проекта

```
hh.ru-clicker/
├── venv/              # Виртуальное окружение (не в git)
├── data/              # Данные бота (не в git)
├── setup.sh           # Скрипт установки (Linux/Mac)
├── setup.bat          # Скрипт установки (Windows)
├── run.sh             # Скрипт запуска (Linux/Mac)
├── run.bat            # Скрипт запуска (Windows)
├── requirements.txt   # Зависимости проекта
└── telegram_bot.py    # Основной файл бота
```

## Решение проблем

### Виртуальное окружение не активируется

**Linux/Mac:**
- Убедитесь, что используете `source venv/bin/activate` (не `./venv/bin/activate`)
- Проверьте права доступа: `chmod +x venv/bin/activate`

**Windows:**
- Используйте `venv\Scripts\activate.bat` или `call venv\Scripts\activate`
- Убедитесь, что PowerShell не блокирует выполнение скриптов

### Пакеты не устанавливаются

- Убедитесь, что виртуальное окружение активировано (видите `(venv)` в терминале)
- Обновите pip: `pip install --upgrade pip`
- Проверьте подключение к интернету

### Playwright не устанавливает браузеры

```bash
# Убедитесь, что playwright установлен
pip install playwright

# Установите браузеры вручную
playwright install chromium
```

## Дополнительная информация

- [Официальная документация venv](https://docs.python.org/3/library/venv.html)
- [Руководство по виртуальным окружениям](https://docs.python.org/3/tutorial/venv.html)
