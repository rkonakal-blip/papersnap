# papersnap

Extract abstracts, figures, and captions from research paper PDFs into a
clean, self-contained HTML viewer — from a single CLI command.

![Python](https://img.shields.io/badge/python-3.10%2B-blue)
![Version](https://img.shields.io/badge/version-0.3.0-green)

## Motivation

Researchers routinely scan dozens of papers to find relevant figures,
check results, or quickly understand a paper's contribution. Doing this
manually — opening PDFs, scrolling through dense multi-column layouts,
copying abstracts — is slow and repetitive.

Existing tools fall short in different ways: cloud-based tools require
API keys and internet access; LLM-based tools are slow and expensive at
scale; raw text extractors (pdfminer, pdfplumber) produce unstructured
dumps that lose all visual context. None of them give you figures and
abstracts together in a browsable format, locally, instantly.

## What papersnap does

papersnap is a fast, lightweight, fully local CLI tool that extracts the
three most decision-relevant parts of any research paper — the abstract,
figures, and captions — and packages them into a single browsable HTML
file. No internet connection, no API calls, no model inference. A typical
10-page paper is processed in under 2 seconds on a standard laptop.

It works directly on the PDF's internal structure using PyMuPDF, combining
spatial layout heuristics, font-size analysis, and format-aware regex
matching to handle the wide variation in how journals typeset figures and
abstracts. It has been tested across Nature, Frontiers, Elsevier, ACS,
IEEE, and Springer formats without any paper-specific configuration.

## Features

- **Abstract extraction** — finds and extracts the abstract even when
  unlabeled, using font-size filtering and layout heuristics
- **Raster figure extraction** — detects embedded images across all
  common journal formats with a scientific-figure gate to reject icons
  and decorations
- **Vector figure rendering** — detects and renders vector/mixed figures
  (block diagrams, circuit schematics, plots) using caption-anchored
  region detection via PyMuPDF — no external dependencies
- **Caption detection** — matches captions across all common styles:
  `Figure 1:`, `Fig. 1 text`, `FIGURE 1 |`, `Fig. S1A.`
- **HTML viewer** — self-contained output with thumbnail grid, lightbox,
  keyboard navigation, dark mode, and copy-to-clipboard abstract
- **Batch processing** — process an entire folder of PDFs in one command
- **Manifest** — structured JSON per paper for downstream use

## Install

```bash
pip install pymupdf typer rich pillow
pip install -e .
```

## Usage

```bash
# Single paper
papersnap extract paper.pdf

# Custom output directory
papersnap extract paper.pdf --output ~/results

# Batch — process every PDF in a folder
papersnap extract papers/
```

Output goes to `~/Desktop/papersnap/<paper-name>/` by default.

## Output structure

```
papersnap/<paper-name>/
├── <paper-name>.html     # self-contained viewer (open in any browser)
├── manifest.json         # structured metadata for downstream use
└── figures/
    ├── figure_1.png
    └── ...
```

## Benchmark

Evaluated on a 50-paper synthetic benchmark covering mixed journal
layouts, figure types (photos, charts, diagrams, spectra, microscopy,
multipanel), and caption styles:

| Metric | Score |
|---|---|
| Figure recall | 96.2% (356/370) |
| Figure exact match | 72% (36/50 papers) |
| Abstract detection | 100% (50/50) |
| Caption presence | 100% (356/356 extracted) |
| Caption accuracy (F1 >= 0.5 vs ground truth) | 90% (333/370) |

Caption accuracy uses word-overlap F1 against ground truth caption text —
a much stricter metric than simply detecting that a caption exists.

## How it works

### Abstract extraction
Two-tier strategy. First looks for an explicit "Abstract" heading and
collects the body blocks that follow, stopping at section headings,
metadata lines (DOI, affiliations, received dates), or vertical gaps.
If no heading is found, falls back to font-size filtering: the dominant
font size on page 0 is used as a body-text proxy, and blocks that differ
by more than 15% are skipped — rejecting titles, author lines, and
footnotes without paper-specific rules.

### Figure extraction
Raster figures are extracted directly from PDF image xrefs and filtered
by size, rendered dimensions, and a scientific-figure gate (checks for a
nearby `Figure N` caption within 350pt). Vector figures are detected by
finding figure caption blocks, computing the region between consecutive
captions, and rendering that region to PNG using `page.get_pixmap()` at
2x zoom — capturing raster, vector, and mixed content in a single call.

### Caption detection
Two-tier regex: a strict pattern (separator required) for full-page
scans, and a spatial pattern (no separator) for proximity searches near
images. A body-reference guard rejects sentences like "Figure 3 shows
that..." that match the pattern but are not captions.

## Known limitations

- **Scanned PDFs**: no text layer means nothing can be extracted — OCR
  would be required
- **Vector region over-capture**: the caption-anchored render region
  spans the full vertical gap between captions, which can include body
  text paragraphs above the figure
- **Sub-panel duplication**: multi-panel figures with separate image
  objects per panel are extracted as individual figures
- **Figures spanning two pages**: may be missed if the image and caption
  are on different pages beyond the search window

## Future work

- Column-aware vector crop for two-column layouts
- Sub-panel grouping: cluster spatially adjacent images that share a
  caption into a single figure
- OCR fallback for scanned PDFs (e.g. Tesseract)
- Bordered table extraction into structured HTML
- arXiv URL as direct input
- Integration with reference managers such as Zotero
