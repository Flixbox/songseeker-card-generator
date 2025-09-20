"""Utilities for writing back automatic URL corrections to the original CSV file.

The dataset used for generation may have been altered by pre-checks (deduplication)
so corrections produced by `validate_dataframe_urls` reference row indices from the
in-memory deduped DataFrame. This module provides logic to locate the matching
row(s) in the original CSV by artist/title (or fallback to URL matching) and
replace the full row with the corrected values. It also supports removal
instructions (action == 'remove_row') so duplicate-removal performed during
pre-checks can be persisted to the original CSV when requested.
"""
from __future__ import annotations

from typing import List, Dict, Any, Optional
import logging
import pandas as pd
import shutil
import os


def _find_key_columns(columns: List[str]):
    lcmap = {c.lower(): c for c in columns}
    title_candidates = ("title", "song", "track")
    artist_candidates = ("artist", "performer", "band", "composer")

    acol = next((lcmap[k] for k in artist_candidates if k in lcmap), None)
    tcol = next((lcmap[k] for k in title_candidates if k in lcmap), None)
    return acol, tcol


def write_corrections_to_csv(
    csv_path: str,
    corrections: List[Dict[str, Any]],
    deduped_df: pd.DataFrame,
    logger: Optional[logging.Logger] = None,
) -> List[Dict[str, Any]]:
    """Apply corrections to the CSV file on disk.

    Supports two kinds of corrections in the provided list:
      - URL replacement corrections (produced by validate_dataframe_urls):
          { 'row_index': <index in deduped_df>, 'original_url': ..., 'matched_url': ..., ... }
      - Duplicate-removal actions (produced by pre-check):
          { 'action': 'remove_row', 'disk_row_index': <index in original CSV>, 'reason': 'duplicate_removed' }

    Args:
        csv_path: path to the original CSV file to modify in-place.
        corrections: list of correction/action dicts.
        deduped_df: the DataFrame used when producing corrections (after
            pre-check/deduplication). Used to look up artist/title values for
            locating the correct row in the on-disk CSV.
        logger: optional logger for informational messages.

    Returns:
        A list describing which CSV row indices were modified on disk.
    """
    if logger is None:
        logger = logging.getLogger(__name__)

    if not corrections:
        logger.info("No corrections provided to write to CSV.")
        return []

    if not os.path.exists(csv_path):
        logger.warning("CSV path does not exist: %s", csv_path)
        return []

    # Read the original CSV from disk
    try:
        original = pd.read_csv(csv_path)
    except Exception as exc:
        logger.exception("Failed to read CSV %s: %s", csv_path, exc)
        return []

    acol, tcol = _find_key_columns(list(original.columns))

    applied = []
    # Collect disk indices to remove (for duplicate removals)
    disk_remove_indices = set()

    for corr in corrections:
        # Handle explicit remove_row actions first
        if corr.get("action") == "remove_row":
            disk_idx = corr.get("disk_row_index")
            if disk_idx is None:
                continue
            # Only remove if that index exists in the disk CSV
            if int(disk_idx) in original.index:
                disk_remove_indices.add(int(disk_idx))
                applied.append({"disk_row_index": int(disk_idx), "action": "remove_row", "reason": corr.get("reason")})
            else:
                logger.warning("Requested removal of disk row %s but it does not exist in CSV", disk_idx)
            continue

        # Otherwise treat as a URL replacement correction
        dedup_idx = corr.get("row_index")
        matched_url = corr.get("matched_url")
        original_url = corr.get("original_url")

        if dedup_idx is None:
            logger.warning("Skipping malformed correction entry (missing row_index): %s", corr)
            continue

        try:
            dedup_row = deduped_df.loc[dedup_idx]
        except Exception:
            logger.warning("Could not find deduped row for index %s; skipping", dedup_idx)
            continue

        # Build match mask using artist+title if possible
        matched_indices = []
        if acol and tcol and acol in original.columns and tcol in original.columns:
            a_val = str(dedup_row.get(acol)) if pd.notna(dedup_row.get(acol)) else ""
            t_val = str(dedup_row.get(tcol)) if pd.notna(dedup_row.get(tcol)) else ""
            if a_val or t_val:
                mask = pd.Series([True] * len(original))
                if a_val:
                    mask = mask & (original[acol].astype(str).str.strip().str.lower() == a_val.strip().lower())
                if t_val:
                    mask = mask & (original[tcol].astype(str).str.strip().str.lower() == t_val.strip().lower())
                matched_indices = original[mask].index.tolist()

        # If no match by keys, try matching by the original URL
        if not matched_indices and "URL" in original.columns and original_url:
            matched_indices = original[original["URL"].astype(str) == str(original_url)].index.tolist()

        # If still nothing, try matching by matched_url (unlikely present yet)
        if not matched_indices and "URL" in original.columns and matched_url:
            matched_indices = original[original["URL"].astype(str) == str(matched_url)].index.tolist()

        if not matched_indices:
            logger.warning(
                "Could not locate a matching row in CSV for deduped index %s (artist=%s, title=%s); skipping",
                dedup_idx, dedup_row.get(acol, ""), dedup_row.get(tcol, ""),
            )
            continue

        # Replace the first matched occurrence on disk with the full dedup_row values
        disk_idx = matched_indices[0]
        logger.info("Replacing CSV row %s with deduped row %s (URL -> %s)", disk_idx, dedup_idx, matched_url)

        # For each column present in the disk CSV, if the dedup row has that column, assign it
        for col in original.columns:
            if col in deduped_df.columns:
                try:
                    original.at[disk_idx, col] = dedup_row.get(col)
                except Exception:
                    # Best-effort: convert to string
                    original.at[disk_idx, col] = str(dedup_row.get(col))
        applied.append({"disk_row_index": int(disk_idx), "deduped_row_index": int(dedup_idx), "matched_url": matched_url})

    # Apply removals to the disk DataFrame if any
    if disk_remove_indices:
        # Only drop indices that still exist in the DataFrame (guard against index changes)
        to_drop = [i for i in disk_remove_indices if i in original.index]
        if to_drop:
            logger.info("Removing %d duplicate row(s) from CSV: %s", len(to_drop), to_drop)
            try:
                original = original.drop(index=to_drop)
            except Exception:
                logger.exception("Failed to drop duplicate rows from CSV in-memory")

    if not applied and not disk_remove_indices:
        logger.info("No rows were updated in CSV after attempting matches.")
        return []

    # Backup original CSV then write modified
    try:
        backup_path = f"{csv_path}.bak"
        shutil.copy2(csv_path, backup_path)
        original.to_csv(csv_path, index=False)
        logger.info("Wrote %d corrected row(s) to CSV; backup saved to %s", len(applied), backup_path)
    except Exception as exc:
        logger.exception("Failed to write corrected CSV %s: %s", csv_path, exc)
        return applied

    return applied
