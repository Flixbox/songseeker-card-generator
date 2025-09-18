"""Shared layout and typography constants for card rendering."""

# 10% padding on each side inside each card box
PADDING_RATIO: float = 0.10

# Relative caps for text blocks based on inner card height
YEAR_MAX_HEIGHT_RATIO: float = 0.20   # Year text may take up to 20% of inner card height
ARTIST_MAX_HEIGHT_RATIO: float = 0.12 # Artist block line size cap relative to inner height
TITLE_MAX_HEIGHT_RATIO: float = 0.12  # Title block line size cap relative to inner height
