"""Drawing helpers for placing images on the ReportLab canvas."""
from reportlab.lib.utils import ImageReader


def draw_image_in_rect(c, pil_img, x, y, width, height):
    """Draw a PIL image scaled to exactly fit the given rectangle (x, y, width, height).
    Coordinates are ReportLab points. Image aspect is preserved by our layout (card size follows image ratio).
    """
    img_reader = ImageReader(pil_img)
    c.drawImage(img_reader, x, y, width=width, height=height)


def draw_background_image(c, pil_img, page_width, page_height):
    """Draw a background image stretched to entire page size."""
    img_reader = ImageReader(pil_img)
    c.drawImage(img_reader, 0, 0, width=page_width, height=page_height)
