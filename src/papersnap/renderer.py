"""Generate a self-contained HTML summary file."""

from __future__ import annotations

import html
from pathlib import Path

from .extractor import FigureInfo
from .utils import encode_png_base64

_CSS = """
:root {
  --bg: #f0f2f5;
  --surface: #ffffff;
  --border: #e2e8f0;
  --text: #1a202c;
  --text-muted: #718096;
  --accent: #4361ee;
  --accent-light: #eef2ff;
  --radius: 10px;
  --shadow: 0 1px 3px rgba(0,0,0,0.07), 0 4px 14px rgba(0,0,0,0.06);
}
@media (prefers-color-scheme: dark) {
  :root {
    --bg: #0f1117;
    --surface: #1a1d27;
    --border: #2d3148;
    --text: #e2e8f0;
    --text-muted: #8892a4;
    --accent: #6680ff;
    --accent-light: #1e2240;
    --shadow: 0 1px 3px rgba(0,0,0,0.3), 0 4px 14px rgba(0,0,0,0.2);
  }
}
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif;
  background: var(--bg);
  color: var(--text);
  line-height: 1.7;
}
.container { max-width: 960px; margin: 0 auto; padding: 48px 24px 80px; }

h1 { font-size: 1.55rem; font-weight: 700; line-height: 1.3; margin-bottom: 14px; }
h2 {
  font-size: 0.72rem; font-weight: 700; text-transform: uppercase;
  letter-spacing: 0.08em; color: var(--text-muted);
  margin-bottom: 16px; display: flex; align-items: center; gap: 10px;
}
.divider { flex: 1; height: 1px; background: var(--border); }

.meta-row { display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 36px; }
.badge {
  display: inline-block; font-size: 0.7rem; font-weight: 700;
  padding: 3px 11px; border-radius: 20px; letter-spacing: 0.04em;
}
.badge-blue  { background: var(--accent-light); color: var(--accent); }
.badge-amber { background: #fff7ed; color: #b45309; }
@media (prefers-color-scheme: dark) {
  .badge-amber { background: #2d1a06; color: #fbbf24; }
}

/* ── Abstract ─────────────────────────────────────── */
#abstract {
  background: var(--surface);
  border: 1px solid var(--border);
  border-left: 4px solid var(--accent);
  border-radius: var(--radius);
  padding: 24px 28px;
  margin-bottom: 40px;
  box-shadow: var(--shadow);
}
#abstract p {
  font-family: Georgia, 'Times New Roman', serif;
  font-size: 0.96rem;
  text-align: justify;
  color: var(--text);
}
.no-abstract { color: var(--text-muted); font-style: italic; }
.copy-btn {
  font-size: 0.68rem; font-weight: 700; padding: 3px 12px;
  border-radius: 6px; border: 1px solid var(--border);
  background: transparent; color: var(--text-muted);
  cursor: pointer; transition: all 0.15s; font-family: inherit;
  letter-spacing: 0.04em;
}
.copy-btn:hover { background: var(--accent-light); color: var(--accent); border-color: var(--accent); }

/* ── Thumbnail grid ───────────────────────────────── */
.fig-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(110px, 1fr));
  gap: 10px;
  margin-bottom: 40px;
}
.thumb {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 8px;
  overflow: hidden;
  cursor: pointer;
  transition: transform 0.15s, box-shadow 0.15s;
  aspect-ratio: 1;
  display: flex; flex-direction: column;
  align-items: center; justify-content: center;
}
.thumb:hover { transform: translateY(-3px); box-shadow: 0 8px 20px rgba(0,0,0,0.13); }
.thumb img { width: 100%; height: 82%; object-fit: cover; }
.thumb-label {
  font-size: 0.62rem; font-weight: 700; color: var(--text-muted);
  padding: 3px 0 2px; letter-spacing: 0.03em;
}
.thumb-vec {
  border: 2px dashed #d97706;
  background: #fffbeb;
  justify-content: center; gap: 4px;
}
@media (prefers-color-scheme: dark) {
  .thumb-vec { background: #1c1408; }
}
.thumb-vec .vec-icon { font-size: 1.4rem; opacity: 0.45; }
.thumb-vec .thumb-label { color: #d97706; }

/* ── Figure cards ─────────────────────────────────── */
.fig-cards { display: flex; flex-direction: column; gap: 24px; }
.fig-card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 24px 28px;
  box-shadow: var(--shadow);
  cursor: pointer;
  transition: box-shadow 0.15s, transform 0.15s;
}
.fig-card:hover { box-shadow: 0 6px 24px rgba(0,0,0,0.11); transform: translateY(-1px); }
.fig-card img {
  display: block; max-width: 100%; height: auto;
  margin: 0 auto; border-radius: 4px;
}
figcaption {
  margin-top: 14px;
  font-family: Georgia, 'Times New Roman', serif;
  font-size: 0.87rem; color: var(--text-muted);
  text-align: center; font-style: italic; line-height: 1.5;
}
.fig-meta {
  margin-top: 10px; text-align: center;
  font-size: 0.67rem; font-weight: 700; color: var(--text-muted);
  letter-spacing: 0.06em; text-transform: uppercase;
}
.fig-meta .dot { margin: 0 6px; opacity: 0.4; }

/* ── Vector placeholder ───────────────────────────── */
.vec-card {
  background: #fffbeb;
  border: 2px dashed #d97706;
  border-radius: var(--radius);
  padding: 36px 28px;
  text-align: center;
  display: flex; flex-direction: column;
  align-items: center; gap: 8px;
  cursor: default;
}
@media (prefers-color-scheme: dark) {
  .vec-card { background: #1c1408; }
}
.vec-card .vec-big { font-size: 2.2rem; opacity: 0.35; margin-bottom: 4px; }
.vec-card .vec-title { font-size: 0.92rem; font-weight: 600; color: #92400e; }
@media (prefers-color-scheme: dark) {
  .vec-card .vec-title { color: #fbbf24; }
}
.vec-card .vec-sub { font-size: 0.8rem; color: var(--text-muted); }

/* ── Lightbox ─────────────────────────────────────── */
.lightbox {
  position: fixed; inset: 0; z-index: 9999;
  display: flex; align-items: center; justify-content: center;
}
.lightbox.hidden { display: none; }
.lb-overlay {
  position: absolute; inset: 0;
  background: rgba(0,0,0,0.88);
  backdrop-filter: blur(6px);
}
.lb-inner {
  position: relative; z-index: 1;
  display: flex; flex-direction: column;
  align-items: center; gap: 16px;
  max-width: 90vw;
}
.lb-inner img {
  max-width: 88vw; max-height: 74vh;
  object-fit: contain; border-radius: 6px;
  box-shadow: 0 24px 64px rgba(0,0,0,0.55);
}
.lb-caption {
  color: rgba(255,255,255,0.82);
  font-family: Georgia, serif; font-size: 0.88rem;
  font-style: italic; text-align: center;
  max-width: 680px; padding: 0 16px; line-height: 1.55;
}
.lb-counter {
  color: rgba(255,255,255,0.45);
  font-size: 0.72rem; font-weight: 700;
  letter-spacing: 0.06em; text-transform: uppercase;
}
.lb-btn {
  position: fixed; background: rgba(255,255,255,0.12);
  border: none; color: white; border-radius: 50%;
  cursor: pointer; display: flex; align-items: center;
  justify-content: center; transition: background 0.15s;
}
.lb-btn:hover { background: rgba(255,255,255,0.28); }
#lb-close { top: 18px; right: 22px; width: 38px; height: 38px; font-size: 1.2rem; }
#lb-prev  { left: 18px;  top: 50%; transform: translateY(-50%); width: 48px; height: 48px; font-size: 1.6rem; }
#lb-next  { right: 18px; top: 50%; transform: translateY(-50%); width: 48px; height: 48px; font-size: 1.6rem; }
"""

_JS = """
(function () {
  var cards = Array.from(document.querySelectorAll('.fig-card'));
  var figs  = cards.map(function (c) {
    var img = c.querySelector('img');
    var cap = c.querySelector('figcaption');
    return { src: img ? img.src : '', caption: cap ? cap.textContent : '' };
  });

  var cur = 0;
  var lb      = document.getElementById('lightbox');
  var lbImg   = document.getElementById('lb-img');
  var lbCap   = document.getElementById('lb-caption');
  var lbCount = document.getElementById('lb-counter');

  function show(idx) {
    cur = (idx + figs.length) % figs.length;
    lbImg.src         = figs[cur].src;
    lbCap.textContent = figs[cur].caption;
    lbCount.textContent = (cur + 1) + ' / ' + figs.length;
    lb.classList.remove('hidden');
    document.body.style.overflow = 'hidden';
  }
  function close() {
    lb.classList.add('hidden');
    document.body.style.overflow = '';
  }
  function nav(d) { show(cur + d); }

  cards.forEach(function (c, i) { c.addEventListener('click', function () { show(i); }); });

  document.querySelectorAll('.thumb:not(.thumb-vec)').forEach(function (t) {
    t.addEventListener('click', function () {
      var idx = parseInt(t.dataset.idx, 10);
      show(idx);
      cards[idx].scrollIntoView({ behavior: 'smooth', block: 'center' });
    });
  });

  document.getElementById('lb-overlay').addEventListener('click', close);
  document.getElementById('lb-close').addEventListener('click', close);
  document.getElementById('lb-prev').addEventListener('click', function () { nav(-1); });
  document.getElementById('lb-next').addEventListener('click', function () { nav(1); });

  document.addEventListener('keydown', function (e) {
    if (lb.classList.contains('hidden')) return;
    if (e.key === 'Escape')      close();
    if (e.key === 'ArrowLeft')   nav(-1);
    if (e.key === 'ArrowRight')  nav(1);
  });

  var copyBtn = document.getElementById('copy-btn');
  if (copyBtn) {
    copyBtn.addEventListener('click', function () {
      var el = document.querySelector('#abstract p');
      var text = el ? el.textContent : '';
      function done() {
        copyBtn.textContent = 'Copied!';
        setTimeout(function () { copyBtn.textContent = 'Copy'; }, 2000);
      }
      if (navigator.clipboard) {
        navigator.clipboard.writeText(text).then(done).catch(function () { fallback(text); done(); });
      } else {
        fallback(text); done();
      }
    });
  }
  function fallback(text) {
    var ta = document.createElement('textarea');
    ta.value = text; ta.style.position = 'fixed'; ta.style.opacity = '0';
    document.body.appendChild(ta); ta.select();
    document.execCommand('copy'); document.body.removeChild(ta);
  }
})();
"""


def build_html(
    pdf_name: str,
    abstract: str | None,
    figures: list[FigureInfo],
    title: str | None = None,
) -> str:
    display_title = html.escape(title) if title else html.escape(
        pdf_name.replace("-", " ").replace("_", " ").title()
    )

    # Pre-encode raster images once each
    b64_cache: dict[int, str] = {}
    for fig in figures:
        if not fig.vector_only and fig.path:
            b64_cache[fig.index] = encode_png_base64(fig.path)

    raster_figs = [f for f in figures if not f.vector_only]
    vector_figs = [f for f in figures if f.vector_only]

    # ── Badges ────────────────────────────────────────────────────
    n_r = len(raster_figs)
    badges = f'<span class="badge badge-blue">{n_r} figure{"s" if n_r != 1 else ""} extracted</span>'
    if vector_figs:
        n_v = len(vector_figs)
        badges += f' <span class="badge badge-amber">{n_v} vector detected</span>'

    # ── Abstract ──────────────────────────────────────────────────
    abstract_html = (
        f"<p>{html.escape(abstract)}</p>" if abstract
        else '<p class="no-abstract">Abstract not found in this document.</p>'
    )
    copy_btn = '<button class="copy-btn" id="copy-btn">Copy</button>' if abstract else ""

    # ── Thumbnail grid ────────────────────────────────────────────
    thumbs: list[str] = []
    raster_idx = 0
    for fig in figures:
        if fig.vector_only:
            thumbs.append(
                f'<div class="thumb thumb-vec" title="Vector figure — page {fig.page}">'
                f'<span class="vec-icon">&#x2B21;</span>'
                f'<span class="thumb-label">Fig.&nbsp;{fig.index}</span>'
                f'</div>'
            )
        else:
            b64 = b64_cache[fig.index]
            thumbs.append(
                f'<div class="thumb" data-idx="{raster_idx}" title="Figure {fig.index} — page {fig.page}">'
                f'<img src="data:image/png;base64,{b64}" alt="Fig {fig.index}" loading="lazy">'
                f'<span class="thumb-label">Fig.&nbsp;{fig.index}</span>'
                f'</div>'
            )
            raster_idx += 1

    # ── Figure cards ──────────────────────────────────────────────
    cards: list[str] = []
    for fig in figures:
        if fig.vector_only:
            cap_escaped = html.escape(fig.caption) if fig.caption else f"Figure {fig.index}"
            cards.append(
                f'<div class="vec-card" id="fig-{fig.index}">'
                f'<span class="vec-big">&#x2B21;</span>'
                f'<span class="vec-title">{cap_escaped.split(chr(10))[0]}</span>'
                f'<span class="vec-sub">Vector figure — raster rendering not available</span>'
                f'<span class="badge badge-amber">VECTOR &nbsp;·&nbsp; Page {fig.page}</span>'
                f'</div>'
            )
        else:
            b64 = b64_cache[fig.index]
            cap_text = html.escape(fig.caption) if fig.caption else f"Figure {fig.index} — page {fig.page}"
            cap_status = "Caption found" if fig.caption_found else "No caption"
            cards.append(
                f'<figure class="fig-card" id="fig-{fig.index}">'
                f'<img src="data:image/png;base64,{b64}" alt="Figure {fig.index}" loading="lazy">'
                f'<figcaption>{cap_text}</figcaption>'
                f'<div class="fig-meta">'
                f'Page {fig.page}<span class="dot">&bull;</span>{cap_status}'
                f'</div>'
                f'</figure>'
            )

    thumb_html = "\n".join(thumbs)
    cards_html = "\n".join(cards) if cards else "<p>No figures found.</p>"

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{display_title} — papersnap</title>
  <style>{_CSS}</style>
</head>
<body>
<div class="container">

  <h1>{display_title}</h1>
  <div class="meta-row">{badges}</div>

  <section id="abstract">
    <h2>Abstract <span class="divider"></span> {copy_btn}</h2>
    {abstract_html}
  </section>

  <section id="figures">
    <h2>Figures <span class="divider"></span></h2>
    <div class="fig-grid">{thumb_html}</div>
    <div class="fig-cards">{cards_html}</div>
  </section>

</div>

<div id="lightbox" class="lightbox hidden">
  <div id="lb-overlay" class="lb-overlay"></div>
  <div class="lb-inner">
    <img id="lb-img" src="" alt="">
    <p id="lb-caption" class="lb-caption"></p>
    <span id="lb-counter" class="lb-counter"></span>
  </div>
  <button id="lb-close" class="lb-btn" title="Close (Esc)">&#x2715;</button>
  <button id="lb-prev"  class="lb-btn" title="Previous">&#x2039;</button>
  <button id="lb-next"  class="lb-btn" title="Next">&#x203a;</button>
</div>

<script>{_JS}</script>
</body>
</html>
"""


def write_html(output_dir: Path, pdf_stem: str, content: str) -> Path:
    out_path = output_dir / f"{pdf_stem}.html"
    out_path.write_text(content, encoding="utf-8")
    return out_path
