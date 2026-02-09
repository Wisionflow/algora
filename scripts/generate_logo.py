"""Generate ALGORA logo programmatically.

Creates a stylized "A" made of connected nodes and geometric lines,
resembling a neural network graph on dark navy background with amber gold accent.
Output: 800x800 PNG (will be resized for Telegram avatar).
"""

from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

# Brand colors
NAVY = (26, 35, 126)       # #1A237E
AMBER = (255, 160, 0)      # #FFA000
WHITE = (255, 255, 255)
SLATE = (96, 125, 139)     # #607D8B

SIZE = 800
CENTER_X = SIZE // 2
CENTER_Y = SIZE // 2

OUTPUT_DIR = Path(__file__).parent.parent / "assets"


def draw_logo() -> Image.Image:
    img = Image.new("RGB", (SIZE, SIZE), NAVY)
    draw = ImageDraw.Draw(img)

    # --- Stylized "A" structure ---
    # The "A" is made of nodes connected by lines
    # Main triangle shape of letter A
    top = (CENTER_X, 120)
    bottom_left = (160, 650)
    bottom_right = (640, 650)
    # Crossbar points
    cross_left = (255, 440)
    cross_right = (545, 440)
    # Mid-points on legs for extra nodes
    mid_left = (208, 545)
    mid_right = (592, 545)
    upper_left = (230, 300)
    upper_right = (570, 300)
    # Inner nodes (neural network feel)
    inner_top = (CENTER_X, 250)
    inner_left = (320, 380)
    inner_right = (480, 380)
    inner_center = (CENTER_X, 340)
    inner_bottom = (CENTER_X, 520)

    # All nodes
    main_nodes = [top, bottom_left, bottom_right, cross_left, cross_right,
                  mid_left, mid_right, upper_left, upper_right]
    inner_nodes = [inner_top, inner_left, inner_right, inner_center, inner_bottom]

    # --- Draw connections (lines) ---
    # Main A structure
    main_edges = [
        (top, upper_left), (upper_left, cross_left), (cross_left, mid_left), (mid_left, bottom_left),
        (top, upper_right), (upper_right, cross_right), (cross_right, mid_right), (mid_right, bottom_right),
        (cross_left, cross_right),
    ]

    # Inner neural network connections
    neural_edges = [
        (top, inner_top),
        (inner_top, inner_left), (inner_top, inner_right), (inner_top, inner_center),
        (inner_left, inner_center), (inner_right, inner_center),
        (inner_left, cross_left), (inner_right, cross_right),
        (inner_center, inner_bottom),
        (inner_bottom, cross_left), (inner_bottom, cross_right),
        (inner_bottom, mid_left), (inner_bottom, mid_right),
        (upper_left, inner_left), (upper_right, inner_right),
    ]

    # Draw neural edges first (thinner, amber with transparency effect)
    for p1, p2 in neural_edges:
        draw.line([p1, p2], fill=(*AMBER, 180), width=2)

    # Draw main structure edges (thicker, bright amber)
    for p1, p2 in main_edges:
        draw.line([p1, p2], fill=AMBER, width=4)

    # --- Draw nodes ---
    def draw_node(pos: tuple[int, int], radius: int, fill: tuple, outline: tuple | None = None):
        x, y = pos
        draw.ellipse(
            [x - radius, y - radius, x + radius, y + radius],
            fill=fill,
            outline=outline,
            width=2,
        )

    # Main structural nodes (larger, amber)
    for node in main_nodes:
        draw_node(node, 10, AMBER, WHITE)

    # Inner neural nodes (smaller, white core with amber outline)
    for node in inner_nodes:
        draw_node(node, 7, WHITE, AMBER)

    # Top node special (largest, glowing)
    draw_node(top, 14, AMBER, WHITE)

    # --- Add "ALGORA" text below the symbol ---
    # Try to load a clean font, fall back to default
    font_size = 72
    try:
        font = ImageFont.truetype("arial.ttf", font_size)
    except OSError:
        try:
            font = ImageFont.truetype("C:/Windows/Fonts/arial.ttf", font_size)
        except OSError:
            font = ImageFont.load_default()

    text = "ALGORA"
    bbox = draw.textbbox((0, 0), text, font=font)
    text_w = bbox[2] - bbox[0]
    text_x = (SIZE - text_w) // 2
    text_y = 695

    # Draw text with slight letter spacing effect
    draw.text((text_x, text_y), text, fill=AMBER, font=font)

    # Subtle decorative dots around the edges (ambient neural network feel)
    ambient_positions = [
        (80, 180), (720, 180), (60, 400), (740, 400),
        (100, 300), (700, 300), (130, 500), (670, 500),
        (50, 550), (750, 550), (90, 650), (710, 650),
    ]
    for pos in ambient_positions:
        draw_node(pos, 3, SLATE)

    # Faint connecting lines from ambient dots to nearest main nodes
    faint_connections = [
        ((80, 180), top), ((720, 180), top),
        ((60, 400), cross_left), ((740, 400), cross_right),
        ((130, 500), mid_left), ((670, 500), mid_right),
    ]
    for p1, p2 in faint_connections:
        draw.line([p1, p2], fill=(*SLATE, 100), width=1)

    return img


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Full size logo
    logo = draw_logo()
    logo_path = OUTPUT_DIR / "logo_800.png"
    logo.save(logo_path, "PNG")
    print(f"Logo saved: {logo_path}")

    # Telegram avatar size (640x640 recommended, min 100x100)
    avatar = logo.resize((640, 640), Image.LANCZOS)
    avatar_path = OUTPUT_DIR / "avatar_640.png"
    avatar.save(avatar_path, "PNG")
    print(f"Avatar saved: {avatar_path}")

    # Small preview
    small = logo.resize((200, 200), Image.LANCZOS)
    small_path = OUTPUT_DIR / "logo_200.png"
    small.save(small_path, "PNG")
    print(f"Preview saved: {small_path}")


if __name__ == "__main__":
    main()
