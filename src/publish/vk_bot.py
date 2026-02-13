"""Publish posts to VK community wall via VK API."""

from __future__ import annotations

import httpx
from loguru import logger

from src.config import VK_API_TOKEN, VK_GROUP_ID, VK_API_VERSION

VK_API_BASE = "https://api.vk.com/method"


async def send_vk_post(
    text: str,
    image_url: str = "",
    source_url: str = "",
) -> dict:
    """Publish a wall post to the VK community.

    Args:
        text: Post text (plain text, no HTML).
        image_url: Optional image URL to attach as a photo.
        source_url: Optional link to attach (shows preview in VK).

    Returns:
        dict with 'published' (bool) and 'post_id' (int or None).
    """
    result = {"published": False, "post_id": None}

    if not VK_API_TOKEN:
        logger.error("VK_API_TOKEN not set")
        return result

    if not VK_GROUP_ID:
        logger.error("VK_GROUP_ID not set")
        return result

    owner_id = f"-{VK_GROUP_ID}"

    # Upload photo if image_url provided
    attachments = []
    if image_url:
        photo_attach = await _upload_photo_from_url(image_url)
        if photo_attach:
            attachments.append(photo_attach)

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            params = {
                "access_token": VK_API_TOKEN,
                "v": VK_API_VERSION,
                "owner_id": owner_id,
                "from_group": 1,
                "message": text,
            }

            if attachments:
                params["attachments"] = ",".join(attachments)

            resp = await client.post(f"{VK_API_BASE}/wall.post", data=params)
            data = resp.json()

        if "response" in data:
            post_id = data["response"].get("post_id")
            result["published"] = True
            result["post_id"] = post_id
            logger.info(
                "Published to VK group {} (post_id={})", VK_GROUP_ID, post_id
            )
        else:
            error = data.get("error", {})
            logger.error(
                "VK API error {}: {}",
                error.get("error_code", "?"),
                error.get("error_msg", str(data)),
            )

    except Exception as e:
        logger.error("Failed to send to VK: {}", e)

    return result


async def _upload_photo_from_url(image_url: str) -> str | None:
    """Download image from URL and upload it to VK wall.

    Returns VK attachment string like 'photo123_456' or None on failure.
    """
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            # Step 1: Get upload server
            resp = await client.post(
                f"{VK_API_BASE}/photos.getWallUploadServer",
                data={
                    "access_token": VK_API_TOKEN,
                    "v": VK_API_VERSION,
                    "group_id": VK_GROUP_ID,
                },
            )
            server_data = resp.json()

            if "error" in server_data:
                logger.warning("VK getWallUploadServer error: {}", server_data["error"])
                return None

            upload_url = server_data["response"]["upload_url"]

            # Step 2: Download the image
            img_resp = await client.get(image_url, follow_redirects=True)
            if img_resp.status_code != 200:
                logger.warning("Failed to download image: {}", image_url)
                return None

            # Determine file extension
            content_type = img_resp.headers.get("content-type", "image/jpeg")
            ext = "jpg"
            if "png" in content_type:
                ext = "png"
            elif "webp" in content_type:
                ext = "webp"

            # Step 3: Upload to VK
            files = {"photo": (f"image.{ext}", img_resp.content, content_type)}
            upload_resp = await client.post(upload_url, files=files)
            upload_data = upload_resp.json()

            if not upload_data.get("photo") or upload_data["photo"] == "[]":
                logger.warning("VK photo upload returned empty result")
                return None

            # Step 4: Save wall photo
            save_resp = await client.post(
                f"{VK_API_BASE}/photos.saveWallPhoto",
                data={
                    "access_token": VK_API_TOKEN,
                    "v": VK_API_VERSION,
                    "group_id": VK_GROUP_ID,
                    "photo": upload_data["photo"],
                    "server": upload_data["server"],
                    "hash": upload_data["hash"],
                },
            )
            save_data = save_resp.json()

            if "response" in save_data and save_data["response"]:
                photo = save_data["response"][0]
                attach = f"photo{photo['owner_id']}_{photo['id']}"
                logger.debug("Uploaded photo to VK: {}", attach)
                return attach
            else:
                logger.warning("VK saveWallPhoto error: {}", save_data)
                return None

    except Exception as e:
        logger.warning("VK photo upload failed: {}", e)
        return None


async def get_group_info() -> dict:
    """Get VK group member count and other info."""
    if not VK_API_TOKEN or not VK_GROUP_ID:
        return {}

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                f"{VK_API_BASE}/groups.getById",
                data={
                    "access_token": VK_API_TOKEN,
                    "v": VK_API_VERSION,
                    "group_id": VK_GROUP_ID,
                    "fields": "members_count",
                },
            )
            data = resp.json()

        if "response" in data:
            groups = data["response"].get("groups", data["response"])
            if isinstance(groups, list) and groups:
                group = groups[0]
                count = group.get("members_count", 0)
                name = group.get("name", "")
                logger.info("VK group '{}' has {} members", name, count)
                return {"members": count, "name": name}
        else:
            logger.warning("VK groups.getById error: {}", data.get("error"))

    except Exception as e:
        logger.error("Failed to get VK group info: {}", e)

    return {}


async def test_connection() -> bool:
    """Test if the VK token is valid and has group wall access."""
    if not VK_API_TOKEN:
        logger.error("VK_API_TOKEN not set")
        return False

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                f"{VK_API_BASE}/groups.getById",
                data={
                    "access_token": VK_API_TOKEN,
                    "v": VK_API_VERSION,
                    "group_id": VK_GROUP_ID,
                },
            )
            data = resp.json()

        if "response" in data:
            groups = data["response"].get("groups", data["response"])
            if isinstance(groups, list) and groups:
                name = groups[0].get("name", VK_GROUP_ID)
                logger.info("VK connected: group '{}'", name)
                return True

        error = data.get("error", {})
        logger.error(
            "VK auth failed: {} ({})",
            error.get("error_msg", "unknown"),
            error.get("error_code", "?"),
        )
        return False

    except Exception as e:
        logger.error("VK connection test failed: {}", e)
        return False
