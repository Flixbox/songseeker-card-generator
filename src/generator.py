"""PDF generation orchestrator for SongSeeker cards."""
from __future__ import annotations

from typing import Optional
from pathlib import Path

import pandas as pd
from PIL import Image
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm

from . import fonts
from .draw import draw_image_in_rect
from .qr_utils import add_qr_code_within_rect
from .text_boxes import add_text_box
from .link_check import validate_dataframe_urls
from .precheck import remove_duplicates
from .csv_utils import write_corrections_to_csv
import logging


def main(
    csv_file_path: str,
    output_pdf_path: Optional[str] = None,
    icon_path: Optional[str] = None,
    mirror_backside: bool = True,
    front_bg_path: Optional[str] = None,
    back_bg_path: Optional[str] = None,
    qr_padding_px: Optional[int] = None,
    shrink_front_pct: float = 0.0,
    shrink_back_pct: float = 0.0,
    fix_links: bool = False,
    fix_csv: bool = False,
):
    # Ensure Unicode TrueType fonts are registered before drawing
    fonts.setup_unicode_fonts()
    data = pd.read_csv(csv_file_path)
    # Remove leading/trailing whitespaces across the DataFrame
    try:
        data = data.map(lambda x: x.strip() if isinstance(x, str) else x)
    except AttributeError:
        data = data.applymap(lambda x: x.strip() if isinstance(x, str) else x)

    # Run pre-checks (deduplication) before any link validation
    logger = logging.getLogger(__name__)
    data, removed_count, removed_indices = remove_duplicates(data, subset=None, keep="first", logger=logger)
    # Build initial corrections list containing duplicate removal actions so they are persisted when --fix-csv is used
    initial_corrections = []
    if removed_count:
        logger.info("Removed %d duplicate rows during pre-check. Remaining rows: %d", removed_count, len(data))
        for ridx in removed_indices:
            # these indices refer to the original DataFrame row indices that were removed by deduplication
            initial_corrections.append({"action": "remove_row", "disk_row_index": int(ridx), "reason": "duplicate_removed"})

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

    # If output path not provided, create a default path under repo-root/output using the CSV file name
    if not output_pdf_path:
        repo_root = Path(__file__).resolve().parents[1]
        output_dir = repo_root / "output"
        output_dir.mkdir(parents=True, exist_ok=True)
        csv_file_name = Path(csv_file_path).stem
        output_pdf_path = output_dir / f"{csv_file_name}.pdf"

    # Ensure the path is a string for reportlab
    c = canvas.Canvas(str(output_pdf_path), pagesize=(page_width, page_height))

    # Keep an original copy for printing replacement previews if link-fixes are applied
    data_original = data.copy(deep=True)

    # Track rows skipped during generation due to missing/malformed URLs
    skipped_indices = []
    url_col = "URL"
    url_col_present = url_col in data.columns
    # Determine initial count of missing/invalid URL entries
    def _is_valid_url_val(v):
        return isinstance(v, str) and v.strip() != ""

    if url_col_present:
        try:
            initial_invalid = int((~data[url_col].apply(_is_valid_url_val)).sum())
        except Exception:
            initial_invalid = 0
    else:
        initial_invalid = len(data)

    # If requested, perform a pre-check of YouTube links and apply suggested corrections.
    logger = logging.getLogger(__name__)
    if fix_links:
        logger.info("Attempting to auto-resolve %d missing/malformed URL(s)...", initial_invalid)
        logger.info("Starting link validation pre-check...")
        results, link_corrections = validate_dataframe_urls(data, url_column=url_col, logger=logger)
        # Merge duplicate removal corrections (from pre-check) with link corrections so both are applied to CSV when requested
        corrections = list(initial_corrections) + list(link_corrections)

        # Count how many corrections filled previously-empty URLs
        filled_missing = 0
        for corr in link_corrections:
            orig = corr.get("original_url")
            if orig is None or orig == "":
                filled_missing += 1
        if filled_missing:
            logger.info("Found and added links for %d previously-missing entries.", filled_missing)

        if corrections:
            logger.info("Applied %d corrections to URLs/rows before PDF generation.", len(corrections))
            logger.info("Replacements / actions applied:")

            # Build a mapping of lowercase column name -> actual column name for flexible lookups
            lcmap = {col.lower(): col for col in data_original.columns}
            title_candidates = ("title", "song", "track")
            artist_candidates = ("artist", "performer", "band", "composer")
            year_candidates = ("year",)

            def find_col(candidates):
                for k in candidates:
                    if k in lcmap:
                        return lcmap[k]
                return None

            tcol = find_col(title_candidates)
            acol = find_col(artist_candidates)
            ycol = find_col(year_candidates)

            for corr in corrections:
                # Handle duplicate removal preview
                if corr.get("action") == "remove_row":
                    disk_idx = corr.get("disk_row_index")
                    logger.info("Duplicate removed from original CSV: disk row index %s", disk_idx)
                    continue

                # Otherwise treat as URL replacement correction (backwards compatible)
                idx = corr.get("row_index")
                orig_url = corr.get("original_url")
                new_url = corr.get("matched_url")
                matched_title = corr.get("matched_title") or ""

                preview_parts = []
                try:
                    row = data_original.loc[idx]
                    if acol and row.get(acol):
                        preview_parts.append(str(row.get(acol)))
                    if tcol and row.get(tcol):
                        preview_parts.append(str(row.get(tcol)))
                    if ycol and row.get(ycol):
                        preview_parts.append(str(row.get(ycol)))
                except Exception:
                    # fall back to matched title or index
                    pass

                preview = ", ".join(preview_parts) if preview_parts else (matched_title or f"row {idx}")
                logger.info("%s\n=> %s\n=> %s", preview, orig_url, new_url)

            # If requested, write corrections back to the original CSV
            if fix_csv:
                try:
                    applied = write_corrections_to_csv(csv_file_path, corrections, data, logger=logger)
                    if applied:
                        logger.info("Wrote %d corrections back to CSV: %s", len(applied), csv_file_path)
                except Exception:
                    logger.exception("Failed to write corrections to CSV")
        else:
            logger.info("No automatic corrections suggested by link validation.")
    else:
        # If not fixing links, inform the user how many entries look malformed/missing and will be skipped
        if initial_invalid:
            logger.info("Note: %d entries have missing or malformed URLs and will be skipped unless --fix-links is used.", initial_invalid)

    for i in range(0, len(data), boxes_per_page):
        # FRONT SIDE (QR)
        for index in range(i, min(i + boxes_per_page, len(data))):
            row = data.iloc[index]
            # determine the URL value safely
            url_val = None
            if url_col_present:
                try:
                    url_val = row.get(url_col)
                except Exception:
                    url_val = None

            valid_url = _is_valid_url_val(url_val)

            if front_bg_img:
                # Compute grid position
                position_index = index % boxes_per_page
                column_index = position_index % boxes_per_row
                row_index = position_index // boxes_per_row
                x = hpageindent + (column_index * card_width)
                y = page_height - vpageindent - ((row_index + 1) * card_height)
                draw_image_in_rect(c, front_bg_img, x, y, card_width, card_height)

                if valid_url:
                    add_qr_code_within_rect(
                        c,
                        str(url_val),
                        (x, y),
                        card_width,
                        card_height,
                        icon_path,
                        qr_padding_px=qr_padding_px,
                        shrink_pct=shrink_front_pct,
                    )
                else:
                    skipped_indices.append(index)
                    logger.debug("Skipping QR for row %s: missing or malformed URL", index)
            else:
                position_index = index % (boxes_per_row * boxes_per_column)
                column_index = position_index % boxes_per_row
                row_index = position_index // boxes_per_row
                x = hpageindent + (column_index * box_size)
                y = page_height - vpageindent - (row_index + 1) * box_size

                if valid_url:
                    add_qr_code_within_rect(
                        c,
                        str(url_val),
                        (x, y),
                        box_size,
                        box_size,
                        icon_path,
                        qr_padding_px=qr_padding_px,
                        shrink_pct=shrink_front_pct,
                    )
                else:
                    skipped_indices.append(index)
                    logger.debug("Skipping QR for row %s: missing or malformed URL", index)
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

    # Log a short summary with input/output paths and generation statistics
    try:
        total_cards = len(data)
    except Exception:
        total_cards = 0

    try:
        pages_per_side = (total_cards + boxes_per_page - 1) // boxes_per_page if boxes_per_page else 0
        total_pages = pages_per_side * 2  # front and back pages
    except Exception:
        pages_per_side = 0
        total_pages = 0

    logger = logging.getLogger(__name__)
    logger.info(
        "🎉 PDF generation complete!\n\n"
        "📥 Input: %s\n"
        "📤 Output: %s\n"
        "🧾 Cards: %d\n"
        "📦 Boxes/page: %d\n"
        "📄 Pages (total): %d",
        csv_file_path,
        output_pdf_path,
        total_cards,
        boxes_per_page,
        total_pages,
    )

    # If link-fixing was not enabled, report how many entries were skipped due to missing/malformed URLs
    if not fix_links and skipped_indices:
        logger.info("Note: %d entries were skipped for QR generation due to missing or malformed URLs. Use --fix-links to attempt automatic fixes.", len(skipped_indices))
