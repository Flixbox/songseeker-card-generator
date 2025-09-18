"""QR code generation and placement utilities."""
from __future__ import annotations

import hashlib
import os
from io import BytesIO
from typing import Dict, Optional, Tuple

import qrcode
from qrcode.image.styledpil import StyledPilImage
import requests

from reportlab.pdfgen.canvas import Canvas

from .layout import inner_rect


def generate_qr_code(url: str, file_path: str, icon_path: Optional[str], icon_image_cache: Dict[str, BytesIO] | None = None, qr_padding_px: Optional[int] = None) -> None:
    """Generate a QR code image for a URL and save to file_path. Optional center icon.

    qr_padding_px controls the quiet zone thickness in pixels (approx), converted to modules.
    """
    if icon_image_cache is None:
        icon_image_cache = {}

    box_size = 10  # pixels per module
    if qr_padding_px is None:
        border_modules = 4  # default quiet zone (modules)
    else:
        border_modules = max(0, int(round(qr_padding_px / box_size)))

    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_Q,
        box_size=box_size,
        border=border_modules,
    )
    qr.add_data(url)
    qr.make(fit=True)
    if not icon_path:
        img = qr.make_image(fill_color="black", back_color="white")
    else:
        if icon_path.startswith("http"):
            if icon_path not in icon_image_cache:
                response = requests.get(icon_path)
                response.raise_for_status()
                icon_image_cache[icon_path] = BytesIO(response.content)
            icon_image = icon_image_cache[icon_path]
            img = qr.make_image(image_factory=StyledPilImage, embeded_image_path=icon_image)
        else:
            img = qr.make_image(image_factory=StyledPilImage, embeded_image_path=icon_path)
    img.save(file_path)


def add_qr_code_within_rect(c: Canvas, url: str, position: Tuple[float, float], box_width: float, box_height: float, icon_path: Optional[str], qr_padding_px: Optional[int] = None, shrink_pct: float | int = 0.0) -> None:
    """Create and draw a QR code centered within the inner padded rect of a card.

    shrink_pct optionally reduces inner content area by percentage before placing QR.
    """
    # Unique temp file name for QR code
    hex_dig = hashlib.sha256(url.encode()).hexdigest()
    qr_code_path = f"qr_{hex_dig}.png"

    generate_qr_code(url, qr_code_path, icon_path, qr_padding_px=qr_padding_px)

    x, y = position
    inner_x, inner_y, inner_w, inner_h = inner_rect(x, y, box_width, box_height)

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

    qr_size = min(inner_w, inner_h)
    qr_x = inner_x + (inner_w - qr_size) / 2
    qr_y = inner_y + (inner_h - qr_size) / 2
    c.drawImage(qr_code_path, qr_x, qr_y, width=qr_size, height=qr_size)
    os.remove(qr_code_path)
