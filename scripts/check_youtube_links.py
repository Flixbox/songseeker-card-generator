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
CSV_GLOB = "**/*.csv"
YOUTUBE_PAT = re.compile(r"https?://(?:www\.)?(?:youtube\.com/watch\?v=|youtu\.be/)([A-Za-z0-9_-]{11})")
TIMEOUT = 15


def find_csv_files(root: Path):
    for p in root.glob(CSV_GLOB):
        if p.is_file():
            yield p


def extract_urls_from_csv(path: Path):
    urls = []
    try:
        with path.open("r", encoding="utf-8", errors="replace") as f:
            reader = csv.reader(f)
            for row in reader:
                for cell in row:
                    if "youtube.com" in cell or "youtu.be" in cell:
                        # extract url(s)
                        for m in re.finditer(r"https?://[\w\-\./\?&=%:#;@!$'()*+,]+", cell):
                            url = m.group(0)
                            if "youtube.com" in url or "youtu.be" in url:
                                urls.append((url, path.as_posix()))
    except Exception as e:
        print(f"Failed to read {path}: {e}", file=sys.stderr)
    return urls


def normalize_url(url: str) -> str:
    # extract the video id and return canonical youtube watch url
    m = YOUTUBE_PAT.search(url)
    if not m:
        return url
    vid = m.group(1)
    return f"https://www.youtube.com/watch?v={vid}"


def check_video(url: str):
    """Use yt-dlp to fetch video metadata. No HTTP fallback.

    Returns a result dict containing at least: url, ok (bool), status (int|None), reason (str), and optional error/title info.
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
        if "unavailable" in low or "not available" in low or "private" in low or "removed" in low:
            reason = "video_unavailable"
        else:
            reason = "yt_dlp_error"
        return {"url": url, "ok": False, "status": None, "reason": reason, "error": err}


def main():
    ap = ArgumentParser()
    ap.add_argument("--root", default=str(REPO_ROOT), help="Repository root to scan")
    ap.add_argument("--output", default=str(Path(__file__).parent / "output_reports"), help="Output folder for reports")
    ap.add_argument("--concurrency", type=int, default=6, help="Parallel requests (not implemented; reserved)")
    args = ap.parse_args()

    root = Path(args.root)
    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)

    found = list(find_csv_files(root))
    print(f"Found {len(found)} CSV files")

    url_map = defaultdict(list)  # normalized -> list of source files
    for p in found:
        for url, src in extract_urls_from_csv(p):
            norm = normalize_url(url)
            url_map[norm].append({"raw": url, "file": src})

    print(f"Found {len(url_map)} unique YouTube urls")

    results = []
    for url, sources in url_map.items():
        print(f"Checking: {url}")
        res = check_video(url)
        res["sources"] = sources
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
        writer.writerow(["url", "ok", "status", "reason", "sources_count", "sources_files_sample"])
        for r in results:
            files = ", ".join({s['file'] for s in r.get('sources', [])})
            writer.writerow([r.get("url"), r.get("ok"), r.get("status"), r.get("reason"), len(r.get("sources", [])), files])

    print(f"Reports written: {json_path} and {csv_path}")


if __name__ == '__main__':
    main()
