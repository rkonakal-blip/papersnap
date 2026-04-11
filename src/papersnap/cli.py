"""papersnap CLI — entry point for the `papersnap` command."""

from __future__ import annotations

import json
import re
import tempfile
import urllib.parse
import urllib.request
from pathlib import Path

import typer
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.prompt import IntPrompt
from rich.table import Table

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


@app.command()
def search(
    query: str = typer.Argument(..., help="Search query for academic papers."),
    top: int = typer.Option(5, "--top", "-n", help="Number of results to display."),
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
    """Search OpenAlex for papers, pick one, download it, and run the extraction pipeline."""
    import fitz

    # Domains that serve PDFs without authentication walls.
    _OPEN_DOMAINS = {
        "arxiv.org", "europepmc.org", "biorxiv.org", "medrxiv.org",
        "ncbi.nlm.nih.gov", "zenodo.org", "hal.science", "chemrxiv.org",
        "eprint.iacr.org", "osf.io", "plos.org", "frontiersin.org",
        "mdpi.com", "hindawi.com",
    }

    def _pdf_url(work: dict) -> str | None:
        """Return a freely downloadable PDF URL, prioritising open repositories."""
        # Best option: arXiv ID → arXiv PDF (never 403s).
        arxiv_raw = (work.get("ids") or {}).get("arxiv", "")
        if arxiv_raw:
            aid = arxiv_raw.split("/abs/")[-1].split("/")[-1]
            return f"https://arxiv.org/pdf/{aid}"

        # Gather all candidate PDF URLs across every location.
        candidates: list[str] = []
        for loc in [work.get("best_oa_location"), work.get("primary_location"),
                    *( work.get("locations") or [])]:
            url = (loc or {}).get("pdf_url")
            if url:
                candidates.append(url)

        # Prefer URLs from known open-repository domains.
        for url in candidates:
            domain = urllib.parse.urlparse(url).netloc.lstrip("www.")
            if any(domain == d or domain.endswith("." + d) for d in _OPEN_DOMAINS):
                return url

        # Fall back to whatever is available.
        return candidates[0] if candidates else None

    def _abstract(work: dict) -> str | None:
        """Reconstruct abstract from OpenAlex inverted index."""
        inv = work.get("abstract_inverted_index")
        if not inv:
            return None
        positions: dict[int, str] = {}
        for word, pos_list in inv.items():
            for p in pos_list:
                positions[p] = word
        return " ".join(positions[k] for k in sorted(positions))

    # --- Fetch results from OpenAlex ---
    with Progress(
        SpinnerColumn(),
        TextColumn("[bold cyan]Searching OpenAlex…"),
        console=console,
        transient=True,
    ) as progress:
        progress.add_task("search", total=None)
        params = urllib.parse.urlencode({
            "search": query,
            "per_page": top,
            "select": (
                "id,ids,title,authorships,publication_year,"
                "abstract_inverted_index,best_oa_location,primary_location,locations"
            ),
        })
        req = urllib.request.Request(
            f"https://api.openalex.org/works?{params}",
            headers={"User-Agent": "papersnap/0.1"},
        )
        with urllib.request.urlopen(req) as resp:
            results = json.loads(resp.read()).get("results", [])

    if not results:
        console.print(f"[yellow]No results found for:[/yellow] {query}")
        raise typer.Exit()

    # --- Display table ---
    table = Table(title=f'OpenAlex results for "{query}"', show_lines=True)
    table.add_column("#", style="bold cyan", width=3)
    table.add_column("Title", style="bold", max_width=50)
    table.add_column("Authors", style="dim", max_width=25)
    table.add_column("Year", style="dim", width=6)
    table.add_column("PDF", width=4)
    table.add_column("Abstract", max_width=50)

    for i, work in enumerate(results, 1):
        ships = work.get("authorships") or []
        names = ", ".join(
            s["author"]["display_name"] for s in ships[:3] if s.get("author")
        )
        if len(ships) > 3:
            names += " et al."
        year = str(work.get("publication_year") or "")
        abstract = _abstract(work)
        preview = (abstract.replace("\n", " ")[:120] + "…") if abstract else "—"
        pdf_marker = "[green]✓[/green]" if _pdf_url(work) else "[dim]✗[/dim]"
        table.add_row(str(i), work.get("title") or "—", names, year, pdf_marker, preview)

    console.print(table)

    # --- Pick paper ---
    choice = IntPrompt.ask("Enter a number to download and process", console=console)
    if not (1 <= choice <= len(results)):
        console.print("[red]Invalid choice.[/red]")
        raise typer.Exit(1)
    work = results[choice - 1]

    # --- Check PDF availability before doing anything else ---
    pdf_url = _pdf_url(work)
    if not pdf_url:
        console.print(
            "[yellow]No open-access PDF is available for this paper.[/yellow] "
            "Try a different result."
        )
        raise typer.Exit()

    # --- Download & run pipeline inside temp dir ---
    root = output if output is not None else Path.home() / "Desktop" / "papersnap"

    # Use the OpenAlex work ID (e.g. W2741809807) as the filename.
    work_id = (work.get("id") or "paper").split("/")[-1]
    pdf_filename = f"{work_id}.pdf"

    with tempfile.TemporaryDirectory() as tmp:
        with Progress(
            SpinnerColumn(),
            TextColumn("[bold cyan]Downloading PDF…"),
            console=console,
            transient=True,
        ) as progress:
            progress.add_task("dl", total=None)
            pdf_path = Path(tmp) / pdf_filename
            req = urllib.request.Request(pdf_url, headers={"User-Agent": "papersnap/0.1"})
            with urllib.request.urlopen(req) as resp:
                pdf_path.write_bytes(resp.read())

        output_dir = root / pdf_path.stem
        try:
            ensure_dir(output_dir)
        except OSError as exc:
            console.print(f"[red]Cannot create output directory:[/red] {exc}")
            raise typer.Exit(1)

        try:
            doc = fitz.open(str(pdf_path))
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
            paper_title = work.get("title") or None
            html_content = build_html(pdf_path.stem, abstract, figures, title=paper_title)
            html_path = write_html(output_dir, pdf_path.stem, html_content)

        console.print(f"[green]HTML written:[/green] {html_path}")

        # --- Manifest ---
        manifest = build_manifest(pdf_path, abstract is not None, figures, html_path)
        manifest_path = write_manifest(output_dir, manifest)
        console.print(f"[green]Manifest written:[/green] {manifest_path}")

    # --- Summary ---
    console.print(
        Panel(
            f"[bold green]Done![/bold green]\n"
            f"  HTML    → {html_path}\n"
            f"  Figures → {output_dir / 'figures'}\n"
            f"  Manifest→ {manifest_path}",
            expand=False,
        )
    )
