"""Three-level product image validation.

Level 1 (free): URL pattern rules
Level 2 (free): HTTP HEAD check (downloadable, correct type, reasonable size)
Level 3 (paid, optional): Claude Vision — check if image matches the product

Philosophy: better a post without a photo than a post with a bad photo.
"""

from __future__ import annotations

import httpx
from loguru import logger

# --- Level 1: URL pattern rules ---

# Junk image patterns from 1688.com / alibaba CDN
REJECT_URL_PATTERNS = [
    "search",
    "avatar",
    "shop-logo",
    "banner",
    "promotion",
    "watermark",
    "/icon/",
    "default",
    "no-image",
    "placeholder",
]

# Valid image extensions
VALID_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}

# Known CDN hosts that may serve images without file extensions
_CDN_HOSTS = ["cbu01.alicdn.com", "img.alicdn.com", "cbu-cdn"]

# Trusted CDN hosts — skip L2 HTTP check (their rate limits block HEAD requests,
# but Telegram API can still fetch these images from its own servers)
_TRUSTED_CDN_HOSTS = ["cbu01.alicdn.com", "img.alicdn.com", "cbu-cdn"]


def validate_url_rules(image_url: str) -> tuple[bool, str]:
    """Level 1: fast URL check without downloading.

    Returns (is_valid, reason).
    """
    if not image_url or not image_url.strip():
        return False, "empty_url"

    url_lower = image_url.lower()

    # Format check
    has_valid_ext = any(ext in url_lower for ext in VALID_EXTENSIONS)
    is_cdn = any(cdn in url_lower for cdn in _CDN_HOSTS)

    if not has_valid_ext and not is_cdn:
        return False, "invalid_format"

    # Reject junk patterns
    for pattern in REJECT_URL_PATTERNS:
        if pattern in url_lower:
            return False, f"rejected_pattern:{pattern}"

    return True, "passed"


async def validate_image_downloadable(
    image_url: str, timeout: float = 10.0,
) -> tuple[bool, str]:
    """Level 2: check that image is downloadable and has reasonable size.

    Uses HEAD request — does not download the full image.
    """
    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            response = await client.head(image_url)

            if response.status_code != 200:
                return False, f"http_{response.status_code}"

            content_type = response.headers.get("content-type", "")
            if not any(t in content_type for t in ["image/", "octet-stream"]):
                return False, f"not_image:{content_type}"

            # File size check (if available)
            content_length = response.headers.get("content-length")
            if content_length:
                size_kb = int(content_length) / 1024
                if size_kb < 5:
                    return False, f"too_small:{size_kb:.0f}kb"
                if size_kb > 10_000:
                    return False, f"too_large:{size_kb:.0f}kb"

            return True, "passed"

    except httpx.TimeoutException:
        return False, "timeout"
    except Exception as e:
        return False, f"error:{str(e)[:50]}"


async def validate_image_with_vision(
    image_url: str,
    product_title: str,
    product_category: str,
    anthropic_client=None,
) -> tuple[bool, str, float]:
    """Level 3 (optional): Claude Vision checks if image matches the product.

    Returns (is_valid, reason, confidence).
    Cost: ~0.5 RUB per check.
    """
    if anthropic_client is None:
        return True, "vision_skipped", 0.0

    try:
        response = await anthropic_client.messages.create(
            model="claude-sonnet-4-5-20250929",
            max_tokens=150,
            messages=[{
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {"type": "url", "url": image_url},
                    },
                    {
                        "type": "text",
                        "text": (
                            f"Это фото должно быть изображением товара: '{product_title}' "
                            f"(категория: {product_category}).\n\n"
                            "Ответь СТРОГО в формате:\n"
                            "VALID или INVALID\n"
                            "Confidence: 0.0-1.0\n"
                            "Reason: краткая причина\n\n"
                            "INVALID если:\n"
                            "- Это коллаж/баннер с текстом, а не фото товара\n"
                            "- Фото не соответствует описанию товара\n"
                            "- Изображение слишком низкого качества\n"
                            "- На фото в основном текст (китайский или любой другой)\n"
                            "- Это лого, иконка или промо-материал"
                        ),
                    },
                ],
            }],
        )

        text = response.content[0].text.strip()
        is_valid = text.startswith("VALID")

        # Extract confidence
        confidence = 0.5
        for line in text.split("\n"):
            if "confidence" in line.lower():
                try:
                    confidence = float(line.split(":")[-1].strip())
                except ValueError:
                    pass

        reason = "vision_approved" if is_valid else "vision_rejected"
        return is_valid, reason, confidence

    except Exception as e:
        logger.warning("Vision validation failed: {}", e)
        return True, "vision_error", 0.0  # On error — skip, don't block


async def validate_product_image(
    image_url: str,
    product_title: str = "",
    product_category: str = "",
    use_vision: bool = False,
    anthropic_client=None,
) -> tuple[bool, str]:
    """Main entry: apply all validation levels sequentially.

    Returns (is_valid, reason).
    If image fails — post is published WITHOUT image (sendMessage instead of sendPhoto).
    """
    # Level 1: URL rules (free, instant)
    valid, reason = validate_url_rules(image_url)
    if not valid:
        logger.info("Image rejected (L1 URL): {} | {}", reason, image_url[:80])
        return False, reason

    # Level 2: Downloadable check (free, 1 HTTP request)
    # Skip for trusted CDNs — their rate limits block our HEAD requests,
    # but Telegram API can still fetch images from its own servers
    is_trusted_cdn = any(cdn in image_url.lower() for cdn in _TRUSTED_CDN_HOSTS)
    if is_trusted_cdn:
        logger.debug("Skipping L2 check for trusted CDN: {}", image_url[:80])
    else:
        valid, reason = await validate_image_downloadable(image_url)
        if not valid:
            logger.info("Image rejected (L2 HTTP): {} | {}", reason, image_url[:80])
            return False, reason

    # Level 3: Vision (paid, optional)
    if use_vision and anthropic_client:
        valid, reason, confidence = await validate_image_with_vision(
            image_url, product_title, product_category, anthropic_client,
        )
        if not valid and confidence > 0.7:
            logger.info(
                "Image rejected (L3 Vision): {} (conf={}) | {}",
                reason, confidence, image_url[:80],
            )
            return False, reason

    return True, "approved"
