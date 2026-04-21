# papersnap

Extract abstracts, figures, and captions from research paper PDFs into a
clean, self-contained HTML viewer — from a single CLI command.

![Python](https://img.shields.io/badge/python-3.10%2B-blue)

## Motivation

Researchers routinely scan dozens of papers to find relevant figures,
check results, or quickly understand a paper's contribution. Doing this
manually — opening PDFs, scrolling through dense layouts, copying
abstracts — is slow and repetitive. Existing tools either require cloud
services and API keys, depend on large language models (slow and
expensive at scale), or produce unstructured text dumps that lose the
visual context of figures entirely.

## What papersnap does

papersnap is a fast, lightweight, fully local CLI tool that extracts the
three most important parts of any research paper — the abstract, figures,
and captions — and packages them into a single browsable HTML file. No
internet connection, no API calls, no model inference. A typical 10-page
paper is processed in under 2 seconds on a standard laptop.

It works directly on the PDF's internal structure using PyMuPDF, combining
spatial layout heuristics, font-size analysis, and format-aware regex
matching to handle the wide variation in how journals typeset figures and
abstracts. It has been tested across Nature, Frontiers, Elsevier, ACS,
IEEE, and Springer formats without any paper-specific configuration.

## Features

- **Abstract extraction** — finds and extracts the abstract even when
  unlabeled, using font-size and layout heuristics
- **Figure extraction** — detects raster figures across journal formats
- **Caption detection** — matches captions across all common styles:
  `Figure 1:`, `Fig. 1 text`, `FIGURE 1 |`, `Fig. S1A.`
- **Vector figure detection** — detects vector figures and flags them
  as placeholders in the output
- **HTML viewer** — self-contained output with thumbnail grid, lightbox,
  dark mode, and copy-to-clipboard abstract
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
├── <paper-name>.html     # self-contained viewer
├── manifest.json         # structured metadata
└── figures/
    ├── figure_1.png
    └── ...
```

## Benchmark

Evaluated on a 50-paper synthetic benchmark designed to cover mixed
journal layouts and figure types:

| Metric | Score |
|---|---|
| Figure recall | 94.6% (350/370) |
| Figure exact match | 64% (32/50 papers) |
| Abstract detection | 100% (50/50) |
| Caption detection | 98% (342/350) |

## Known limitations

- Vector-only figures are detected but not rendered — shown as
  placeholders in the HTML output
- Figures spanning two pages may be missed

## Future work

- Full vector figure rendering via caption-anchored region detection
- Extraction of bordered tables into structured HTML
- Support for figures that span two pages
- arXiv URL as direct input (download and process in one command)
- Integration with reference managers such as Zotero
