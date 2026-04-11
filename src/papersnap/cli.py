"""papersnap CLI — entry point for the `papersnap` command."""

from __future__ import annotations

from pathlib import Path

import typer
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn

from .extractor import extract_abstract, extract_figures, extract_metadata
from .manifest import build_manifest, write_manifest
from .renderer import build_html, write_html
from .utils import console, ensure_dir

app = typer.Typer(
    name="papersnap",
    help="Extract and visualize research paper abstracts and figures from a PDF.",
    add_completion=False,
)


@app.callback()
def _callback() -> None:
    pass


def _process_pdf(paper: Path, output_dir: Path) -> None:
    """Run the full extraction pipeline for a single PDF."""
    import fitz

    console.print(
        Panel(
            f"[bold]papersnap[/bold] — processing [cyan]{paper.name}[/cyan]\n"
            f"Output → {output_dir}",
            expand=False,
        )
    )

    try:
        ensure_dir(output_dir)
    except OSError as exc:
        console.print(f"[red]Cannot create output directory:[/red] {exc}")
        raise typer.Exit(1)

    try:
        doc = fitz.open(str(paper))
    except Exception as exc:
        console.print(f"[red]Failed to open PDF:[/red] {exc}")
        raise typer.Exit(1)

    console.print(f"[dim]Pages:[/dim] {len(doc)}")

    # --- Title ---
    title = extract_metadata(doc)
    if title:
        console.print(f"[dim]Title:[/dim] {title[:80]}{'…' if len(title) > 80 else ''}")

    # --- Abstract ---
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
        transient=True,
    ) as progress:
        progress.add_task("Extracting abstract…", total=None)
        abstract = extract_abstract(doc)

    if abstract:
        preview = abstract[:120] + ("…" if len(abstract) > 120 else "")
        console.print(f"[green]Abstract found[/green] — {preview}")
    else:
        console.print("[yellow]Abstract not found[/yellow] — placeholder will appear in HTML")

    # --- Figures ---
    console.print("\nExtracting figures…")
    figures = extract_figures(doc, output_dir)
    doc.close()

    console.print(
        f"\n[green]{len(figures)} figure{'s' if len(figures) != 1 else ''} extracted[/green]"
    )

    if not figures:
        console.print(
            "[yellow]No raster figures found.[/yellow] "
            "Vector-only figures are not supported."
        )

    # --- HTML ---
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
        transient=True,
    ) as progress:
        progress.add_task("Building HTML…", total=None)
        html_content = build_html(paper.stem, abstract, figures, title=title)
        html_path = write_html(output_dir, paper.stem, html_content)

    console.print(f"[green]HTML written:[/green] {html_path}")

    # --- Manifest ---
    manifest = build_manifest(paper, abstract is not None, figures, html_path, title=title)
    manifest_path = write_manifest(output_dir, manifest)
    console.print(f"[green]Manifest written:[/green] {manifest_path}")

    console.print(
        Panel(
            f"[bold green]Done![/bold green]\n"
            f"  HTML    → {html_path}\n"
            f"  Figures → {output_dir / 'figures'}\n"
            f"  Manifest→ {manifest_path}",
            expand=False,
        )
    )


@app.command()
def extract(
    paper: Path = typer.Argument(
        ...,
        help="Path to a PDF file or a directory of PDFs.",
        exists=True,
        file_okay=True,
        dir_okay=True,
        readable=True,
    ),
    output: Path = typer.Option(
        None,
        "--output",
        "-o",
        help=(
            "Root directory for output. Each paper gets a subfolder named after "
            "the PDF. Defaults to ~/Desktop/papersnap."
        ),
    ),
) -> None:
    """Extract abstract, figures, and captions from a PDF or a folder of PDFs."""
    root = output if output is not None else Path.home() / "Desktop" / "papersnap"

    if paper.is_dir():
        pdfs = sorted(paper.glob("*.pdf"))
        if not pdfs:
            console.print(f"[yellow]No PDF files found in:[/yellow] {paper}")
            raise typer.Exit(1)
        console.print(f"[bold]Batch mode:[/bold] {len(pdfs)} PDFs in {paper}")
        for pdf in pdfs:
            _process_pdf(pdf, root / pdf.stem)
        console.print(f"\n[bold green]Batch complete — {len(pdfs)} PDFs processed.[/bold green]")
    else:
        _process_pdf(paper, root / paper.stem)


