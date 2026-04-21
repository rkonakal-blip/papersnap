"""PDF parsing: abstract extraction and figure extraction."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import fitz  # PyMuPDF

from .caption import find_caption
from .utils import console

# Headings that signal the end of the abstract.
# Covers: numbered sections (1. / 1 / I. / II.), common heading words,
# keyword blocks, ACM/IEEE/Nature metadata lines.
_STOP_HEADINGS = re.compile(
    r"^(i\.?\s+)?introduction"                              # Introduction (with/without I.)
    r"|^keywords?\s*[:\-—]?"                                # Keywords / Keywords:
    r"|^key\s+words?\s*[:\-—]?"                             # Key words:
    r"|^index\s+terms?\s*[:\-—]?"                           # Index Terms
    r"|^ccs\s+concepts?"                                    # ACM CCS Concepts
    r"|^acm\s+reference"                                    # ACM Reference Format
    r"|^[1-9]\d*\s*[\.:\)]\s*\w"                           # 1. / 2. / 1) / 1: Anything
    r"|^[IVX]+\s*[\.:\)]\s*\w"                             # Roman numeral sections
    r"|^(background|motivation|related\s+work|preliminaries"
    r"|overview|methodology|methods?|approach|system|framework"
    r"|experiments?|evaluation|results?|discussion|conclusion)",
    re.IGNORECASE,
)

# Metadata lines that signal the end of the abstract in journal PDFs.
# These appear after the abstract body (received dates, DOI, affiliations, emails).
_METADATA_LINE = re.compile(
    r"received[\s:]|accepted[\s:]|published[\s:]"   # submission timeline
    r"|doi[\s:/]|arxiv[\s:/]"                        # identifiers
    r"|\b@\w+\.\w+"                                  # email address
    r"|✉"                                        # ✉ corresponding-author marker (Nature)
    r"|©|copyright\s"                                # copyright notice
    r"|corresponding\s+author"                       # correspondence note
    r"|edited\s+by|reviewed\s+by"                    # journal peer-review metadata
    r"|specialty\s+section|citation:"                # journal section / citation line
    r"|^\d+\s+(?:department|universit|institute|laborator|school|faculty"
    r"|center|centre|ecole|polytechni|technolog|research\s+group"
    r"|division|college|hospital)",                  # numbered affiliation lines
    re.IGNORECASE,
)

# Minimum image dimensions to keep (filters icons, decorations).
_MIN_DIM = 50

# Minimum pixel area to keep (rejects tiny decorative graphics).
_MIN_AREA = 5_000

# Caption label pattern used to decide whether an image is a scientific figure.
_CAPTION_START_RE = re.compile(r"^\s*(Figure|Fig\.?)\s+\d+", re.IGNORECASE)

# How many points around an image to scan for ANY "Figure" text reference
# (used for the scientific-figure gate). The scientific-figure gate is the
# primary false-positive guard, so this can be wide.
_FIGURE_REF_SEARCH_PT = 350

# Minimum rendered size on the page (points). Filters out dataset thumbnails,
# grid sub-images, and decorative icons that are large in pixels but tiny on page.
_MIN_RENDER_PT = 50

# Vector extraction — noise filters for individual drawing paths.
_VEC_MIN_PATH_DIM = 5      # skip paths tiny in BOTH dimensions (tick marks, dots)
_VEC_MIN_PATH_AREA = 500   # area threshold for non-spine paths
_VEC_MIN_SPINE_LEN = 20    # paths longer than this in one dimension are kept as spines
_VEC_RENDER_ZOOM = 2       # render vector regions at 2× for crisp output
_VEC_BBOX_MARGIN = 6       # padding added around the computed cluster bbox (pts)

@dataclass
class FigureInfo:
    index: int
    path: Path | None  # None for vector placeholders
    page: int          # 1-based
    caption: str | None
    width_px: int
    height_px: int
    vector_only: bool = False

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
    for page_num in range(min(2, len(doc))):
        page = doc[page_num]
        blocks = [b for b in page.get_text("blocks") if b[6] == 0]
        blocks.sort(key=lambda b: (b[1], b[0]))
        page_mid_x = page.rect.width / 2

        for i, block in enumerate(blocks):
            stripped = block[4].strip()

            # Pattern 1: "Abstract" alone on its own line — body in following blocks.
            if re.match(r"^abstract\s*[:\-—]?\s*$", stripped, re.IGNORECASE):
                body = _collect_abstract_body(blocks[i + 1:], page_mid_x)
                if body:
                    return body

            # Pattern 2: "Abstract—text" / "Abstract: text" inline.
            # Body often continues in subsequent blocks so collect those too.
            fused = re.match(
                r"^abstract\s*[:\-—]\s*(.+)", stripped, re.IGNORECASE | re.DOTALL
            )
            if fused:
                head = fused.group(1).strip()
                tail = _collect_abstract_body(blocks[i + 1:], page_mid_x)
                return _clean_text(head + (" " + tail if tail else ""))

            # Pattern 3: "Abstract\nbody text" merged into one block by PyMuPDF.
            merged = re.match(
                r"^abstract\s*[:\-—]?\s*\n(.+)", stripped, re.IGNORECASE | re.DOTALL
            )
            if merged:
                return _clean_text(merged.group(1))

    return None


def _collect_abstract_body(blocks: list, page_mid_x: float) -> str | None:
    """Collect body blocks after an Abstract heading.

    Stops at a section heading, a vertical gap that is notably larger than the
    first gap seen (adaptive baseline), or a hard 350-word cap.
    Short blocks (< 5 words) are skipped — they are metadata lines, not body text.
    """
    parts: list[str] = []
    col_x: float | None = None
    prev_y1: float | None = None
    baseline_gap: float | None = None

    for b in blocks:
        t = b[4].strip()
        if not t:
            continue
        if _is_section_heading(t):
            break
        if _METADATA_LINE.search(t):
            break

        if prev_y1 is not None:
            gap = b[1] - prev_y1
            if baseline_gap is None:
                baseline_gap = max(gap, 1.0)
            elif parts and gap > max(baseline_gap * 2.5, 10.0):
                break

        if len(t.split()) < 5:
            prev_y1 = b[3]
            continue

        block_w = b[2] - b[0]
        if col_x is None:
            col_x = b[0]
        elif block_w <= page_mid_x:
            if (b[0] < page_mid_x) != (col_x < page_mid_x):
                continue

        parts.append(t)
        prev_y1 = b[3]
        if len(" ".join(parts).split()) > 350:
            break

    return _clean_text(" ".join(parts)) if parts else None


def _unlabeled_abstract(doc: fitz.Document) -> str | None:
    """Infer abstract from page 0 using font-size filtering.

    Skips blocks whose average font size differs significantly from the page's
    dominant body font — catching titles (larger) and affiliations (smaller)
    without needing paper-specific regex patterns.
    """
    page = doc[0]
    page_mid_x = page.rect.width / 2
    body_font = _dominant_fontsize(page)

    # Build block list with per-block average font size from dict mode.
    rich_blocks = []
    for b in page.get_text("dict")["blocks"]:
        if b.get("type") != 0:
            continue
        spans = [s for line in b.get("lines", []) for s in line.get("spans", []) if s["text"].strip()]
        if not spans:
            continue
        text = " ".join(s["text"] for s in spans).strip()
        avg_size = sum(s["size"] for s in spans) / len(spans)
        rich_blocks.append((b["bbox"], text, avg_size))

    rich_blocks.sort(key=lambda x: (x[0][1], x[0][0]))  # top-to-bottom

    # Stop at first section heading.
    stop_idx = len(rich_blocks)
    for i, (_, text, _) in enumerate(rich_blocks):
        if _is_section_heading(text):
            stop_idx = i
            break

    col_x: float | None = None
    parts: list[str] = []

    for bbox, t, font_size in rich_blocks[:stop_idx]:
        if len(t.split()) < 30:
            continue
        if _METADATA_LINE.search(t):
            continue
        # Skip blocks whose font size is notably different from body text —
        # bigger = title/heading/authors, smaller = affiliations/footnotes.
        if body_font > 0 and abs(font_size - body_font) > body_font * 0.15:
            continue
        x0, _, x1, _ = bbox
        if col_x is None:
            col_x = x0
        else:
            block_w = x1 - x0
            if block_w <= page_mid_x:
                if (x0 < page_mid_x) != (col_x < page_mid_x):
                    continue
        parts.append(t)
        if len(" ".join(parts).split()) > 250:
            break

    return _clean_text(" ".join(parts)) if parts else None


def _dominant_fontsize(page: fitz.Page) -> float:
    """Return the most common font size on the page — proxy for body text size."""
    from collections import Counter
    sizes: list[int] = []
    for b in page.get_text("dict")["blocks"]:
        if b.get("type") != 0:
            continue
        for line in b.get("lines", []):
            for span in line.get("spans", []):
                if span["text"].strip():
                    sizes.append(round(span["size"]))
    return float(Counter(sizes).most_common(1)[0][0]) if sizes else 10.0


def _is_section_heading(text: str) -> bool:
    first_line = text.split("\n")[0].strip()
    if _STOP_HEADINGS.match(first_line):
        return True
    # Short all-caps line (≤6 words, no sentence punctuation) → likely a heading.
    words = first_line.split()
    if (2 <= len(words) <= 6
            and first_line == first_line.upper()
            and not any(c in first_line for c in ".?!")):
        return True
    return False


def _clean_text(text: str) -> str:
    return " ".join(text.split())


# ---------------------------------------------------------------------------
# Title / metadata extraction
# ---------------------------------------------------------------------------

def extract_metadata(doc: fitz.Document) -> str | None:
    """Return the paper title from PDF metadata or largest font on page 0, or None."""
    meta = doc.metadata or {}
    raw_title = (meta.get("title") or "").strip()
    if (raw_title
            and len(raw_title.split()) >= 4
            and any(c.isalpha() for c in raw_title)
            and not raw_title.replace(" ", "").isnumeric()):
        return raw_title

    try:
        page = doc[0]
        cutoff = page.rect.y0 + page.rect.height * 0.40
        spans = []
        for blk in page.get_text("rawdict")["blocks"]:
            if blk.get("bbox", (0, 0, 0, 0))[1] > cutoff:
                continue
            for line in blk.get("lines", []):
                for span in line.get("spans", []):
                    text = span.get("text", "").strip()
                    if not text or text.replace(" ", "").isnumeric() or len(text) < 4:
                        continue
                    spans.append(span)
        if spans:
            max_size = max(s["size"] for s in spans)
            parts = [
                s["text"].strip()
                for s in spans
                if abs(s["size"] - max_size) < 0.5 and s["text"].strip()
            ]
            candidate = _clean_text(" ".join(parts))
            if candidate and (len(candidate.split()) >= 4 or len(candidate) >= 20):
                return candidate
    except Exception:
        pass

    return None


# ---------------------------------------------------------------------------
# Figure extraction
# ---------------------------------------------------------------------------

def extract_figures(doc: fitz.Document, output_dir: Path) -> list[FigureInfo]:
    """Extract scientific figures from the document (raster + vector)."""
    figures_dir = output_dir / "figures"
    figures_dir.mkdir(parents=True, exist_ok=True)

    figures: list[FigureInfo] = []
    seen_xrefs: set[int] = set()

    for page_num in range(len(doc)):
        page = doc[page_num]
        page_raster_rects: list[fitz.Rect] = []

        # ── Raster pass ──────────────────────────────────────────────────────
        for img_info in page.get_images(full=True):
            xref = img_info[0]
            if xref in seen_xrefs:
                continue
            seen_xrefs.add(xref)

            image_data = doc.extract_image(xref)
            w, h = image_data["width"], image_data["height"]

            if w < _MIN_DIM or h < _MIN_DIM or w * h < _MIN_AREA:
                continue

            rects = page.get_image_rects(xref)
            image_rect = rects[0] if rects else page.rect

            if image_rect.width < _MIN_RENDER_PT or image_rect.height < _MIN_RENDER_PT:
                continue

            if not _is_scientific_figure(page, image_rect, doc, page_num):
                console.print(
                    f"  [dim]page {page_num + 1}[/dim] "
                    f"[yellow]skipped[/yellow] — no Figure caption found "
                    f"(likely photo or decoration)"
                )
                continue

            idx = len(figures) + 1
            png_path = figures_dir / f"figure_{idx}.png"

            pix = fitz.Pixmap(doc, xref)
            if pix.colorspace and pix.colorspace.n > 3:
                pix = fitz.Pixmap(fitz.csRGB, pix)
            pix.save(str(png_path))

            caption = find_caption(page, image_rect, doc, page_num, idx)
            figures.append(FigureInfo(
                index=idx, path=png_path, page=page_num + 1,
                caption=caption, width_px=w, height_px=h,
            ))
            page_raster_rects.append(image_rect)
            status = "caption found" if caption else "no caption"
            console.print(
                f"  [dim]figure {idx}[/dim] page {page_num + 1} "
                f"[dim]({w}×{h})[/dim] — {status}"
            )

        # ── Vector pass ───────────────────────────────────────────────────────
        for fig in _extract_vector_figures(
            doc, page, page_num, figures_dir, len(figures) + 1, page_raster_rects
        ):
            figures.append(fig)

    return figures


def _extract_vector_figures(
    doc: fitz.Document,
    page: fitz.Page,
    page_num: int,
    figures_dir: Path,
    next_idx: int,
    raster_rects: list,
) -> list[FigureInfo]:
    """Detect vector figures (captions with no raster nearby) and return placeholders."""
    results: list[FigureInfo] = []

    for caption_block in _find_figure_captions(page):
        caption_rect = fitz.Rect(caption_block[:4])
        if _caption_covered_by_raster(caption_rect, raster_rects):
            continue

        idx = next_idx + len(results)
        caption_text = " ".join(caption_block[4].strip().split())
        results.append(FigureInfo(
            index=idx, path=None, page=page_num + 1,
            caption=caption_text, width_px=0, height_px=0,
            vector_only=True,
        ))
        console.print(
            f"  [dim]figure {idx}[/dim] page {page_num + 1} "
            f"[yellow](vector — detected, excluded)[/yellow]"
        )

    return results


def _find_figure_captions(page: fitz.Page) -> list:
    """Return all text blocks on the page whose text starts with 'Figure N'."""
    return [b for b in page.get_text("blocks") if _CAPTION_START_RE.match(b[4].strip())]


def _caption_covered_by_raster(caption_rect: fitz.Rect, raster_rects: list) -> bool:
    """True if a raster figure already occupies the area above this caption."""
    search_zone = fitz.Rect(
        caption_rect.x0 - 50,
        caption_rect.y0 - _FIGURE_REF_SEARCH_PT,
        caption_rect.x1 + 50,
        caption_rect.y1,
    )
    return any(search_zone.intersects(r) for r in raster_rects)


def _drawing_cluster_bbox(page: fitz.Page, search_rect: fitz.Rect) -> fitz.Rect | None:
    """Return the union bbox of significant drawing paths within search_rect."""
    relevant: list[fitz.Rect] = []
    for path in page.get_drawings():
        r = fitz.Rect(path["rect"])
        if not r.intersects(search_rect):
            continue
        # Skip paths that are tiny in both dimensions (dots, very short ticks).
        if r.width < _VEC_MIN_PATH_DIM and r.height < _VEC_MIN_PATH_DIM:
            continue
        # Keep thin-but-long paths (axis spines: e.g. 0.8pt × 200pt).
        # For everything else, require a minimum area to filter decorative noise.
        if r.width * r.height < _VEC_MIN_PATH_AREA and max(r.width, r.height) < _VEC_MIN_SPINE_LEN:
            continue
        relevant.append(r)

    if not relevant:
        return None

    bbox = relevant[0]
    for r in relevant[1:]:
        bbox |= r

    # Add margin and clip to page.
    m = _VEC_BBOX_MARGIN
    bbox = fitz.Rect(bbox.x0 - m, bbox.y0 - m, bbox.x1 + m, bbox.y1 + m)
    bbox &= page.rect
    return bbox if not bbox.is_empty else None


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
