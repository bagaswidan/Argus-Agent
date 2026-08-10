"""Branding — Argus.

Logo terinspirasi Argus Panoptes (mitologi Yunani): raksasa bermata 100,
penjaga setia yang melihat segalanya. Mata sentral = kesadaran penuh;
8 mata satelit = 8 prinsip Konstitusi; iris berlapis = pipeline arsitektur;
pupil = GOAL (visi: memahami goal, bukan sekadar prompt).

Blueprint source: Argus Engineering Specification v1.0 (PART 1).
"""
from __future__ import annotations

from pathlib import Path

# ---------------------------------------------------------------------------
# Visi & Misi dari blueprint (PART 1 §2, §3)
# ---------------------------------------------------------------------------
VISION = [
    "Memahami goal, bukan sekadar prompt",
    "Keputusan berdasarkan evidence",
    "Capability sebagai abstraksi utama",
    "Belajar dari pengalaman",
    "Ringan, tetapi dapat diperluas",
]

CONSTITUTION = [
    "Truth Before Fluency",
    "Evidence Before Conclusion",
    "User In Control",
    "Never Guess",
    "Verify Before Respond",
    "Security First",
    "Learn From Every Execution",
    "Small by Default, Powerful by Choice",
]

# Pipeline arsitektur (PART 1 §5)
PIPELINE = (
    "Communication → Brain → Goal → Planning → Decision → Capability → "
    "Security → Runtime → Verification → Reflection → Knowledge → Response"
)

# ---------------------------------------------------------------------------
# ASCII logo
# ---------------------------------------------------------------------------
LOGO_ASCII = r'''
        .-"++++"-.
       .'  ####  '.
      (    ######    )
      |    ########    |
      |    ##..######  |
      |    ########    |
      (    ######    )
       '.  ####  .'
         '-....-'
'''

WORDMARK = r'''
    ___    ____  ________  _______
   /   |  / __ \/ ____/ / / / ___/
  / /| | / /_/ / / __/ / / /\__ \
 / ___ |/ _, _/ /_/ / /_/ /___/ /
/_/  |_/_/ |_|\____/\____//____/
'''


def logo() -> str:
    """Logo lengkap: mata + wordmark + visi + konstitusi + pipeline."""
    eye = LOGO_ASCII.strip("\n")
    lines = [
        eye,
        "",
        WORDMARK.rstrip("\n"),
        "",
        "the all-seeing agent",
        "",
        "VISION",
        *[f"  {i+1}. {v}" for i, v in enumerate(VISION)],
        "",
        "CONSTITUTION",
        *[f"  {i+1}. {c}" for i, c in enumerate(CONSTITUTION)],
        "",
        "PIPELINE",
        f"  {PIPELINE}",
    ]
    return "\n".join(lines)


def eye_only() -> str:
    return LOGO_ASCII.strip("\n")


def wordmark_only() -> str:
    return WORDMARK.rstrip("\n")


# ---------------------------------------------------------------------------
# Rendered JPEG — mata + 8 mata satelit (konstitusi) + visi + pipeline
# ---------------------------------------------------------------------------
_FONT_CANDIDATES = [
    # Linux (Debian/Ubuntu)
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    # macOS
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "/System/Library/Fonts/Helvetica.ttc",
    "/Library/Fonts/Arial.ttf",
    # Windows
    "C:/Windows/Fonts/arialbd.ttf",
    "C:/Windows/Fonts/arial.ttf",
    "C:/Windows/Fonts/segoeui.ttf",
]

_FONT_MONO_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
    "/System/Library/Fonts/Menlo.ttc",
    "/System/Library/Fonts/Supplemental/Courier New.ttf",
    "C:/Windows/Fonts/consola.ttf",
    "C:/Windows/Fonts/cour.ttf",
]


def _load_font(candidates: list[str], size: int):
    from PIL import ImageFont

    for path in candidates:
        try:
            return ImageFont.truetype(path, size)
        except Exception:  # noqa: BLE001
            continue
    return ImageFont.load_default(size)


def render_logo_jpeg(path: Optional[str] = None, width: int = 1000) -> str:
    import tempfile
    path = path or str(Path(tempfile.gettempdir()) / "argus_logo.jpg")
    import math

    from PIL import Image, ImageDraw

    BG = (10, 10, 13)
    GOLD = (201, 168, 107)
    GOLD_BRIGHT = (235, 205, 150)
    GOLD_DIM = (120, 100, 70)
    TEXT = (232, 232, 234)
    DIM = (120, 120, 132)

    font_big = _load_font(_FONT_CANDIDATES, 72)
    font_small = _load_font(_FONT_MONO_CANDIDATES, 15)
    font_tiny = _load_font(_FONT_MONO_CANDIDATES, 12)

    h = 820
    img = Image.new("RGB", (width, h), BG)
    d = ImageDraw.Draw(img)
    cx = width // 2
    eye_top = 40
    eye_cy = eye_top + 120

    # --- mata sentral ---
    d.ellipse([cx - 180, eye_top, cx + 180, eye_top + 240], outline=GOLD_DIM, width=3)
    d.ellipse([cx - 108, eye_top + 55, cx + 108, eye_top + 185], outline=GOLD, width=4)
    d.ellipse([cx - 66, eye_top + 82, cx + 66, eye_top + 158], outline=GOLD_BRIGHT, width=3)
    # pupil = GOAL
    d.ellipse([cx - 30, eye_top + 100, cx + 30, eye_top + 140], fill=GOLD_BRIGHT)
    bbox = d.textbbox((0, 0), "GOAL", font=font_tiny)
    d.text(
        (cx - (bbox[2] - bbox[0]) // 2 - bbox[0], eye_top + 116),
        "GOAL", font=font_tiny, fill=(10, 10, 13),
    )
    d.ellipse([cx - 12, eye_top + 106, cx - 2, eye_top + 116], fill=(255, 250, 235))

    # --- 8 mata satelit = 8 prinsip konstitusi ---
    short = [
        "TRUTH", "EVIDENCE", "USER", "NEVER GUESS",
        "VERIFY", "SECURITY", "LEARN", "SMALL",
    ]
    for i, label in enumerate(short):
        ang = math.radians(i * 45 - 90)
        sx = cx + 260 * math.cos(ang)
        sy = eye_cy + 175 * math.sin(ang)
        # mata satelit
        d.ellipse([sx - 10, sy - 7, sx + 10, sy + 7], outline=GOLD_DIM, width=2)
        d.ellipse([sx - 3.5, sy - 2.5, sx + 3.5, sy + 2.5], fill=GOLD)
        # label
        bbox = d.textbbox((0, 0), label, font=font_tiny)
        lx = sx - (bbox[2] - bbox[0]) // 2
        ly = sy + 16
        if i in (0, 1, 6, 7):  # top labels above
            ly = sy - 22
        d.text((lx - bbox[0], ly), label, font=font_tiny, fill=DIM)

    # garis penghubung mata satelit (lingkaran orbit)
    d.ellipse([cx - 260, eye_cy - 175, cx + 260, eye_cy + 175], outline=(60, 55, 45), width=1)

    # --- wordmark ---
    bbox = d.textbbox((0, 0), "ARGUS", font=font_big)
    wtext = bbox[2] - bbox[0]
    d.text((cx - wtext // 2 - bbox[0], 310), "ARGUS", font=font_big, fill=TEXT)

    # --- tagline ---
    tag = "the all-seeing agent"
    bbox = d.textbbox((0, 0), tag, font=font_small)
    d.text((cx - (bbox[2] - bbox[0]) // 2 - bbox[0], 402), tag, font=font_small, fill=GOLD)

    # --- vision ---
    vy = 450
    d.text((cx - 320, vy), "V I S I O N", font=font_tiny, fill=DIM)
    for i, v in enumerate(VISION):
        bbox = d.textbbox((0, 0), v, font=font_tiny)
        d.text(
            (cx - (bbox[2] - bbox[0]) // 2 - bbox[0], vy + 22 + i * 19),
            v, font=font_tiny, fill=TEXT,
        )

    # --- constitution ringkas ---
    cy = 640
    d.text((cx - 320, cy), "K O N S T I T U S I", font=font_tiny, fill=DIM)
    for i in range(0, 8, 2):
        left = CONSTITUTION[i]
        right = CONSTITUTION[i + 1] if i + 1 < 8 else ""
        y = cy + 22 + (i // 2) * 19
        bbox_l = d.textbbox((0, 0), left, font=font_tiny)
        bbox_r = d.textbbox((0, 0), right, font=font_tiny)
        d.text((cx - 300 - bbox_l[0], y), left, font=font_tiny, fill=TEXT)
        d.text((cx + 40 - bbox_r[0], y), right, font=font_tiny, fill=TEXT)

    img.save(path, "JPEG", quality=93)
    return path
