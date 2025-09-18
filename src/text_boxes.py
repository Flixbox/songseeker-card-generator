"""Rendering of text boxes for the card backside."""
from __future__ import annotations

from typing import Optional, Tuple, List

import pandas as pd

from . import fonts
from .layout import inner_rect
from .text_utils import wrap_text_to_width
from .constants import (
    YEAR_MAX_HEIGHT_RATIO,
    ARTIST_MAX_HEIGHT_RATIO,
    TITLE_MAX_HEIGHT_RATIO,
)


def add_text_box(
    c,
    info: pd.Series,
    position: Tuple[float, float],
    box_width: float,
    box_height: float,
    font_artist: Optional[str] = None,
    font_size_artist: float = 14,
    font_title: Optional[str] = None,
    font_size_title: float = 14,
    font_year: Optional[str] = None,
    font_size_year: float = 50,
    shrink_pct: float | int = 0.0,
):
    x, y = position
    inner_x, inner_y, inner_w, inner_h = inner_rect(x, y, box_width, box_height)

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

    default_font_color = "0,0,0"  # Default color is black

    # Check if 'backcol' is in info and set the fill color for the card background
    if "backcol" in info and not pd.isna(info["backcol"]):
        r, g, b = tuple(float(x) for x in str(info["backcol"]).split(","))
        c.setFillColorRGB(r, g, b)
        c.rect(x, y, box_width, box_height, fill=1)
    else:
        c.rect(x, y, box_width, box_height)

    r, g, b = tuple(float(x) for x in default_font_color.split(","))
    c.setFillColorRGB(r, g, b)

    # Compose content blocks
    artist_text = None if "Artist" not in info or pd.isna(info["Artist"]) else f"{info['Artist']}"
    title_text = None if "Title" not in info or pd.isna(info["Title"]) else f"{info['Title']}"
    year_text = None if "Year" not in info or pd.isna(info["Year"]) else f"{info['Year']}"

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
    # Cap initial sizes relative to inner height
    size_year = min(size_year, inner_h * YEAR_MAX_HEIGHT_RATIO)
    size_artist = min(size_artist, inner_h * ARTIST_MAX_HEIGHT_RATIO)
    size_title = min(size_title, inner_h * TITLE_MAX_HEIGHT_RATIO)

    # Iteratively wrap and scale to ensure content fits in inner box
    min_font_size = 6.0
    max_iters = 8
    for _ in range(max_iters):
        artist_lines = wrap_text_to_width(c, artist_text, font_artist, size_artist, inner_w) if artist_text else []
        title_lines = wrap_text_to_width(c, title_text, font_title, size_title, inner_w) if title_text else []

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
        scale_down = max(0.1, (inner_h / total_height) * 0.98)
        size_artist = max(min_font_size, size_artist * scale_down)
        size_title = max(min_font_size, size_title * scale_down)
        size_year = max(min_font_size, size_year * scale_down)

    # After scaling, ensure year fits width if present
    if year_text:
        lw = c.stringWidth(year_text, font_year, size_year)
        if lw > inner_w and lw > 0:
            size_year = max(min_font_size, size_year * (inner_w / lw) * 0.98)

    # Recompute lines for final placement
    artist_lines = wrap_text_to_width(c, artist_text, font_artist, size_artist, inner_w) if artist_text else []
    title_lines = wrap_text_to_width(c, title_text, font_title, size_title, inner_w) if title_text else []
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

    # Draw year (single line), centered horizontally
    if year_text:
        line_width = c.stringWidth(year_text, font_year, size_year)
        line_x = inner_x + (inner_w - line_width) / 2
        current_y -= size_year
        c.setFont(font_year, size_year)
        c.drawString(line_x, current_y, year_text)
