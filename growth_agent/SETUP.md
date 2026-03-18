# ALGORA Growth Agent — Инструкция по установке и настройке

## Что это

Telegram-агент, который мониторит целевые чаты, отвечает на релевантные сообщения от имени живого человека и органично упоминает твой канал. Работает 24/7 в Docker.

**Принцип работы:**
1. Агент подключается к Telegram как обычный пользователь (не бот)
2. Читает сообщения в указанных чатах
3. Для каждого сообщения проверяет релевантность по ключевым словам
4. Если тема подходит — спрашивает у LLM: «стоит ли ответить?»
5. Если да — ждёт случайную паузу (60–300 сек) и отвечает
6. Каждые N ответов органично упоминает канал

---

## Требования

- Docker + Docker Compose
- **NATS AI Proxy** (предоставляет ALGORA-платформа) — для вызова LLM
- **PostgreSQL** (предоставляет ALGORA-платформа) — для хранения чатов и лимитов
- Telegram-аккаунт (обычный, не бот) — лучше свежий, не привязанный к другим проектам
- Telegram API credentials: `api_id` + `api_hash` (получить на https://my.telegram.org)

---

## Шаг 1 — Получить Telegram API credentials

1. Зайди на https://my.telegram.org → войди через номер телефона
2. Перейди в **API development tools**
3. Создай приложение (название любое)
4. Скопируй `App api_id` и `App api_hash`

---

## Шаг 2 — Настроить конфигурацию

```bash
cp .env.example .env
```

Открой `.env` и заполни:

```env
TG_API_ID=твой_api_id
TG_API_HASH=твой_api_hash
TG_PHONE=+7XXXXXXXXXX        # номер телефона аккаунта

AGENT_NAME=Имя               # имя, от которого пишет агент
CHANNEL_LINK=@твой_канал     # канал, который продвигаем

NATS_URL=nats://10.0.0.2:4222
POSTGRES_DSN=postgresql://growth_user:пароль@10.0.0.2:5432/algora_growth

RELEVANCE_KEYWORDS=слово1,слово2,слово3   # ключевые слова для фильтра
```

**NATS_URL и POSTGRES_DSN** — уточни у ALGORA-команды, они предоставят.

---

## Шаг 3 — Настроить промпты (личность агента)

Все промпты в папке `prompts/`. Редактируй обычным текстовым редактором — **Python-код трогать не нужно**.

| Файл | Что настраивает |
|------|----------------|
| `prompts/system_prompt.txt` | Кто такой агент, стиль письма, запреты |
| `prompts/decision_prompt.txt` | Правила: когда отвечать, когда молчать |
| `prompts/dm_system_prompt.txt` | Как отвечать на личные сообщения |
| `prompts/dm_response_prompt.txt` | Формат ответа на личку |

В промптах используй `{AGENT_NAME}` и `{CHANNEL_LINK}` — они подставляются автоматически из `.env`.

**Пример изменения под другую нишу** (например, недвижимость):

В `system_prompt.txt` замени:
```
Ты {AGENT_NAME}. Продаёшь на WB и Ozon, импорт из Китая. В чатах 2 года.
```
На:
```
Ты {AGENT_NAME}. Занимаешься арендой коммерческой недвижимости, 5 лет опыта.
```

В `decision_prompt.txt` замени критерии respond=true:
```
- конкретный вопрос по теме чата И ты точно знаешь ответ
```
На более специфичные для своей ниши.

И в `.env` замени `RELEVANCE_KEYWORDS`:
```
RELEVANCE_KEYWORDS=аренда,ипотека,недвижимость,застройщик,квартира,объект,сделка
```

---

## Шаг 4 — Инициализировать базу данных

```bash
docker compose run --rm agent python scripts/setup_db.py
```

Создаёт таблицы `chats` и `schedule` в PostgreSQL.

---

## Шаг 5 — Авторизация в Telegram (один раз)

```bash
docker compose run --rm agent python scripts/run_agent.py --auth
```

Введи код из SMS/приложения. Сессия сохранится в `sessions/` и при последующих запусках авторизация не нужна.

---

## Шаг 6 — Добавить целевые чаты

Агент мониторит только чаты, которые есть в базе данных. Есть два способа добавить:

### Вариант А — вручную через sync_chats.py
Сначала **вступи** в нужные чаты с телефона агента, затем:

```bash
docker compose run --rm agent python scripts/sync_chats.py
```

Синхронизирует все диалоги Telegram → PostgreSQL.

### Вариант Б — автопоиск через scout_chats.py
```bash
docker compose run --rm agent python scripts/scout_chats.py
```

Ищет живые чаты по поисковым запросам (нужно настроить запросы внутри скрипта).

### Проверить список чатов
```bash
docker compose run --rm agent python -c "
import asyncio
from src.db import init_pool, get_active_chats
async def main():
    await init_pool('твой_POSTGRES_DSN')
    chats = await get_active_chats()
    for c in chats: print(c['id'], c['title'])
asyncio.run(main())
"
```

---

## Шаг 7 — Запустить

```bash
docker compose up -d
```

Агент запустится в фоне и будет работать 24/7.

---

## Мониторинг

### Логи в реальном времени
```bash
docker compose logs -f agent
```

Что искать в логах:
- `Monitoring N chats` — агент стартовал, N чатов в работе
- `Relevant message (score=X.XX)` — найдено потенциально релевантное сообщение
- `Replied in chat ...` — отправлен ответ
- `Skipping reply ... — limit reached` — суточный лимит в чате исчерпан
- `Chat N permanently deactivated` — агент забанен в чате, чат отключён автоматически

### Статистика ответов
```bash
docker compose run --rm agent python -c "
import asyncio
from src.db import init_pool
import asyncpg

async def main():
    pool = await asyncpg.create_pool('твой_POSTGRES_DSN')
    rows = await pool.fetch('''
        SELECT c.title, COUNT(r.id) as replies,
               SUM(r.included_channel_link::int) as links
        FROM responses r
        JOIN chats c ON c.id = r.chat_id
        GROUP BY c.title ORDER BY replies DESC
    ''')
    for r in rows:
        print(f\"{r['title'][:50]}: {r['replies']} ответов, {r['links']} со ссылкой\")
    await pool.close()
asyncio.run(main())
"
```

---

## Лимиты и безопасность

По умолчанию агент работает осторожно:
- **3 сообщения** в одном чате в день (`MAX_MESSAGES_PER_DAY`)
- **Минимум 1 час** между ответами в одном чате (`MIN_INTERVAL_SEC=3600`)
- **60–300 секунд** случайная пауза перед каждым ответом
- **Ссылка на канал** — не чаще 1 раза на каждые 7 ответов

Если агент получит бан в чате — он **автоматически** отключит этот чат и больше не будет в него писать.

---

## Настройка лимитов

В `.env`:
```env
MAX_MESSAGES_PER_DAY=2     # уменьши если чаты агрессивно банят
MIN_INTERVAL_SEC=7200      # увеличь паузу между ответами (в сек)
```

---

## Структура файлов

```
growth_agent/
├── .env.example          # шаблон конфига
├── .env                  # твой конфиг (не в git!)
├── Dockerfile
├── docker-compose.yml
├── prompts/              # ← РЕДАКТИРУЙ ТОЛЬКО ЭТИ ФАЙЛЫ
│   ├── system_prompt.txt       # личность агента
│   ├── decision_prompt.txt     # правила ответов в чатах
│   ├── dm_system_prompt.txt    # поведение в личке
│   └── dm_response_prompt.txt  # формат ответа в личке
├── scripts/
│   ├── run_agent.py      # точка запуска
│   ├── setup_db.py       # инициализация БД
│   ├── sync_chats.py     # синхронизация чатов из Telegram
│   └── scout_chats.py    # автопоиск новых чатов
└── src/                  # код агента (не трогать)
    ├── actor.py          # отправка сообщений
    ├── brain.py          # LLM-решения
    ├── config.py         # конфигурация
    ├── db.py             # база данных
    ├── listener.py       # мониторинг чатов
    ├── relevance.py      # фильтр ключевых слов
    └── scheduler.py      # сброс счётчиков в полночь
```

---

## Частые вопросы

**Агент получил бан в чате — что делать?**
Ничего. Он автоматически отключит чат (`our_status = 'banned'`) и больше не будет туда писать.

**Как добавить новый чат в работу?**
Вступи в чат с телефона агента → запусти `sync_chats.py`.

**Агент отвечает слишком часто / редко?**
Отредактируй `RELEVANCE_KEYWORDS` в `.env` (меньше слов = реже реагирует) и `MAX_MESSAGES_PER_DAY`.

**Как сменить нишу (другая тема чатов)?**
1. Обнови `RELEVANCE_KEYWORDS` в `.env`
2. Перепиши `prompts/system_prompt.txt` и `prompts/decision_prompt.txt`
3. Добавь новые целевые чаты через `sync_chats.py`
4. Перезапусти: `docker compose restart`
