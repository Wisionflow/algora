---
name: algora-growth-agent
description: |
  Skill for developing and calibrating the Algora Growth Agent — an autonomous AI-powered Telegram userbot that monitors seller chats, gives expert answers, and attracts subscribers to @algora_trends. Use this skill whenever the task involves: writing or improving LLM prompts for the Growth Agent's BRAIN module, calibrating response behavior (tone, frequency, when to mention the channel), working with Telethon userbot code (LISTENER, ACTOR modules), managing chat engagement strategy (which chats to join, keyword filtering, relevance scoring), analyzing Growth Agent metrics (responses sent, conversions, bans), debugging NATS AI Proxy integration, Docker deployment of the agent, or any aspect of automated audience acquisition. Also trigger when someone mentions growth hacking for Telegram, userbot development, chat monitoring, or automated community engagement. If the user asks about getting subscribers, audience growth, or the CMO agent — use this skill.
---

# Algora Growth Agent (CMO)

## What This Is

The Growth Agent is an autonomous Telegram userbot that:
1. **Listens** to 10-30 seller chats for relevant messages
2. **Decides** whether to respond (relevance scoring + LLM judgment)
3. **Responds** with expert answers about Chinese sourcing, margins, WB/Ozon
4. **Attracts** subscribers to @algora_trends naturally (1 in 5 responses include channel link)

**Milestone:** 100 subscribers in 30 days = proof that autonomous audience acquisition works.

## Architecture

```
LISTENER (Telethon) → BRAIN (NATS AI Proxy → Llama 3.3 70B) → ACTOR (Telethon)
                                    ↕
                          MEMORY (PostgreSQL)
```

### Modules

| Module | File | Role |
|--------|------|------|
| **LISTENER** | listener.py | Monitors chats via Telethon, filters by 25 keywords, calculates relevance score |
| **BRAIN** | brain.py | Sends message + context to LLM via NATS, gets JSON decision (should_respond + response) |
| **ACTOR** | actor.py | Sends response with rate limits (3/chat/day), delays (30-120s), tracks channel mentions |
| **MEMORY** | db.py | PostgreSQL: chats, messages, responses, metrics, schedule |
| **SCHEDULER** | scheduler.py | Active hours, daily limits, cooldowns |

### Infrastructure

- **Host:** Hetzner EU server (167.17.181.140), directory `/home/mantas/cmo/`
- **LLM:** Llama 3.3 70B via NATS AI Proxy on Russian VPS (10.0.0.2:4222)
- **DB:** PostgreSQL on Russian VPS (10.0.0.2:5432, database `algora_growth`)
- **Connection:** AmneziaWG tunnel between servers (~51ms latency)
- **Cost:** ~$0.02/month for LLM (extremely cheap via Llama 3.3 70B)

## BRAIN Prompt Guidelines

The BRAIN module prompt is the most critical component. It determines response quality and whether the agent gets banned or builds trust.

### Core Principles for Prompt Writing

1. **Expert persona, not salesman.** The agent is a knowledgeable seller/sourcing specialist who shares experience. Never pitches the channel directly.

2. **Relevance gate is strict.** Only respond to messages about: product sourcing from China, margin calculations, 1688/Alibaba, WB/Ozon analytics, logistics/cargo, supplier verification. Skip everything else.

3. **Value first, link second.** Every response must contain genuinely useful information. The channel link is a "by the way" addition, not the purpose.

4. **Match chat culture.** Informal in casual chats, more structured in professional ones. Use seller jargon naturally (маржа, юнит-экономика, FOB, карго, селлер, ВБ, озон).

5. **JSON output format.** The BRAIN must return valid JSON:
```json
{
  "should_respond": true,
  "reason": "Question about finding suppliers on 1688",
  "response": "На 1688 по этой категории сейчас...",
  "include_channel": false,
  "confidence": 0.85
}
```

### Prompt Template Structure

```
SYSTEM: You are an experienced WB/Ozon seller who sources products from China.
You participate in seller chats and share genuine expertise.

CONTEXT:
- Chat: {chat_name} ({chat_description})
- Recent messages: {last_5_messages}
- New message from {username}: "{message_text}"

RULES:
1. Only respond if the message is about: [topics list]
2. Response must be 2-4 sentences, practical and specific
3. Include real numbers when possible (margins, prices, timelines)
4. Mention @algora_trends only when naturally relevant (max 1 in 5 responses)
5. Never be promotional. Never use marketing language.
6. If unsure — don't respond (should_respond: false)

Respond in JSON format: {schema}
```

### Anti-Ban Strategy

| Risk | Mitigation |
|------|-----------|
| Too many messages | Max 3 responses/chat/day, 10 total/day |
| Too fast replies | Random delay 30-120 seconds |
| Promotional tone | Prompt explicitly forbids marketing language |
| Pattern detection | Vary response style, don't repeat phrases |
| Admin suspicion | Be genuinely helpful — useful members don't get banned |
| TG rate limits | Telethon flood protection, exponential backoff |

### Keyword Relevance Scoring

The LISTENER pre-filters messages by keywords before sending to BRAIN:

**High relevance (score 3):** маржа, 1688, поставщик, закупка, FOB, себестоимость
**Medium relevance (score 2):** WB, Ozon, селлер, Китай, карго, доставка
**Low relevance (score 1):** товар, продажи, маркетплейс, бизнес, ниша

Threshold: score ≥ 2 → send to BRAIN for decision.

## Calibration Process

### Phase 1: Observation (Days 1-3)
- Agent joins chats but only reads (ACTOR disabled)
- BRAIN processes messages and logs decisions without sending
- Review logs: are the "should_respond" decisions correct?

### Phase 2: Soft Launch (Days 4-7)
- 2-3 responses per day across all chats
- Manual review of every sent response
- Adjust prompt based on:
  - Did the response get reactions? (good sign)
  - Did anyone reply positively? (great sign)
  - Did admin react negatively? (red flag → adjust)

### Phase 3: Full Operation (Day 8+)
- 5-10 responses per day
- Automated monitoring of metrics
- Weekly prompt adjustments based on data

## Metrics to Track

| Metric | Where | Target |
|--------|-------|--------|
| Messages processed/day | MEMORY | 100-500 |
| Responses sent/day | MEMORY | 5-10 |
| Response quality (manual review) | Logs | >80% helpful |
| Channel mentions/day | MEMORY | 1-2 |
| New subscribers/day | TG API | 3-5 |
| Conversion (response → subscribe) | Calculated | >5% |
| Bans/warnings | MEMORY | 0 |

## Target Chats

Types of Telegram chats to monitor:
- **WB/Ozon seller chats** (МПшник, WB Партнёры, Селлер WB) — primary
- **China sourcing chats** (закупки, карго, 1688) — high relevance
- **Beginner entrepreneur chats** — high conversion potential
- **Avoid:** crypto chats, general business, tech chats (off-topic)

## Docker Deployment

```yaml
# docker-compose.yml on Hetzner
services:
  cmo:
    build: .
    container_name: algora-cmo
    restart: unless-stopped
    environment:
      - TG_API_ID=${TG_API_ID}
      - TG_API_HASH=${TG_API_HASH}
      - TG_PHONE=${TG_PHONE}
      - DATABASE_URL=postgresql://growth_user:...@10.0.0.2:5432/algora_growth
      - NATS_URL=nats://10.0.0.2:4222
    volumes:
      - ./session:/app/session  # Telethon session persistence
    networks:
      - algora-net
    mem_limit: 512m
```

First launch requires interactive SMS verification for Telethon.
