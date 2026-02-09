"""Generate 4 ALGORA logo variants for selection.

Each variant: stylized "A" on dark navy background with amber gold accent.
Variant 1: Constellation — minimal dots and thin lines, starfield feel
Variant 2: Monolith — bold solid geometric "A", clean and heavy
Variant 3: Circuit — PCB traces and right-angle connections
Variant 4: Portal — concentric arcs with "A" silhouette, sci-fi feel

Usage:
    python -X utf8 scripts/generate_logo.py
"""

from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

# Brand colors
NAVY = (26, 35, 126)       # #1A237E
AMBER = (255, 160, 0)      # #FFA000
AMBER_DIM = (180, 112, 0)  # dimmed amber for secondary elements
WHITE = (255, 255, 255)
SLATE = (96, 125, 139)     # #607D8B

SIZE = 800
CX = SIZE // 2
CY = SIZE // 2

OUTPUT_DIR = Path(__file__).parent.parent / "assets"


def _load_font(size: int):
    for path in ["C:/Windows/Fonts/arial.ttf", "arial.ttf"]:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _draw_text(draw: ImageDraw.ImageDraw, text: str, y: int, font_size: int = 68, color=AMBER):
    font = _load_font(font_size)
    bbox = draw.textbbox((0, 0), text, font=font)
    tw = bbox[2] - bbox[0]
    draw.text(((SIZE - tw) // 2, y), text, fill=color, font=font)


def _node(draw, pos, radius, fill, outline=None):
    x, y = pos
    draw.ellipse([x - radius, y - radius, x + radius, y + radius],
                 fill=fill, outline=outline, width=2)


# ═══════════════════════════════════════════════════════════════════
# VARIANT 1 — Constellation (minimal, starfield, elegant)
# ═══════════════════════════════════════════════════════════════════
def variant_constellation() -> Image.Image:
    img = Image.new("RGB", (SIZE, SIZE), NAVY)
    draw = ImageDraw.Draw(img)

    # Sparse star-like dots in background
    import random
    random.seed(42)
    for _ in range(60):
        x = random.randint(30, SIZE - 30)
        y = random.randint(30, 660)
        r = random.choice([1, 1, 1, 2])
        opacity = random.randint(60, 140)
        _node(draw, (x, y), r, (96, 125, 139))

    # "A" as constellation — key stars connected by thin lines
    top = (CX, 100)
    left = (170, 600)
    right = (630, 600)
    cl = (270, 410)
    cr = (530, 410)
    ul = (220, 505)
    ur = (580, 505)
    mid_upper_l = (250, 260)
    mid_upper_r = (550, 260)

    stars = [top, left, right, cl, cr, ul, ur, mid_upper_l, mid_upper_r]
    edges = [
        (top, mid_upper_l), (top, mid_upper_r),
        (mid_upper_l, cl), (mid_upper_r, cr),
        (cl, ul), (cr, ur),
        (ul, left), (ur, right),
        (cl, cr),  # crossbar
    ]

    # Thin connecting lines
    for p1, p2 in edges:
        draw.line([p1, p2], fill=AMBER_DIM, width=2)

    # Star nodes — varying sizes for depth
    sizes = [12, 6, 6, 8, 8, 5, 5, 7, 7]
    for star, sz in zip(stars, sizes):
        # Glow effect
        _node(draw, star, sz + 4, (255, 200, 50))
        _node(draw, star, sz, AMBER)
        _node(draw, star, max(2, sz - 3), WHITE)

    _draw_text(draw, "ALGORA", 690)
    return img


# ═══════════════════════════════════════════════════════════════════
# VARIANT 2 — Monolith (bold, solid, corporate)
# ═══════════════════════════════════════════════════════════════════
def variant_monolith() -> Image.Image:
    img = Image.new("RGB", (SIZE, SIZE), NAVY)
    draw = ImageDraw.Draw(img)

    # Thick solid "A" shape
    outer_top = (CX, 80)
    outer_bl = (110, 620)
    outer_br = (690, 620)

    # Inner cutout (triangle inside the A)
    inner_top = (CX, 260)
    inner_bl = (290, 470)
    inner_br = (510, 470)

    # Left leg
    ll_outer = [(outer_top[0] - 60, outer_top[1] + 80), outer_bl,
                (outer_bl[0] + 110, outer_bl[1]), (outer_top[0], outer_top[1])]
    # Right leg
    rl_outer = [(outer_top[0], outer_top[1]), (outer_br[0] - 110, outer_br[1]),
                outer_br, (outer_top[0] + 60, outer_top[1] + 80)]

    # Draw full triangle
    draw.polygon([outer_top, outer_bl, outer_br], fill=AMBER)

    # Cut out inner triangle (navy to create the "A" hole)
    draw.polygon([inner_top, inner_bl, inner_br], fill=NAVY)

    # Crossbar gap — cut horizontal strip in the legs below the hole
    bar_y1 = 490
    bar_y2 = 530
    # Left gap
    draw.rectangle([0, bar_y1, 265, bar_y2], fill=NAVY)
    # Right gap
    draw.rectangle([535, bar_y1, SIZE, bar_y2], fill=NAVY)

    # Subtle edge glow — draw slightly larger amber shape behind
    # (already done by the solid fill)

    # Add a thin white accent line on top edge
    draw.line([(CX - 2, 80), (112, 618)], fill=WHITE, width=1)
    draw.line([(CX + 2, 80), (688, 618)], fill=WHITE, width=1)

    # Decorative horizontal lines at bottom
    for i in range(3):
        y = 645 + i * 12
        alpha = 200 - i * 60
        draw.line([(200 + i * 40, y), (600 - i * 40, y)], fill=AMBER_DIM, width=1)

    _draw_text(draw, "ALGORA", 690, color=AMBER)
    return img


# ═══════════════════════════════════════════════════════════════════
# VARIANT 3 — Circuit (PCB traces, tech-oriented)
# ═══════════════════════════════════════════════════════════════════
def variant_circuit() -> Image.Image:
    img = Image.new("RGB", (SIZE, SIZE), NAVY)
    draw = ImageDraw.Draw(img)

    # Circuit-style "A" with right-angle segments and solder pads
    # Build the A from horizontal and vertical/diagonal segments

    pad_r = 8  # solder pad radius
    trace_w = 5

    # Key points on the "A"
    top = (CX, 100)
    # Left leg — using angled + vertical segments
    la1 = (CX - 30, 160)
    la2 = (CX - 100, 280)
    la3 = (200, 280)
    la4 = (200, 400)  # crossbar left
    la5 = (200, 500)
    la6 = (160, 600)
    la7 = (160, 640)

    # Right leg — mirror
    ra1 = (CX + 30, 160)
    ra2 = (CX + 100, 280)
    ra3 = (600, 280)
    ra4 = (600, 400)  # crossbar right
    ra5 = (600, 500)
    ra6 = (640, 600)
    ra7 = (640, 640)

    # Crossbar
    cb_l = (200, 400)
    cb_r = (600, 400)

    # Branch traces (decorative)
    br1_start = (200, 340)
    br1_end = (130, 340)
    br2_start = (600, 340)
    br2_end = (670, 340)
    br3_start = (CX, 280)
    br3_end = (CX, 220)

    # Draw traces
    traces = [
        # Left leg
        [top, la1, la2, la3, la4, la5, la6, la7],
        # Right leg
        [top, ra1, ra2, ra3, ra4, ra5, ra6, ra7],
        # Crossbar
        [cb_l, cb_r],
        # Branch traces
        [br1_start, br1_end],
        [br2_start, br2_end],
    ]

    for trace in traces:
        for i in range(len(trace) - 1):
            draw.line([trace[i], trace[i + 1]], fill=AMBER, width=trace_w)

    # Vertical center trace from crossbar down
    draw.line([(CX, 400), (CX, 460)], fill=AMBER, width=trace_w)
    _node(draw, (CX, 460), pad_r - 2, AMBER, WHITE)

    # Draw solder pads at key junctions
    pad_points = [top, la2, la3, la4, la7, ra2, ra3, ra4, ra7,
                  br1_end, br2_end, cb_l, cb_r]

    for p in pad_points:
        _node(draw, p, pad_r, AMBER, WHITE)

    # Special top pad (larger, glowing)
    _node(draw, top, pad_r + 5, AMBER, WHITE)
    _node(draw, top, pad_r - 1, NAVY)
    _node(draw, top, 3, AMBER)

    # Bottom pads — larger (IC pin style)
    for p in [la7, ra7]:
        draw.rectangle([p[0] - 14, p[1] - 6, p[0] + 14, p[1] + 6], fill=AMBER, outline=WHITE, width=1)

    # Background grid (subtle)
    for x in range(0, SIZE, 40):
        draw.line([(x, 0), (x, SIZE)], fill=(30, 40, 140), width=1)
    for y in range(0, SIZE, 40):
        draw.line([(0, y), (SIZE, y)], fill=(30, 40, 140), width=1)

    _draw_text(draw, "ALGORA", 690)
    return img


# ═══════════════════════════════════════════════════════════════════
# VARIANT 4 — Portal (concentric arcs, sci-fi, futuristic)
# ═══════════════════════════════════════════════════════════════════
def variant_portal() -> Image.Image:
    img = Image.new("RGB", (SIZE, SIZE), NAVY)
    draw = ImageDraw.Draw(img)

    # Concentric arc rings behind the "A"
    center = (CX, 380)
    radii = [320, 270, 220, 170]

    for i, r in enumerate(radii):
        bbox = [center[0] - r, center[1] - r, center[0] + r, center[1] + r]
        width = 3 if i % 2 == 0 else 2
        color = AMBER if i < 2 else AMBER_DIM
        # Draw arcs (top portion)
        draw.arc(bbox, start=200, end=340, fill=color, width=width)

    # Smaller decorative arcs at bottom
    for r in [130, 90]:
        bbox = [center[0] - r, center[1] - r, center[0] + r, center[1] + r]
        draw.arc(bbox, start=20, end=160, fill=SLATE, width=1)

    # Clean geometric "A" in center — bold lines
    top = (CX, 90)
    bl = (185, 590)
    br = (615, 590)
    cl = (280, 420)
    cr = (520, 420)

    # Draw "A" with thick lines
    line_w = 8
    draw.line([top, bl], fill=AMBER, width=line_w)
    draw.line([top, br], fill=AMBER, width=line_w)
    draw.line([cl, cr], fill=AMBER, width=line_w)

    # Bright dot at apex
    _node(draw, top, 16, AMBER)
    _node(draw, top, 8, WHITE)

    # Dots at crossbar ends
    _node(draw, cl, 8, AMBER, WHITE)
    _node(draw, cr, 8, AMBER, WHITE)

    # Dots at base
    _node(draw, bl, 6, AMBER)
    _node(draw, br, 6, AMBER)

    # Radial lines from apex (radar/scan effect)
    for angle_deg in [-70, -55, -40, 40, 55, 70]:
        angle = math.radians(angle_deg - 90)  # -90 so 0 is up
        length = 50
        x2 = top[0] + math.cos(angle) * length
        y2 = top[1] + math.sin(angle) * length
        draw.line([top, (x2, y2)], fill=SLATE, width=1)

    # Horizontal scan lines across entire image (subtle)
    for y in range(100, 650, 30):
        opacity_color = (30, 40, 140)
        draw.line([(50, y), (750, y)], fill=opacity_color, width=1)

    _draw_text(draw, "ALGORA", 690)
    return img


# ═══════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════
def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    variants = {
        "v1_constellation": variant_constellation,
        "v2_monolith": variant_monolith,
        "v3_circuit": variant_circuit,
        "v4_portal": variant_portal,
    }

    for name, func in variants.items():
        img = func()
        path = OUTPUT_DIR / f"logo_{name}.png"
        img.save(path, "PNG")
        print(f"Saved: {path}")

    print(f"\nAll 4 variants saved to {OUTPUT_DIR}/")


if __name__ == "__main__":
    main()
