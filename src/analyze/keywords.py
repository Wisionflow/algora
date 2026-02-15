"""Keyword extraction and generation for WB search optimization."""

from __future__ import annotations

import re

from anthropic import AsyncAnthropic
from loguru import logger

from src.config import ANTHROPIC_API_KEY
from src.models import RawProduct

# Reuse stopwords from alibaba_1688.py
_RU_STOP_EXACT = frozenset(
    "для с и в на от из по к о не без при до через под над хит мини "
    "все это тот эта как что где или его она".split()
)

_RU_JUNK_STEMS = (
    "трансгранич", "популярн", "креативн", "интернет-знаменитост",
    "продаж", "фабрик", "оптов", "красив", "уникальн",
    "европейск", "британск", "американск", "стандартн",
    "интеллектуальн", "продаваем", "горяч", "товар",
    "продукт", "новых", "новый", "новая", "новое", "новые",
    "подходит", "подходящ", "применяет", "применим",
    "бестселлер", "считанн", "модн", "классическ",
    "второ", "изменени", "однотонн", "волнист",
    "готов", "прямые", "заводск",
)


def _is_junk_word(word: str) -> bool:
    """Check if a word is a stopword or matches a junk stem."""
    if word in _RU_STOP_EXACT:
        return True
    return any(word.startswith(stem) for stem in _RU_JUNK_STEMS)


def extract_keywords_from_title(title_ru: str, limit: int = 10) -> list[str]:
    """Extract meaningful keywords from Russian product title.

    Args:
        title_ru: Russian product title
        limit: Maximum number of keywords to extract (default 10)

    Returns:
        List of keywords (lowercase, deduplicated, stopwords removed)

    Example:
        >>> extract_keywords_from_title("Беспроводные наушники TWS с ANC и USB-C")
        ['беспроводные', 'наушники', 'tws', 'anc', 'usb-c']
    """
    if not title_ru:
        return []

    # Remove punctuation, convert to lowercase
    cleaned = re.sub(r"[,.()\[\]{}\"/\\!?;:]+", " ", title_ru.lower())

    # Extract unique meaningful words
    seen = set()
    keywords = []

    for word in cleaned.split():
        # Filter: duplicates, short words (<= 2 chars), digits, stopwords/junk
        if word in seen or len(word) <= 2 or word.isdigit() or _is_junk_word(word):
            continue

        seen.add(word)
        keywords.append(word)

        if len(keywords) >= limit:
            break

    return keywords


async def generate_ai_keywords(product: RawProduct, limit: int = 5) -> list[str]:
    """Generate SEO-optimized WB keywords using Claude AI.

    Args:
        product: Product to generate keywords for
        limit: Number of keywords to generate (default 5)

    Returns:
        List of AI-suggested keywords, or empty list if API call fails

    Example:
        >>> await generate_ai_keywords(product)
        ['наушники беспроводные', 'TWS наушники', 'блютуз гарнитура', 'AirPods аналог', 'вакуумные наушники']
    """
    if not ANTHROPIC_API_KEY:
        logger.debug("No ANTHROPIC_API_KEY — skipping AI keyword generation")
        return []

    try:
        client = AsyncAnthropic(api_key=ANTHROPIC_API_KEY)

        system_prompt = f"""Ты помогаешь русскоязычным продавцам на маркетплейсах (Wildberries, Ozon) подбирать ключевые слова для поиска товаров.

Твоя задача: предложить {limit} ключевых фраз для поиска на Wildberries, по которым потенциальные покупатели могут искать этот товар.

Требования:
- Ключевые слова на русском языке
- Каждая фраза 1-3 слова (например: "наушники беспроводные", "TWS наушники", "блютуз гарнитура")
- Включай популярные синонимы и вариации (например: "фонарь налобный" + "фонарик для рыбалки")
- НЕ используй хэштеги, НЕ используй знаки препинания
- Возвращай ТОЛЬКО список фраз через запятую, БЕЗ нумерации, БЕЗ объяснений

Пример ответа: наушники беспроводные, TWS наушники, блютуз гарнитура, AirPods аналог, вакуумные наушники"""

        user_prompt = f"""Товар: {product.title_ru}
Категория: {product.category}

Предложи {limit} ключевых фраз:"""

        response = await client.messages.create(
            model="claude-sonnet-4-5-20250929",
            max_tokens=200,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )

        # Parse response: "keyword1, keyword2, keyword3" -> ["keyword1", "keyword2", "keyword3"]
        text = response.content[0].text.strip()
        keywords = [kw.strip() for kw in text.split(",") if kw.strip()]

        logger.debug("AI keywords generated: {}", keywords[:limit])
        return keywords[:limit]

    except Exception as e:
        logger.warning("AI keyword generation failed: {}", e)
        return []


def select_optimized_keyword(
    extracted: list[str],
    ai_suggested: list[str],
    fallback: str = "",
) -> str:
    """Select the best keyword for WB API search.

    Priority:
    1. First AI-suggested keyword (if available) — Claude knows WB search patterns
    2. First 2 extracted keywords joined (e.g., "наушники беспроводные")
    3. Fallback (usually product.wb_keyword from collection)

    Args:
        extracted: Keywords extracted from title
        ai_suggested: AI-generated keywords
        fallback: Fallback keyword (default empty)

    Returns:
        Optimized keyword string for WB search

    Example:
        >>> select_optimized_keyword(["наушники", "tws"], ["TWS наушники"], "наушники")
        "TWS наушники"
    """
    if ai_suggested:
        return ai_suggested[0]

    if len(extracted) >= 2:
        return " ".join(extracted[:2])

    if extracted:
        return extracted[0]

    return fallback


async def generate_keywords(product: RawProduct) -> dict:
    """Generate all keyword variations for a product.

    This is the main entry point for keyword enrichment.

    Args:
        product: RawProduct to enrich with keywords

    Returns:
        Dict with:
            - extracted: list[str] — keywords extracted from title
            - ai_suggested: list[str] — AI-generated SEO keywords
            - wb_optimized: str — best keyword for WB API search

    Example:
        >>> result = await generate_keywords(product)
        >>> result
        {
            "extracted": ["беспроводные", "наушники", "tws", "anc"],
            "ai_suggested": ["наушники беспроводные", "TWS наушники", "блютуз гарнитура"],
            "wb_optimized": "наушники беспроводные"
        }
    """
    # Extract keywords from title
    extracted = extract_keywords_from_title(product.title_ru, limit=10)

    # Generate AI keywords (may fail gracefully and return [])
    ai_suggested = await generate_ai_keywords(product, limit=5)

    # Select best keyword for WB search
    wb_optimized = select_optimized_keyword(
        extracted=extracted,
        ai_suggested=ai_suggested,
        fallback=product.wb_keyword,
    )

    return {
        "extracted": extracted,
        "ai_suggested": ai_suggested,
        "wb_optimized": wb_optimized,
    }
