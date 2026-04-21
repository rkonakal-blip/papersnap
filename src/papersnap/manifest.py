"""manifest.json schema and writer."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from .extractor import FigureInfo


@dataclass
class FigureEntry:
    index: int
    filename: str | None
    page: int
    caption: str | None
    caption_found: bool
    width_px: int
    height_px: int
    vector_only: bool = False


@dataclass
class Manifest:
    source_pdf: str
    generated_at: str
    title: str | None
    figure_count: int
    abstract_found: bool
    output_html: str
    figures: list[FigureEntry]


def build_manifest(
    source_pdf: Path,
    abstract_found: bool,
    figures: list[FigureInfo],
    output_html: Path,
    title: str | None = None,
) -> Manifest:
    return Manifest(
        source_pdf=source_pdf.name,
        generated_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        title=title,
        figure_count=len(figures),
        abstract_found=abstract_found,
        output_html=output_html.name,
        figures=[
            FigureEntry(
                index=fig.index,
                filename=fig.path.name if fig.path else None,
                page=fig.page,
                caption=fig.caption,
                caption_found=fig.caption_found,
                width_px=fig.width_px,
                height_px=fig.height_px,
                vector_only=fig.vector_only,
            )
            for fig in figures
        ],
    )


def write_manifest(output_dir: Path, manifest: Manifest) -> Path:
    out_path = output_dir / "manifest.json"
    out_path.write_text(
        json.dumps(asdict(manifest), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return out_path
