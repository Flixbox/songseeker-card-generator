import pandas as pd
from PIL import Image
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfbase.pdfmetrics import registerFontFamily
import qrcode
from qrcode.image.styledpil import StyledPilImage
import hashlib
import argparse
import textwrap
import os
import requests
from io import BytesIO

PADDING_RATIO = 0.10  # 10% padding on each side inside each card box
YEAR_MAX_HEIGHT_RATIO = 0.20  # Year text may take up to 20% of inner card height
ARTIST_MAX_HEIGHT_RATIO = 0.12  # Artist block line size cap relative to inner height
TITLE_MAX_HEIGHT_RATIO = 0.12   # Title block line size cap relative to inner height

import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))
import src.fonts as fonts

def _inner_rect(x, y, width, height, padding_ratio=PADDING_RATIO):
    """Return the inner content rectangle applying padding on all sides."""
    pad_x = width * padding_ratio
    pad_y = height * padding_ratio
    return (x + pad_x, y + pad_y, width - 2 * pad_x, height - 2 * pad_y)

def _wrap_text_to_width(c, text, font_name, font_size, max_width):
    """Wrap text into lines that do not exceed max_width using ReportLab width metrics.
    Falls back to character-level splitting if a single word exceeds max_width.
    Returns a list of lines (strings)."""
    if text is None or str(text).strip() == "":
        return []
    words = str(text).split()
    lines = []
    current = ""
    for w in words:
        candidate = (current + " " + w).strip()
        if c.stringWidth(candidate, font_name, font_size) <= max_width:
            current = candidate
        else:
            # If current is empty, the single word might be too long — split by characters
            if current == "":
                segment = ""
                for ch in w:
                    if c.stringWidth(segment + ch, font_name, font_size) <= max_width:
                        segment += ch
                    else:
                        if segment:
                            lines.append(segment)
                        segment = ch
                if segment:
                    current = segment
                else:
                    current = ""
            else:
                lines.append(current)
                current = w
    if current:
        lines.append(current)
    return lines

def draw_image_in_rect(c, pil_img, x, y, width, height):
    """Draw a PIL image scaled to exactly fit the given rectangle (x, y, width, height).
    Coordinates are ReportLab points. Image aspect is preserved by our layout (card size follows image ratio).
    """
    img_reader = ImageReader(pil_img)
    c.drawImage(img_reader, x, y, width=width, height=height)

def draw_background_image(c, pil_img, page_width, page_height):
    # Use ImageReader to draw PIL images directly onto the canvas (avoids TypeError with BytesIO)
    img_reader = ImageReader(pil_img)
    c.drawImage(img_reader, 0, 0, width=page_width, height=page_height)

def generate_qr_code(url, file_path, icon_path, icon_image_cache={}, qr_padding_px=None):
    # box_size controls pixels per QR module; border is measured in modules
    box_size = 10
    if qr_padding_px is None:
        border_modules = 4  # default quiet zone (modules)
    else:
        # Convert desired pixel padding to module count; allow 0 but warn in docs
        border_modules = max(0, int(round(qr_padding_px / box_size)))

    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_Q,
        box_size=box_size,
        border=border_modules,
    )
    qr.add_data(url)
    qr.make(fit=True)
    if icon_path is None:
        img = qr.make_image(fill_color="black", back_color="white")
    else:
        if icon_path.startswith('http'):
            if icon_path not in icon_image_cache:
                response = requests.get(icon_path)
                icon_image_cache[icon_path] = BytesIO(response.content)
            icon_image = icon_image_cache[icon_path]
            img = qr.make_image(image_factory=StyledPilImage, embeded_image_path=icon_image)
        else:
            img = qr.make_image(image_factory=StyledPilImage, embeded_image_path=icon_path)
    img.save(file_path)

def add_qr_code_with_border(c, url, position, box_width, box_height, icon_path, qr_padding_px=None, shrink_pct=0.0):
    hash_object = hashlib.sha256(url.encode())
    hex_dig = hash_object.hexdigest()

    qr_code_path = f"qr_{hex_dig}.png"  # Unique path for each QR code
    generate_qr_code(url, qr_code_path, icon_path, qr_padding_px=qr_padding_px)
    x, y = position
    # Constrain QR to the inner padded rectangle
    inner_x, inner_y, inner_w, inner_h = _inner_rect(x, y, box_width, box_height)
    # Optionally shrink content area by percentage and re-center
    try:
        pct = float(shrink_pct or 0.0)
    except (TypeError, ValueError):
        pct = 0.0
    scale = 1.0 - (pct / 100.0)
    # Clamp scale to avoid degenerate zero sizes
    scale = max(0.05, min(1.0, scale))
    if scale < 1.0:
        scaled_w = inner_w * scale
        scaled_h = inner_h * scale
        inner_x = inner_x + (inner_w - scaled_w) / 2.0
        inner_y = inner_y + (inner_h - scaled_h) / 2.0
        inner_w = scaled_w
        inner_h = scaled_h
    # Keep QR square: size is min of inner dimensions; center within the inner box
    qr_size = min(inner_w, inner_h)
    qr_x = inner_x + (inner_w - qr_size) / 2
    qr_y = inner_y + (inner_h - qr_size) / 2
    c.drawImage(qr_code_path, qr_x, qr_y, width=qr_size, height=qr_size)
    # c.rect(x, y, box_size, box_size)
    os.remove(qr_code_path)

def add_text_box(c, info, position, box_width, box_height,
                 font_artist=None, font_size_artist=14,
                 font_title=None, font_size_title=14,
                 font_year=None, font_size_year=50,
                 shrink_pct=0.0):
    x, y = position
    # Establish an inner padded content area
    inner_x, inner_y, inner_w, inner_h = _inner_rect(x, y, box_width, box_height)

    # Optionally shrink content area by percentage and re-center
    try:
        pct = float(shrink_pct or 0.0)
    except (TypeError, ValueError):
        pct = 0.0
    scale = 1.0 - (pct / 100.0)
    scale = max(0.05, min(1.0, scale))
    if scale < 1.0:
        scaled_w = inner_w * scale
        scaled_h = inner_h * scale
        inner_x = inner_x + (inner_w - scaled_w) / 2.0
        inner_y = inner_y + (inner_h - scaled_h) / 2.0
        inner_w = scaled_w
        inner_h = scaled_h

    # Base margins; will be scaled along with fonts if needed
    text_margin = 4.0

    default_font_color = '0,0,0' # Default color is black

    # Check if 'backcol' is in info and set the fill color
    if 'backcol' in info and not pd.isna(info['backcol']):
        r, g, b = tuple(float(x) for x in info['backcol'].split(','))
        c.setFillColorRGB(r, g, b)
        c.rect(x, y, box_width, box_height, fill=1)
    else:
        c.rect(x, y, box_width, box_height)

    r, g, b = tuple(float(x) for x in default_font_color.split(','))
    c.setFillColorRGB(r, g, b)

    # Compose content blocks
    artist_text = None if 'Artist' not in info or pd.isna(info['Artist']) else f"{info['Artist']}"
    title_text = None if 'Title' not in info or pd.isna(info['Title']) else f"{info['Title']}"
    year_text = None if 'Year' not in info or pd.isna(info['Year']) else f"{info['Year']}"

    # Choose fonts (use Unicode TTF if available)
    if not font_artist:
        font_artist = fonts.FONT_BOLD_NAME
    if not font_title:
        font_title = fonts.FONT_REGULAR_NAME
    if not font_year:
        font_year = fonts.FONT_BOLD_NAME

    # Start with provided base sizes
    size_artist = float(font_size_artist)
    size_title = float(font_size_title)
    size_year = float(font_size_year)
    # Cap initial year size relative to inner height so it doesn't dominate
    size_year = min(size_year, inner_h * YEAR_MAX_HEIGHT_RATIO)
    # Cap initial artist and title sizes relative to inner height
    size_artist = min(size_artist, inner_h * ARTIST_MAX_HEIGHT_RATIO)
    size_title = min(size_title, inner_h * TITLE_MAX_HEIGHT_RATIO)

    # Iteratively wrap and scale to ensure content fits in inner box
    min_font_size = 6.0
    max_iters = 8
    for _ in range(max_iters):
        artist_lines = _wrap_text_to_width(c, artist_text, font_artist, size_artist, inner_w) if artist_text else []
        title_lines = _wrap_text_to_width(c, title_text, font_title, size_title, inner_w) if title_text else []

        # Line gaps proportional to font sizes
        gap_artist = size_artist * 0.25
        gap_title = size_title * 0.25
        block_gap = min(size_artist, size_title, size_year) * 0.4

        total_height = 0.0
        if artist_lines:
            total_height += len(artist_lines) * size_artist + max(0, len(artist_lines) - 1) * gap_artist
        if artist_lines and (title_lines or year_text):
            total_height += block_gap
        if title_lines:
            total_height += len(title_lines) * size_title + max(0, len(title_lines) - 1) * gap_title
        if title_lines and year_text:
            total_height += block_gap
        if year_text:
            total_height += size_year

        if total_height <= inner_h:
            break

        # Scale down sizes proportionally to fit, with a small safety margin
        scale = max(0.1, (inner_h / total_height) * 0.98)
        size_artist = max(min_font_size, size_artist * scale)
        size_title = max(min_font_size, size_title * scale)
        size_year = max(min_font_size, size_year * scale)

    # After scaling, ensure year fits width if present
    if year_text:
        lw = c.stringWidth(year_text, font_year, size_year)
        if lw > inner_w and lw > 0:
            size_year = max(min_font_size, size_year * (inner_w / lw) * 0.98)

    # After adjustments, recompute lines for final placement
    artist_lines = _wrap_text_to_width(c, artist_text, font_artist, size_artist, inner_w) if artist_text else []
    title_lines = _wrap_text_to_width(c, title_text, font_title, size_title, inner_w) if title_text else []
    gap_artist = size_artist * 0.25
    gap_title = size_title * 0.25
    block_gap = min(size_artist, size_title, size_year) * 0.4

    # Compute final total height and top-down placement within inner box
    total_height = 0.0
    if artist_lines:
        total_height += len(artist_lines) * size_artist + max(0, len(artist_lines) - 1) * gap_artist
    if artist_lines and (title_lines or year_text):
        total_height += block_gap
    if title_lines:
        total_height += len(title_lines) * size_title + max(0, len(title_lines) - 1) * gap_title
    if title_lines and year_text:
        total_height += block_gap
    if year_text:
        total_height += size_year

    current_y = inner_y + inner_h  # start at top of inner box

    # Draw artist
    if artist_lines:
        current_y -= size_artist
        for idx, line in enumerate(artist_lines):
            line_width = c.stringWidth(line, font_artist, size_artist)
            line_x = inner_x + (inner_w - line_width) / 2
            c.setFont(font_artist, size_artist)
            c.drawString(line_x, current_y, line)
            if idx < len(artist_lines) - 1:
                current_y -= (gap_artist + size_artist)
        if (title_lines or year_text):
            current_y -= block_gap

    # Draw title
    if title_lines:
        current_y -= size_title
        for idx, line in enumerate(title_lines):
            line_width = c.stringWidth(line, font_title, size_title)
            line_x = inner_x + (inner_w - line_width) / 2
            c.setFont(font_title, size_title)
            c.drawString(line_x, current_y, line)
            if idx < len(title_lines) - 1:
                current_y -= (gap_title + size_title)
        if year_text:
            current_y -= block_gap

    # Draw year (single line), align centered horizontally
    if year_text:
        line_width = c.stringWidth(year_text, font_year, size_year)
        line_x = inner_x + (inner_w - line_width) / 2
        current_y -= size_year
        c.setFont(font_year, size_year)
        c.drawString(line_x, current_y, year_text)


def main(csv_file_path, output_pdf_path, icon_path=None, mirror_backside=True, front_bg_path=None, back_bg_path=None, qr_padding_px=None, shrink_front_pct=0.0, shrink_back_pct=0.0):
    # Ensure Unicode TrueType fonts are registered before drawing
    fonts.setup_unicode_fonts()
    data = pd.read_csv(csv_file_path)
    # Remove leading/trailing whitespaces across the DataFrame using DataFrame.map (fallback to applymap for older pandas)
    try:
        data = data.map(lambda x: x.strip() if isinstance(x, str) else x)
    except AttributeError:
        data = data.applymap(lambda x: x.strip() if isinstance(x, str) else x)

    # Handle background images and page/card size
    front_bg_img = None
    back_bg_img = None
    if front_bg_path and back_bg_path:
        front_bg_img = Image.open(front_bg_path)
        back_bg_img = Image.open(back_bg_path)
        if front_bg_img.size != back_bg_img.size:
            raise ValueError("Front and back background images must be the exact same size.")
        # Set page size based on background image DPI
        dpi = front_bg_img.info.get('dpi', (300, 300))[0]  # fallback to 300 dpi if not present
        px_width, px_height = front_bg_img.size
        page_width = px_width * 72.0 / dpi
        page_height = px_height * 72.0 / dpi

        # Use 3 columns; derive card height from image aspect ratio
        boxes_per_row = 3
        hpageindent = 0
        vpageindent = 0
        card_width = (page_width - 2 * hpageindent) / boxes_per_row
        aspect = px_height / px_width  # height/width
        card_height = card_width * aspect
        # Determine rows that fit fully
        boxes_per_column = int((page_height - 2 * vpageindent) // card_height) if card_height > 0 else 1
        boxes_per_column = max(1, boxes_per_column)
        boxes_per_page = boxes_per_row * boxes_per_column
    else:
        from reportlab.lib.pagesizes import A4
        page_width, page_height = A4
        box_size = 6.5 * cm
        boxes_per_row = int(page_width // box_size)
        boxes_per_column = int(page_height // box_size)
        boxes_per_page = boxes_per_row * boxes_per_column
        vpageindent = 0.8 * cm
        hpageindent = (page_width - (box_size * boxes_per_row)) / 2

    c = canvas.Canvas(output_pdf_path, pagesize=(page_width, page_height))

    for i in range(0, len(data), boxes_per_page):
        # FRONT SIDE (QR)
        for index in range(i, min(i + boxes_per_page, len(data))):
            row = data.iloc[index]
            if front_bg_img:
                # Compute grid position
                position_index = index % boxes_per_page
                column_index = position_index % boxes_per_row
                row_index = position_index // boxes_per_row
                x = hpageindent + (column_index * card_width)
                y = page_height - vpageindent - ((row_index + 1) * card_height)
                # Draw background image in the card rect and then QR centered
                draw_image_in_rect(c, front_bg_img, x, y, card_width, card_height)
                add_qr_code_with_border(c, row['URL'], (x, y), card_width, card_height, icon_path, qr_padding_px=qr_padding_px, shrink_pct=shrink_front_pct)
            else:
                position_index = index % (boxes_per_row * boxes_per_column)
                column_index = position_index % boxes_per_row
                row_index = position_index // boxes_per_row
                x = hpageindent + (column_index * box_size)
                y = page_height - vpageindent - (row_index + 1) * box_size
                add_qr_code_with_border(c, row['URL'], (x, y), box_size, box_size, icon_path, qr_padding_px=qr_padding_px, shrink_pct=shrink_front_pct)
        c.showPage()

        # BACK SIDE (TEXT)
        for index in range(i, min(i + boxes_per_page, len(data))):
            row = data.iloc[index]
            if back_bg_img:
                position_index = index % boxes_per_page
                # Mirror column if requested
                if mirror_backside:
                    column_index = (boxes_per_row - 1) - (position_index % boxes_per_row)
                else:
                    column_index = position_index % boxes_per_row
                row_index = position_index // boxes_per_row
                x = hpageindent + (column_index * card_width)
                y = page_height - vpageindent - ((row_index + 1) * card_height)
                draw_image_in_rect(c, back_bg_img, x, y, card_width, card_height)
                add_text_box(c, row, (x, y), card_width, card_height, shrink_pct=shrink_back_pct)
            else:
                position_index = index % boxes_per_page
                if mirror_backside:
                    column_index = (boxes_per_row-1) - position_index % boxes_per_row
                else:
                    column_index = position_index % boxes_per_row
                row_index = position_index // boxes_per_row
                x = hpageindent + (column_index * box_size)
                y = page_height - vpageindent - (row_index + 1) * box_size
                add_text_box(c, row, (x, y), box_size, box_size, shrink_pct=shrink_back_pct)
        c.showPage()

    c.save()

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("csv_file", help="Path to the CSV file")
    parser.add_argument("output_pdf", help="Path to the output PDF file")
    parser.add_argument("--icon", help="path to icon to embedd to QR Code, should not exeed 300x300px and using transparent background", required=False)
    parser.add_argument("--no-mirror-backside", action="store_true", help="Disable mirroring on the backside (text side)")
    parser.add_argument("--front-bg", help="Path to background image for the front (QR) side", required=False)
    parser.add_argument("--back-bg", help="Path to background image for the back (text) side", required=False)
    parser.add_argument("--qr-padding-px", type=int, default=None, help="QR code white border thickness in pixels (quiet zone). Example: 10. Note: QR spec recommends ~4 modules (~40px with default settings); reducing too much may impact scan reliability.")
    parser.add_argument("--shrink-front", type=float, default=0.0, help="Shrink percentage for front (QR) content area, 0-100. Example: 10 => 10% smaller (90% of original). Values are clamped to a safe minimum size.")
    parser.add_argument("--shrink-back", type=float, default=0.0, help="Shrink percentage for back (text) content area, 0-100. Example: 15 => 15% smaller. Values are clamped to a safe minimum size.")
    args = parser.parse_args()
    mirror_backside = not args.no_mirror_backside
    main(args.csv_file, args.output_pdf, args.icon, mirror_backside, args.front_bg, args.back_bg, qr_padding_px=args.qr_padding_px, shrink_front_pct=args.shrink_front, shrink_back_pct=args.shrink_back)
