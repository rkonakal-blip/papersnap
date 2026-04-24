"""Tests for evaluation metric functions."""

import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from evaluate import word_overlap_f1, caption_accuracy


# ---------------------------------------------------------------------------
# word_overlap_f1
# ---------------------------------------------------------------------------

def test_f1_exact_match():
    assert word_overlap_f1("hello world", "hello world") == pytest.approx(1.0)


def test_f1_no_overlap():
    assert word_overlap_f1("hello world", "foo bar") == pytest.approx(0.0)


def test_f1_partial_overlap():
    score = word_overlap_f1("the quick brown fox", "the quick dog")
    assert 0.0 < score < 1.0


def test_f1_empty_strings():
    assert word_overlap_f1("", "hello") == pytest.approx(0.0)
    assert word_overlap_f1("hello", "") == pytest.approx(0.0)
    assert word_overlap_f1("", "") == pytest.approx(0.0)


def test_f1_case_insensitive():
    assert word_overlap_f1("Figure One", "figure one") == pytest.approx(1.0)


def test_f1_hyphenation_artifact():
    """Common PDF extraction artifact: 'convert- ers' should still match 'converters'."""
    score = word_overlap_f1(
        "MPC for power converters and drives",
        "MPC for power convert- ers and drives",
    )
    assert score > 0.7


# ---------------------------------------------------------------------------
# caption_accuracy
# ---------------------------------------------------------------------------

def make_gt_fig(caption_text, page=1):
    return {"caption_text": caption_text, "page": page}


def make_ext_fig(caption, page=1):
    return {"caption": caption, "page": page}


def test_caption_accuracy_perfect():
    gt = [make_gt_fig("Fig. 1. Block diagram of the system.", page=1)]
    ext = [make_ext_fig("Fig. 1. Block diagram of the system.", page=1)]
    correct, total = caption_accuracy(gt, ext)
    assert total == 1
    assert correct == 1


def test_caption_accuracy_wrong_caption():
    gt = [make_gt_fig("Fig. 1. Block diagram of the system.", page=1)]
    ext = [make_ext_fig("Fig. 2. Experimental results.", page=1)]
    correct, total = caption_accuracy(gt, ext)
    assert total == 1
    assert correct == 0


def test_caption_accuracy_no_extracted():
    gt = [make_gt_fig("Fig. 1. Something.", page=1)]
    correct, total = caption_accuracy(gt, [])
    assert total == 1
    assert correct == 0


def test_caption_accuracy_no_gt_captions():
    gt = [{"page": 1}]  # no caption_text field
    ext = [make_ext_fig("Fig. 1. Something.", page=1)]
    correct, total = caption_accuracy(gt, ext)
    assert total == 0
    assert correct == 0


def test_caption_accuracy_multiple_figures():
    gt = [
        make_gt_fig("Fig. 1. Power circuit of the AFE.", page=1),
        make_gt_fig("Fig. 2. Block diagram of the control strategy.", page=2),
        make_gt_fig("Fig. 3. Experimental results for the converter.", page=3),
    ]
    ext = [
        make_ext_fig("Fig. 1. Power circuit of the AFE.", page=1),
        make_ext_fig("Fig. 2. Block diagram of the control strategy.", page=2),
        make_ext_fig("Fig. 99. Completely wrong caption.", page=3),
    ]
    correct, total = caption_accuracy(gt, ext)
    assert total == 3
    assert correct == 2


def test_caption_accuracy_falls_back_to_any_page():
    """If no extracted figure on the right page, fall back to best match across all pages."""
    gt = [make_gt_fig("Fig. 1. Power circuit.", page=1)]
    ext = [make_ext_fig("Fig. 1. Power circuit.", page=5)]  # wrong page
    correct, total = caption_accuracy(gt, ext)
    assert total == 1
    assert correct == 1
