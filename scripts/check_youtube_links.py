#!/usr/bin/env python3
"""
Find all CSV files under the repository, extract YouTube URLs, and check whether the video pages load and appear to be available.

Behavior:
- Recursively searches the repository for .csv files (skips typical binary directories).
- Extracts URLs from any CSV cell that contains "youtube.com" or "youtu.be".
- For each unique URL, uses pafy (with yt-dlp backend if available) to probe video metadata; failure to load metadata indicates the video is likely unavailable.
- Saves a JSON report and a CSV report into scripts/output_reports/{timestamp}_report.json(.csv)

Notes:
- This script uses pafy+yt-dlp to fetch video metadata. If yt-dlp is not installed the script will still attempt pafy and otherwise fall back to a simple HTTP heuristic.
"""
import csv
import hashlib
import json
import os
import re
import sys
import time
from argparse import ArgumentParser
from collections import defaultdict
from datetime import datetime
from pathlib import Path

try:
    import yt_dlp as ytdlp
except Exception:
    ytdlp = None

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CSV_GLOB = "**/*.csv"
DEFAULT_YOUTUBE_REGEX = r"https?://(?:www\.)?(?:youtube\.com/watch\?v=|youtu\.be/)([A-Za-z0-9_-]{11})"
TIMEOUT = 15


def find_csv_files(root: Path, csv_glob: str = DEFAULT_CSV_GLOB):
    for p in root.glob(csv_glob):
        if p.is_file():
            yield p


def extract_urls_from_csv(path: Path):
    urls = []
    try:
        with path.open("r", encoding="utf-8", errors="replace") as f:
            reader = csv.reader(f)
            for rownum, row in enumerate(reader, start=1):
                # keep the original row text so we can print corrected CSV lines later
                row_text = ", ".join(row)
                for cell in row:
                    if "youtube.com" in cell or "youtu.be" in cell:
                        # extract url(s)
                        for m in re.finditer(r"https?://[\w\-\./\?&=%:#;@!$'()*+,]+", cell):
                            url = m.group(0)
                            if "youtube.com" in url or "youtu.be" in url:
                                # return tuple: (url, file, rownum, row_text)
                                urls.append((url, path.as_posix(), rownum, row_text))
    except Exception as e:
        print(f"Failed to read {path}: {e}", file=sys.stderr)
    return urls


def normalize_url(url: str, youtube_pat: re.Pattern) -> str:
    # extract the video id and return canonical youtube watch url
    m = youtube_pat.search(url)
    if not m:
        return url
    vid = m.group(1)
    return f"https://www.youtube.com/watch?v={vid}"


# New precheck: detect duplicate (title, artist) within the same CSV file.
def precheck_duplicates(csv_paths):
    """Return True if no duplicates found. If duplicates are found, print row numbers and row contents and return False.

    Behavior:
    - Looks for header columns that indicate title and artist (case-insensitive).
    - If a file does not contain identifiable title/artist columns, the file is skipped with an informational message.
    - Duplicates across different files are allowed; duplicates inside the same file cause failure.
    """
    any_duplicates = False
    title_keys = ("title", "song", "track")
    artist_keys = ("artist", "performer", "band", "composer")

    for p in csv_paths:
        try:
            with p.open("r", encoding="utf-8", errors="replace") as f:
                reader = csv.reader(f)
                rows = list(reader)
        except Exception as e:
            print(f"Failed to read {p}: {e}", file=sys.stderr)
            continue

        if not rows:
            continue

        header = rows[0]
        hdr_lower = [h.lower() for h in header]
        title_idx = None
        artist_idx = None
        for i, h in enumerate(hdr_lower):
            if title_idx is None and any(k in h for k in title_keys):
                title_idx = i
            if artist_idx is None and any(k in h for k in artist_keys):
                artist_idx = i
            if title_idx is not None and artist_idx is not None:
                break

        if title_idx is None or artist_idx is None:
            # No clear title/artist header found; skip duplicate check for this file.
            print(f"Skipping duplicate check for {p} (no title/artist header detected)")
            continue

        mapping = defaultdict(list)  # (title_lower, artist_lower) -> list of (rownum, row)
        for idx, row in enumerate(rows[1:], start=2):
            # Safely get cell values by index
            t = row[title_idx].strip() if len(row) > title_idx else ""
            a = row[artist_idx].strip() if len(row) > artist_idx else ""
            key = (t.lower(), a.lower())
            mapping[key].append((idx, row))

        file_duplicates = {k: v for k, v in mapping.items() if len(v) > 1}
        if file_duplicates:
            any_duplicates = True
            print(f"Duplicate title+artist found in {p}:")
            for k, occ in file_duplicates.items():
                for rownum, row in occ:
                    # join row cells to a single printable string
                    line = ", ".join(row)
                    print(f"{rownum} | {line}")

    return not any_duplicates


def search_and_verify(search_query: str, max_results: int = 5, ydl_opts=None):
    """Search YouTube using yt-dlp and verify the top results.

    Performs a ytsearch for up to max_results entries, then attempts to fetch
    metadata for each candidate in order. Returns a dict with keys
    (matched_url, title, length, result_index) for the first verified result,
    or None if no verified candidate is found.
    """
    if ytdlp is None:
        return None
    if ydl_opts is None:
        ydl_opts = {"quiet": True}
    try:
        with ytdlp.YoutubeDL(ydl_opts) as ydl:
            q = f"ytsearch{max_results}:{search_query}"
            sres = ydl.extract_info(q, download=False)
        # yt-dlp may return a dict containing 'entries' or a list directly
        if isinstance(sres, dict):
            entries = sres.get("entries") or []
        elif isinstance(sres, list):
            entries = sres
        else:
            entries = []

        # Debug: report how many entries we received
        try:
            n_entries = len(entries)
        except Exception:
            n_entries = 0
        print(f"[search] > Search returned {n_entries} candidate(s) for query: {search_query}")

        if not entries:
            print(f"[search] > No candidates found for query: {search_query}")
            return None

        width = len(str(max_results))
        for i, info in enumerate(entries[:max_results], start=1):
            candidate = info.get("webpage_url") if isinstance(info, dict) else None
            if not candidate:
                # fallback to id if present
                vid = (info.get('id') if isinstance(info, dict) else None)
                if vid:
                    candidate = f"https://www.youtube.com/watch?v={vid}"
                else:
                    # skip malformed entry
                    print(f"[{str(i).rjust(width)}/{max_results}] > Skipping malformed search entry")
                    continue

            # logging for enumeration and candidate info
            title_hint = info.get("title") if isinstance(info, dict) else "(no title)"
            print(f"[{str(i).rjust(width)}/{max_results}] > Trying candidate: {candidate} ({title_hint})")
            # Verify availability by attempting to fetch metadata for the candidate
            try:
                with ytdlp.YoutubeDL(ydl_opts) as ydl:
                    vinfo = ydl.extract_info(candidate, download=False)
                title = vinfo.get("title")
                duration = vinfo.get("duration")
                print(f"[{str(i).rjust(width)}/{max_results}] > Verified: {candidate} ({title})")
                return {"matched_url": candidate, "title": title, "length": duration, "result_index": i}
            except Exception as ve:
                # candidate failed; log and try the next one
                print(f"[{str(i).rjust(width)}/{max_results}] > Candidate failed verification: {candidate} ({ve})")
                continue
    except Exception as se:
        print(f"[search] > Search failed for query: {search_query} ({se})")
        return None
    return None


def check_video(url: str, search_query: str = None):
    """Use yt-dlp to fetch video metadata. If direct lookup fails and a search_query
    is provided, attempt a ytsearch and verify the top results using
    search_and_verify().

    Returns a result dict containing at least: url, ok (bool), status (int|None), reason (str),
    and optional error/title/matched_url info.
    """
    if ytdlp is None:
        return {"url": url, "ok": False, "status": None, "reason": "yt_dlp_missing", "error": "yt-dlp is not installed. Run: pip install yt-dlp"}

    ydl_opts = {"quiet": True}
    try:
        with ytdlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
        title = info.get("title")
        duration = info.get("duration")
        return {"url": url, "ok": True, "status": 200, "reason": "yt_dlp_ok", "title": title, "length": duration}
    except Exception as e:
        err = str(e)
        low = err.lower()
        # If we have a search query, try a ytsearch and verify top results
        if search_query:
            matched = search_and_verify(search_query, max_results=5, ydl_opts=ydl_opts)
            if matched:
                # Return a successful result pointing to the verified match
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
        return {"url": url, "ok": False, "status": None, "reason": reason, "error": err}


def make_search_query(row_text: str) -> str | None:
    """Create a concise search query from a CSV row text by removing URLs and extra noise.

    Returns None if resulting query is empty.
    """
    if not row_text:
        return None
    # remove URLs
    text = re.sub(r"https?://\S+", "", row_text)
    # remove youtube tokens and common punctuation
    text = re.sub(r"youtu\.be|youtube\.com|www\.|\(.*?\)", "", text, flags=re.I)
    # replace non-word characters with spaces
    text = re.sub(r"[^\w\s'-]", " ", text)
    # collapse whitespace
    text = re.sub(r"\s+", " ", text).strip()
    # if we have a CSV-like 'title, artist' structure, prefer first two fields
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
    # limit length
    return q[:200]


def main():
    ap = ArgumentParser()
    ap.add_argument("--root", default=str(REPO_ROOT), help="Repository root to scan")
    ap.add_argument("--output", default=str(Path(__file__).parent / "output_reports"), help="Output folder for reports")
    ap.add_argument("--concurrency", type=int, default=6, help="Parallel requests (not implemented; reserved)")
    ap.add_argument("--glob", default=DEFAULT_CSV_GLOB, help="Glob pattern to find CSV files (default '**/*.csv')")
    ap.add_argument("--youtube-regex", default=DEFAULT_YOUTUBE_REGEX, help="Regex to extract YouTube video id (must contain a capturing group for the id)")
    args = ap.parse_args()

    root = Path(args.root)
    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)

    try:
        youtube_pat = re.compile(args.youtube_regex)
    except re.error as e:
        print(f"Invalid youtube-regex: {e}", file=sys.stderr)
        sys.exit(2)

    found = list(find_csv_files(root, args.glob))
    print(f"Found {len(found)} CSV files (glob={args.glob})")

    # Run duplicate-title+artist precheck. Duplicates inside the same file are not permitted.
    if not precheck_duplicates(found):
        print("Duplicate title+artist entries detected within a single file. Aborting.", file=sys.stderr)
        sys.exit(3)

    url_map = defaultdict(list)  # normalized -> list of source dicts
    for p in found:
        for url, src, rownum, row_text in extract_urls_from_csv(p):
            norm = normalize_url(url, youtube_pat)
            url_map[norm].append({"raw": url, "file": src, "rownum": rownum, "row_text": row_text})

    print(f"Found {len(url_map)} unique YouTube urls")

    total = len(url_map)
    width = len(str(total))

    results = []
    corrections_map = defaultdict(list)  # file -> list of corrections
    for idx, (url, sources) in enumerate(url_map.items(), start=1):
        counter = f"[{str(idx).rjust(width)}/{total}]"
        print(f"{counter} Checking: {url}")
        # Use the first source's row_text as a search query if the direct lookup fails
        search_query = None
        if sources and sources[0].get("row_text"):
            # sanitize the row_text into a concise search query
            search_query = make_search_query(sources[0]["row_text"])
            if search_query:
                print(f"{counter} Using search query: {search_query[:120]}")

        res = check_video(url, search_query=search_query)
        res["sources"] = sources

        # If the check produced a matched_url different from the original normalized url, record corrections
        matched = res.get("matched_url")
        if matched and matched != url:
            print(f"  -> Suggested match found: {matched} ({res.get('title')})")
            for s in sources:
                corrections_map[s["file"]].append({
                    "rownum": s.get("rownum"),
                    "row_text": s.get("row_text"),
                    "original_url": s.get("raw"),
                    "matched_url": matched,
                    "matched_title": res.get("title"),
                    "matched_length": res.get("length"),
                })
        else:
            # If no matched URL was produced, notify immediately
            if not matched and not res.get("ok"):
                reason = res.get("reason")
                err = res.get("error", "")
                print(f"  -> No suggested match found for {url} (reason: {reason})")
                if err:
                    print(f"     error: {err}")

        results.append(res)
        # polite delay
        time.sleep(0.5)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    json_path = out_dir / f"{ts}_report.json"
    csv_path = out_dir / f"{ts}_report.csv"

    with json_path.open("w", encoding="utf-8") as jf:
        json.dump(results, jf, ensure_ascii=False, indent=2)

    with csv_path.open("w", encoding="utf-8", newline="") as cf:
        writer = csv.writer(cf)
        writer.writerow(["url", "ok", "status", "reason", "sources_count", "sources_files_sample", "matched_url", "matched_title"])
        for r in results:
            files = ", ".join({s['file'] for s in r.get('sources', [])})
            writer.writerow([
                r.get("url"), r.get("ok"), r.get("status"), r.get("reason"), len(r.get("sources", [])), files,
                r.get("matched_url", ""), r.get("title", ""),
            ])

    print(f"Reports written: {json_path} and {csv_path}")

    # Print summary of corrections with CSV lines per file
    if corrections_map:
        print("\nCorrections found for the following files:")
        for fn, items in corrections_map.items():
            print(f"\n{fn}:")
            for it in items:
                print(f"  row {it['rownum']}: {it['row_text']} -> {it['matched_url']} ({it.get('matched_title')})")
    else:
        print("No suggested corrections found.")


if __name__ == '__main__':
    main()
