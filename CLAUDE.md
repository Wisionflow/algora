# ALGORA — AI-аналитик китайского рынка для селлеров WB/Ozon

## Что это
Автоматическая система, которая парсит товары с 1688.com, анализирует маржу и конкуренцию,
генерирует посты с AI-инсайтами и публикует в Telegram-канал @algora_trends.

## Архитектура
Пайплайн из 4 модулей:
1. **Collect** (src/collect/) — парсинг 1688.com через Apify API, данные WB через API
2. **Analyze** (src/analyze/) — скоринг (trend, competition, margin, reliability), AI-инсайты через Claude API
3. **Compose** (src/compose/) — генерация 5 типов постов для Telegram и VK
4. **Publish** (src/publish/) — публикация через Telegram Bot API и VK API

## Как запустить

### Полный пайплайн (парсинг → анализ → публикация)
python -X utf8 -m scripts.run_pipeline --source 1688 --category electronics --top 3

### Тестовый запуск (без публикации)
python -X utf8 -m scripts.run_pipeline --source demo --dry-run

### Конкретный тип поста
python -X utf8 -m scripts.post_niche_review --dry-run
python -X utf8 -m scripts.post_beginner_mistake --dry-run
python -X utf8 -m scripts.post_product_of_week --dry-run
python -X utf8 -m scripts.post_weekly_top --dry-run

### Планировщик
python -X utf8 -m scripts.scheduler --once    # один раз сейчас
python -X utf8 -m scripts.scheduler --test    # dry-run

## Переменные окружения (.env)
- ANTHROPIC_API_KEY — Claude API для AI-инсайтов и ключевых слов
- TELEGRAM_BOT_TOKEN — токен Telegram-бота
- TELEGRAM_CHANNEL_ID — ID канала (@algora_trends)
- APIFY_API_TOKEN — Apify для парсинга 1688.com
- VK_API_TOKEN — VK Community access token (на паузе)
- VK_GROUP_ID — ID VK-группы (на паузе)

## Структура
- src/ — основной код (collect, analyze, compose, publish)
- scripts/ — скрипты запуска и утилиты
- data/ — SQLite база, кэши, логи (не в git)
- assets/ — логотипы и брендинг
- docs/ — документация проекта
- tests/ — тесты (пока пустые)

## Фото-валидация
- 3 уровня: URL rules → HTTP check → Vision (опционально)
- Если фото не прошло валидацию — пост публикуется без фото
- Vision включается через IMAGE_VISION_ENABLED=true в .env
- Стоимость vision: ~180 руб/мес при 10 проверках/день
- Файл: src/analyze/image_validator.py

## Правила
- НИКОГДА не выводи значения API-ключей и токенов
- Для тестирования используй --dry-run
- Python 3.12 (как в CI)
- База данных: data/algora.db (SQLite)
- Логи: data/algora.log
