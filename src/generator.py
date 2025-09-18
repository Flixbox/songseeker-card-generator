"""PDF generation orchestrator for SongSeeker cards."""
from __future__ import annotations

from typing import Optional

import pandas as pd
from PIL import Image
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm

from . import fonts
from .draw import draw_image_in_rect
from .qr_utils import add_qr_code_within_rect
from .text_boxes import add_text_box


def main(
    csv_file_path: str,
    output_pdf_path: str,
    icon_path: Optional[str] = None,
    mirror_backside: bool = True,
    front_bg_path: Optional[str] = None,
    back_bg_path: Optional[str] = None,
    qr_padding_px: Optional[int] = None,
    shrink_front_pct: float = 0.0,
    shrink_back_pct: float = 0.0,
):
    # Ensure Unicode TrueType fonts are registered before drawing
    fonts.setup_unicode_fonts()
    data = pd.read_csv(csv_file_path)
    # Remove leading/trailing whitespaces across the DataFrame
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
        dpi = front_bg_img.info.get("dpi", (300, 300))[0]  # fallback to 300 dpi if not present
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
                draw_image_in_rect(c, front_bg_img, x, y, card_width, card_height)
                add_qr_code_within_rect(
                    c,
                    row["URL"],
                    (x, y),
                    card_width,
                    card_height,
                    icon_path,
                    qr_padding_px=qr_padding_px,
                    shrink_pct=shrink_front_pct,
                )
            else:
                position_index = index % (boxes_per_row * boxes_per_column)
                column_index = position_index % boxes_per_row
                row_index = position_index // boxes_per_row
                x = hpageindent + (column_index * box_size)
                y = page_height - vpageindent - (row_index + 1) * box_size
                add_qr_code_within_rect(
                    c,
                    row["URL"],
                    (x, y),
                    box_size,
                    box_size,
                    icon_path,
                    qr_padding_px=qr_padding_px,
                    shrink_pct=shrink_front_pct,
                )
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
                    column_index = (boxes_per_row - 1) - position_index % boxes_per_row
                else:
                    column_index = position_index % boxes_per_row
                row_index = position_index // boxes_per_row
                x = hpageindent + (column_index * box_size)
                y = page_height - vpageindent - (row_index + 1) * box_size
                add_text_box(c, row, (x, y), box_size, box_size, shrink_pct=shrink_back_pct)
        c.showPage()

    c.save()
