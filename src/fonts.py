import os
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfbase.pdfmetrics import registerFontFamily

# Public font names to be used across the document. These will be set up
# to point at Unicode TrueType fonts when available (e.g., Arial on Windows),
# falling back to built-in Helvetica if not found.
FONT_REGULAR_NAME = "Helvetica"
FONT_BOLD_NAME = "Helvetica-Bold"


def _try_register_ttf_font(family_name, regular_path, bold_path=None):
    """Register TTF fonts with ReportLab. Returns (regular_name, bold_name)."""
    regular_name = family_name
    bold_name = f"{family_name}-Bold" if bold_path else family_name
    pdfmetrics.registerFont(TTFont(regular_name, regular_path))
    if bold_path:
        pdfmetrics.registerFont(TTFont(bold_name, bold_path))
        registerFontFamily(family_name, normal=regular_name, bold=bold_name)
    return regular_name, bold_name


def setup_unicode_fonts():
    """Best-effort registration of Unicode fonts so extended characters (e.g., ō) render.
    On Windows, try common fonts from C:\\Windows\\Fonts. If none found, keep Helvetica.
    """
    global FONT_REGULAR_NAME, FONT_BOLD_NAME
    font_dirs = []
    # Common Windows fonts directory
    try:
        font_dirs.append(os.path.join(os.environ.get("WINDIR", r"C:\\Windows"), "Fonts"))
    except Exception:
        pass
    # Also allow fonts near the project (e.g., dropped into repo)
    font_dirs.append(os.path.abspath("."))
    # Candidate families (regular, bold)
    candidates = [
        ("Arial", ["arial.ttf", "ARIAL.TTF"], ["arialbd.ttf", "ARIALBD.TTF"]),
        ("SegoeUI", ["segoeui.ttf", "SEGOEUI.TTF"], ["segoeuib.ttf", "SEGOEUIB.TTF"]),
        ("Calibri", ["calibri.ttf", "CALIBRI.TTF"], ["calibrib.ttf", "CALIBRIB.TTF"]),
        ("Verdana", ["verdana.ttf", "VERDANA.TTF"], ["verdanab.ttf", "VERDANAB.TTF"]),
        ("Tahoma", ["tahoma.ttf", "TAHOMA.TTF"], ["tahomabd.ttf", "TAHOMABD.TTF"]),
        ("DejaVuSans", ["DejaVuSans.ttf"], ["DejaVuSans-Bold.ttf"]),
        ("NotoSans", ["NotoSans-Regular.ttf"], ["NotoSans-Bold.ttf"]),
    ]

    def find_file(possible_names):
        for d in font_dirs:
            for name in possible_names:
                p = os.path.join(d, name)
                if os.path.isfile(p):
                    return p
        return None

    for family, reg_list, bold_list in candidates:
        reg_path = find_file(reg_list)
        if not reg_path:
            continue
        bold_path = find_file(bold_list)
        try:
            regular_name, bold_name = _try_register_ttf_font(family, reg_path, bold_path)
            FONT_REGULAR_NAME, FONT_BOLD_NAME = regular_name, (bold_name if bold_path else regular_name)
            return
        except Exception:
            continue
    # If no TTF font could be registered, keep defaults (Helvetica family)
