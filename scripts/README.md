check_youtube_links.py

Usage:

python scripts/check_youtube_links.py

Outputs:
- scripts/output_reports/<timestamp>_report.json
- scripts/output_reports/<timestamp>_report.csv

Notes:
- This script uses yt-dlp to fetch YouTube metadata via the yt-dlp Python library.
- If you previously used pafy with youtube-dl, prefer installing yt-dlp and pafy is no longer required.

Installing dependencies:

# Recommended: install yt-dlp and pafy
follow the root readme file to install all dependencies

# Alternatively, if you want to use pafy's internal backend (not recommended), set this env var before running:
# On PowerShell (Windows):
# $env:PAFY_BACKEND = "internal"
# On macOS/Linux:
# export PAFY_BACKEND=internal

Be mindful of request volume; the script includes a small delay between requests.
