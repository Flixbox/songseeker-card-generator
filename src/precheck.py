"""Pre-check utilities for SongSeeker card generation.

This module provides functionality that should run before URL/link
validation. Currently it removes duplicate rows from the input
DataFrame.
"""
from __future__ import annotations

from typing import Optional, Tuple, List
import pandas as pd
import logging


def remove_duplicates(
    df: pd.DataFrame,
    subset: Optional[List[str]] = None,
    keep: str = "first",
    logger: Optional[logging.Logger] = None,
) -> Tuple[pd.DataFrame, int, List[int]]:
    """Remove duplicate rows from the provided DataFrame.

    By default this function will ignore URL/link columns and attempt to
    deduplicate using artist and title columns (case-insensitive). If
    neither artist nor title columns can be found it falls back to using
    all columns.

    Args:
        df: The input DataFrame.
        subset: Columns to consider when identifying duplicates. If None,
            the function will try to use artist/title columns and ignore URLs.
        keep: Which duplicate to keep (passed to DataFrame.drop_duplicates).
        logger: Optional logger for informational messages.

    Returns:
        A tuple of (deduped_dataframe, removed_count, removed_row_indices).
    """
    if logger is None:
        logger = logging.getLogger(__name__)

    try:
        before = len(df)

        # If caller didn't specify a subset, try to use artist/title only
        subset_cols: Optional[List[str]] = None
        if subset is None:
            lcmap = {col.lower(): col for col in df.columns}
            title_candidates = ("title", "song", "track")
            artist_candidates = ("artist", "performer", "band", "composer")

            acol = next((lcmap[k] for k in artist_candidates if k in lcmap), None)
            tcol = next((lcmap[k] for k in title_candidates if k in lcmap), None)

            if acol and tcol:
                subset_cols = [acol, tcol]
                logger.debug("Pre-check: deduplicating using columns: %s", subset_cols)
            elif tcol:
                subset_cols = [tcol]
                logger.debug("Pre-check: deduplicating using title column: %s", tcol)
            elif acol:
                subset_cols = [acol]
                logger.debug("Pre-check: deduplicating using artist column: %s", acol)
            else:
                # No artist/title columns found; fall back to all columns
                subset_cols = None
                logger.debug(
                    "Pre-check: no artist/title columns detected; falling back to all columns for deduplication"
                )
        else:
            subset_cols = subset

        # Identify duplicates and drop them using the chosen subset (or all columns)
        if subset_cols:
            duplicated_mask = df.duplicated(subset=subset_cols, keep=keep)
            removed_row_indices = df[duplicated_mask].index.tolist()
            deduped = df.drop_duplicates(subset=subset_cols, keep=keep)
        else:
            duplicated_mask = df.duplicated(keep=keep)
            removed_row_indices = df[duplicated_mask].index.tolist()
            deduped = df.drop_duplicates(keep=keep)

        removed = before - len(deduped)

        if removed:
            if subset_cols:
                logger.info("Pre-check: removed %d duplicate rows (by %s)", removed, subset_cols)
            else:
                logger.info("Pre-check: removed %d duplicate rows (by all columns)", removed)
            logger.debug("Removed duplicate row indices: %s", removed_row_indices)

        return deduped, removed, removed_row_indices
    except Exception as exc:  # pragma: no cover - defensive fallback
        logger.exception("Error while removing duplicates in pre-check: %s", exc)
        # If anything goes wrong, return the original DataFrame unchanged
        return df, 0, []
