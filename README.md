# Account Manager (Telegram)

Система для сбора и мониторинга информации о пользователях и группах в Telegram с использованием библиотеки Telethon.

## Возможности

- **Аутентификация**: вход по телефону или QR-коду
- **Мониторинг пользователей**: отслеживание статуса онлайн, действий (печатает, записывает голосовые и т.д.)
- **Сбор данных**: автоматическое скачивание фото профиля и историй (stories)
- **Автоматизация**: прослушка каналов с обработкой сообщений по паттернам
- **Планировщик задач**: периодическая проверка пользователей (каждые 20 секунд)
- **API сервис**: FastAPI интерфейс для получения логов и данных
- **Docker**: готовые конфигурации для контейнеризации

## Технологический стек

- **Python 3.11**
- **Telethon** - Telegram Client API
- **FastAPI** + **Uvicorn** - веб-сервер и API
- **APScheduler** - планировщик задач
- **Pydantic / Pydantic-settings** - управление конфигурацией
- **Docker / Docker Compose** - контейнеризация

## Структура проекта

```
AccountManager-Telethon/
├── src/
│   ├── app/
│   │   ├── api/              # FastAPI роутеры
│   │   │   └── monitoring_log.py
│   │   ├── services/         # Сервисы (FastAPI)
│   │   │   └── uvicorn_service.py
│   │   └── main.py           # Точка входа приложения
│   ├── core/
│   │   ├── settings.py       # Настройки (pydantic)
│   │   ├── schemas.py        # Pydantic схемы
│   │   └── logging_settings.py
│   ├── managers/             # Менеджеры логики
│   │   ├── account_manager.py      # Координатор всех менеджеров
│   │   ├── telethon_manager.py    # Работа с Telegram API
│   │   ├── monitoring_manager.py  # Мониторинг пользователей
│   │   ├── automation_manager.py  # Автоматизация и прослушка
│   │   └── secure_manager.py     # Безопасность (заглушка)
│   └── patterns/
│       └── RegexPattern.py   # Паттерны для обработки сообщений
├── storage/
│   ├── managers/             # Данные менеджеров
│   ├── sessions/             # Telegram сессии
│   ├── qr/                  # QR-коды для входа
│   ├── patterns/             # JSON паттерны для каналов
│   └── users/               # Данные пользователей (фото, истории, логи)
├── logs/                    # Логи приложения
├── docker-compose.yml       # Docker Compose конфигурация
├── docker-compose.local.yml # Локальная конфигурация
├── Dockerfile               # Образ для Docker
├── requirements.txt         # Python зависимости
└── .env                     # Переменные окружения
```

## Установка

### Локальная установка

1. Клонируйте репозиторий:
```bash
git clone https://github.com/AmongFox/AccountManager-Telethon.git
cd AccountManager-Telethon
```

2. Создайте виртуальное окружение:
```bash
python -m venv venv
.\venv\Scripts\activate  # Windows
source venv/bin/activate  # Linux/Mac
```

3. Установите зависимости:
```bash
pip install -r requirements.txt
```

4. Настройте переменные окружения в файле `.env` (см. раздел Конфигурация).

5. Запустите приложение:
```bash
python src/app/main.py
```

### Docker установка

```bash
docker-compose up -d
```

## Конфигурация

Создайте файл `.env` в корне проекта:

```env
# Основные настройки
APP_NAME='Account Manager'
APP_VERSION=1.0.0

# Telegram API (получить на https://my.telegram.org)
API_ID=your_api_id
API_HASH=your_api_hash
APP_ID=your_app_id
APP_TITLE=AccountApplication
APP_SHORTNAME=ACAPP

# Сессия (оставьте пустым для первого входа)
SESSION_NAME=
PHONE_NUMBER=your_phone_number

# Системная информация
SYSTEM_VERSION=4.16.30-vxCUSTOM
DEVICE_MODEL=Desktop

# Каналы для прослушки (через запятую)
CHANNEL_IDS=

# FastAPI
UVICORN_SERVICE_HOST=0.0.0.0
UVICORN_SERVICE_PORT=8000
UVICORN_SERVICE_ENABLED=True

# CORS
CORS_ORIGINS=*
CORS_ALLOW_CREDENTIALS=True
CORS_ALLOW_METHODS=*
CORS_ALLOW_HEADERS=*

# Прокси MTProxy (опционально)
PROXY_ENABLED=False
PROXY_SERVER=proxy-server.com
PROXY_PORT=443
PROXY_SECRET=your_proxy_secret

# Отладка
DEBUG=False
```

## Использование

### Первый запуск и аутентификация

При первом запуске вам потребуется авторизоваться:

1. Введите номер телефона
2. Введите код подтверждения из Telegram
3. При наличии 2FA - введите пароль

Сессия сохранится в `storage/sessions/`.

### Мониторинг пользователей

Создайте файл `storage/managers/monitoring/logging_user_updates.txt` со списком пользователей (ID или username, разделенные `;` или новой строкой):

```
123456789;
@username1;
@username2
```

Также создайте `storage/managers/monitoring/user_check_scheduler.txt` для периодической проверки.

### Автоматизация (прослушка каналов)

1. Укажите ID каналов в `.env`:
```env
CHANNEL_IDS=123456789,987654321
```

2. Создайте паттерны в `storage/patterns/` с именем `<channel_id>.json`:
```json
{
  "patterns": [
    {
      "id": 1,
      "text": "regex_pattern_here",
      "threshold": 0.8,
      "chat_id": -100123456789,
      "response": "Ответ на сообщение"
    }
  ]
}
```

### API Endpoints

#### Получить логи обновлений пользователя
```
GET /monitoring/{user_id}/logs
```

## Логирование

Логи сохраняются в:
- `logs/` - общие логи приложения
- `storage/users/{user_id}/monitoring/logging_user_updates/updates.log` - логи обновлений пользователей
- `storage/users/{user_id}/monitoring/user_check_scheduler/{timestamp}/data.log` - данные проверок

## Docker Compose

### Продакшн
```bash
docker-compose up -d
```