---
name: algora-content-pipeline
description: |
  Skill for working with the Algora content pipeline — the automated system that parses Chinese wholesale platforms (1688.com), scores products, generates AI insights, and publishes Telegram posts for WB/Ozon sellers. Use this skill whenever the task involves: creating or editing Telegram post templates, fixing content quality issues (duplicates, truncated names, Chinese characters in supplier names, API errors leaking into posts, wrong categories), running or debugging the pipeline (Collect → Analyze → Compose → Publish), working with product scoring (margin calculation, trend analysis, competition metrics), improving post formats, adding new post types, or anything related to @algora_trends content generation. Also trigger when the user mentions telegram_post.py, run_pipeline.py, scoring.py, or any Algora pipeline module. If someone asks about product data, post quality, or content automation for marketplace sellers — this is the skill to use.
---

# Algora Content Pipeline

## What This Is

Algora's content pipeline is a fully automated system that:
1. **Collects** product data from Chinese platforms (1688.com via Apify)
2. **Analyzes** products (margin calculation, WB competition, scoring)
3. **Composes** Telegram posts with AI-generated insights (Claude API)
4. **Publishes** to @algora_trends via Telegram Bot API

Pipeline runs via GitHub Actions (1x/day). 275+ products in SQLite database.

## Architecture

```
src/
├── collect/          # Parsers (1688.com via Apify, WB analytics)
│   ├── alibaba_1688.py
│   └── wb_analytics.py
├── analyze/          # Scoring, enrichment, AI analysis
│   ├── scoring.py        # 4-component score: trend, competition, margin, reliability
│   ├── enrichment.py     # Currency, delivery cost, customs estimation
│   └── ai_analysis.py    # Claude API for product insights
├── compose/          # Post generation
│   └── telegram_post.py  # 5 post types, HTML formatting for Telegram
├── publish/          # Delivery
│   └── telegram_bot.py   # Bot API sendMessage/sendPhoto
├── db.py             # SQLite CRUD
├── config.py         # Environment variables, constants
└── models.py         # Dataclasses (RawProduct, AnalyzedProduct)

scripts/
├── run_pipeline.py   # Main entry point
└── scheduler.py      # Scheduling logic
```

## Known Issues (from Content Audit)

These are recurring quality problems to watch for and prevent:

| Issue | Where to Fix | Priority |
|-------|-------------|----------|
| **Duplicate products published** | run_pipeline.py + db.py (check offerId before publish) | Critical |
| **API errors leaked into post text** | telegram_post.py (sanitize before publish) | Critical |
| **Category "all" displayed as-is** | telegram_post.py (fallback → "Разное") | High |
| **Product names truncated mid-word** | telegram_post.py (smart truncation at word boundary) | High |
| **Chinese characters in supplier name** | telegram_post.py (detect CJK → "Китайская фабрика") | Medium |
| **Search URLs instead of product URLs** | collect/*.py (validate URL format) | Medium |
| **post_type/category = None** | run_pipeline.py (ensure fields populated) | Low |

## Post Format (Current v3)

```
ALGORA ▸ [Категория]

📦 [Название товара на русском]

💰 Экономика:
• Цена FOB: ¥XX (~XX₽)
• Себестоимость в РФ: ~XX₽/шт
• Цена на WB: ~XX₽

📊 Рынок:
• Конкуренты на WB: XX
• Расчётная маржа: ~XX%
• Тренд: +XX% за месяц

💡 ИИ-инсайт:
[2-3 предложения: почему интересен, риски, рекомендация]

🏭 Поставщик: [имя/Китайская фабрика] ([X лет])
🔗 [ссылка на товар]

#[категория] #китай #маржа
```

## Quality Checklist for Posts

Before any post goes live, verify:
- [ ] Product name is complete (not truncated mid-word)
- [ ] Margin calculation is realistic (flag if >80%)
- [ ] No Chinese characters visible to reader (supplier name, product specs)
- [ ] No API error strings in text
- [ ] Product URL is a direct link (not a search page)
- [ ] Category is meaningful (not "all" or None)
- [ ] AI insight is present and specific (not generic filler)
- [ ] No duplicate — offerId not already published
- [ ] Post length < 1500 characters (Telegram optimal)
- [ ] HTML formatting renders correctly (no raw markdown)

## Scoring Components

Products are scored on 4 axes (each 0-10):

| Component | What It Measures | High Score Means |
|-----------|-----------------|-----------------|
| `trend_score` | Sales growth rate (30d vs prior 30d) | Growing fast |
| `competition_score` | WB competitors count (inverted) | Few competitors |
| `margin_score` | Calculated margin % | High profitability |
| `reliability_score` | Supplier years + rating | Trusted factory |

`total_score` = weighted sum → used to rank products for publication.

## Working With the Pipeline

### Running
```bash
python scripts/run_pipeline.py              # Full pipeline
python scripts/run_pipeline.py --dry-run    # No publishing
python scripts/run_pipeline.py --category gadgets --limit 10
```

### Testing Changes
Always use `--dry-run` first. Check output in `data/algora.log`.

### Environment Variables
```
ANTHROPIC_API_KEY    # Claude API for insights
TELEGRAM_BOT_TOKEN   # Bot for publishing
TELEGRAM_CHANNEL_ID  # @algora_trends
APIFY_API_TOKEN      # 1688.com parser
```

## Content Strategy Context

- **Target audience:** WB/Ozon sellers looking for trending products from China
- **Tone:** Professional, data-driven, no fluff. "Корпорация Алгора" — a system, not a blogger
- **Value proposition:** Save 10+ hours/week on product research
- **Current subscribers:** ~4 (early stage, Growth Agent deploying)
- **Frequency:** 1 post/day (free channel), planned 6/day for PRO
