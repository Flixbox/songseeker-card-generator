import argparse
import os
import sys
import logging


# Ensure src/ is importable when running as a script
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))
from src.generator import main


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("csv_file", help="Path to the CSV file")
    parser.add_argument("output_pdf", help="Path to the output PDF file")
    parser.add_argument("--icon", help="path to icon to embedd to QR Code, should not exeed 300x300px and using transparent background", required=False)
    parser.add_argument("--no-mirror-backside", action="store_true", help="Disable mirroring on the backside (text side)")
    parser.add_argument("--front-bg", help="Path to background image for the front (QR) side", required=False)
    parser.add_argument("--back-bg", help="Path to background image for the back (text) side", required=False)
    parser.add_argument("--qr-padding-px", type=int, default=None, help="QR code white border thickness in pixels (quiet zone). Example: 10. Note: QR spec recommends ~4 modules (~40px with default settings); reducing too much may impact scan reliability.")
    parser.add_argument("--shrink-front", type=float, default=0.0, help="Shrink percentage for front (QR) content area, 0-100. Example: 10 => 10% smaller (90% of original). Values are clamped to a safe minimum size.")
    parser.add_argument("--shrink-back", type=float, default=0.0, help="Shrink percentage for back (text) content area, 0-100. Example: 15 => 15% smaller. Values are clamped to a safe minimum size.")
    parser.add_argument("--fix-links", action="store_true", help="Perform YouTube link validation and try to auto-correct broken links before generating cards")
    parser.add_argument("--fix-csv", action="store_true", help="Write automatic link corrections back to the input CSV file (implies --fix-links)")
    args = parser.parse_args()

    # If fix_csv requested, ensure fix_links is enabled as well
    if args.fix_csv:
        args.fix_links = True

    mirror_backside = not args.no_mirror_backside
    # configure basic logging to console so users are kept up-to-date
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    main(
        args.csv_file,
        args.output_pdf,
        args.icon,
        mirror_backside,
        args.front_bg,
        args.back_bg,
        fix_links=args.fix_links,
        qr_padding_px=args.qr_padding_px,
        shrink_front_pct=args.shrink_front,
        shrink_back_pct=args.shrink_back,
        fix_csv=args.fix_csv,
    )
