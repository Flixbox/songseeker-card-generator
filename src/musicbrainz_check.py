"""MusicBrainz-based year verification and correction utilities.

This module provides a single function `check_and_fix_years` which will
query the MusicBrainz webservice for release/release-group first-release
dates and use the discovered year to correct the 'year' column in the
in-memory deduped DataFrame. When a correction is made a corresponding
correction entry is appended to the provided corrections list so calling
code can persist the change to the original CSV using the existing
`write_corrections_to_csv` helper (which replaces the disk row with the
updated in-memory deduped row).
"""
from __future__ import annotations

from typing import List, Dict, Any, Optional
import logging

try:
    import musicbrainzngs
except Exception:  # pragma: no cover - optional dependency
    musicbrainzngs = None


def _find_key_columns(columns):
    lcmap = {c.lower(): c for c in columns}
    title_candidates = ("title", "song", "track")
    artist_candidates = ("artist", "performer", "band", "composer")
    year_candidates = ("year",)

    acol = next((lcmap[k] for k in artist_candidates if k in lcmap), None)
    tcol = next((lcmap[k] for k in title_candidates if k in lcmap), None)
    ycol = next((lcmap[k] for k in year_candidates if k in lcmap), None)
    return acol, tcol, ycol


def _parse_year(value) -> Optional[int]:
    if value is None:
        return None
    try:
        if isinstance(value, (int, float)):
            return int(value)
        s = str(value).strip()
        if not s:
            return None
        # handle strings like '1999', '1999-05-01', "c.1999"
        # extract the first 4-digit group
        import re

        m = re.search(r"(\d{4})", s)
        if m:
            return int(m.group(1))
    except Exception:
        pass
    return None


def check_and_fix_years(
    df,
    csv_path: str,
    corrections: Optional[List[Dict[str, Any]]] = None,
    logger: Optional[logging.Logger] = None,
) -> List[Dict[str, Any]]:
    """Use MusicBrainz to verify/fix the year for rows in `df`.

    Args:
        df: the deduplicated pandas DataFrame used for generation (modified in-place).
        csv_path: path to the original CSV (used only for user-agent contact details/logging).
        corrections: an optional list to append year-correction entries to. If provided,
            new corrections will be appended to this list. Each correction will be a dict
            containing at least 'row_index', 'original_year', 'matched_year'.
        logger: optional logger.

    Returns:
        A list of correction dicts that were added by this function.
    """
    if logger is None:
        logger = logging.getLogger(__name__)

    added = []

    if musicbrainzngs is None:
        logger.info("musicbrainzngs is not installed; skipping MusicBrainz year checks.")
        return added

    # Configure rate limiting and user agent as recommended
    try:
        musicbrainzngs.set_rate_limit(limit_or_interval=1.0, new_requests=1)
    except Exception:
        # If this fails, continue; it's non-fatal
        logger.debug("Failed to set MusicBrainz rate limit (continuing)")

    try:
        musicbrainzngs.set_useragent("songseeker-card-generator", "0.0", contact="https://github.com/Flixbox/songseeker-card-generator")
    except Exception:
        logger.debug("Failed to set MusicBrainz user agent (continuing)")

    # Determine key columns
    try:
        acol, tcol, ycol = _find_key_columns(list(df.columns))
    except Exception:
        acol = tcol = ycol = None

    if not ycol:
        logger.info("No year column detected in dataset; skipping MusicBrainz checks.")
        return added

    # Iterate rows and attempt to discover a canonical release year
    try:
        rows = list(df.iterrows())
    except Exception:
        logger.exception("Failed to iterate DataFrame rows for MusicBrainz checks")
        return added

    for idx, row in rows:
        try:
            orig_year_val = row.get(ycol) if ycol in row.index else None
            orig_year = _parse_year(orig_year_val)

            # Build a query using artist + title when possible
            artist = str(row.get(acol)).strip() if acol and row.get(acol) and not (isinstance(row.get(acol), float) and __import__('math').isnan(row.get(acol))) else ""
            title = str(row.get(tcol)).strip() if tcol and row.get(tcol) and not (isinstance(row.get(tcol), float) and __import__('math').isnan(row.get(tcol))) else ""

            # Skip rows without artist+title context
            query_terms = " ".join([p for p in (artist, title) if p]).strip()
            if not query_terms:
                continue

            # Perform a search for release-groups which often contain a first-release-date
            try:
                logger.debug("MusicBrainz: searching release-groups for: %s", query_terms)
                result = musicbrainzngs.search_release_groups(query_terms, limit=5)
                rgs = result.get("release-group-list") or []
            except Exception as ex:
                logger.debug("MusicBrainz search failed for %s: %s", query_terms, ex)
                rgs = []

            found_year = None
            # Try to find the first sensible year from results
            for rg in rgs:
                # musicbrainzngs often uses 'first-release-date'
                date = rg.get("first-release-date") or rg.get("first_release_date") or rg.get("firstrelease-date")
                if not date:
                    # as a fallback try to fetch detailed release info from release-group
                    gid = rg.get("id")
                    if gid:
                        try:
                            rg_full = musicbrainzngs.get_release_group_by_id(gid, includes=["releases"]) or {}
                            releases = rg_full.get("release-group", {}).get("release-list") or []
                            # pick the earliest release with a date
                            for rel in releases:
                                rdate = rel.get("date") or rel.get("release-date")
                                if rdate:
                                    date = rdate
                                    break
                        except Exception:
                            pass
                if date:
                    # date may be YYYY-MM-DD or YYYY
                    try:
                        y = int(str(date).split("-")[0])
                        if y > 0:
                            found_year = y
                            break
                    except Exception:
                        continue

            if found_year is None:
                # no candidate year discovered
                continue

            # Compare and update if different
            if orig_year != found_year:
                # Update DataFrame in-place
                try:
                    df.at[idx, ycol] = found_year
                except Exception:
                    df.loc[idx, ycol] = found_year

                corr = {"row_index": int(idx), "original_year": orig_year_val, "matched_year": found_year, "reason": "musicbrainz_year_correction"}
                added.append(corr)
                if corrections is not None:
                    corrections.append(corr)
                logger.info("Corrected year for row %s: %s -> %s", idx, orig_year_val, found_year)
        except Exception:
            logger.exception("Error while checking/fixing year for row %s", idx)
            continue

    return added
