"""Caption detection via spatial proximity and regex matching."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import fitz

# Strict: separator required — used for full-page scan to avoid matching
# body sentences like "Figure 3 shows that..." across the whole page.
_CAPTION_STRICT = re.compile(
    r"^\s*(Figure|Fig\.?)\s+[Ss]?\d+[A-Za-z]?\s*[:.—\-|,]", re.IGNORECASE
)

# Spatial: separator optional — proximity to the image is already the guard.
# Covers Nature/Springer style "Fig. 1 Description..." with no separator.
_CAPTION_SPATIAL = re.compile(
    r"^\s*(Figure|Fig\.?)\s+[Ss]?\d+[A-Za-z]?\b", re.IGNORECASE
)

# Negative guard: body sentences that reference a figure but are not captions.
_BODY_REF = re.compile(
    r"^\s*(Figure|Fig\.?)\s+[Ss]?\d+[A-Za-z]?\s+"
    r"(shows?|demonstrates?|illustrates?|depicts?|indicates?|presents?|"
    r"reveals?|displays?|compares?|summarizes?|highlights?|suggests?|"
    r"confirms?|provides?|gives?|lists?)\b",
    re.IGNORECASE,
)

# How far below the image bbox (in points) to search.
_SEARCH_DEPTH_PT = 200

# How far above the image bbox (some papers caption above).
_SEARCH_ABOVE_PT = 60


def find_caption(
    page: "fitz.Page",
    image_rect: "fitz.Rect",
    doc: "fitz.Document",
    page_num: int,
    figure_index: int,
) -> str | None:
    """Return the full caption string for an image, or None if not found.

    Search order:
    1. Column-aware window below the image (same horizontal band).
    2. Window above the image.
    3. Top of the next page (same column).
    4. Full-page scan by figure index number.
    """
    result = _below_search(page, image_rect)
    if result:
        return result

    result = _above_search(page, image_rect)
    if result:
        return result

    if page_num + 1 < len(doc):
        result = _top_of_page_search(doc[page_num + 1], image_rect)
        if result:
            return result

    return _full_page_scan(page, figure_index)


def _below_search(page: "fitz.Page", image_rect: "fitz.Rect") -> str | None:
    import fitz

    page_rect = page.rect
    search_rect = fitz.Rect(
        page_rect.x0,
        image_rect.y1,
        page_rect.x1,
        min(image_rect.y1 + _SEARCH_DEPTH_PT, page_rect.y1),
    )
    return _find_in_rect(page, search_rect, image_rect)


def _above_search(page: "fitz.Page", image_rect: "fitz.Rect") -> str | None:
    import fitz

    page_rect = page.rect
    search_rect = fitz.Rect(
        page_rect.x0,
        max(image_rect.y0 - _SEARCH_ABOVE_PT, page_rect.y0),
        page_rect.x1,
        image_rect.y0,
    )
    return _find_in_rect(page, search_rect, image_rect)


def _top_of_page_search(
    page: "fitz.Page", image_rect: "fitz.Rect"
) -> str | None:
    import fitz

    page_rect = page.rect
    search_rect = fitz.Rect(
        page_rect.x0,
        page_rect.y0,
        page_rect.x1,
        page_rect.y0 + _SEARCH_DEPTH_PT,
    )
    return _find_in_rect(page, search_rect, image_rect)


def _find_in_rect(
    page: "fitz.Page",
    search_rect: "fitz.Rect",
    image_rect: "fitz.Rect",
) -> str | None:
    """Search clipped rect for a caption, preferring same-column blocks.

    Two-tier matching:
    1. Strict pattern (separator required) — higher confidence.
    2. Relaxed pattern (no separator) — fallback, guarded by body-ref filter.
    Each tier tries column-aligned blocks before accepting any block in the rect.
    """
    blocks = page.get_text("blocks", clip=search_rect)
    blocks = sorted(blocks, key=lambda b: (b[1], b[0]))

    for strict in (True, False):
        for prefer_x in (image_rect, None):
            idx = _find_caption_block(blocks, prefer_x=prefer_x, strict=strict)
            if idx is not None:
                return _accumulate_caption(blocks, idx)

    return None


def _find_caption_block(
    blocks: list,
    prefer_x: "fitz.Rect | None",
    strict: bool,
) -> int | None:
    pattern = _CAPTION_STRICT if strict else _CAPTION_SPATIAL
    for i, block in enumerate(blocks):
        text = block[4].strip()
        if not pattern.match(text):
            continue
        if not strict and _BODY_REF.match(text):
            continue
        if prefer_x is not None:
            bx0, bx1 = block[0], block[2]
            if bx1 < prefer_x.x0 - 10 or bx0 > prefer_x.x1 + 10:
                continue
        return i
    return None


def _accumulate_caption(blocks: list, start: int) -> str:
    """Return the caption block text.
    Captions are always a single block in well-formed PDFs — accumulating
    continuation blocks only pulls in body text from adjacent paragraphs."""
    return _clean(blocks[start][4].strip())


def _full_page_scan(page: "fitz.Page", figure_index: int) -> str | None:
    pattern = re.compile(
        rf"^\s*(Figure|Fig\.?)\s+[Ss]?{figure_index}[A-Za-z]?\s*[:.—\-|,]",
        re.IGNORECASE,
    )
    blocks = sorted(page.get_text("blocks"), key=lambda b: (b[1], b[0]))
    for i, block in enumerate(blocks):
        if pattern.match(block[4].strip()):
            return _accumulate_caption(blocks, i)
    return None


def _clean(text: str) -> str:
    return " ".join(text.split())
