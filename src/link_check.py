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
    import yt_dlp as ytdlp
except Exception:
    ytdlp = None

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


def search_and_verify(search_query: str, max_results: int = 5, ydl_opts: Optional[dict] = None, logger: Optional[logging.Logger] = None) -> Optional[Dict[str, Any]]:
    if ytdlp is None:
        return None
    if ydl_opts is None:
        ydl_opts = {"quiet": True}

    logger.info("Starting search query: %s", search_query)

    try:
        with ytdlp.YoutubeDL(ydl_opts) as ydl:
            q = f"ytsearch{max_results}:{search_query}"
            sres = ydl.extract_info(q, download=False)
        if isinstance(sres, dict):
            entries = sres.get("entries") or []
        elif isinstance(sres, list):
            entries = sres
        else:
            entries = []

        try:
            n_entries = len(entries)
        except Exception:
            n_entries = 0
        if logger:
            logger.info("[search] returned %d candidate(s) for query: %s", n_entries, search_query)

        if not entries:
            return None

        width = len(str(max_results))
        for i, info in enumerate(entries[:max_results], start=1):
            candidate = info.get("webpage_url") if isinstance(info, dict) else None
            if not candidate:
                vid = (info.get('id') if isinstance(info, dict) else None)
                if vid:
                    candidate = f"https://www.youtube.com/watch?v={vid}"
                else:
                    if logger:
                        logger.debug("Skipping malformed search entry")
                    continue

            title_hint = info.get("title") if isinstance(info, dict) else "(no title)"
            if logger:
                logger.info("Trying candidate %d/%d: %s (%s)", i, max_results, candidate, title_hint)

            try:
                with ytdlp.YoutubeDL(ydl_opts) as ydl:
                    vinfo = ydl.extract_info(candidate, download=False)
                title = vinfo.get("title")
                duration = vinfo.get("duration")
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
    if ytdlp is None:
        return {"url": url, "ok": False, "status": None, "reason": "yt_dlp_missing", "error": "yt-dlp is not installed. Run: pip install yt-dlp"}

    ydl_opts = {"quiet": True}
    try:
        with ytdlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
        title = info.get("title")
        duration = info.get("duration")
        if logger:
            logger.info("URL OK: %s (%s)", url, title)
        return {"url": url, "ok": True, "status": 200, "reason": "yt_dlp_ok", "title": title, "length": duration}
    except Exception as e:
        err = str(e)
        low = err.lower()
        if search_query:
            matched = search_and_verify(search_query, max_results=5, ydl_opts=ydl_opts, logger=logger)
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

        if "unavailable" in low or "not available" in low or "private" in low or "removed" in low:
            reason = "video_unavailable"
        else:
            reason = "yt_dlp_error"
        if logger:
            logger.warning("URL check failed: %s (%s)", url, err)
        return {"url": url, "ok": False, "status": None, "reason": reason, "error": err}


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

    # Iterate over unique normalized URLs to avoid duplicate checks
    urls = df[url_column].dropna().astype(str)
    unique_norms = {}
    for idx, raw in urls.items():
        norm = normalize_url(raw, youtube_pat)
        unique_norms.setdefault(norm, []).append((idx, raw))

    total = len(unique_norms)
    logger.info("Checking %d unique URL(s)", total)

    for i, (norm, occurrences) in enumerate(unique_norms.items(), start=1):
        logger.info("[%d/%d] Checking: %s", i, total, norm)
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

        res = check_video(norm, search_query=search_query, logger=logger)
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
