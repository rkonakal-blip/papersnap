"""PDF parsing: abstract extraction and figure extraction."""

from __future__ import annotations

import re
import textwrap
from dataclasses import dataclass
from pathlib import Path

import fitz  # PyMuPDF
from PIL import Image, ImageDraw, ImageFont

from .caption import find_caption
from .utils import console

# Headings that signal the end of the abstract.
_STOP_HEADINGS = re.compile(
    r"^(1\.?\s+)?introduction|keywords?|index terms?|"
    r"1\s*$|i\.\s+introduction",
    re.IGNORECASE,
)

# Minimum image dimensions to keep (filters icons, decorations).
_MIN_DIM = 80

# Minimum pixel area to keep (rejects tiny decorative graphics).
_MIN_AREA = 15_000

# Caption label pattern used to decide whether an image is a scientific figure.
_CAPTION_START_RE = re.compile(r"^\s*(Figure|Fig\.?)\s+\d+", re.IGNORECASE)

# How many points around an image to scan for ANY "Figure" text reference
# (used for the scientific-figure gate). Kept tight to avoid false positives
# from unrelated figure references elsewhere on the page.
_FIGURE_REF_SEARCH_PT = 200

# Minimum rendered size on the page (points). Filters out dataset thumbnails,
# grid sub-images, and decorative icons that are large in pixels but tiny on page.
_MIN_RENDER_PT = 100

# Caption rendering constants (pixels).
_CAPTION_FONT_SIZE = 20
_CAPTION_PADDING = 20
_CAPTION_LINE_WIDTH = 80  # chars per line


@dataclass
class FigureInfo:
    index: int
    path: Path
    page: int          # 1-based
    caption: str | None
    width_px: int
    height_px: int

    @property
    def caption_found(self) -> bool:
        return self.caption is not None


# ---------------------------------------------------------------------------
# Abstract extraction
# ---------------------------------------------------------------------------

def extract_abstract(doc: fitz.Document) -> str | None:
    """Return the abstract text or None if not found."""
    # Primary: look for an explicit 'Abstract' heading.
    result = _labeled_abstract(doc)
    if result:
        return result
    # Fallback: infer abstract as the first substantive block(s) before the
    # first section heading on page 0 (handles papers with no 'Abstract' label).
    return _unlabeled_abstract(doc)


def _labeled_abstract(doc: fitz.Document) -> str | None:
    """Find abstract when an explicit 'Abstract' heading is present."""
    # Only scan the first two pages — abstracts are never further in.
    # Process each page independently so y-coordinates stay page-relative.
    for page_num in range(min(2, len(doc))):
        page = doc[page_num]
        blocks = [b for b in page.get_text("blocks") if b[6] == 0]
        blocks.sort(key=lambda b: (b[1], b[0]))
        page_mid_x = page.rect.width / 2

        for i, block in enumerate(blocks):
            stripped = block[4].strip()

            # "Abstract" heading alone on its own line.
            if re.match(r"^abstract\s*[:\-—]?\s*$", stripped, re.IGNORECASE):
                parts: list[str] = []
                col_x: float | None = None

                for b in blocks[i + 1:]:
                    t = b[4].strip()
                    if not t:
                        continue
                    if _is_section_heading(t):
                        break
                    if col_x is None:
                        col_x = b[0]
                    else:
                        same_col = (b[0] < page_mid_x) == (col_x < page_mid_x)
                        if not same_col:
                            continue
                    parts.append(t)
                    if len(" ".join(parts).split()) > 350:
                        break
                if parts:
                    return _clean_text(" ".join(parts))

            # "Abstract: text on the same line."
            fused = re.match(
                r"^abstract\s*[:\-—]\s+(.+)", stripped, re.IGNORECASE | re.DOTALL
            )
            if fused:
                return _clean_text(fused.group(1))

    return None


def _unlabeled_abstract(doc: fitz.Document) -> str | None:
    """Infer abstract from page 0: the first substantive block(s) before the
    first section heading, skipping short metadata blocks (title, authors,
    affiliations) which are always < 50 words."""
    page = doc[0]
    blocks = [b for b in page.get_text("blocks") if b[6] == 0]
    blocks.sort(key=lambda b: (b[1], b[0]))
    page_mid_x = page.rect.width / 2

    # Find where the first section heading is.
    stop_idx = len(blocks)
    for i, b in enumerate(blocks):
        if _is_section_heading(b[4].strip()):
            stop_idx = i
            break

    col_x: float | None = None
    parts: list[str] = []

    for b in blocks[:stop_idx]:
        t = b[4].strip()
        # Skip metadata: title, authors, affiliations are always short.
        if len(t.split()) < 50:
            continue
        # Establish column from first qualifying block.
        if col_x is None:
            col_x = b[0]
        else:
            same_col = (b[0] < page_mid_x) == (col_x < page_mid_x)
            if not same_col:
                continue
        parts.append(t)
        if len(" ".join(parts).split()) > 350:
            break

    return _clean_text(" ".join(parts)) if parts else None


def _is_section_heading(text: str) -> bool:
    # Check only the first line — heading blocks sometimes include the first
    # sentence of the section, making the full block > 60 chars.
    first_line = text.split("\n")[0].strip()
    return bool(_STOP_HEADINGS.match(first_line))


def _clean_text(text: str) -> str:
    return " ".join(text.split())


# ---------------------------------------------------------------------------
# Figure extraction
# ---------------------------------------------------------------------------

def extract_figures(doc: fitz.Document, output_dir: Path) -> list[FigureInfo]:
    """Extract scientific figures, composite captions onto PNGs."""
    figures_dir = output_dir / "figures"
    figures_dir.mkdir(parents=True, exist_ok=True)

    figures: list[FigureInfo] = []
    seen_xrefs: set[int] = set()  # global — same image in appendix/repeated pages extracted once

    for page_num in range(len(doc)):
        page = doc[page_num]

        for img_info in page.get_images(full=True):
            xref = img_info[0]
            if xref in seen_xrefs:
                continue
            seen_xrefs.add(xref)

            image_data = doc.extract_image(xref)
            w, h = image_data["width"], image_data["height"]

            if w < _MIN_DIM or h < _MIN_DIM or w * h < _MIN_AREA:
                continue

            # Get image position for caption search and column alignment.
            rects = page.get_image_rects(xref)
            image_rect = rects[0] if rects else page.rect

            # Rendered-size gate: skip images that appear tiny on the page
            # (dataset thumbnails, multi-panel grid cells, icons).
            if image_rect.width < _MIN_RENDER_PT or image_rect.height < _MIN_RENDER_PT:
                continue

            # --- Scientific figure gate ---
            # Only keep images that have a "Figure X" caption or reference nearby.
            if not _is_scientific_figure(page, image_rect, doc, page_num):
                console.print(
                    f"  [dim]page {page_num + 1}[/dim] "
                    f"[yellow]skipped[/yellow] — no Figure caption found "
                    f"(likely photo or decoration)"
                )
                continue

            idx = len(figures) + 1
            png_path = figures_dir / f"figure_{idx}.png"

            # Normalize to PNG (handles JPEG, JPEG2000, CMYK→RGB).
            pix = fitz.Pixmap(doc, xref)
            if pix.colorspace and pix.colorspace.n > 3:
                pix = fitz.Pixmap(fitz.csRGB, pix)
            pix.save(str(png_path))

            caption = find_caption(page, image_rect, doc, page_num, idx)

            # Composite caption text onto the PNG.
            _composite_caption(png_path, caption)

            figures.append(
                FigureInfo(
                    index=idx,
                    path=png_path,
                    page=page_num + 1,
                    caption=caption,
                    width_px=w,
                    height_px=h,
                )
            )
            status = "caption found" if caption else "no caption"
            console.print(
                f"  [dim]figure {idx}[/dim] page {page_num + 1} "
                f"[dim]({w}×{h})[/dim] — {status}"
            )

    return figures


# ---------------------------------------------------------------------------
# Scientific figure gate
# ---------------------------------------------------------------------------

def _is_scientific_figure(
    page: fitz.Page,
    image_rect: fitz.Rect,
    doc: fitz.Document,
    page_num: int,
) -> bool:
    """Return True if a Figure/Fig caption or reference is near the image."""
    # Check current page in an expanded window around the image.
    expanded = fitz.Rect(
        page.rect.x0,
        max(image_rect.y0 - _FIGURE_REF_SEARCH_PT, page.rect.y0),
        page.rect.x1,
        min(image_rect.y1 + _FIGURE_REF_SEARCH_PT, page.rect.y1),
    )
    blocks = page.get_text("blocks", clip=expanded)
    for block in blocks:
        if _CAPTION_START_RE.match(block[4].strip()):
            return True

    # Check next page top (caption on following page).
    if page_num + 1 < len(doc):
        next_page = doc[page_num + 1]
        top_rect = fitz.Rect(
            next_page.rect.x0, next_page.rect.y0,
            next_page.rect.x1, next_page.rect.y0 + _FIGURE_REF_SEARCH_PT,
        )
        for block in next_page.get_text("blocks", clip=top_rect):
            if _CAPTION_START_RE.match(block[4].strip()):
                return True

    return False


# ---------------------------------------------------------------------------
# Caption compositing
# ---------------------------------------------------------------------------

def _composite_caption(png_path: Path, caption: str | None) -> None:
    """Render caption text below the figure image and overwrite the PNG."""
    if not caption:
        return

    img = Image.open(png_path).convert("RGB")
    img_w, img_h = img.size

    # Wrap caption text to fit the image width.
    wrapped_lines = textwrap.wrap(caption, width=_CAPTION_LINE_WIDTH)
    if not wrapped_lines:
        return

    # Try to load a default font; fall back to PIL built-in.
    try:
        font = ImageFont.truetype("arial.ttf", _CAPTION_FONT_SIZE)
    except (IOError, OSError):
        try:
            font = ImageFont.truetype(
                "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
                _CAPTION_FONT_SIZE,
            )
        except (IOError, OSError):
            font = ImageFont.load_default()

    # Measure text height using a temporary draw surface.
    tmp_draw = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    line_h = int(tmp_draw.textbbox((0, 0), "Ag", font=font)[3]) + 4
    caption_block_h = line_h * len(wrapped_lines) + _CAPTION_PADDING * 2

    # Build composite: original image on top, white caption block below.
    composite = Image.new("RGB", (img_w, img_h + caption_block_h), "white")
    composite.paste(img, (0, 0))

    draw = ImageDraw.Draw(composite)

    # Thin separator line between image and caption.
    draw.line(
        [(0, img_h), (img_w, img_h)],
        fill="#cccccc",
        width=1,
    )

    # Render each wrapped line.
    y = img_h + _CAPTION_PADDING
    for line in wrapped_lines:
        draw.text((_CAPTION_PADDING, y), line, fill="#222222", font=font)
        y += line_h

    composite.save(str(png_path), "PNG")
