"""Layout helpers for card placement and sizing."""
from typing import Tuple
from .constants import PADDING_RATIO


def inner_rect(x: float, y: float, width: float, height: float, padding_ratio: float = PADDING_RATIO) -> Tuple[float, float, float, float]:
    """Return the inner content rectangle applying padding on all sides.

    Args:
        x, y: Lower-left origin of the outer rectangle (ReportLab coordinates)
        width, height: Dimensions of the outer rectangle
        padding_ratio: Ratio of width/height used as padding on each side
    Returns:
        (inner_x, inner_y, inner_width, inner_height)
    """
    pad_x = width * padding_ratio
    pad_y = height * padding_ratio
    return (x + pad_x, y + pad_y, width - 2 * pad_x, height - 2 * pad_y)
