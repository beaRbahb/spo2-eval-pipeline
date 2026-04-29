"""
Signal Noir — HL7 Clinical Message Thumbnail
Terminal-style code snippet with syntax highlighting for social media.
1200x630px, dark background, JetBrains Mono.
"""

from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageChops
from pathlib import Path
import os
import math

# ── Paths ──────────────────────────────────────────────────────────
FONT_DIR = os.path.join(os.path.expanduser("~"), ".claude", "skills", "canvas-design", "canvas-fonts")
OUT_DIR = str(Path(__file__).parent)

MONO = os.path.join(FONT_DIR, "JetBrainsMono-Regular.ttf")
MONO_BOLD = os.path.join(FONT_DIR, "JetBrainsMono-Bold.ttf")

# ── Canvas ─────────────────────────────────────────────────────────
W, H = 1200, 630

# ── Tokyo Night Palette ────────────────────────────────────────────
BG         = (26, 27, 38)        # #1a1b26
BG_CHROME  = (22, 22, 30)        # darker title bar
GUTTER     = (60, 65, 90)        # #3c4160 line numbers
PIPE       = (86, 95, 137)       # #565f89 delimiters
PURPLE     = (187, 154, 247)     # #bb9af7 segment names
CYAN       = (125, 207, 255)     # #7dcfff LOINC codes
BLUE       = (122, 162, 247)     # #7aa2f7 descriptive text
GREEN      = (158, 206, 106)     # #9ece6a numeric values
RED        = (247, 118, 142)     # #f7768e abnormal/emergency
AMBER      = (224, 175, 104)     # #e0af68 reference ranges
WHITE      = (169, 177, 214)     # #a9b1d6 default text
DOT_RED    = (255, 95, 86)
DOT_YELLOW = (255, 189, 46)
DOT_GREEN  = (39, 201, 63)


def draw_vignette(img):
    """Smooth radial vignette using pixel-level distance calculation."""
    rgba = img.convert("RGBA")
    vig = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    pixels = vig.load()
    cx, cy = W / 2, H / 2
    max_dist = math.sqrt(cx ** 2 + cy ** 2)
    for y in range(H):
        for x in range(W):
            dist = math.sqrt((x - cx) ** 2 + (y - cy) ** 2)
            ratio = dist / max_dist
            # Stronger vignette — kicks in after 0.5 radius
            alpha = int(min(255, max(0, 90 * max(0, (ratio - 0.4) / 0.6) ** 1.5)))
            pixels[x, y] = (0, 0, 0, alpha)
    vig = vig.filter(ImageFilter.GaussianBlur(radius=15))
    result = Image.alpha_composite(rgba, vig)
    return result.convert("RGB")


def draw_glow(draw_img, x, y, text, font, color, radius=12):
    """Draw a soft glow behind text for emphasis (red alerts)."""
    glow_layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    glow_draw = ImageDraw.Draw(glow_layer)
    # Draw text in glow color at slightly larger opacity
    glow_color = (color[0], color[1], color[2], 60)
    for dx in range(-2, 3):
        for dy in range(-2, 3):
            glow_draw.text((x + dx, y + dy), text, fill=glow_color, font=font)
    glow_layer = glow_layer.filter(ImageFilter.GaussianBlur(radius=radius))
    draw_img.paste(Image.alpha_composite(draw_img.convert("RGBA"), glow_layer).convert("RGB"), (0, 0))
    return draw_img


def tokenize_hl7_line(line):
    """
    Parse an HL7 line into (text, color, bold) tokens.
    Returns list of (string, color_tuple, is_bold).
    """
    tokens = []

    if not line.strip():
        return tokens

    # Split on pipes but keep them
    parts = line.split("|")
    segment_name = parts[0] if parts else ""

    # Segment name — bold purple
    tokens.append((segment_name, PURPLE, True))

    for i, part in enumerate(parts[1:], 1):
        # Pipe delimiter
        tokens.append(("|", PIPE, False))

        if not part:
            continue

        # Check for known patterns within each field
        colored = False

        # EMERGENCY / emergency — bold red
        if part in ("emergency", "EMERGENCY") or part.startswith("EMERGENCY"):
            tokens.append((part, RED, True))
            colored = True

        # AA abnormal flag
        elif part == "AA":
            tokens.append((part, RED, True))
            colored = True

        # Reference ranges like >94, >90, <100
        elif part.startswith(">") or part.startswith("<"):
            tokens.append((part, AMBER, False))
            colored = True

        # Caret-separated fields (e.g., 59408-5^Description^LN)
        elif "^" in part:
            subparts = part.split("^")
            for j, sp in enumerate(subparts):
                if j > 0:
                    tokens.append(("^", PIPE, False))
                if not sp:
                    continue

                # LOINC code pattern
                if sp in ("59408-5", "X-TRIAGE-001", "X-SATSEC-001", "X-URGENCY-001", "X-DESAT-001"):
                    tokens.append((sp, CYAN, False))
                # Standard identifiers
                elif sp in ("LN", "L", "MR"):
                    tokens.append((sp, GUTTER, False))
                # ORU^R01 message type
                elif sp in ("ORU", "R01", "ORU_R01"):
                    tokens.append((sp, CYAN, False))
                # Descriptive clinical text
                elif any(kw in sp for kw in ["Oxygen", "saturation", "Mean", "Min", "Overnight",
                                               "SpO2", "Monitoring", "Triage", "Label",
                                               "SatSeconds", "Burden"]):
                    tokens.append((sp, BLUE, False))
                # NICU, hospital names
                elif sp in ("NICU", "NICU_HOSPITAL", "SPO2_EVAL_PIPELINE", "EHR_SYSTEM",
                             "DEMO_HOSPITAL", "BABY", "DEMO"):
                    tokens.append((sp, WHITE, False))
                else:
                    tokens.append((sp, WHITE, False))
            colored = True

        # Pure numeric values
        elif _is_numeric(part):
            tokens.append((part, GREEN, False))
            colored = True

        # Timestamps (long digit strings)
        elif part.isdigit() and len(part) >= 8:
            tokens.append((part, WHITE, False))
            colored = True

        # Units
        elif part in ("%", "sec", "{events}"):
            tokens.append((part, WHITE, False))
            colored = True

        # Status flags
        elif part in ("F", "P", "U", "NM", "ST", "1", "2", "3", "5"):
            tokens.append((part, WHITE, False))
            colored = True

        if not colored:
            tokens.append((part, WHITE, False))

    return tokens


def _is_numeric(s):
    try:
        float(s)
        return True
    except ValueError:
        return False


def main():
    img = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(img)

    # ── Load fonts (larger for thumbnail readability) ──────────────
    font_code = ImageFont.truetype(MONO, 16)
    font_code_bold = ImageFont.truetype(MONO_BOLD, 16)
    font_gutter = ImageFont.truetype(MONO, 14)
    font_title = ImageFont.truetype(MONO, 11)
    font_status = ImageFont.truetype(MONO, 11)

    # ── Terminal chrome ────────────────────────────────────────────
    chrome_h = 36
    draw.rectangle([0, 0, W, chrome_h], fill=BG_CHROME)
    # Three dots
    dot_y = chrome_h // 2
    for i, color in enumerate([DOT_RED, DOT_YELLOW, DOT_GREEN]):
        cx = 20 + i * 22
        draw.ellipse([cx - 6, dot_y - 6, cx + 6, dot_y + 6], fill=color)
    # Title text — centered
    title = "hl7_oru_r01_emergency.hl7"
    tw = draw.textlength(title, font=font_title)
    draw.text(((W - tw) / 2, dot_y - 6), title, fill=GUTTER, font=font_title)
    # Thin separator line
    draw.line([(0, chrome_h), (W, chrome_h)], fill=(40, 42, 54), width=1)

    # ── HL7 Lines ──────────────────────────────────────────────────
    lines = [
        'MSH|^~\\&|SPO2_EVAL_PIPELINE|NICU_HOSPITAL|EHR_SYSTEM|NICU_HOSPITAL|20260427||ORU^R01|P|2.5.1',
        'PID|1||b5a2ae59^^^NICU^MR||BABY^DEMO||20260411|U',
        'OBR|1|992459ab||59408-5^Overnight SpO2 Monitoring^LN|||20250101210000||||||F',
        'OBX|1|NM|59408-5^Oxygen saturation Mean^LN||90.0|%|>94|AA|||F',
        'OBX|2|NM|59408-5^Oxygen saturation Min^LN||76.6|%|>90|AA|||F',
        'OBX|3|ST|X-TRIAGE-001^Triage Label^L||emergency||||||F',
        'OBX|5|NM|X-SATSEC-001^SatSeconds Burden^L||1025|sec|<100||||F',
        'NTE|1|L|EMERGENCY \u2014 Severe desaturation event reaching 77% overnight',
    ]

    # Layout — vertically center the code block
    gutter_w = 50
    left_margin = gutter_w + 18
    line_height = 32
    status_h = 26
    code_block_h = len(lines) * line_height
    available_h = H - chrome_h - status_h
    top_start = chrome_h + (available_h - code_block_h) // 2

    # ── Gutter background ──────────────────────────────────────────
    draw.rectangle([0, chrome_h + 1, gutter_w, H - status_h], fill=(20, 21, 32))

    # ── Subtle scan lines for depth (very faint) ──────────────────
    for y in range(chrome_h, H - status_h, 2):
        draw.line([(gutter_w + 1, y), (W, y)], fill=(24, 25, 36), width=1)

    # ── Line highlights ────────────────────────────────────────────
    # NTE emergency line — stronger highlight with red-shifted tint
    nte_y = top_start + 7 * line_height - 4
    draw.rectangle([gutter_w + 1, nte_y, W, nte_y + line_height],
                   fill=(38, 28, 34))
    # Left red accent bar on NTE line
    draw.rectangle([gutter_w + 1, nte_y, gutter_w + 4, nte_y + line_height],
                   fill=(247, 118, 142))

    # AA flag lines — subtle warm highlight
    for idx in [3, 4]:
        hy = top_start + idx * line_height - 4
        draw.rectangle([gutter_w + 1, hy, W, hy + line_height],
                       fill=(32, 28, 36))

    # ── Collect glow positions for red tokens ──────────────────────
    red_glow_items = []

    # ── Render each line ───────────────────────────────────────────
    for line_num, line_text in enumerate(lines):
        y = top_start + line_num * line_height

        # Gutter number — right-aligned
        num_str = str(line_num + 1)
        nw = draw.textlength(num_str, font=font_gutter)
        # Highlight gutter number for emergency line
        gutter_color = RED if line_num == 7 else GUTTER
        draw.text((gutter_w - nw - 10, y + 1), num_str, fill=gutter_color, font=font_gutter)

        # Tokenize and render
        tokens = tokenize_hl7_line(line_text)
        x = left_margin

        for text, color, bold in tokens:
            font = font_code_bold if bold else font_code
            draw.text((x, y), text, fill=color, font=font)
            # Track red tokens for glow pass
            if color == RED:
                red_glow_items.append((x, y, text, font))
            x += draw.textlength(text, font=font)

    # ── Glow pass for red elements ─────────────────────────────────
    for gx, gy, gtext, gfont in red_glow_items:
        img = draw_glow(img, gx, gy, gtext, gfont, RED, radius=10)
    # Redraw red text on top after glow (glow is behind)
    draw = ImageDraw.Draw(img)
    for line_num, line_text in enumerate(lines):
        y = top_start + line_num * line_height
        tokens = tokenize_hl7_line(line_text)
        x = left_margin
        for text, color, bold in tokens:
            font = font_code_bold if bold else font_code
            if color == RED:
                draw.text((x, y), text, fill=color, font=font)
            x += draw.textlength(text, font=font)

    # ── Cursor blink ───────────────────────────────────────────────
    cursor_y = top_start + len(lines) * line_height + 6
    draw.rectangle([left_margin, cursor_y, left_margin + 10, cursor_y + 22],
                   fill=(169, 177, 214))

    # ── Faint gutter separator ─────────────────────────────────────
    draw.line([(gutter_w, chrome_h), (gutter_w, H - status_h)],
              fill=(35, 37, 50), width=1)

    # ── Bottom status bar ──────────────────────────────────────────
    status_y = H - status_h
    draw.rectangle([0, status_y, W, H], fill=BG_CHROME)
    draw.line([(0, status_y), (W, status_y)], fill=(40, 42, 54), width=1)

    # Status bar content
    left_status = "  HL7 v2.5.1"
    right_status = "ORU^R01  |  UTF-8  |  8 lines  "
    draw.text((8, status_y + 7), left_status, fill=GUTTER, font=font_status)
    rw = draw.textlength(right_status, font=font_status)
    draw.text((W - rw - 8, status_y + 7), right_status, fill=GUTTER, font=font_status)

    # Red dot indicator — active alert
    draw.ellipse([W - rw - 22, status_y + 9, W - rw - 14, status_y + 17], fill=RED)

    # ── Vignette ───────────────────────────────────────────────────
    img = draw_vignette(img)

    # ── Save ───────────────────────────────────────────────────────
    out_path = os.path.join(OUT_DIR, "hl7-thumbnail.png")
    img.save(out_path, "PNG", quality=100)
    print(f"Saved: {out_path}")
    print(f"Size: {W}x{H}px")


if __name__ == "__main__":
    main()
