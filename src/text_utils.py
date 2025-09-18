"""Text utilities relying on ReportLab width metrics."""
from typing import List


def wrap_text_to_width(c, text: str, font_name: str, font_size: float, max_width: float) -> List[str]:
    """Wrap text into lines that do not exceed max_width using ReportLab width metrics.
    Falls back to character-level splitting if a single word exceeds max_width.
    Returns a list of lines (strings).
    """
    if text is None or str(text).strip() == "":
        return []
    words = str(text).split()
    lines: List[str] = []
    current = ""
    for w in words:
        candidate = (current + " " + w).strip()
        if c.stringWidth(candidate, font_name, font_size) <= max_width:
            current = candidate
        else:
            if current == "":
                # If current is empty, the single word might be too long — split by characters
                segment = ""
                for ch in w:
                    if c.stringWidth(segment + ch, font_name, font_size) <= max_width:
                        segment += ch
                    else:
                        if segment:
                            lines.append(segment)
                        segment = ch
                if segment:
                    current = segment
                else:
                    current = ""
            else:
                lines.append(current)
                current = w
    if current:
        lines.append(current)
    return lines
