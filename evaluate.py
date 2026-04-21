#!/usr/bin/env python3
"""
PaperSnap evaluation script.

Compares PaperSnap extraction results against ground truth for a synthetic benchmark.

Usage:
  # Using the central manifests folder (preferred)
  python evaluate.py \\
    --manifests "C:/Users/Rithika/Desktop/papersnap/manifests" \\
    --ground-truth "C:/Users/Rithika/synthetic_dataset_generator/synthetic_dataset/ground_truth"

  # With abstract text quality (word-overlap F1) — requires source PDFs
  python evaluate.py \\
    --manifests "C:/Users/Rithika/Desktop/papersnap/manifests" \\
    --ground-truth "C:/Users/Rithika/synthetic_dataset_generator/synthetic_dataset/ground_truth" \\
    --pdfs "C:/Users/Rithika/synthetic_dataset_generator/synthetic_dataset/pdfs" \\
    --papersnap-output ~/Desktop/papersnap

  # Save results to JSON
  python evaluate.py ... --output-json eval_results.json
"""

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path

import fitz  # PyMuPDF — already a PaperSnap dependency
from rich.console import Console
from rich.table import Table


@dataclass
class PaperResult:
    paper_id: str
    gt_figure_count: int
    extracted_figure_count: int
    figure_delta: int
    abstract_found: bool
    caption_found_count: int
    caption_total: int
    abstract_f1: float | None


def load_manifest(manifests_dir: Path, paper_id: str) -> dict | None:
    # Central manifests folder: manifest_{paper_id}.json
    central = manifests_dir / f"manifest_{paper_id}.json"
    if central.exists():
        return json.loads(central.read_text(encoding="utf-8"))
    # Fallback: per-paper subfolder layout
    per_paper = manifests_dir / paper_id / "manifest.json"
    if per_paper.exists():
        return json.loads(per_paper.read_text(encoding="utf-8"))
    return None


def load_ground_truth(gt_dir: Path, paper_id: str) -> dict | None:
    path = gt_dir / f"{paper_id}_gt.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def extract_abstract_from_html(papersnap_dir: Path, paper_id: str) -> str | None:
    html_path = papersnap_dir / paper_id / f"{paper_id}.html"
    if not html_path.exists():
        return None
    html = html_path.read_text(encoding="utf-8", errors="replace")
    m = re.search(r'<section[^>]+id="abstract"[^>]*>.*?<p>(.*?)</p>', html, re.DOTALL)
    if not m:
        return None
    text = re.sub(r"<[^>]+>", "", m.group(1))
    return text.strip()


def extract_abstract_from_pdf(pdf_path: Path) -> str | None:
    """Extract the abstract section text from a source PDF using PyMuPDF."""
    doc = fitz.open(str(pdf_path))
    full_text = ""
    for page_num in range(min(2, doc.page_count)):
        full_text += doc[page_num].get_text()
    doc.close()

    # Grab text after "Abstract" heading until the next section heading
    m = re.search(
        r"(?:^|\n)[Aa]bstract\s*\n(.*?)(?=\n[A-Z][A-Za-z ]{2,}\n|\n\d+[\.\s]|\Z)",
        full_text,
        re.DOTALL,
    )
    if m:
        return m.group(1).strip()
    return None


def word_overlap_f1(text1: str, text2: str) -> float:
    words1 = set(re.findall(r"\b\w+\b", text1.lower()))
    words2 = set(re.findall(r"\b\w+\b", text2.lower()))
    if not words1 or not words2:
        return 0.0
    common = words1 & words2
    precision = len(common) / len(words1)
    recall = len(common) / len(words2)
    if precision + recall == 0:
        return 0.0
    return 2 * precision * recall / (precision + recall)


def evaluate_paper(
    paper_id: str,
    manifests_dir: Path,
    gt_dir: Path,
    pdfs_dir: Path | None,
    papersnap_output: Path | None,
) -> PaperResult | None:
    manifest = load_manifest(manifests_dir, paper_id)
    gt = load_ground_truth(gt_dir, paper_id)
    if manifest is None or gt is None:
        return None

    gt_figure_count = len(gt.get("figures", []))
    extracted_count = manifest.get("figure_count", 0)
    abstract_found = manifest.get("abstract_found", False)

    figures = manifest.get("figures", [])
    caption_found_count = sum(1 for f in figures if f.get("caption_found", False))

    abstract_f1 = None
    if abstract_found and pdfs_dir is not None and papersnap_output is not None:
        pdf_path = pdfs_dir / f"{paper_id}.pdf"
        extracted_text = extract_abstract_from_html(papersnap_output, paper_id)
        ref_text = extract_abstract_from_pdf(pdf_path) if pdf_path.exists() else None
        if extracted_text and ref_text:
            abstract_f1 = word_overlap_f1(extracted_text, ref_text)

    return PaperResult(
        paper_id=paper_id,
        gt_figure_count=gt_figure_count,
        extracted_figure_count=extracted_count,
        figure_delta=extracted_count - gt_figure_count,
        abstract_found=abstract_found,
        caption_found_count=caption_found_count,
        caption_total=extracted_count,
        abstract_f1=abstract_f1,
    )


def discover_papers(manifests_dir: Path, gt_dir: Path) -> list[str]:
    """Return sorted list of paper IDs present in both manifests folder and GT."""
    # Central folder: manifest_{paper_id}.json
    central_ids = {
        p.stem.removeprefix("manifest_")
        for p in manifests_dir.glob("manifest_*.json")
    }
    # Fallback: per-paper subfolders
    subfolder_ids = {
        p.name
        for p in manifests_dir.iterdir()
        if p.is_dir() and (p / "manifest.json").exists()
    }
    papersnap_ids = central_ids | subfolder_ids
    gt_ids = {p.stem.removesuffix("_gt") for p in gt_dir.glob("*_gt.json")}
    return sorted(papersnap_ids & gt_ids)


def print_results(results: list[PaperResult], show_f1: bool, console: Console) -> None:
    table = Table(title="PaperSnap Benchmark Results", show_lines=False)
    table.add_column("Paper ID", style="bold")
    table.add_column("GT Figs", justify="right")
    table.add_column("Extracted", justify="right")
    table.add_column("Delta", justify="right")
    table.add_column("Abstract", justify="center")
    table.add_column("Captions", justify="right")
    if show_f1:
        table.add_column("Abstract F1", justify="right")

    for r in results:
        delta_str = f"+{r.figure_delta}" if r.figure_delta > 0 else str(r.figure_delta)
        delta_style = "red" if r.figure_delta != 0 else "green"
        abstract_str = "[green]Yes[/]" if r.abstract_found else "[red]No[/]"
        caption_str = (
            f"{r.caption_found_count}/{r.caption_total}"
            if r.caption_total > 0
            else "0/0"
        )
        row = [
            r.paper_id,
            str(r.gt_figure_count),
            str(r.extracted_figure_count),
            f"[{delta_style}]{delta_str}[/]",
            abstract_str,
            caption_str,
        ]
        if show_f1:
            f1_str = f"{r.abstract_f1:.2f}" if r.abstract_f1 is not None else "N/A"
            row.append(f1_str)
        table.add_row(*row)

    console.print(table)


def print_summary(results: list[PaperResult], console: Console) -> None:
    n = len(results)
    if n == 0:
        console.print("[red]No results to summarize.[/]")
        return

    exact_match = sum(1 for r in results if r.figure_delta == 0)
    over_detect = sum(1 for r in results if r.figure_delta > 0)
    under_detect = sum(1 for r in results if r.figure_delta < 0)
    total_gt = sum(r.gt_figure_count for r in results)
    total_extracted = sum(r.extracted_figure_count for r in results)
    mae = sum(abs(r.figure_delta) for r in results) / n
    abstract_found_count = sum(1 for r in results if r.abstract_found)

    total_captions_found = sum(r.caption_found_count for r in results)
    total_captions_possible = sum(r.caption_total for r in results)

    f1_scores = [r.abstract_f1 for r in results if r.abstract_f1 is not None]

    console.print(f"\n[bold]Summary ({n} papers)[/bold]")
    console.print(
        f"  Figure exact match:     {exact_match}/{n} ({exact_match / n * 100:.0f}%)"
    )
    console.print(f"  Mean absolute error:    {mae:.2f} figures/paper")
    console.print(
        f"  Over-detection:         {over_detect} papers  |  Under-detection: {under_detect} papers"
    )
    console.print(
        f"  Total GT figures:       {total_gt}  ->  Extracted: {total_extracted}"
        f"  (net delta {total_extracted - total_gt:+d})"
    )
    console.print(
        f"  Abstract detection:     {abstract_found_count}/{n} ({abstract_found_count / n * 100:.0f}%)"
    )
    if total_captions_possible > 0:
        console.print(
            f"  Caption detection:      {total_captions_found}/{total_captions_possible}"
            f" ({total_captions_found / total_captions_possible * 100:.0f}%)"
        )
    if f1_scores:
        console.print(
            f"  Mean abstract text F1:  {sum(f1_scores) / len(f1_scores):.2f}"
            f"  (over {len(f1_scores)} papers with extracted abstract)"
        )


def print_diagnose(paper_ids: list[str], manifests_dir: Path, gt_dir: Path, console: Console) -> None:
    type_miss_counts: Counter = Counter()
    total_missed = 0

    for paper_id in paper_ids:
        manifest = load_manifest(manifests_dir, paper_id)
        gt = load_ground_truth(gt_dir, paper_id)
        if not manifest or not gt:
            continue

        valid_gt = [
            f for f in gt.get("figures", [])
            if not f.get("is_vector") and f.get("caption_text")
        ]

        gt_by_page: dict[int, list] = defaultdict(list)
        for f in valid_gt:
            gt_by_page[f["page"]].append(f)

        extracted_by_page: dict[int, int] = defaultdict(int)
        for f in manifest.get("figures", []):
            extracted_by_page[f["page"]] += 1

        paper_misses = []
        for page, gt_figs in sorted(gt_by_page.items()):
            n_missed = max(0, len(gt_figs) - extracted_by_page.get(page, 0))
            for fig in gt_figs[:n_missed]:
                ftype = fig.get("figure_type", "unknown")
                paper_misses.append((page, ftype))
                type_miss_counts[ftype] += 1

        if paper_misses:
            console.print(f"\n  [bold]{paper_id}[/bold] — {len(paper_misses)} missed")
            for page, ftype in paper_misses:
                console.print(f"    page {page:2d}  {ftype}")
            total_missed += len(paper_misses)

    console.print(f"\n[bold]Missed by figure type (total {total_missed}):[/bold]")
    for ftype, count in type_miss_counts.most_common():
        console.print(f"  {count:3d}  {ftype}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Evaluate PaperSnap extraction against ground truth."
    )
    parser.add_argument(
        "--manifests",
        type=Path,
        default=None,
        help="Central manifests folder (contains manifest_{paper_id}.json files)",
    )
    parser.add_argument(
        "--papersnap-output",
        type=Path,
        default=None,
        help="Root folder with per-paper subfolders (fallback, also needed for abstract F1)",
    )
    parser.add_argument(
        "--ground-truth",
        type=Path,
        required=True,
        help="Folder containing {paper_id}_gt.json ground truth files",
    )
    parser.add_argument(
        "--pdfs",
        type=Path,
        default=None,
        help="Folder containing source PDFs (enables abstract text F1, requires --papersnap-output too)",
    )
    parser.add_argument(
        "--output-json",
        type=Path,
        default=None,
        help="Optional path to write per-paper results as JSON",
    )
    parser.add_argument(
        "--diagnose",
        action="store_true",
        help="Show per-paper missed figure breakdown by page and type",
    )
    args = parser.parse_args()

    if args.manifests is None and args.papersnap_output is None:
        print("ERROR: provide --manifests or --papersnap-output", file=sys.stderr)
        sys.exit(1)

    manifests_dir = (args.manifests or args.papersnap_output).expanduser().resolve()
    papersnap_output = args.papersnap_output.expanduser().resolve() if args.papersnap_output else None
    gt_dir = args.ground_truth.expanduser().resolve()
    pdfs_dir = args.pdfs.expanduser().resolve() if args.pdfs else None

    if not manifests_dir.is_dir():
        print(f"ERROR: manifests folder does not exist: {manifests_dir}", file=sys.stderr)
        sys.exit(1)
    if not gt_dir.is_dir():
        print(f"ERROR: --ground-truth does not exist: {gt_dir}", file=sys.stderr)
        sys.exit(1)

    console = Console()
    paper_ids = discover_papers(manifests_dir, gt_dir)

    if not paper_ids:
        console.print("[red]No matching papers found between manifests and ground truth.[/]")
        sys.exit(1)

    console.print(f"Evaluating {len(paper_ids)} papers...")
    results: list[PaperResult] = []
    for pid in paper_ids:
        result = evaluate_paper(pid, manifests_dir, gt_dir, pdfs_dir, papersnap_output)
        if result is not None:
            results.append(result)

    show_f1 = pdfs_dir is not None and papersnap_output is not None
    print_results(results, show_f1=show_f1, console=console)
    print_summary(results, console=console)

    if args.diagnose:
        console.print("\n[bold underline]Diagnose — missed raster figures with captions[/bold underline]")
        print_diagnose(paper_ids, manifests_dir, gt_dir, console)

    if args.output_json:
        out_path = args.output_json.expanduser().resolve()
        out_path.write_text(
            json.dumps([asdict(r) for r in results], indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        console.print(f"\nResults saved to {out_path}")


if __name__ == "__main__":
    main()
