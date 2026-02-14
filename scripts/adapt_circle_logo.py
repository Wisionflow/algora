"""Adapt circular logo for Telegram channel avatar.

Telegram shows avatars in a circular frame, so we need to:
1. Center the circular logo in a square canvas
2. Ensure all important elements fit within the circular crop
3. Optimize file size for fast loading

Usage:
    python -X utf8 scripts/adapt_circle_logo.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from PIL import Image, ImageDraw

# Paths
ASSETS_DIR = Path(__file__).parent.parent / "assets"
INPUT_PATH = ASSETS_DIR / "new_circle_logo.png.png"
OUTPUT_PATH = ASSETS_DIR / "avatar_640.png"

# Background color - light neutral that works with the logo
LIGHT_BG = (240, 242, 245)  # Very light gray-blue


def create_circular_mask(size: int) -> Image.Image:
    """Create a circular mask for preview/testing."""
    mask = Image.new("L", (size, size), 0)
    draw = ImageDraw.Draw(mask)
    draw.ellipse([0, 0, size, size], fill=255)
    return mask


def adapt_circular_logo():
    """Adapt circular logo for Telegram's circular avatar frame."""
    print(f"Reading circular logo from: {INPUT_PATH}")

    if not INPUT_PATH.exists():
        print(f"[ERROR] File not found: {INPUT_PATH}")
        return False

    # Open original image
    img = Image.open(INPUT_PATH)
    print(f"Original size: {img.size}, mode: {img.mode}, file size: {INPUT_PATH.stat().st_size / 1024 / 1024:.1f} MB")

    # Target size for Telegram
    target_size = 640

    # Convert to RGBA if needed
    if img.mode != "RGBA":
        img = img.convert("RGBA")

    # Get original dimensions
    width, height = img.size

    # Calculate scaling - we want to fit the logo within the circular frame
    # Leave a small margin (5%) to ensure nothing gets cut off at the edges
    margin = 0.95  # Use 95% of the available space
    scale = min(target_size / width, target_size / height) * margin
    new_width = int(width * scale)
    new_height = int(height * scale)

    print(f"Resizing to: {new_width}x{new_height} (with {int((1-margin)*100)}% safety margin)")

    # Resize with high-quality resampling
    img_resized = img.resize((new_width, new_height), Image.Resampling.LANCZOS)

    # Create square canvas with light background
    canvas = Image.new("RGB", (target_size, target_size), LIGHT_BG)

    # Center the logo on canvas
    x_offset = (target_size - new_width) // 2
    y_offset = (target_size - new_height) // 2

    # Paste with alpha channel if available
    if img_resized.mode == "RGBA":
        # Create background
        background = Image.new("RGB", (new_width, new_height), LIGHT_BG)
        background.paste(img_resized, mask=img_resized.split()[3])  # Use alpha as mask
        canvas.paste(background, (x_offset, y_offset))
    else:
        canvas.paste(img_resized, (x_offset, y_offset))

    # Save with aggressive optimization to reduce file size
    print(f"Saving optimized avatar...")
    canvas.save(OUTPUT_PATH, "PNG", optimize=True, quality=85)

    # Check file size
    file_size_kb = OUTPUT_PATH.stat().st_size / 1024
    print(f"\n[OK] Avatar saved to: {OUTPUT_PATH}")
    print(f"Size: {target_size}x{target_size} pixels")
    print(f"File size: {file_size_kb:.1f} KB (compressed from {INPUT_PATH.stat().st_size / 1024:.1f} KB)")

    # Show circular crop preview info
    print(f"\n💡 Note: Telegram will crop this to a circle.")
    print(f"   All important elements are centered and will be visible.")

    return True


if __name__ == "__main__":
    print("=" * 60)
    print("ALGORA — Circular Logo Adaptation for Telegram")
    print("=" * 60)

    success = adapt_circular_logo()

    if success:
        print("\n" + "=" * 60)
        print("✓ Circular logo adapted successfully!")
        print("Next: Run 'python -X utf8 scripts/setup_channel.py' to update")
        print("=" * 60)
    else:
        print("\n[ERROR] Failed to adapt logo")
        sys.exit(1)
