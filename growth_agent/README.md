# Algora Growth Agent

Telegram userbot для органического привлечения подписчиков в @algora_trends.

## Как работает

```
LISTENER (Telethon) → BRAIN (OpenRouter LLM) → ACTOR (Telethon)
                             ↕
                   MEMORY (PostgreSQL)
```

1. **Listener** мониторит чаты из таблицы `chats`, фильтрует релевантные сообщения
2. **Brain** решает отвечать ли и что писать (OpenRouter API)
3. **Actor** отправляет ответ с задержкой 30–120 сек, соблюдает лимиты

## Быстрый старт

### 1. Получить Telegram API credentials
Зайди на https://my.telegram.org → My Applications → создай приложение.
Скопируй `api_id` и `api_hash`.

### 2. Настроить .env
```bash
cp .env.example .env
# Заполни TG_API_ID, TG_API_HASH, TG_PHONE, OPENROUTER_API_KEY, POSTGRES_DSN
```

### 3. Создать таблицы в БД
```bash
pip install -r requirements.txt
python -m scripts.setup_db
```

### 4. Тест без реального Telegram
```bash
python -m scripts.run_agent --mock
```

### 5. Первый запуск (авторизация)
```bash
python -m scripts.run_agent
# Telethon запросит код из Telegram — введи его
```

### 6. Деплой на сервер (через Mantas_Synth/)
Создай запрос-файл в `../Mantas_Synth/` — партнёр задеплоит контейнер.

## Переменные окружения

| Переменная | Описание |
|-----------|---------|
| TG_API_ID | Из my.telegram.org |
| TG_API_HASH | Из my.telegram.org |
| TG_PHONE | Номер телефона аккаунта |
| OPENROUTER_API_KEY | Ключ OpenRouter |
| POSTGRES_DSN | Строка подключения к БД |
| MAX_MESSAGES_PER_DAY | Лимит ответов на чат (default: 3) |

## Добавить чат для мониторинга

```python
import asyncio
from src import db, config
from src.models import Chat

async def add():
    await db.init_pool(config.POSTGRES_DSN)
    chat = Chat(
        telegram_id=-1001234567890,
        title="Продавцы WB — общий",
        topic="marketplace",
        member_count=5000,
    )
    await db.upsert_chat(chat)
    await db.close_pool()

asyncio.run(add())
```
