"""Adapt the new logo for Telegram channel avatar.

Telegram requirements:
- Size: 640x640 pixels (square)
- Format: PNG or JPG
- File size: ideally under 200KB

Usage:
    python -X utf8 scripts/adapt_logo_for_telegram.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from PIL import Image, ImageDraw

# Paths
ASSETS_DIR = Path(__file__).parent.parent / "assets"
INPUT_PATH = ASSETS_DIR / "new_logo.png.png"
OUTPUT_PATH = ASSETS_DIR / "avatar_640.png"

# Brand colors (from brand identity)
NAVY = (26, 35, 126)  # #1A237E - primary dark
LIGHT_BG = (240, 240, 245)  # Light gray-blue


def adapt_logo():
    """Adapt logo to Telegram avatar format."""
    print(f"Reading logo from: {INPUT_PATH}")

    if not INPUT_PATH.exists():
        print(f"[ERROR] File not found: {INPUT_PATH}")
        return False

    # Open original image
    img = Image.open(INPUT_PATH)
    print(f"Original size: {img.size}, mode: {img.mode}")

    # Get original dimensions
    width, height = img.size

    # Create square canvas (640x640) with light background
    target_size = 640
    canvas = Image.new("RGB", (target_size, target_size), LIGHT_BG)

    # Calculate scaling to fit logo in square while maintaining aspect ratio
    # We want to preserve the entire logo, so scale to fit
    scale = min(target_size / width, target_size / height)
    new_width = int(width * scale)
    new_height = int(height * scale)

    # Resize logo with high-quality resampling
    img_resized = img.resize((new_width, new_height), Image.Resampling.LANCZOS)

    # If image has transparency, convert to RGB
    if img_resized.mode == "RGBA":
        # Create a background with light color
        background = Image.new("RGB", img_resized.size, LIGHT_BG)
        background.paste(img_resized, mask=img_resized.split()[3])  # Use alpha as mask
        img_resized = background

    # Center the logo on canvas
    x_offset = (target_size - new_width) // 2
    y_offset = (target_size - new_height) // 2
    canvas.paste(img_resized, (x_offset, y_offset))

    # Save with optimization
    canvas.save(OUTPUT_PATH, "PNG", optimize=True, quality=95)

    # Check file size
    file_size_kb = OUTPUT_PATH.stat().st_size / 1024
    print(f"\n[OK] Avatar saved to: {OUTPUT_PATH}")
    print(f"Size: {target_size}x{target_size} pixels")
    print(f"File size: {file_size_kb:.1f} KB")

    if file_size_kb > 200:
        print(f"[WARNING] File size is large ({file_size_kb:.1f} KB). Consider further optimization.")

    return True


if __name__ == "__main__":
    print("=" * 60)
    print("ALGORA — Logo Adaptation for Telegram")
    print("=" * 60)

    success = adapt_logo()

    if success:
        print("\n" + "=" * 60)
        print("✓ Logo adapted successfully!")
        print("Next step: Run 'python -X utf8 scripts/setup_channel.py' to update channel")
        print("=" * 60)
    else:
        print("\n[ERROR] Failed to adapt logo")
        sys.exit(1)
