"""Utilities to validate and attempt to correct YouTube links used by the generator.

This is a compact, focused subset of the behavior in
scripts/check_youtube_links.py adapted to work with pandas DataFrames
and provide programmatic results.
"""
from __future__ import annotations

import logging
import re
from typing import Optional, Dict, Any, List

try:
    from ytmusicapi import YTMusic
except Exception:
    YTMusic = None

DEFAULT_YOUTUBE_REGEX = r"https?://(?:www\.)?(?:youtube\.com/watch\?v=|youtu\.be/)([A-Za-z0-9_-]{11})"


def normalize_url(url: str, youtube_pat: re.Pattern) -> str:
    m = youtube_pat.search(url)
    if not m:
        return url
    vid = m.group(1)
    return f"https://www.youtube.com/watch?v={vid}"


def make_search_query(row_text: str) -> Optional[str]:
    if not row_text:
        return None
    text = re.sub(r"https?://\S+", "", row_text)
    text = re.sub(r"youtu\.be|youtube\.com|www\.|\(.*?\)", "", text, flags=re.I)
    text = re.sub(r"[^\w\s'-]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    parts = [p.strip() for p in text.split(',') if p.strip()]
    if len(parts) >= 2:
        q = f"{parts[0]} {parts[1]}"
    elif parts:
        q = parts[0]
    else:
        q = text
    q = q.strip()
    if not q:
        return None
    return q[:200]


def search_and_verify(search_query: str, max_results: int = 5, logger: Optional[logging.Logger] = None) -> Optional[Dict[str, Any]]:
    """Search YouTube Music for songs and verify a candidate using YTMusic.get_song.

    Limits the search to music (songs only) as requested.
    """
    if YTMusic is None:
        return None

    if logger is None:
        logger = logging.getLogger(__name__)

    logger.info("Starting search query: %s", search_query)

    try:
        ytm = YTMusic()
        entries = ytm.search(search_query, filter="songs", limit=max_results)

        if not entries:
            return None

        n_entries = len(entries)
        if logger:
            logger.info("[search] returned %d candidate(s) for query: %s", n_entries, search_query)

        for i, info in enumerate(entries[:max_results], start=1):
            # Expecting a video id on song results
            video_id = info.get("videoId") or info.get("videoId")
            if not video_id:
                if logger:
                    logger.debug("Skipping malformed search entry")
                continue

            candidate = f"https://www.youtube.com/watch?v={video_id}"
            title_hint = info.get("title") if isinstance(info, dict) else "(no title)"
            if logger:
                logger.info("Trying candidate %d/%d: %s (%s)", i, max_results, candidate, title_hint)

            try:
                song = ytm.get_song(video_id)
                # get_song returns nested metadata in a dict; try common keys
                title = None
                duration = None
                if isinstance(song, dict):
                    # common patterns: videoDetails.title and videoDetails.lengthSeconds
                    vd = song.get("videoDetails") or {}
                    title = vd.get("title") or info.get("title")
                    length_seconds = vd.get("lengthSeconds")
                    if length_seconds:
                        try:
                            duration = int(length_seconds)
                        except Exception:
                            duration = None
                    # fallback: search result duration string
                    if not duration:
                        duration = info.get("duration")
                else:
                    title = info.get("title")
                    duration = info.get("duration")

                if logger:
                    logger.info("Verified candidate: %s (%s)", candidate, title)
                return {"matched_url": candidate, "title": title, "length": duration, "result_index": i}
            except Exception as ve:
                if logger:
                    logger.info("Candidate failed verification: %s (%s)", candidate, ve)
                continue
    except Exception as se:
        if logger:
            logger.info("Search failed for query %s (%s)", search_query, se)
        return None
    return None


def check_video(url: str, search_query: Optional[str] = None, logger: Optional[logging.Logger] = None) -> Dict[str, Any]:
    """Validate a YouTube URL using ytmusicapi when possible.

    If the direct lookup fails and a search query is provided, attempt to find
    a matching song via the music-only search and return a suggested replacement.
    """
    if YTMusic is None:
        return {"url": url, "ok": False, "status": None, "reason": "ytmusic_missing", "error": "ytmusicapi is not installed. Run: pip install ytmusicapi"}

    if logger is None:
        logger = logging.getLogger(__name__)

    # try to extract the video id from the URL
    try:
        m = re.search(DEFAULT_YOUTUBE_REGEX, url)
        vid = m.group(1) if m else None
    except Exception:
        vid = None

    try:
        ytm = YTMusic()
        if vid:
            # Try direct lookup
            try:
                info = ytm.get_song(vid)
                title = None
                duration = None

                # Determine if the returned metadata represents a video rather than a song.
                is_video = False
                if isinstance(info, dict):
                    # Check microformat/schema hints
                    mf = info.get("microformat", {}).get("microformatDataRenderer") if info.get("microformat") else None
                    schema = None
                    if isinstance(mf, dict):
                        schema = mf.get("schemaDotOrgType") or mf.get("schema.orgType") or mf.get("schemaDotOrgType")
                    if schema and "VideoObject" in str(schema):
                        is_video = True

                    # Check videoDetails for video-specific flags
                    vd = info.get("videoDetails") or {}
                    if vd.get("isLiveContent"):
                        is_video = True
                    # musicVideoType indicates music video / uploaded track
                    if vd.get("musicVideoType"):
                        is_video = True

                    # Populate title/duration if available
                    title = vd.get("title") or info.get("title")
                    ls = vd.get("lengthSeconds") or vd.get("durationSeconds")
                    if ls:
                        try:
                            duration = int(ls)
                        except Exception:
                            duration = None

                else:
                    title = None
                    duration = None

                if is_video:
                    # Treat as invalid for our music-only requirement and fall through to search-based replacement
                    if logger:
                        logger.info("URL appears to be a video (not a song): %s (%s)", url, title)
                    # Do not return success here; allow search-based match below
                else:
                    # Valid song
                    if logger:
                        logger.info("URL OK: %s (%s)", url, title)
                    return {"url": url, "ok": True, "status": 200, "reason": "ytmusic_ok", "title": title, "length": duration}
            except Exception as e:
                err = str(e)
                if logger:
                    logger.warning("Direct lookup failed for %s (%s)", url, err)
                # fall through to search-based matching

        # If we reach here and a search_query is provided, try to find a match
        if search_query:
            matched = search_and_verify(search_query, max_results=5, logger=logger)
            if matched:
                if logger:
                    logger.info("Matched by search: %s -> %s (%s)", url, matched.get("matched_url"), matched.get("title"))
                return {
                    "url": url,
                    "ok": True,
                    "status": 200,
                    "reason": "matched_by_search_verified",
                    "matched_url": matched.get("matched_url"),
                    "title": matched.get("title"),
                    "length": matched.get("length"),
                    "search_query": search_query,
                    "search_result_index": matched.get("result_index"),
                }

        # If no match and direct lookup failed, determine reason
        reason = "video_unavailable"
        if logger:
            logger.warning("URL check failed: %s (no match found)", url)
        return {"url": url, "ok": False, "status": None, "reason": reason, "error": "no match found"}
    except Exception as e:
        err = str(e)
        if logger:
            logger.warning("URL check failed: %s (%s)", url, err)
        return {"url": url, "ok": False, "status": None, "reason": "ytmusic_error", "error": err}


def validate_dataframe_urls(df, url_column: str = "URL", youtube_regex: str = DEFAULT_YOUTUBE_REGEX, logger: Optional[logging.Logger] = None):
    """Validate and attempt to fix YouTube links in the provided DataFrame.

    Returns a tuple: (results_list, corrections_list)
    - results_list: list of per-URL result dicts from check_video
    - corrections_list: list of dicts describing replacements made
    """
    import pandas as pd  # local import to avoid adding pandas as global dependency here

    if logger is None:
        logger = logging.getLogger(__name__)

    try:
        youtube_pat = re.compile(youtube_regex)
    except re.error:
        logger.error("Invalid YouTube regex provided")
        return [], []

    if url_column not in df.columns:
        logger.warning("DataFrame does not contain expected column '%s' - skipping link checks", url_column)
        return [], []

    seen = {}
    results = []
    corrections = []

    # Ensure the URL column can accept string replacements to avoid dtype warnings
    try:
        df[url_column] = df[url_column].astype(object)
    except Exception:
        # fallback: continue without casting
        pass

    unique_norms = {}
    for idx, raw in df[url_column].items():
        # Normalize raw value and treat missing/empty values as unique per-row
        if pd.isna(raw):
            raw_str = ""
        else:
            raw_str = str(raw).strip()

        if not raw_str:
            # Use a per-row placeholder key for empty/missing URLs so each row can be
            # searched/verified independently instead of being grouped together.
            key = f"__ROW_EMPTY__:{idx}"
        else:
            key = normalize_url(raw_str, youtube_pat)

        unique_norms.setdefault(key, []).append((idx, raw_str))

    total = len(unique_norms)
    logger.info("Checking %d unique URL(s)", total)

    for i, (norm, occurrences) in enumerate(unique_norms.items(), start=1):
        # If this is a per-row placeholder (empty URL), display an empty string in logs
        display_norm = "" if str(norm).startswith("__ROW_EMPTY__:") else norm
        logger.info("[%d/%d] Checking: %s", i, total, display_norm)
        row_text = None
        # try to build a search_query from one of the CSV rows if possible
        # pick the first occurrence's row text if other columns exist
        # store the DataFrame row concatenation as a heuristic
        first_idx = occurrences[0][0]
        try:
            row = df.loc[first_idx]
            # concatenate textual cells to build context for a search
            text_cells = [str(v) for v in row.values if isinstance(v, (str,)) and v.strip()]
            if text_cells:
                row_text = ", ".join(text_cells[:3])
        except Exception:
            row_text = None

        search_query = make_search_query(row_text) if row_text else None
        if search_query:
            logger.debug("Using search query: %s", search_query)

        # Pass an empty string to check_video when handling placeholder keys
        input_url_for_check = "" if str(norm).startswith("__ROW_EMPTY__:") else norm
        res = check_video(input_url_for_check, search_query=search_query, logger=logger)
        results.append(res)

        matched = res.get("matched_url")
        if matched and matched != norm:
            logger.info("Applying suggested match: %s -> %s", norm, matched)
            for idx, raw in occurrences:
                # update DataFrame in-place
                df.at[idx, url_column] = matched
                corrections.append({"row_index": idx, "original_url": raw, "matched_url": matched, "matched_title": res.get("title")})
        else:
            if not res.get("ok"):
                logger.warning("No suggested match for %s (reason: %s)", norm, res.get("reason"))

        # polite delay not strictly necessary here - callers may choose to add delays if desired

    logger.info("Link validation complete. %d correction(s) applied.", len(corrections))
    return results, corrections
