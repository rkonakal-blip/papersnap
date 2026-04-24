"""Tests for extractor utility functions."""

import pytest
from pathlib import Path
from papersnap.extractor import FigureInfo, _deduplicate_figures


def make_fig(index, page, caption, width=100, height=100, path="fig.png", vector_only=False):
    p = Path(path) if path else None
    return FigureInfo(
        index=index, path=p, page=page,
        caption=caption, width_px=width, height_px=height,
        vector_only=vector_only,
    )


# ---------------------------------------------------------------------------
# _deduplicate_figures
# ---------------------------------------------------------------------------

def test_dedup_no_duplicates():
    figs = [
        make_fig(1, 1, "Fig. 1. First figure."),
        make_fig(2, 1, "Fig. 2. Second figure."),
        make_fig(3, 2, "Fig. 3. Third figure."),
    ]
    result = _deduplicate_figures(figs)
    assert len(result) == 3
    assert [f.index for f in result] == [1, 2, 3]


def test_dedup_removes_placeholder_when_rendered_exists():
    """A vector placeholder should be removed when a rendered version has the same caption."""
    figs = [
        make_fig(1, 3, "Fig. 6. Power circuit.", width=1224, height=447, path="fig1.png"),
        make_fig(2, 3, "Fig. 6. Power circuit.", width=0, height=0, path=None, vector_only=True),
    ]
    result = _deduplicate_figures(figs)
    assert len(result) == 1
    assert result[0].path is not None
    assert result[0].index == 1


def test_dedup_keeps_placeholder_when_no_rendered_version():
    """A placeholder with no rendered counterpart should be kept."""
    figs = [
        make_fig(1, 1, "Fig. 1. First figure.", width=100, height=100),
        make_fig(2, 2, "Fig. 2. Vector only.", width=0, height=0, path=None, vector_only=True),
    ]
    result = _deduplicate_figures(figs)
    assert len(result) == 2


def test_dedup_keeps_two_rendered_same_caption():
    """Two rendered figures with the same caption (sub-panels) are both kept."""
    figs = [
        make_fig(1, 1, "Fig. 1. Sub-panel figure.", width=819, height=819, path="fig1.png"),
        make_fig(2, 1, "Fig. 1. Sub-panel figure.", width=820, height=819, path="fig2.png"),
    ]
    result = _deduplicate_figures(figs)
    assert len(result) == 2


def test_dedup_keeps_different_captions_same_page():
    """Different captions on the same page must both be kept."""
    figs = [
        make_fig(1, 1, "Fig. 1. First.", width=100, height=100),
        make_fig(2, 1, "Fig. 2. Second.", width=100, height=100),
    ]
    result = _deduplicate_figures(figs)
    assert len(result) == 2


def test_dedup_reindexes_after_removal():
    """Indices should be sequential 1-N after deduplication."""
    figs = [
        make_fig(1, 1, "Fig. 1. Power circuit.", path="fig1.png"),
        make_fig(2, 1, "Fig. 1. Power circuit.", path=None, vector_only=True),
        make_fig(3, 2, "Fig. 2. Another figure.", path="fig3.png"),
    ]
    result = _deduplicate_figures(figs)
    assert len(result) == 2
    assert [f.index for f in result] == [1, 2]


def test_dedup_no_caption_figures_always_kept():
    """Figures without captions are never deduplicated."""
    figs = [
        make_fig(1, 1, None),
        make_fig(2, 1, None),
        make_fig(3, 1, "Fig. 1. Real caption."),
    ]
    result = _deduplicate_figures(figs)
    assert len(result) == 3


def test_dedup_same_caption_different_pages_both_kept():
    """Same caption text on different pages should not be deduplicated."""
    figs = [
        make_fig(1, 1, "Fig. 1. Circuit diagram.", path="fig1.png"),
        make_fig(2, 2, "Fig. 1. Circuit diagram.", path=None, vector_only=True),
    ]
    result = _deduplicate_figures(figs)
    assert len(result) == 2
