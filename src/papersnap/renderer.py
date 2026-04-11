"""Generate a self-contained HTML summary file."""

from __future__ import annotations

import html
from pathlib import Path

from .extractor import FigureInfo
from .utils import encode_png_base64

_CSS = """
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
    font-family: Georgia, serif;
    max-width: 900px;
    margin: 40px auto;
    padding: 0 24px;
    color: #1a1a1a;
    line-height: 1.7;
}
h1 { font-size: 1.6rem; margin-bottom: 8px; }
h2 { font-size: 1.2rem; margin: 32px 0 12px; border-bottom: 1px solid #ddd; padding-bottom: 6px; }
#abstract p { font-size: 0.97rem; text-align: justify; }
#figures { margin-top: 16px; }
figure {
    margin: 36px 0;
    padding: 16px;
    border: 1px solid #e0e0e0;
    border-radius: 6px;
    background: #fafafa;
}
figure img {
    display: block;
    max-width: 100%;
    height: auto;
    margin: 0 auto;
}
figcaption {
    margin-top: 10px;
    font-size: 0.88rem;
    font-style: italic;
    color: #555;
    text-align: center;
}
.no-abstract { color: #888; font-style: italic; }
.badge {
    display: inline-block;
    font-size: 0.75rem;
    background: #e8f0fe;
    color: #1a5276;
    border-radius: 4px;
    padding: 2px 8px;
    margin-bottom: 20px;
}
"""


def build_html(
    pdf_name: str,
    abstract: str | None,
    figures: list[FigureInfo],
) -> str:
    title = html.escape(pdf_name)

    abstract_html = (
        f"<p>{html.escape(abstract)}</p>"
        if abstract
        else '<p class="no-abstract">Abstract not found in this document.</p>'
    )

    figure_blocks: list[str] = []
    for fig in figures:
        b64 = encode_png_base64(fig.path)
        caption_text = html.escape(fig.caption) if fig.caption else "Caption not found."
        figure_blocks.append(
            f'<figure id="fig-{fig.index}">\n'
            f'  <img src="data:image/png;base64,{b64}" '
            f'alt="Figure {fig.index}" loading="lazy">\n'
            f"  <figcaption>{caption_text}</figcaption>\n"
            f"</figure>"
        )

    figures_html = "\n".join(figure_blocks) if figure_blocks else "<p>No figures found.</p>"
    figure_count_badge = f'<span class="badge">{len(figures)} figure{"s" if len(figures) != 1 else ""} extracted</span>'

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{title} — papersnap</title>
  <style>{_CSS}</style>
</head>
<body>
  <h1>{title}</h1>
  {figure_count_badge}

  <section id="abstract">
    <h2>Abstract</h2>
    {abstract_html}
  </section>

  <section id="figures">
    <h2>Figures</h2>
    {figures_html}
  </section>
</body>
</html>
"""


def write_html(output_dir: Path, pdf_stem: str, content: str) -> Path:
    out_path = output_dir / f"{pdf_stem}.html"
    out_path.write_text(content, encoding="utf-8")
    return out_path
