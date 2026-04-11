"""papersnap CLI — entry point for the `papersnap` command."""

from __future__ import annotations

from pathlib import Path

import typer
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn

from .extractor import extract_abstract, extract_figures
from .manifest import build_manifest, write_manifest
from .renderer import build_html, write_html
from .utils import console, ensure_dir

app = typer.Typer(
    name="papersnap",
    help="Extract and visualize research paper abstracts and figures from a PDF.",
    add_completion=False,
)


@app.command()
def extract(
    paper: Path = typer.Argument(
        ...,
        help="Path to the input PDF file.",
        exists=True,
        file_okay=True,
        dir_okay=False,
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
    """Extract abstract, figures, and captions from a research paper PDF."""
    import fitz

    # Default root: ~/Desktop/papersnap; each paper gets its own subfolder.
    root = output if output is not None else Path.home() / "Desktop" / "papersnap"
    output = root / paper.stem

    console.print(
        Panel(
            f"[bold]papersnap[/bold] — processing [cyan]{paper.name}[/cyan]\n"
            f"Output → {output}",
            expand=False,
        )
    )

    # Verify output directory is writable before doing any work.
    try:
        ensure_dir(output)
    except OSError as exc:
        console.print(f"[red]Cannot create output directory:[/red] {exc}")
        raise typer.Exit(1)

    # Open PDF.
    try:
        doc = fitz.open(str(paper))
    except Exception as exc:
        console.print(f"[red]Failed to open PDF:[/red] {exc}")
        raise typer.Exit(1)

    console.print(f"[dim]Pages:[/dim] {len(doc)}")

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
    figures = extract_figures(doc, output)
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
        html_content = build_html(paper.stem, abstract, figures)
        html_path = write_html(output, paper.stem, html_content)

    console.print(f"[green]HTML written:[/green] {html_path}")

    # --- Manifest ---
    manifest = build_manifest(paper, abstract is not None, figures, html_path)
    manifest_path = write_manifest(output, manifest)
    console.print(f"[green]Manifest written:[/green] {manifest_path}")

    # --- Summary ---
    console.print(
        Panel(
            f"[bold green]Done![/bold green]\n"
            f"  HTML    → {html_path}\n"
            f"  Figures → {output / 'figures'}\n"
            f"  Manifest→ {manifest_path}",
            expand=False,
        )
    )
